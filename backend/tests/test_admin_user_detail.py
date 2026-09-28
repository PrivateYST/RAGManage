"""平台用户详情接口回归：覆盖资料、当前授权和脱敏审计历史的聚合返回。"""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


class DetailConnection:
    """最小数据库夹具，验证详情接口执行三段只读查询并关闭连接。"""

    def __init__(self) -> None:
        self.closed = False

    async def fetchrow(self, query: str, *args: object) -> dict[str, object]:
        assert "FROM users" in query
        assert args == (7,)
        return {
            "id": "7",
            "login": "alice",
            "display_name": "Alice",
            "status": "active",
            "platform_role": None,
            "last_login_at": None,
            "created_at": "2026-09-01T00:00:00Z",
        }

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        assert args == (7,) or args == ("7",)
        if "tenant_members" in query:
            return [
                {
                    "tenant_id": "3",
                    "tenant_code": "demo",
                    "tenant_name": "演示",
                    "role_code": "customer_reader",
                    "status": "active",
                    "created_at": "2026-09-01T00:00:00Z",
                }
            ]
        return [
            {
                "id": "1",
                "action": "space_member.add",
                "target_type": "user",
                "target_id": "7",
                "change_summary": {"role_code": "customer_reader"},
                "created_at": "2026-09-01T00:00:00Z",
            }
        ]

    async def close(self) -> None:
        self.closed = True


def test_platform_admin_can_read_user_detail_and_authorization_history(monkeypatch) -> None:
    """平台管理员可读取授权聚合，且响应不包含密码或会话凭据。"""
    connection = DetailConnection()
    monkeypatch.setattr(
        "app.main._authenticated_user",
        AsyncMock(return_value={"user": {"id": "9", "platform_role": "platform_admin"}}),
    )
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))

    with TestClient(create_app(Settings())) as client:
        response = client.get("/api/v1/admin/users/7")

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["login"] == "alice"
    assert body["memberships"][0]["tenant_code"] == "demo"
    assert body["history"][0]["action"] == "space_member.add"
    assert "password" not in body
    assert connection.closed
