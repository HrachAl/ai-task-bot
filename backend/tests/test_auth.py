"""How a caller gets a board, and how the board stays theirs.

Covers the two ways a request proves who it is, and that a request with no
proof gets nothing.
"""

from httpx import AsyncClient

from tests.conftest import bot_headers


class TestUnauthenticatedRequestsAreRejected:
    async def test_listing_tasks_requires_credentials(self, anon_client: AsyncClient):
        response = await anon_client.get("/api/tasks")
        assert response.status_code == 401

    async def test_creating_a_task_requires_credentials(self, anon_client: AsyncClient):
        response = await anon_client.post("/api/tasks", json={"title": "Sneaky"})
        assert response.status_code == 401

    async def test_me_requires_credentials(self, anon_client: AsyncClient):
        response = await anon_client.get("/api/me")
        assert response.status_code == 401

    async def test_an_unknown_bearer_token_is_rejected(self, anon_client: AsyncClient):
        response = await anon_client.get(
            "/api/tasks", headers={"Authorization": "Bearer not-a-real-token"}
        )
        assert response.status_code == 401

    async def test_a_wrong_internal_secret_is_rejected(self, anon_client: AsyncClient):
        response = await anon_client.get(
            "/api/tasks",
            headers={"X-Internal-Token": "guessed-it", "X-Telegram-Id": "1"},
        )
        assert response.status_code == 401


class TestInternalCallerActsForATelegramUser:
    async def test_first_contact_creates_the_account(self, client: AsyncClient):
        response = await client.get("/api/me", headers=bot_headers(4242, "newcomer"))

        assert response.status_code == 200
        body = response.json()
        assert body["telegram_id"] == 4242
        assert body["username"] == "newcomer"
        assert body["access_token"]

    async def test_the_same_telegram_id_always_resolves_to_one_account(
        self, client: AsyncClient
    ):
        first = await client.get("/api/me", headers=bot_headers(4243))
        second = await client.get("/api/me", headers=bot_headers(4243))

        assert first.json()["id"] == second.json()["id"]
        assert first.json()["access_token"] == second.json()["access_token"]

    async def test_a_non_numeric_telegram_id_is_rejected(self, anon_client: AsyncClient):
        response = await anon_client.get(
            "/api/tasks",
            headers={
                **bot_headers(1),
                "X-Telegram-Id": "not-a-number",
            },
        )
        assert response.status_code == 401


class TestDashboardTokenLogin:
    """The token in the /dashboard link is the whole login flow."""

    async def test_the_token_from_me_authenticates_later_requests(
        self, client: AsyncClient, anon_client: AsyncClient
    ):
        me = (await client.get("/api/me")).json()
        await client.post("/api/tasks", json={"title": "From Telegram"})

        response = await anon_client.get(
            "/api/tasks", headers={"Authorization": f"Bearer {me['access_token']}"}
        )

        assert response.status_code == 200
        assert [task["title"] for task in response.json()] == ["From Telegram"]

    async def test_the_dashboard_url_carries_the_token(self, client: AsyncClient):
        body = (await client.get("/api/me")).json()
        assert body["dashboard_url"].endswith(f"?token={body['access_token']}")

    async def test_each_account_gets_a_different_token(self, client: AsyncClient):
        one = (await client.get("/api/me", headers=bot_headers(5001))).json()
        two = (await client.get("/api/me", headers=bot_headers(5002))).json()

        assert one["access_token"] != two["access_token"]

    async def test_a_token_only_reaches_its_own_board(
        self, client: AsyncClient, anon_client: AsyncClient
    ):
        mine = (await client.get("/api/me")).json()
        await client.post("/api/tasks", json={"title": "Mine"}, headers=bot_headers(6001))

        response = await anon_client.get(
            "/api/tasks", headers={"Authorization": f"Bearer {mine['access_token']}"}
        )

        assert [task["title"] for task in response.json()] == []
