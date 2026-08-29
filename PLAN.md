# AI Task Bot — Implementation Plan

## Context

`/var/www/Task-manager` is empty. This is a greenfield build of an internship technical
assessment: an omni-channel task manager where tasks are captured from Telegram (text and
voice) and appear live on a React Kanban dashboard.

The whole point of the assessment is that **two flows work end to end and are easy to explain
in an interview**:

```
text:  Telegram → bot → FastAPI → PostgreSQL → Redis pub/sub → WebSocket → React
voice: Telegram → bot → FastAPI → Redis/Celery → worker → Whisper → PostgreSQL
                                                        → Redis pub/sub → WebSocket → React
```

Everything else is deliberately out of scope. The deliverable is a small, polished,
production-quality MVP — not a Jira clone.

**Deliverable of this task:** `/var/www/Task-manager/PLAN.md`, containing the plan below.
No application code yet.

### Decisions locked with the user
| Decision | Choice | Why |
|---|---|---|
| Telegram transport | **aiogram long polling in its own `bot` container** | No public HTTPS/ngrok — `docker compose up` just works for a reviewer |
| Transcription | **OpenAI Whisper API** behind a `Transcriber` protocol | Small image, fast feedback; local model would be multi-GB and slow on CPU |
| Task scoping | **One shared board, no login** | Matches the "no complex authentication" scope note |

### Explicit non-goals
Auth/roles, comments, labels, priorities, subtasks, attachments, search, notification centre,
multi-tenancy, task creation or deletion from the dashboard, persisted within-column ordering.

---

## 1. Architecture

Six containers on one Docker network. One Python package (`app`) runs as three processes.

```
┌──────────┐   long polling    ┌───────────────────────────────┐
│ Telegram │◄─────────────────►│  bot        (aiogram)         │
└──────────┘   sendMessage /   └──────────────┬────────────────┘
      ▲        editMessageText    HTTP (internal token)
      │                                       ▼
      │                        ┌───────────────────────────────┐
      │                        │  backend    (FastAPI/uvicorn) │
      │                        │  REST + WebSocket             │
      │                        └───┬──────────┬────────────┬───┘
      │                            │          │            │
      │                    SQLAlchemy    enqueue      subscribe
      │                            ▼          ▼            ▲
      │                     ┌───────────┐ ┌──────────────────┐
      │                     │ PostgreSQL│ │ Redis            │
      │                     └───────────┘ │ broker + pub/sub │
      │                            ▲      └────────┬─────────┘
      │  getFile / download        │               │ publish
      │  editMessageText           │               │
      └────────────────────┬───────┴───────────────┘
                           │
                  ┌────────┴──────────────────────┐        ┌──────────────┐
                  │  worker  (Celery)             │        │  frontend    │
                  │  download → Whisper → update  │        │  nginx+React │
                  └───────────────────────────────┘        └──────────────┘
                                                              ▲ /api, /ws proxied
```

Two rules keep it explainable:
1. **The backend owns the database write path for creation.** The bot never touches Postgres —
   it speaks HTTP to the backend. (The worker *does* write directly; it is a trusted internal
   process finishing a row the backend created.)
2. **All realtime fan-out goes through one Redis pub/sub channel.** Whoever changes a task
   publishes an event; the backend is the only WebSocket holder and forwards it. This is why a
   Celery worker with no WebSocket connections can still update the browser.

---

## 2. Service boundaries

| Service | Responsibility | Talks to |
|---|---|---|
| **bot** | Telegram I/O only. Parse update → call backend → reply. No DB, no OpenAI. | Telegram API, backend HTTP |
| **backend** | HTTP API, validation, persistence, enqueue Celery jobs, hold WebSockets, forward Redis events | Postgres, Redis, Celery broker |
| **worker** | Long/failure-prone work: download audio, transcribe, finalise the task, tell the user | Telegram API, OpenAI, Postgres, Redis |
| **frontend** | Render board, drag-and-drop, consume WebSocket | backend via nginx proxy |
| **postgres** | Persistence | — |
| **redis** | Celery broker + result backend + pub/sub channel | — |

`backend`, `worker`, and `bot` share **one Docker image** built from `backend/Dockerfile`, with
three different `command`s. Shared config, models, and integrations, three deployables.

---

## 3. Database schema

Two tables. SQLAlchemy 2.x declarative with `Mapped[...]` / `mapped_column`, one Alembic
migration.

**`users`**

| column | type | notes |
|---|---|---|
| `id` | `bigserial` PK | |
| `telegram_id` | `bigint` | **unique**, indexed |
| `username` | `varchar(64)` null | |
| `first_name` | `varchar(128)` null | shown on cards |
| `created_at` | `timestamptz` | `server_default=now()` |

**`tasks`**

| column | type | notes |
|---|---|---|
| `id` | `bigserial` PK | |
| `user_id` | `bigint` FK → `users.id` `ON DELETE CASCADE` | indexed |
| `title` | `text` | the task text / transcript |
| `status` | enum `task_status` | `pending` \| `in_progress` \| `completed`, default `pending` |
| `source` | enum `task_source` | `text` \| `voice` |
| `transcription_status` | enum `transcription_status` null | `pending` \| `processing` \| `done` \| `failed`; `NULL` for text tasks |
| `transcription_error` | `text` null | short human-readable reason |
| `telegram_file_id` | `varchar(256)` null | voice only, for re-download/debug |
| `created_at` | `timestamptz` | `server_default=now()` |
| `updated_at` | `timestamptz` | `onupdate=now()` |

Index: `ix_tasks_status_created_at (status, created_at DESC)` — the board's only query shape.

Notes
- Native Postgres enums via `sa.Enum(PyEnum, name=...)`, created explicitly in the migration.
- A voice task is inserted **immediately** with a placeholder title
  (`🎤 Voice message — transcribing…`) so the card appears on the board within milliseconds.
  The worker later overwrites `title`.
- `chat_id` / `ack_message_id` are **not** columns — they are passed as Celery task arguments,
  keeping Telegram transport detail out of the domain model.

> **Note (backend-foundation phase):** the first implementation slice (REST API only, no
> Telegram/Redis/Celery/Whisper yet) uses a simplified version of this schema — `users` without
> `first_name`, plus `updated_at`; `tasks` with a plain `description` field and without
> `source` / `transcription_status` / `transcription_error` / `telegram_file_id`. Those columns
> are added back via a follow-up Alembic migration when the Telegram/voice phase lands.

---

## 4. API endpoints

Prefix `/api`. `TaskRead` is the single response shape used by REST *and* WebSocket.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/health` | — | liveness; checks DB + Redis |
| `GET` | `/api/tasks` | — | list board; optional `?status=`, `?limit=` (default 200) |
| `POST` | `/api/tasks` | `X-Internal-Token` | **bot only**: create task; enqueues transcription when `source=voice` |
| `PATCH` | `/api/tasks/{id}` | — | `{"status": "in_progress"}` — used by drag-and-drop |
| `WS` | `/ws/tasks` | — | live `task.created` / `task.updated` events |

`POST /api/tasks` request body:
```json
{
  "telegram_id": 123456789, "username": "hrach", "first_name": "Hrach",
  "source": "voice",
  "title": null,
  "telegram_file_id": "AwACAgIAAx...", "chat_id": 123456789, "ack_message_id": 42
}
```
Pydantic validates the discriminated shape: `source=text` requires a non-empty `title`;
`source=voice` requires `telegram_file_id` and `chat_id`. Returns `201` + `TaskRead`.

`TaskRead`:
```json
{
  "id": 7, "title": "Buy milk", "status": "pending", "source": "voice",
  "transcription_status": "done", "transcription_error": null,
  "created_at": "...", "updated_at": "...",
  "user": {"telegram_id": 123456789, "username": "hrach", "first_name": "Hrach"}
}
```

The internal token is a shared secret in a header — deliberately *not* a user auth system.

---

## 5. Telegram text flow

1. `bot` receives a text message (aiogram `Message` handler, `F.text & ~F.text.startswith("/")`).
2. Trims, rejects empty / >1000 chars with a friendly reply.
3. `POST /api/tasks` with `source=text`.
4. Backend: `get_or_create_user(telegram_id)` → insert task (`status=pending`) → commit →
   publish `task.created` to Redis → return `201`.
5. Backend's pub/sub listener fans the event out to every open WebSocket.
6. Bot replies `✅ Task added: "<title>"`.

`/start` upserts the user and greets; `/help` explains text + voice usage. Nothing else.

---

## 6. Telegram voice flow

1. `bot` receives `message.voice` (also accept `message.audio`).
2. Guard rails **before** any work: `duration > 120s` or `file_size > 20 MB` → reject with a
   clear message (20 MB is Telegram's bot download limit).
3. Bot sends an immediate placeholder reply: `🎤 Got it — transcribing…`, keeps its `message_id`.
4. `POST /api/tasks` with `source=voice`, `telegram_file_id`, `chat_id`, `ack_message_id`.
5. Backend inserts the task with placeholder title + `transcription_status=pending`, publishes
   `task.created`, then `transcribe_voice.delay(task_id, file_id, chat_id, ack_message_id)`,
   and returns `201`. **The card is already on the dashboard, in a "transcribing" state.**
6. Worker:
   a. set `transcription_status=processing` → publish `task.updated`;
   b. `getFile` → download the OGG to a `tempfile.NamedTemporaryFile` (deleted in `finally`);
   c. `Transcriber.transcribe(path)` → text;
   d. update `title` + `transcription_status=done` → commit → publish `task.updated`;
   e. `editMessageText` on the placeholder → `✅ Task added: "<transcript>"`.
7. Dashboard card morphs from shimmer to real text with no refresh.

Failure at any step → see §13.

---

## 7. Redis / Celery architecture

Redis plays **two** roles, on two logical databases, which is worth saying out loud in an
interview:

| Role | URL | Used by |
|---|---|---|
| Celery broker + result backend | `redis://redis:6379/0` | backend (producer), worker (consumer) |
| Pub/sub event bus (`task_events` channel) | `redis://redis:6379/1` | backend (pub + sub), worker (pub) |

`app/worker/celery_app.py`:
```python
celery_app = Celery("taskbot", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_acks_late=True,              # redeliver if the worker dies mid-transcription
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,     # long tasks: don't hoard messages
    task_time_limit=180, task_soft_time_limit=150,
    task_serializer="json", result_serializer="json", accept_content=["json"],
    task_default_queue="transcription",
)
```

One queue (`transcription`), one task (`transcribe_voice`), `concurrency=2`. The worker uses a
**separate synchronous** SQLAlchemy engine/session (`create_engine` + `sessionmaker`) — Celery
tasks are sync, the backend is async; do not share an async engine across the fork.

Retries: `autoretry_for=(httpx.TransportError, httpx.TimeoutException, RateLimitError,
APIConnectionError)`, `retry_backoff=2`, `retry_backoff_max=60`, `retry_jitter=True`,
`max_retries=3`. Non-retryable errors (bad file, 4xx from OpenAI) fail immediately.

---

## 8. Whisper integration

`app/integrations/transcriber.py`

```python
class Transcriber(Protocol):
    def transcribe(self, audio_path: str) -> str: ...

class OpenAIWhisperTranscriber:
    def __init__(self, api_key: str, model: str = "whisper-1", language: str | None = None): ...
    def transcribe(self, audio_path: str) -> str:
        with open(audio_path, "rb") as f:
            return self.client.audio.transcriptions.create(
                model=self.model, file=f, language=self.language,
                response_format="text",
            ).strip()

def get_transcriber() -> Transcriber:  # single factory, read from settings
```

- Model and language come from env (`WHISPER_MODEL`, `WHISPER_LANGUAGE`; language unset = auto).
- Telegram voice is OGG/Opus, which the API accepts directly — **no ffmpeg needed**, keeping the
  worker image slim.
- Empty transcript (silence) is treated as a failure, not an empty task.
- Transcripts longer than 500 chars are truncated for the card title.
- The `Protocol` exists so tests inject a `FakeTranscriber` and so a local model could be
  swapped in later without touching the Celery task.

---

## 9. WebSocket architecture

```
POST /api/tasks ──┐
                  ├─► publish JSON to Redis channel "task_events"
worker update ────┘                    │
                                       ▼
        backend lifespan task: redis.pubsub().subscribe("task_events")
                                       │
                                       ▼
                   ConnectionManager.broadcast(payload)  → every open /ws/tasks
```

- `app/realtime/manager.py` — `ConnectionManager` holding a `set[WebSocket]`, with
  `connect` / `disconnect` / `broadcast`. `broadcast` sends inside `try/except` and collects
  dead sockets for removal, so one dead client cannot break the loop.
- `app/realtime/listener.py` — an `asyncio.Task` started in the FastAPI `lifespan`, subscribing
  to `task_events` and calling `manager.broadcast`. Cancelled cleanly on shutdown.
- Event envelope: `{"type": "task.created" | "task.updated", "task": {<TaskRead>}}`.
- Server sends a `{"type": "ping"}` every 25s so idle proxies don't drop the socket.
- Going through Redis (rather than calling `manager.broadcast` directly) is what makes the
  **worker** able to update the UI, and would let the backend scale to >1 replica for free.

---

## 10. React architecture

React 18 + TypeScript + Vite. Dependencies kept tiny: `@tanstack/react-query`, `@dnd-kit/core`,
`@dnd-kit/sortable`, `date-fns`. No component library, no Redux — plain CSS Modules.

```
src/
├── main.tsx                 QueryClientProvider
├── App.tsx                  header + view toggle + board/list
├── types.ts                 Task, TaskStatus, TaskEvent (mirrors TaskRead)
├── api/client.ts            fetch wrapper, base URL from import.meta.env
├── api/tasks.ts             fetchTasks(), updateTaskStatus()
├── hooks/useTasks.ts        useQuery(['tasks'])
├── hooks/useUpdateTaskStatus.ts  useMutation + optimistic cache update + rollback
├── hooks/useTaskStream.ts   WebSocket → queryClient.setQueryData upsert
└── components/
    ├── KanbanBoard.tsx  Column.tsx  TaskCard.tsx
    ├── ListView.tsx     ViewToggle.tsx  ConnectionBadge.tsx  EmptyState.tsx
```

State model — deliberately one source of truth:
- React Query holds the task list.
- `useTaskStream` receives an event and **upserts into the same cache entry** (replace by `id`,
  else prepend). No second store, no refetch storm.
- `useUpdateTaskStatus` writes optimistically; the echoed `task.updated` event is idempotent.

`useTaskStream` details: opens `ws(s)://<host>/ws/tasks`, reconnects with exponential backoff
(1s → 15s, jittered), and on every successful **re**connect calls
`queryClient.invalidateQueries(['tasks'])` to heal anything missed while offline. Exposes
`status: 'connecting' | 'open' | 'closed'` for `ConnectionBadge`.

---

## 11. Kanban UX

- Three fixed columns: **Pending · In Progress · Completed**, each with a live count.
- **Card**: source icon (💬 text / 🎤 voice), title, author first name/@username, relative time
  ("2 min ago").
- **Voice states**, the visual payoff of the whole project:
  - `pending`/`processing` → shimmer skeleton over the title + "transcribing…" caption, card
    slightly dimmed and **not draggable**;
  - `done` → normal card, a brief highlight flash on arrival;
  - `failed` → red left border, `⚠️ Transcription failed` + the short reason.
- **List view** toggle: single chronological table (status pill, source, title, author, time) —
  satisfies the "Kanban **or** List" requirement by offering both, sharing the same cache.
- **Responsive**: CSS Grid `repeat(3, 1fr)` on desktop; under 900px columns stack vertically and
  stay drop targets; touch drag works via `@dnd-kit` `TouchSensor` with an activation delay so
  page scrolling still works.
- Header shows a connection dot (green live / amber reconnecting) and the total count.
- Empty board shows a hint: "Send a message to your Telegram bot to create your first task."

---

## 12. Drag-and-drop behaviour

`@dnd-kit/core` — `DndContext` in `KanbanBoard`, `useDroppable` per `Column`, `useDraggable` per
`TaskCard`.

- Sensors: `PointerSensor` (8px activation distance so clicks aren't swallowed),
  `TouchSensor` (250ms delay, 5px tolerance), `KeyboardSensor` (space to lift, arrows to move,
  space to drop) — keyboard-accessible for free.
- `DragOverlay` renders a tilted, shadowed copy of the card; the source slot dims.
- The hovered column gets a highlighted border/background.
- **On drop into a different column**: optimistic cache write → `PATCH /api/tasks/{id}` →
  on error roll back the snapshot and show an inline toast "Couldn't update — reverted".
- **Drop into the same column is a no-op**: within-column ordering is *not* persisted. Columns
  are always ordered `created_at DESC`. This is a conscious scope call — a `position` column and
  reindexing logic buys nothing the assessment asks for, and it is a clean thing to say in the
  interview.
- Cards mid-transcription are not draggable (their status is not meaningful yet).

---

## 13. Error handling

**Voice pipeline (the graded path)**

| Failure | Where | Behaviour |
|---|---|---|
| Voice > 120s or > 20 MB | bot, pre-flight | Reject before any task is created; explain the limit |
| `getFile` / download fails | worker | Celery retry ×3 with exponential backoff |
| OpenAI timeout / 5xx / rate limit | worker | Same retry policy |
| OpenAI 4xx (bad audio/key) | worker | No retry — fail fast |
| Empty transcript | worker | Treated as failure: "Couldn't hear anything" |
| Retries exhausted / soft time limit | worker `on_failure` | `transcription_status=failed`, `transcription_error=<short reason>`, title → `🎤 Voice message (transcription failed)`, publish `task.updated`, edit the Telegram placeholder to `⚠️ Couldn't transcribe: <reason>` |

The temp audio file is removed in a `finally` block on every path.

**Backend** — Pydantic validation → `422` with field detail; a global exception handler returns
`{"detail": ...}` and never leaks a traceback; unknown task id → `404`; missing/incorrect
`X-Internal-Token` → `401`; structured logging with the task id on every state transition.

**Bot** — every handler wrapped by an aiogram error middleware: backend unreachable / 5xx →
"⚠️ Service temporarily unavailable, try again in a moment"; the exception is logged with the
`telegram_id`, and the bot keeps polling.

**Frontend** — query error → retry button; mutation error → rollback + toast; WebSocket drop →
amber badge, backoff reconnect, invalidate on recovery.

**Startup** — `backend`/`worker`/`bot` depend on `postgres` and `redis` **healthchecks**; the
backend entrypoint runs `alembic upgrade head` before uvicorn, so a fresh clone needs no manual
migration step.

---

## 14. Docker architecture

`docker-compose.yml`, six services:

| service | image / build | command | depends_on |
|---|---|---|---|
| `postgres` | `postgres:16-alpine` | — | — |
| `redis` | `redis:7-alpine` | — | — |
| `backend` | `./backend` | `entrypoint.sh` → alembic + `uvicorn app.main:app --host 0.0.0.0 --port 8000` | postgres, redis (healthy) |
| `worker` | `./backend` (same image) | `celery -A app.worker.celery_app worker -Q transcription -c 2 -l info` | postgres, redis (healthy) |
| `bot` | `./backend` (same image) | `python -m app.bot.main` | backend (healthy) |
| `frontend` | `./frontend` | nginx | backend |

- Healthchecks: `pg_isready`, `redis-cli ping`, `curl -f localhost:8000/api/health`.
- Volumes: `pgdata:` named volume. Only `postgres` (5432, optional) and `frontend` (`80:80`)
  publish ports in dev; the backend is reachable at `http://localhost:8000` for API poking.
- **backend Dockerfile**: `python:3.12-slim`, non-root user, deps installed from
  `pyproject.toml` in a cached layer, then source. One image, three commands.
- **frontend Dockerfile**: multi-stage — `node:20-alpine` runs `npm ci && npm run build`, then
  `nginx:alpine` serves `dist/`. `nginx.conf` proxies `/api` → `backend:8000` and `/ws` →
  `backend:8000` with `Upgrade`/`Connection` headers, plus SPA fallback `try_files ... /index.html`.
  Same-origin means **no CORS config and no build-time API URL** — worth mentioning.
- `docker-compose.override.yml` (optional, dev): mounts `./backend` and runs uvicorn `--reload`,
  swaps the frontend for the Vite dev server on `5173` with HMR.
- `.env` at the repo root feeds all services via `env_file`.

---

## 15. Testing strategy

Pragmatic, not exhaustive — cover the two core flows and the failure modes.

**Backend** — `pytest`, `pytest-asyncio`, `httpx.ASGITransport`.
- Fixtures: a real Postgres (the compose service, separate `taskbot_test` database), each test in
  a transaction rolled back at teardown; `fakeredis` for pub/sub; dependency overrides for the
  internal-token check.
- `tests/test_api_tasks.py` — create text task → `201` + row + event published; create voice task
  → placeholder row + Celery `.delay` called (mocked) ; `PATCH` status transitions; invalid status
  → `422`; missing internal token → `401`.
- `tests/test_transcription_task.py` — `CELERY_TASK_ALWAYS_EAGER`, `FakeTranscriber` and a mocked
  Telegram client: happy path updates title + status; transcriber raising → `failed` + error
  message + Telegram edit called; empty transcript → `failed`; temp file removed in all cases.
- `tests/test_realtime.py` — `ConnectionManager.broadcast` reaches every client and evicts dead
  sockets; the listener converts a Redis message into a broadcast.
- `tests/test_ws_endpoint.py` — Starlette `TestClient.websocket_connect`, publish, assert frame.

**Frontend** — Vitest + React Testing Library.
- `useTaskStream` upsert logic (created prepends, updated replaces by id, unknown type ignored).
- `KanbanBoard` groups tasks into the right columns and renders counts.
- `TaskCard` renders the three voice states.

**Manual E2E checklist** in the README (see §18) — the thing the reviewer will actually run.

CI is out of scope, but tests run with `docker compose run --rm backend pytest`.

---

## 16. Project directory structure

```
Task-manager/
├── docker-compose.yml
├── docker-compose.override.yml     # optional dev: hot reload
├── .env.example
├── .gitignore
├── README.md
├── PLAN.md
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── entrypoint.sh
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/0001_initial.py
│   ├── app/
│   │   ├── main.py                 # FastAPI app, routers, lifespan (pub/sub listener)
│   │   ├── config.py               # pydantic-settings Settings
│   │   ├── db.py                   # async engine/session, Base
│   │   ├── db_sync.py              # sync engine/session for Celery
│   │   ├── enums.py
│   │   ├── models.py               # User, Task
│   │   ├── schemas.py              # TaskCreate, TaskRead, TaskStatusUpdate, UserRead
│   │   ├── deps.py                 # get_db, verify_internal_token
│   │   ├── api/
│   │   │   ├── health.py
│   │   │   ├── tasks.py
│   │   │   └── ws.py
│   │   ├── services/
│   │   │   ├── users.py            # get_or_create_user
│   │   │   ├── tasks.py            # create_task, update_status, list_tasks
│   │   │   └── events.py           # publish_task_event
│   │   ├── realtime/
│   │   │   ├── manager.py          # ConnectionManager
│   │   │   └── listener.py         # Redis subscriber → broadcast
│   │   ├── integrations/
│   │   │   ├── telegram.py         # getFile / download / sendMessage / editMessageText
│   │   │   └── transcriber.py      # Transcriber protocol + OpenAI impl + factory
│   │   ├── worker/
│   │   │   ├── celery_app.py
│   │   │   └── tasks.py            # transcribe_voice
│   │   └── bot/
│   │       ├── main.py             # Dispatcher + start_polling
│   │       ├── handlers.py         # /start, /help, text, voice
│   │       ├── middleware.py       # error handling
│   │       └── api_client.py       # httpx client → backend
│   └── tests/
└── frontend/
    ├── Dockerfile
    ├── nginx.conf
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    └── src/                        # as laid out in §10
```

The bot lives inside the `app` package to reuse `config`/`schemas` and ship one image, but it
**only** talks HTTP — the service boundary is preserved in code, not just in the diagram.

---

## 17. Environment variables

`.env.example` at the repo root:

```dotenv
# --- Postgres ---
POSTGRES_USER=taskbot
POSTGRES_PASSWORD=taskbot
POSTGRES_DB=taskbot
DATABASE_URL=postgresql+asyncpg://taskbot:taskbot@postgres:5432/taskbot
DATABASE_URL_SYNC=postgresql+psycopg://taskbot:taskbot@postgres:5432/taskbot

# --- Redis ---
REDIS_URL=redis://redis:6379/0          # Celery broker + backend
REDIS_PUBSUB_URL=redis://redis:6379/1   # realtime events
TASK_EVENTS_CHANNEL=task_events

# --- Telegram ---
TELEGRAM_BOT_TOKEN=                     # from @BotFather
MAX_VOICE_DURATION_SECONDS=120
MAX_VOICE_FILE_MB=20

# --- OpenAI ---
OPENAI_API_KEY=
WHISPER_MODEL=whisper-1
WHISPER_LANGUAGE=                       # blank = auto-detect

# --- Internal ---
BACKEND_INTERNAL_URL=http://backend:8000
INTERNAL_API_TOKEN=change-me            # bot → backend shared secret
LOG_LEVEL=INFO
```

Loaded by a single `Settings(BaseSettings)` in `app/config.py`; the frontend needs no build-time
variables because nginx proxies same-origin.

---

## 18. README structure

1. **What it does** — one paragraph + the two flow diagrams from §1.
2. **Demo** — GIF/screenshot placeholder: Telegram voice message on the left, card appearing and
   morphing on the right.
3. **Architecture** — the container diagram + the table from §2, and the two "why" rules.
4. **Tech stack** — one line per choice.
5. **Quick start**
   ```bash
   cp .env.example .env      # fill TELEGRAM_BOT_TOKEN and OPENAI_API_KEY
   docker compose up --build
   # dashboard → http://localhost:3000   API docs → http://localhost:8000/docs
   ```
6. **Getting a bot token** — three lines about @BotFather.
7. **Manual E2E checklist** — send text → card appears; send voice → placeholder appears,
   becomes the transcript, Telegram message is edited; drag a card → status persists across
   refresh; open two browser tabs → both update live.
8. **API reference** — the table from §4 + the WebSocket event shape.
9. **Running tests** — `docker compose run --rm backend pytest`, `npm test` in `frontend/`.
10. **Design decisions & trade-offs** — polling vs webhook, Redis pub/sub for worker→browser
    events, one image / three processes, no auth, no persisted ordering.
11. **What I'd do next** — task editing/deletion, per-user boards, auth, CI, Sentry.

---

## Implementation order

1. Scaffold repo, `.env.example`, `docker-compose.yml` with `postgres` + `redis` only.
2. Backend skeleton: config, db, models, Alembic initial migration, `/api/health`. Verify
   `docker compose up backend` migrates cleanly.
3. `GET`/`POST`/`PATCH /api/tasks` + services + internal-token dependency. Verify via `/docs`.
4. Redis pub/sub: `events.publish_task_event`, `ConnectionManager`, listener, `/ws/tasks`.
   Verify with `wscat` while POSTing.
5. Bot: `/start`, `/help`, text handler → real task from a real Telegram chat.
6. Celery app + `transcribe_voice` + Telegram file download + `Transcriber`. Verify a voice note
   end to end.
7. Frontend: Vite scaffold, types, React Query list, Kanban columns, cards.
8. `useTaskStream` + connection badge; verify live creation in two tabs.
9. `@dnd-kit` drag-and-drop + optimistic `PATCH`.
10. Voice card states (shimmer / failed) + list view + responsive polish.
11. Frontend Dockerfile + nginx proxy; full `docker compose up --build` from a clean clone.
12. Tests (backend then frontend), then README.

Steps 1–6 deliver the graded backend flows; 7–10 the dashboard. Each step is independently
demoable.

---

## Verification

**Automated**
```bash
docker compose run --rm backend pytest -q          # backend suite
docker compose run --rm frontend npm test          # (or npm test in frontend/)
```

**End-to-end, from a clean clone** — the reviewer's path, and the real acceptance test:
```bash
cp .env.example .env    # add TELEGRAM_BOT_TOKEN + OPENAI_API_KEY
docker compose up --build
```
1. Open `http://localhost:3000` — empty board, green "live" badge.
2. Telegram → `/start` → greeting; send `Buy milk` → bot replies `✅ Task added`, card appears in
   **Pending** with no page refresh.
3. Send a voice note → placeholder card appears **immediately** with a shimmer; within a few
   seconds the title becomes the transcript and the Telegram placeholder message is edited in
   place. `docker compose logs -f worker` shows the task received and completed.
4. Drag the card Pending → In Progress → Completed; hard-refresh — the status persisted.
5. Open a second tab; create a task from Telegram — both tabs update.
6. **Failure path**: stop the worker (`docker compose stop worker`), send a voice note — the card
   stays in "transcribing". Restart the worker — because of `task_acks_late`, the queued job is
   picked up and completes. Then set an invalid `OPENAI_API_KEY`, restart the worker, send a
   voice note → card shows `⚠️ Transcription failed` and Telegram reports the error.
7. `docker compose down && docker compose up` — tasks survive (named volume).
8. Resize the browser to mobile width — columns stack, drag still works.

---

## Status

- [x] Architecture & plan (this document)
- [x] Backend foundation — REST API for tasks, PostgreSQL, Alembic, tests (no Telegram/Redis/Celery/Whisper/WebSocket yet)
- [x] Telegram bot (text + voice) wired to the backend
- [x] Redis/Celery async transcription pipeline (Whisper integration behind a `Transcriber` protocol; live end-to-end smoke-tested with a real Redis + Celery worker)
- [x] WebSocket realtime fan-out (`/ws/tasks` + Redis pub/sub bridge; `task_created`/`task_updated` broadcast on text creation, voice creation, and REST status updates; live end-to-end smoke-tested with two concurrent clients)
- [x] React dashboard (React + TypeScript + Vite, Kanban board with `@dnd-kit` drag-and-drop, live WebSocket sync, toasts, responsive layout; verified with a headless-browser pass covering REST/WS integration, drag-and-drop, optimistic update + rollback, and desktop/tablet/mobile layouts)
- [x] Full docker-compose stack (postgres, redis, backend, worker, bot, frontend — all healthchecked and dependency-ordered; `docker compose up --build` verified end-to-end: text flow and voice-flow enqueue confirmed through the real nginx-proxied stack, migrations run automatically and idempotently, postgres volume survives a full `down`/`up` cycle)
- [x] Final review — full requirements pass against every section of this document; fixed a real concurrency bug (`get_or_create_user` race on a new `telegram_id`, most reachable via the dashboard's shared sentinel user — see `app/services/users.py` / `sync_repo.py`, regression tests in `tests/test_race_conditions.py`), removed dead `.env` config, added `.gitignore`, wrote `README.md`. 86 backend tests passing, frontend typecheck/build clean, `docker compose up --build` verified fresh from an empty volume.
- [x] Post-review polish — dedicated `notify_telegram` Celery task so a Telegram delivery failure retries via Redis instead of being silently dropped; inline status-choice keyboard on both text and voice bot confirmations (same `PATCH` path as dashboard drag-and-drop); frontend visual redesign (refined color/spacing/typography system, drag/drop and real-time-arrival animations, mobile horizontal-scroll board) plus a persisted light/dark theme toggle. 95 backend tests passing. Final end-to-end pass: clean `docker compose down && up --build`, REST+WebSocket event delivery, and the voice-pipeline failure/retry/notify chain all verified against the live containers.
