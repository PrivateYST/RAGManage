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


class FakeTenantListConnection:
    """客户空间列表夹具：验证 Key 摘要返回而不模拟完整数据库驱动。"""

    def __init__(self) -> None:
        self.closed = False

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        assert "current_key.key_prefix" in query
        assert "api_keys ak" in query
        assert args == ()
        return [
            {
                "id": "42",
                "code": "customer-a",
                "name": "客户 A",
                "status": "active",
                "created_at": "2026-09-17T00:00:00Z",
                "member_count": 3,
                "knowledge_base_count": 2,
                "api_key_id": "9",
                "api_key_status": "active",
                "api_key_prefix": "sk-customer…1234",
                "api_key_token_limit": 1000,
                "api_key_token_used": 120,
                "api_key_token_remaining": 880,
                "api_key_expires_at": None,
            }
        ]

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


def test_admin_tenant_list_includes_key_summary_without_plaintext(monkeypatch) -> None:
    """空间管理列表返回脱敏 Key 摘要，不能把完整客户凭据放进列表响应。"""
    connection = FakeTenantListConnection()
    context = {"user": {"id": "7", "platform_role": "platform_admin"}}
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=context))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))

    with TestClient(create_app(Settings())) as client:
        response = client.get("/api/v1/admin/tenants")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["api_key_id"] == "9"
    assert item["api_key_prefix"] == "sk-customer…1234"
    assert item["api_key_token_remaining"] == 880
    assert "raw_key" not in item
    assert connection.closed
