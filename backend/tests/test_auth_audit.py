import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.core.auth import authenticate, password_hasher, revoke_token
from app.core.config import Settings
from app.main import create_app


class FakeTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: object) -> None:
        return None


class AuthConnection:
    def __init__(self, user: dict[str, Any] | None = None) -> None:
        self.user = user
        self.execute_calls: list[tuple[Any, ...]] = []
        self.closed = False
        self.revoked_session: dict[str, int] | None = None

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        if "FROM users u" in query:
            return self.user
        if "UPDATE sessions SET revoked_at" in query:
            return self.revoked_session
        raise AssertionError(f"未处理的 fetchrow 查询：{query}")

    async def fetchval(self, query: str, *args: object) -> int:
        assert "INSERT INTO sessions" in query
        return 55

    async def fetch(self, query: str, *args: object) -> list[dict[str, Any]]:
        if "FROM tenant_members" in query or "FROM menus" in query:
            return []
        raise AssertionError(f"未处理的 fetch 查询：{query}")

    async def execute(self, query: str, *args: object) -> None:
        self.execute_calls.append((query, *args))

    async def close(self) -> None:
        self.closed = True


def _audit_call(connection: AuthConnection) -> tuple[Any, ...]:
    return next(call for call in connection.execute_calls if "INSERT INTO audit_logs" in call[0])


def test_successful_login_records_session_audit_without_secrets(monkeypatch: Any) -> None:
    connection = AuthConnection(
        {
            "id": 11,
            "login": "admin",
            "display_name": "平台管理员",
            "password_hash": password_hasher.hash("correct-password"),
            "platform_role_id": 1,
            "platform_role": "platform_admin",
        }
    )
    monkeypatch.setattr("app.core.auth.asyncpg.connect", AsyncMock(return_value=connection))

    result = asyncio.run(
        authenticate(
            Settings(database_url="postgresql://test"),
            " admin ",
            "correct-password",
        )
    )

    assert result is not None
    assert result["user"]["id"] == "11"
    audit = _audit_call(connection)
    assert audit[2] == "auth.login.success"
    assert audit[3] == "session"
    assert audit[4] == "55"
    assert json.loads(audit[5]) == {"login": "admin", "result": "success"}
    assert "correct-password" not in str(connection.execute_calls)
    assert result["token"] not in str(audit)
    assert connection.closed


def test_failed_login_records_generic_reason_without_password(monkeypatch: Any) -> None:
    connection = AuthConnection()
    monkeypatch.setattr("app.core.auth.asyncpg.connect", AsyncMock(return_value=connection))

    result = asyncio.run(
        authenticate(Settings(database_url="postgresql://test"), "unknown", "wrong-password")
    )

    assert result is None
    audit = _audit_call(connection)
    assert audit[1] is None
    assert audit[2] == "auth.login.failed"
    assert audit[3] == "user"
    assert json.loads(audit[5]) == {
        "login": "unknown",
        "reason": "invalid_credentials",
    }
    assert "wrong-password" not in str(connection.execute_calls)


def test_wrong_password_is_not_attributed_to_target_user(monkeypatch: Any) -> None:
    connection = AuthConnection(
        {
            "id": 11,
            "login": "admin",
            "display_name": "平台管理员",
            "password_hash": password_hasher.hash("correct-password"),
            "platform_role_id": 1,
            "platform_role": "platform_admin",
        }
    )
    monkeypatch.setattr("app.core.auth.asyncpg.connect", AsyncMock(return_value=connection))

    result = asyncio.run(
        authenticate(Settings(database_url="postgresql://test"), "admin", "wrong-password")
    )

    assert result is None
    audit = _audit_call(connection)
    assert audit[1] is None
    assert audit[3] == "user"
    assert audit[4] == "11"


def test_logout_revokes_session_and_records_audit(monkeypatch: Any) -> None:
    connection = AuthConnection()
    connection.revoked_session = {"id": 55, "user_id": 11}
    monkeypatch.setattr("app.core.auth.asyncpg.connect", AsyncMock(return_value=connection))

    asyncio.run(revoke_token(Settings(database_url="postgresql://test"), "session-token"))

    audit = _audit_call(connection)
    assert audit[1] == 11
    assert audit[2] == "auth.logout"
    assert audit[3] == "session"
    assert audit[4] == "55"
    assert "session-token" not in str(connection.execute_calls)


class PasswordConnection:
    def __init__(self) -> None:
        self.password_hash = password_hasher.hash("current-password")
        self.fetchval_calls = 0
        self.execute_calls: list[tuple[Any, ...]] = []

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()

    async def fetchval(self, query: str, *args: object) -> object:
        self.fetchval_calls += 1
        if "SELECT password_hash" in query:
            return self.password_hash
        if "WITH revoked AS" in query:
            return 2
        raise AssertionError(f"未处理的 fetchval 查询：{query}")

    async def execute(self, query: str, *args: object) -> None:
        self.execute_calls.append((query, *args))

    async def close(self) -> None:
        return None


def test_password_change_audits_revoked_sessions_without_passwords(monkeypatch: Any) -> None:
    connection = PasswordConnection()
    monkeypatch.setattr(
        "app.main._authenticated_user",
        AsyncMock(return_value={"user": {"id": "11"}}),
    )
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/auth/password",
            json={"current_password": "current-password", "new_password": "new-password"},
        )

    assert response.status_code == 204
    audit = next(call for call in connection.execute_calls if "INSERT INTO audit_logs" in call[0])
    assert json.loads(audit[3]) == {"revoked_sessions": 2}
    assert "current-password" not in str(connection.execute_calls)
    assert "new-password" not in str(connection.execute_calls)
