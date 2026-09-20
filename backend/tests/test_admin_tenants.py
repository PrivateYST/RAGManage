from typing import Any
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


class FakeTransaction:
    def __init__(self) -> None:
        self.entered = False
        self.exited = False

    async def __aenter__(self) -> None:
        self.entered = True

    async def __aexit__(self, *args: object) -> None:
        self.exited = True


class FakeConnection:
    def __init__(self) -> None:
        self.transaction_context = FakeTransaction()
        self.execute_calls: list[tuple[Any, ...]] = []
        self.closed = False

    def transaction(self) -> FakeTransaction:
        return self.transaction_context

    async def fetchrow(self, query: str, *args: object) -> dict[str, object]:
        assert "INSERT INTO tenants" in query
        assert args == ("customer-a", "客户 A")
        return {
            "id": "42",
            "code": "customer-a",
            "name": "客户 A",
            "status": "active",
            "created_at": "2026-09-17T00:00:00Z",
        }

    async def fetchval(self, query: str, *args: object) -> int:
        assert "code = 'space_admin'" in query
        assert args == ()
        return 3

    async def execute(self, query: str, *args: object) -> None:
        self.execute_calls.append((query, *args))

    async def close(self) -> None:
        self.closed = True


def test_create_tenant_grants_creator_space_admin_membership(monkeypatch) -> None:
    connection = FakeConnection()
    context = {"user": {"id": "7", "platform_role": "platform_admin"}}
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=context))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/admin/tenants",
            json={"code": "customer-a", "name": "客户 A"},
        )

    assert response.status_code == 201
    assert response.json()["id"] == "42"
    assert connection.transaction_context.entered
    assert connection.transaction_context.exited
    assert len(connection.execute_calls) == 1
    membership_query, tenant_id, user_id, role_id = connection.execute_calls[0]
    assert "INSERT INTO tenant_members" in membership_query
    assert (tenant_id, user_id, role_id) == (42, 7, 3)
    assert connection.closed
