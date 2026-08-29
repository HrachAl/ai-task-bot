import pytest
from httpx import AsyncClient


async def create_task(
    client: AsyncClient, *, telegram_id: int = 1, title: str = "Buy milk", **extra
) -> dict:
    payload = {"telegram_id": telegram_id, "title": title, **extra}
    response = await client.post("/api/tasks", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


class TestTaskCreation:
    async def test_create_task_returns_201_and_task(self, client: AsyncClient):
        body = await create_task(client, title="Buy milk", description="2 liters")

        assert body["title"] == "Buy milk"
        assert body["description"] == "2 liters"
        assert body["status"] == "pending"
        assert body["id"] > 0
        assert body["user_id"] > 0

    async def test_create_task_creates_user_lazily(self, client: AsyncClient):
        first = await create_task(client, telegram_id=42, title="First")
        second = await create_task(client, telegram_id=42, title="Second")

        assert first["user_id"] == second["user_id"]

    async def test_create_task_without_title_is_rejected(self, client: AsyncClient):
        response = await client.post("/api/tasks", json={"telegram_id": 1, "title": ""})
        assert response.status_code == 422

    async def test_create_task_with_blank_title_is_rejected(self, client: AsyncClient):
        response = await client.post("/api/tasks", json={"telegram_id": 1, "title": "   "})
        assert response.status_code == 422

    async def test_create_task_without_telegram_id_uses_dashboard_user(
        self, client: AsyncClient
    ):
        """The web dashboard has no Telegram identity — omitting telegram_id
        must fall back to the reserved dashboard user, not fail."""
        response = await client.post("/api/tasks", json={"title": "Buy milk"})
        assert response.status_code == 201
        assert response.json()["title"] == "Buy milk"

    async def test_create_task_accepts_explicit_status(self, client: AsyncClient):
        body = await create_task(client, title="Done already", status="completed")
        assert body["status"] == "completed"


class TestTaskListing:
    async def test_list_tasks_returns_created_tasks(self, client: AsyncClient):
        await create_task(client, title="Task A")
        await create_task(client, title="Task B")

        response = await client.get("/api/tasks")
        assert response.status_code == 200
        titles = {task["title"] for task in response.json()}
        assert {"Task A", "Task B"}.issubset(titles)

    async def test_list_tasks_empty_by_default(self, client: AsyncClient):
        response = await client.get("/api/tasks")
        assert response.status_code == 200
        assert response.json() == []

    async def test_list_tasks_filters_by_status(self, client: AsyncClient):
        await create_task(client, title="Pending one")
        completed = await create_task(client, title="Completed one")
        await client.patch(f"/api/tasks/{completed['id']}", json={"status": "completed"})

        response = await client.get("/api/tasks", params={"status": "completed"})
        assert response.status_code == 200
        titles = [task["title"] for task in response.json()]
        assert titles == ["Completed one"]

    async def test_get_single_task(self, client: AsyncClient):
        created = await create_task(client, title="Solo task")
        response = await client.get(f"/api/tasks/{created['id']}")
        assert response.status_code == 200
        assert response.json()["title"] == "Solo task"

    async def test_get_missing_task_returns_404(self, client: AsyncClient):
        response = await client.get("/api/tasks/999999")
        assert response.status_code == 404
        assert response.json()["detail"] == "Task 999999 not found"


class TestTaskUpdate:
    async def test_update_task_status(self, client: AsyncClient):
        created = await create_task(client, title="To update")
        response = await client.patch(
            f"/api/tasks/{created['id']}", json={"status": "in_progress"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "in_progress"
        assert body["updated_at"] != created["updated_at"]

    async def test_update_task_title_and_description(self, client: AsyncClient):
        created = await create_task(client, title="Old title")
        response = await client.patch(
            f"/api/tasks/{created['id']}",
            json={"title": "New title", "description": "New description"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["title"] == "New title"
        assert body["description"] == "New description"
        assert body["status"] == "pending"

    async def test_update_missing_task_returns_404(self, client: AsyncClient):
        response = await client.patch("/api/tasks/999999", json={"status": "completed"})
        assert response.status_code == 404

    async def test_update_with_no_fields_is_rejected(self, client: AsyncClient):
        created = await create_task(client, title="Untouched")
        response = await client.patch(f"/api/tasks/{created['id']}", json={})
        assert response.status_code == 422

    async def test_update_with_blank_title_is_rejected(self, client: AsyncClient):
        created = await create_task(client, title="Has a title")
        response = await client.patch(f"/api/tasks/{created['id']}", json={"title": "   "})
        assert response.status_code == 422


class TestTaskDeletion:
    async def test_delete_task_returns_204(self, client: AsyncClient):
        created = await create_task(client, title="To delete")
        response = await client.delete(f"/api/tasks/{created['id']}")
        assert response.status_code == 204

    async def test_delete_task_removes_it(self, client: AsyncClient):
        created = await create_task(client, title="To delete")
        await client.delete(f"/api/tasks/{created['id']}")

        response = await client.get(f"/api/tasks/{created['id']}")
        assert response.status_code == 404

    async def test_delete_missing_task_returns_404(self, client: AsyncClient):
        response = await client.delete("/api/tasks/999999")
        assert response.status_code == 404


class TestInvalidTaskStatus:
    async def test_create_task_with_invalid_status_returns_422(self, client: AsyncClient):
        response = await client.post(
            "/api/tasks", json={"telegram_id": 1, "title": "Bad status", "status": "bogus"}
        )
        assert response.status_code == 422

    async def test_update_task_with_invalid_status_returns_422(self, client: AsyncClient):
        created = await create_task(client, title="Has valid status")
        response = await client.patch(f"/api/tasks/{created['id']}", json={"status": "bogus"})
        assert response.status_code == 422

    @pytest.mark.parametrize("valid_status", ["pending", "in_progress", "completed"])
    async def test_all_valid_statuses_are_accepted(self, client: AsyncClient, valid_status: str):
        created = await create_task(client, title=f"Status {valid_status}")
        response = await client.patch(
            f"/api/tasks/{created['id']}", json={"status": valid_status}
        )
        assert response.status_code == 200
        assert response.json()["status"] == valid_status
