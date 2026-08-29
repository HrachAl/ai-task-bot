# AI Task Bot

An omni-channel task manager: send a text or voice message to a Telegram bot and it
shows up instantly — Kanban-style — on a web dashboard. Voice messages are transcribed
asynchronously by Whisper via a Celery worker so the bot never blocks waiting on
OpenAI. Status changes made on the dashboard (including drag-and-drop) sync back to
every connected browser over WebSocket in real time.

```
Telegram text  → FastAPI → PostgreSQL ─────────────────────┐
                                                             ├─→ WebSocket → React
Telegram voice → FastAPI → Redis/Celery → Worker → Whisper ─┘
                                          → PostgreSQL
```

This is an internship technical assessment. The scope is intentionally a small,
polished MVP — not an enterprise project-management clone. There is no auth system,
no roles, no labels/priorities/subtasks/attachments, and no notification center by
design (see [PLAN.md](PLAN.md) for the full architecture rationale).

## Architecture

Six containers, three of which share one Python image:

| Service | Role | Talks to |
|---|---|---|
| `bot` | aiogram long-polling — Telegram I/O only | Telegram API, `backend` (HTTP) |
| `backend` | FastAPI REST API + WebSocket server; runs DB migrations on boot | PostgreSQL, Redis |
| `worker` | Celery worker — voice transcription pipeline | PostgreSQL, Redis, Telegram API, OpenAI |
| `frontend` | React dashboard, built and served by nginx | `backend` (proxied, same-origin) |
| `postgres` | Persistent storage — the single source of truth | — |
| `redis` | Celery broker **and** the realtime pub/sub bus | — |

Two design rules keep the system easy to reason about:

1. **The bot never touches Postgres or Redis directly.** It only speaks HTTP to
   `backend` (`POST /api/tasks`, `POST /api/tasks/voice`). This keeps the bot a thin,
   easily-testable I/O layer — `backend` owns every write.
2. **All realtime fan-out goes through one Redis pub/sub channel** (`task_events`,
   separate Redis logical DB from the Celery broker). Whoever changes a task —
   `backend` for text/status changes, `worker` for finished transcriptions — publishes
   an event there. `backend` is the only process holding live WebSocket connections
   and re-broadcasts whatever it receives. This is what lets a **worker in a
   completely different process** push updates into the browser.

### Text flow
`Telegram text → bot → POST /api/tasks → PostgreSQL commit → publish → WebSocket → React`

### Voice flow
`Telegram voice → bot → POST /api/tasks/voice (202, no DB write yet) → Celery/Redis
→ worker downloads the file → Whisper → PostgreSQL commit → publish → WebSocket → React`

No `Task` row exists until transcription actually succeeds — a failed or empty
transcription never leaves partial data behind, and the bot edits its own "🎤
transcribing…" placeholder message with the final result (or a clear failure notice).

Both the text and voice confirmations also attach an inline keyboard (Pending / In
Progress / Completed). Tapping a button calls the same `PATCH /api/tasks/{id}` the
dashboard's drag-and-drop uses, so the status change shows up on the board in real
time without leaving Telegram.

## Technology stack

**Backend** — Python 3.12, FastAPI, SQLAlchemy 2.x (async), Alembic, Pydantic v2,
aiogram 3, Celery 5 + Redis, OpenAI SDK (Whisper), pytest.
**Frontend** — React 18, TypeScript, Vite, `@dnd-kit` for drag-and-drop, CSS Modules
with a small design-token system (light theme by default, with a persisted
light/dark toggle in the header) — no state-management library, no CSS framework.
**Infra** — Docker, Docker Compose, nginx (serves the built frontend and proxies
`/api` + `/ws` to the backend — same origin, no CORS needed in production).

## Project structure

```
backend/
  app/
    api/          REST + WebSocket routes (tasks.py, ws.py, health.py)
    bot/          aiogram handlers, input validation, backend HTTP client
    worker/       Celery app + the transcribe_voice task
    services/     business logic (tasks, users, voice pipeline, realtime events)
    integrations/ Telegram Bot API client, Whisper transcriber (behind a Protocol)
    realtime/     WebSocket ConnectionManager + the Redis pub/sub listener
    models.py, schemas.py, db.py / db_sync.py, config.py, exceptions.py
  alembic/         one migration: initial schema (users, tasks)
  tests/           95 tests — see "How to test" below
frontend/
  src/
    api/           tiny fetch-based client (client.ts, tasks.ts)
    components/    AppShell, Header, KanbanBoard/Column, TaskCard, TaskModal,
                    TaskDetails, Toast, EmptyState, LoadingState, ...
    hooks/         useTasks (state + optimistic updates), useTaskSocket, useToasts,
                    useTheme (light/dark, persisted to localStorage)
    types/         Task, TaskStatus, WebSocket event, API error shapes
docker-compose.yml
.env.example
PLAN.md            the original architecture plan this was built from
```

## Setup

**Prerequisites:** Docker + Docker Compose. That's it — Postgres, Redis, and all
language runtimes run inside containers.

```bash
cp .env.example .env
# edit .env: add TELEGRAM_BOT_TOKEN and OPENAI_API_KEY to use the bot for real
# (see "Telegram bot" / "OpenAI / Whisper" below — the rest of the app works without them)

docker compose up --build
```

- Dashboard: **http://localhost:3000**
- API docs (Swagger UI): **http://localhost:8001/docs**
- Health check: **http://localhost:8001/api/health**

(Port `8001` is only the **host-side** port — inside the Docker network, `backend`
still listens on `8000`; only its published port on the host was moved, e.g. to avoid
clashing with something else already running on port 8000 on the host machine.)

The dashboard loads the full task list via `GET /api/tasks` on first paint, then a
WebSocket connection (`/ws/tasks`, proxied by nginx) keeps it in sync live — no
polling, no manual refresh needed. A small colored dot in the header shows connection
status (green = live, amber = reconnecting), and the client reconnects automatically
with exponential backoff if the connection drops.

## Environment variables

All variables live in one `.env` file at the repo root (see `.env.example` for the
full annotated list). The important ones:

| Variable | Purpose |
|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Postgres credentials — used both to initialize the `postgres` container and to build `DATABASE_URL` |
| `DATABASE_URL` | Async SQLAlchemy URL the backend and Alembic use |
| `REDIS_URL` | Celery broker + result backend |
| `REDIS_PUBSUB_URL` / `TASK_EVENTS_CHANNEL` | Realtime event bus (deliberately a separate Redis logical DB from the Celery broker, same instance) |
| `TELEGRAM_BOT_TOKEN` | From [@BotFather](https://t.me/BotFather) — required for the bot to do anything |
| `MAX_VOICE_DURATION_SECONDS` / `MAX_VOICE_FILE_MB` | Bot rejects oversized voice notes before ever touching Redis/Celery |
| `OPENAI_API_KEY` | Required for real transcription |
| `WHISPER_MODEL` / `WHISPER_LANGUAGE` | Defaults to `whisper-1`, auto-detect language |
| `BACKEND_INTERNAL_URL` | How the `bot` container reaches `backend` (`http://backend:8000` inside Docker) |
| `CORS_ORIGINS` | Only matters if you run the frontend dev server separately from nginx (see below) |

Without `TELEGRAM_BOT_TOKEN` / `OPENAI_API_KEY`, everything **except the bot itself**
works fine — the REST API, WebSocket, dashboard, and worker (it'll just fail
gracefully on the Telegram/OpenAI calls with retries, then a clear error message) are
fully functional for local testing.

### Telegram bot configuration

1. Message [@BotFather](https://t.me/BotFather) on Telegram, run `/newbot`, follow the
   prompts.
2. Copy the token it gives you into `.env` as `TELEGRAM_BOT_TOKEN`.
3. `docker compose up -d --build bot` (or just re-run `docker compose up --build`).
4. Message your bot: plain text becomes a task immediately; a voice note gets an
   instant "🎤 transcribing…" reply, then that same message is edited in place once
   Whisper finishes.

The bot uses **long polling**, not webhooks — no public URL, ngrok, or TLS
certificate needed to run it locally.

### OpenAI / Whisper configuration

Set `OPENAI_API_KEY` in `.env`. That's the only required step — `WHISPER_MODEL`
defaults to `whisper-1` and `WHISPER_LANGUAGE` is left blank for auto-detection.
Transcription is behind a small `Transcriber` protocol
(`backend/app/integrations/transcriber.py`), so the tests exercise the real pipeline
logic against a fake implementation rather than hitting the OpenAI API.

## Docker startup

`docker compose up --build` builds and starts, in dependency order:

1. `postgres` and `redis` (each has a real healthcheck — `pg_isready` / `redis-cli
   ping` — everything else waits on them being healthy, not just "started")
2. `backend` — waits for postgres+redis, **runs `alembic upgrade head`
   automatically**, then starts uvicorn; has its own healthcheck (`GET /api/health`)
3. `worker` and `frontend` — wait for `backend` to be healthy
4. `bot` — also waits for `backend`; requires a valid `TELEGRAM_BOT_TOKEN` or it exits
   immediately (this doesn't block anything else — the REST API, dashboard, and
   worker are fully independent of the bot)

`backend`, `worker`, and `bot` are **one Docker image** (`backend/Dockerfile`) run
with three different commands — shared code, three deployables. `worker` and `bot`
skip the image's migration step (`entrypoint: []` override in `docker-compose.yml`)
so migrations only ever run once, from `backend`.

Ports published to the host: **3000** (dashboard) and **8001** (API). Postgres and
Redis are only reachable on the internal Docker network — not published to the host —
since nothing outside the compose network needs to reach them directly.

## Database migrations

One Alembic migration (`backend/alembic/versions/..._initial_schema...py`) creates
`users` and `tasks`. It runs automatically on every `backend` container start
(`backend/entrypoint.sh` → `alembic upgrade head`, before uvicorn starts) — reproducible
by construction: a fresh `docker compose up --build` always ends up on the same schema,
and re-running it is a no-op (idempotent) if already at head.

To run migrations manually (e.g., against a local Postgres outside Docker):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
# set DATABASE_URL in backend/.env to point at your Postgres
alembic upgrade head
```

## How the worker works

The Celery worker (`backend/app/worker/tasks.py`) owns the entire voice pipeline so
the bot's Telegram handler never blocks:

1. The bot validates duration/size limits, immediately replies "🎤 transcribing…",
   then calls `POST /api/tasks/voice` — which enqueues a Celery job and returns `202`
   with **no database write yet**.
2. The worker downloads the voice file from Telegram, sends it to Whisper, and only
   *then* creates the `Task` row — so Postgres only ever holds successfully
   transcribed tasks, never partial ones.
3. It publishes a `task_created` event (see below) and edits the bot's placeholder
   message with the final transcript.

**Failure handling**, tuned per failure type (`backend/app/exceptions.py` +
`backend/app/worker/tasks.py`):

| Failure | Behavior |
|---|---|
| Telegram download error, transient Whisper/OpenAI error | Retried automatically (`autoretry_for`, exponential backoff, jitter, max 3 retries) |
| Empty/invalid audio, silent recording | Failed immediately — retrying an unusable file wastes time, so these are excluded from `autoretry_for` |
| Retries exhausted, or a non-retryable failure | The bot edits the placeholder with a clear failure message (`⚠️ Couldn't transcribe...`), via a Celery `on_failure` hook that fires exactly once |

Both the success confirmation and the failure notice above are delivered by a
dedicated `notify_telegram` Celery task (`notify_telegram_task`), not a direct
Telegram API call — so a transient Telegram/network error while *sending the
notification itself* is retried (3 attempts, exponential backoff) via the same
Redis queue, instead of silently dropping the user's confirmation.

`task_acks_late=True` means a message is only removed from Redis after the job
finishes successfully — if a worker process is killed mid-job, the job is redelivered
rather than silently lost (the standard at-least-once tradeoff for a task queue; see
"Known limitations" below).

## How real-time updates work

- `backend` holds a `ConnectionManager` (`backend/app/realtime/manager.py`) — a plain
  set of live WebSocket connections at `/ws/tasks`. It broadcasts to all of them and
  silently drops any connection that fails to receive (client already gone) — no
  crash, no reconnection storm.
- A background task in `backend`'s lifespan subscribes to a Redis pub/sub channel and
  re-broadcasts every message it receives to `ConnectionManager`. **Both** the
  request-handling code (text creation, `PATCH` status updates) and the separate
  Celery worker (finished transcriptions) publish to this same channel — this is the
  only reason a worker in another process can push updates into someone's browser.
- Every publish path is wrapped so a Redis hiccup can **never** fail the request that
  already committed to Postgres — the realtime layer is a convenience, not a
  dependency, exactly as the spec requires ("WebSocket is only responsible for
  real-time synchronization").
- On the frontend, `useTaskSocket` reconnects with exponential backoff (1s → 15s) on
  drop, and re-syncs the task list on every successful reconnect. Incoming events are
  merged by **upsert-by-id** (`useTasks.upsertTask`) — replace if the id is already in
  the list, prepend otherwise — so a duplicate or out-of-order event can never produce
  a duplicate card, and the same merge path handles both a REST response and a
  WebSocket echo of that same change identically.

## Drag-and-drop and status updates

Dragging a card to another column (`@dnd-kit`) updates local state **optimistically**,
then calls `PATCH /api/tasks/{id}`. If that request fails, the board reverts to the
pre-drag snapshot and a toast explains what happened — verified with a headless
browser test that force-fails the `PATCH` call and confirms both the rollback and the
toast.

## How to test the application

**Backend** — 95 tests (`pytest`), no mocking of the database — a real Postgres
(a `*_test` database) with each test isolated in a rolled-back transaction/savepoint.
Covers: task CRUD + validation, the voice pipeline's success/failure paths (download
failure, invalid audio, transcription failure, empty transcript) with a fake
Telegram/Whisper client, the Celery task's retry configuration and failure
notification, realtime event publishing (including that a broken Redis never breaks a
request), the WebSocket endpoint against a real Redis, and two concurrency
regression tests for a user-creation race condition (see "Known limitations" fixed
below).

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
# point backend/.env at a Postgres + Redis (docker run postgres:16-alpine / redis:7-alpine
# works fine for this — create a `<db>_test` database alongside the main one)
alembic upgrade head
pytest
```

**Frontend**:

```bash
cd frontend
npm install
npm run typecheck   # tsc -b --noEmit
npm run build        # production build
```

**End-to-end**, from a clean clone:

```bash
cp .env.example .env   # add TELEGRAM_BOT_TOKEN + OPENAI_API_KEY to test the bot for real
docker compose up --build
```

1. Open http://localhost:3000 — empty board, green "Live" WebSocket badge.
2. Click **New Task**, fill in a title, submit — it appears on the board instantly,
   no reload.
3. Message your bot on Telegram: plain text → a task appears on the board within a
   second. A voice note → a "transcribing…" placeholder appears immediately, then
   updates in place with the transcript once Whisper finishes — and the Telegram
   message is edited to match.
4. Drag a card between columns — status persists across a page refresh.
5. Open a second browser tab — create a task in one, watch it appear live in the
   other.
6. Click a card → change its status or delete it from the detail panel.

## Known limitations (explicit scope decisions)

- **No authentication.** Per the assessment's explicit scope, there's no auth layer.
  `POST /api/tasks` and `POST /api/tasks/voice` are open — trusted callers only
  (the bot and the dashboard). Don't expose port 8001 to the public internet as-is.
- **At-least-once voice processing.** `task_acks_late=True` means a worker crashing
  in the narrow window between committing a task and acknowledging the message could
  cause that voice message to be processed twice on redelivery. This is the standard,
  deliberate tradeoff against the alternative (losing the job entirely on crash) and
  is not expected to matter at this scale.
- **No within-column ordering.** Cards are always sorted by creation time; dropping a
  card back into its own column is a no-op. Persisting manual order would need a new
  column and reindexing logic that nothing in the spec calls for.
