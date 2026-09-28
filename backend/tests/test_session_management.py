"""验证用户只管理本人有效登录会话，并撤销时保留不可变审计记录。"""

import hashlib
import json
from typing import Any
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.security import session_csrf_token
from app.main import create_app


class FakeTransaction:
    """为路由测试提供可观察的事务边界，不模拟数据库内部实现。"""

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: object) -> None:
        return None


class SessionConnection:
    """记录会话列表与撤销 SQL 调用，并返回当前场景对应的公开行。"""

    def __init__(self, revoked: dict[str, Any] | None) -> None:
        self.revoked = revoked
        self.fetch_calls: list[tuple[str, tuple[object, ...]]] = []
        self.fetchrow_calls: list[tuple[str, tuple[object, ...]]] = []
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []
        self.closed = False

    def transaction(self) -> FakeTransaction:
        """让审计写入与会话撤销处于同一个测试事务。"""
        return FakeTransaction()

    async def fetch(self, query: str, *args: object) -> list[dict[str, Any]]:
        """返回用户作用域内的有效会话列表。"""
        self.fetch_calls.append((query, args))
        return [
            {
                "id": "31",
                "created_at": "2026-09-20T00:00:00Z",
                "last_seen_at": "2026-09-23T00:00:00Z",
                "expires_at": "2026-09-23T12:00:00Z",
                "is_current": True,
            },
            {
                "id": "32",
                "created_at": "2026-09-21T00:00:00Z",
                "last_seen_at": "2026-09-22T00:00:00Z",
                "expires_at": "2026-09-24T00:00:00Z",
                "is_current": False,
            },
        ]

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        """只返回本用户仍有效且未撤销的目标 Session。"""
        self.fetchrow_calls.append((query, args))
        return self.revoked

    async def execute(self, query: str, *args: object) -> None:
        """保存本次撤销对应的脱敏审计事件。"""
        self.execute_calls.append((query, args))

    async def close(self) -> None:
        """记录路由已释放数据库连接。"""
        self.closed = True


def _session_client(
    monkeypatch: Any,
    connection: SessionConnection,
    *,
    token: str = "current-session-token",
) -> TestClient:
    """构造带合法 Session 和 CSRF 双提交凭据的 API 客户端。"""
    settings = Settings()
    context = {"user": {"id": "11"}, "token": token}
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=context))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    client = TestClient(create_app(settings))
    csrf = session_csrf_token(settings.csrf_secret_value, token)
    client.cookies.set("ragmanage_session", token)
    client.cookies.set("ragmanage_csrf", csrf)
    return client


def test_session_list_returns_only_current_users_active_sessions(monkeypatch: Any) -> None:
    """列表按认证用户隔离，并标出当前 Session 供用户识别正在使用的设备。"""
    connection = SessionConnection(None)
    client = _session_client(monkeypatch, connection)

    with client:
        response = client.get("/api/v1/auth/sessions")

    query, args = connection.fetch_calls[0]
    assert response.status_code == 200
    assert response.json()["items"][0]["is_current"] is True
    assert response.json()["items"][1]["is_current"] is False
    assert args == (11, hashlib.sha256(b"current-session-token").hexdigest(), 100)
    assert "user_id = $1" in query
    assert "revoked_at IS NULL" in query
    assert connection.closed


def test_user_can_revoke_another_owned_session_and_audit_it(monkeypatch: Any) -> None:
    """成功撤销本人其他会话写审计，但不清除当前浏览器仍在使用的 Cookie。"""
    connection = SessionConnection({"id": 32, "user_id": 11, "token_hash": "other-session-hash"})
    client = _session_client(monkeypatch, connection)

    with client:
        response = client.delete(
            "/api/v1/auth/sessions/32",
            headers={"x-csrf-token": client.cookies.get("ragmanage_csrf")},
        )

    assert response.status_code == 204
    assert not response.headers.get("set-cookie")
    query, args = connection.fetchrow_calls[0]
    assert args == (32, 11)
    assert "user_id = $2" in query
    audit_query, audit_args = connection.execute_calls[0]
    assert "auth.session.revoked" in audit_query
    assert audit_args[:2] == (11, "32")
    assert json.loads(str(audit_args[2])) == {"result": "revoked"}
    assert connection.closed


def test_revoking_current_session_expires_both_browser_cookies(monkeypatch: Any) -> None:
    """撤销当前 Session 后立即清除认证与 CSRF Cookie，避免继续提交失效身份。"""
    token = "current-session-token"
    current_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    connection = SessionConnection({"id": 31, "user_id": 11, "token_hash": current_hash})
    client = _session_client(monkeypatch, connection, token=token)

    with client:
        response = client.delete(
            "/api/v1/auth/sessions/31",
            headers={"x-csrf-token": client.cookies.get("ragmanage_csrf")},
        )

    set_cookie = response.headers.get("set-cookie", "")
    assert response.status_code == 204
    assert "ragmanage_session" in set_cookie
    assert "ragmanage_csrf" in set_cookie


def test_session_cannot_revoke_another_users_session(monkeypatch: Any) -> None:
    """不存在、不属于本人或已撤销的会话统一返回 404，避免枚举其他账号。"""
    connection = SessionConnection(None)
    client = _session_client(monkeypatch, connection)

    with client:
        response = client.delete(
            "/api/v1/auth/sessions/999",
            headers={"x-csrf-token": client.cookies.get("ragmanage_csrf")},
        )

    assert response.status_code == 404
    assert connection.execute_calls == []
    assert connection.closed
