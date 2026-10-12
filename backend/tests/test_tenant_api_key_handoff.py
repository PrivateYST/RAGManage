"""医院 API Key 交接接口回归：确保确认范围、角色边界和明文处理保持安全。"""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.core.api_keys import hash_api_key
from app.core.config import Settings
from app.main import TenantApiKeyConfiguration, create_app


class FakeTransaction:
    """为接口测试提供可观察的事务边界，不连接或修改开发数据库。"""

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_: object) -> None:
        return None


class FakeTenantKeyConnection:
    """模拟单个医院的 Key 元数据、授权检查与确认审计写入。"""

    def __init__(
        self,
        *,
        row: dict[str, Any] | None = None,
        tenant_access: bool = True,
        space_admin: bool = True,
        configured_at: datetime | None = None,
    ) -> None:
        self.row = row
        self.tenant_access = tenant_access
        self.space_admin = space_admin
        self.configured_at = configured_at
        self.calls: list[tuple[Any, ...]] = []
        self.closed = False

    def transaction(self) -> FakeTransaction:
        """允许测试断言确认元数据和审计日志共享同一事务。"""
        return FakeTransaction()

    async def fetchval(self, query: str, *args: object) -> Any:
        """按授权查询顺序返回访问权，并模拟首次确认时间戳。"""
        self.calls.append((query, *args))
        if "UPDATE api_keys SET configured_at" in query:
            self.configured_at = datetime.now(UTC)
            return self.configured_at
        if "JOIN roles r" in query:
            return self.space_admin
        if "JOIN tenants t" in query:
            return self.tenant_access
        raise AssertionError(f"未处理的 fetchval 查询：{query}")

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        """返回未脱敏之外的状态元数据，或模拟 Key 与当前医院不匹配。"""
        self.calls.append((query, *args))
        if "SELECT ak.key_prefix" in query:
            return self.row
        if "SELECT ak.id, ak.key_prefix" in query:
            return self.row
        raise AssertionError(f"未处理的 fetchrow 查询：{query}")

    async def execute(self, query: str, *args: object) -> str:
        """记录审计写入，供测试检查操作摘要不包含提交的凭据。"""
        self.calls.append((query, *args))
        return "INSERT 0 1"

    async def close(self) -> None:
        """记录路由是否在 finally 中关闭连接。"""
        self.closed = True


def _active_key_row(*, configured_at: datetime | None = None) -> dict[str, Any]:
    """构造当前空间最新且可用的测试 Key 元数据，不包含明文凭据。"""
    return {
        "id": 9,
        "key_prefix": "sk-abcdefgh…wxyz",
        "status": "active",
        "expires_at": None,
        "token_limit": 1000,
        "token_used": 100,
        "token_reserved": 50,
        "configured_at": configured_at,
        "tenant_status": "active",
    }


def _space_admin_context() -> dict[str, Any]:
    """构造没有平台角色、由后端空间成员关系再授权的医院管理员。"""
    return {"user": {"id": "8", "platform_role": None}, "spaces": []}


def test_key_confirmation_requires_system_assigned_format() -> None:
    """粘贴格式只允许平台签发的 sk- 前缀，空白边界会在校验时清除。"""
    payload = TenantApiKeyConfiguration(api_key="  sk-valid-test-key  ")

    assert payload.api_key.get_secret_value() == "sk-valid-test-key"

    try:
        TenantApiKeyConfiguration(api_key="global-gateway-key")
    except ValueError as error:
        assert "sk-" in str(error)
    else:
        raise AssertionError("非 sk- 凭据必须被拒绝")


def test_space_admin_reads_only_masked_latest_key_status(monkeypatch: Any) -> None:
    """医院管理员只能读取本空间脱敏前缀与交接状态，接口不返回完整 Key。"""
    configured_at = datetime(2026, 10, 12, tzinfo=UTC)
    connection = FakeTenantKeyConnection(row=_active_key_row(configured_at=configured_at))
    monkeypatch.setattr(
        "app.main._authenticated_user", AsyncMock(return_value=_space_admin_context())
    )
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))

    with TestClient(create_app(Settings())) as client:
        response = client.get("/api/v1/spaces/3/api-key/configuration")

    assert response.status_code == 200
    assert response.json() == {
        "configured": True,
        "key_prefix": "sk-abcdefgh…wxyz",
        "status": "active",
        "configured_at": configured_at.isoformat().replace("+00:00", "Z"),
    }
    assert "raw_key" not in response.json()
    assert connection.closed


def test_space_admin_confirms_only_matching_current_key_without_persisting_plaintext(
    monkeypatch: Any,
) -> None:
    """首次确认只写入账号与时间，审计和 SQL 参数都不含提交的 Key 明文。"""
    raw_key = "sk-current-hospital-secret"
    connection = FakeTenantKeyConnection(row=_active_key_row())
    monkeypatch.setattr(
        "app.main._authenticated_user", AsyncMock(return_value=_space_admin_context())
    )
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/spaces/3/api-key/configuration",
            json={"api_key": raw_key},
        )

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert response.json()["key_prefix"] == "sk-abcdefgh…wxyz"
    assert raw_key not in response.text
    confirmation_query = next(
        call for call in connection.calls if "SELECT ak.id, ak.key_prefix" in call[0]
    )
    assert confirmation_query[1:] == (3, hash_api_key(raw_key))
    assert all(raw_key not in str(call) for call in connection.calls)
    assert any("UPDATE api_keys SET configured_at" in str(call) for call in connection.calls)
    assert any("api_key.configure" in str(call) for call in connection.calls)
    assert connection.closed


def test_other_hospital_key_is_rejected_without_writes(monkeypatch: Any) -> None:
    """数据库只查当前医院最新 Key，错贴其他医院凭据不会写状态或审计。"""
    connection = FakeTenantKeyConnection(row=None)
    monkeypatch.setattr(
        "app.main._authenticated_user", AsyncMock(return_value=_space_admin_context())
    )
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/spaces/3/api-key/configuration",
            json={"api_key": "sk-other-hospital-key"},
        )

    assert response.status_code == 400
    assert "不匹配" in response.json()["detail"]
    assert not any("UPDATE api_keys" in str(call) for call in connection.calls)
    assert not any("INSERT INTO audit_logs" in str(call) for call in connection.calls)
    assert connection.closed


def test_space_member_cannot_confirm_hospital_key(monkeypatch: Any) -> None:
    """普通医院成员可属于该空间，但没有管理员角色时不能确认 API Key。"""
    connection = FakeTenantKeyConnection(space_admin=False)
    monkeypatch.setattr(
        "app.main._authenticated_user", AsyncMock(return_value=_space_admin_context())
    )
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/spaces/3/api-key/configuration",
            json={"api_key": "sk-current-hospital-secret"},
        )

    assert response.status_code == 403
    assert not any("SELECT ak.id, ak.key_prefix" in str(call) for call in connection.calls)
    assert connection.closed


def test_platform_admin_cannot_use_hospital_confirmation_endpoint(monkeypatch: Any) -> None:
    """平台管理员负责签发和发放，医院确认入口拒绝平台级账号。"""
    database = AsyncMock()
    monkeypatch.setattr(
        "app.main._authenticated_user",
        AsyncMock(return_value={"user": {"id": "7", "platform_role": "platform_admin"}}),
    )
    monkeypatch.setattr("app.main._database", database)

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/spaces/3/api-key/configuration",
            json={"api_key": "sk-current-hospital-secret"},
        )

    assert response.status_code == 403
    database.assert_not_awaited()


def test_unusable_assigned_key_cannot_be_confirmed(monkeypatch: Any) -> None:
    """停用 Key 不得标记交接完成，便于管理员发现状态异常并重新分配。"""
    row = {**_active_key_row(), "status": "disabled"}
    connection = FakeTenantKeyConnection(row=row)
    monkeypatch.setattr(
        "app.main._authenticated_user", AsyncMock(return_value=_space_admin_context())
    )
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/spaces/3/api-key/configuration",
            json={"api_key": "sk-current-hospital-secret"},
        )

    assert response.status_code == 409
    assert "停用" in response.json()["detail"]
    assert not any("UPDATE api_keys SET configured_at" in str(call) for call in connection.calls)
    assert connection.closed
