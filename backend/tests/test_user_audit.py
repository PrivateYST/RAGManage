"""验证用户管理操作的审计归属、会话撤销和敏感信息保护。"""

import json
from typing import Any
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


class FakeTransaction:
    """提供异步事务上下文，使接口测试只关注审计行为而不依赖真实数据库。"""

    async def __aenter__(self) -> None:
        """进入无副作用的测试事务。"""
        return None

    async def __aexit__(self, *args: object) -> None:
        """退出测试事务；异常由测试客户端按原语义继续处理。"""
        return None


class UserAuditConnection:
    """模拟用户管理所需的数据访问，并保留写操作供断言审计载荷。"""

    def __init__(self) -> None:
        """初始化写调用记录。"""
        self.execute_calls: list[tuple[Any, ...]] = []

    def transaction(self) -> FakeTransaction:
        """返回与 asyncpg 事务接口兼容的测试上下文。"""
        return FakeTransaction()

    async def fetchval(self, query: str, *args: object) -> object:
        """按查询意图返回角色、空间存在性和撤销会话数量。"""
        if "scope = 'platform'" in query:
            return 1
        if "scope = 'tenant'" in query:
            return 2
        if "SELECT EXISTS" in query:
            return True
        if "WITH revoked AS" in query:
            return 3
        raise AssertionError(f"未处理的 fetchval 查询：{query}")

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        """返回固定的创建结果、更新前快照和更新后状态。"""
        if "INSERT INTO users" in query:
            return {
                "id": 21,
                "login": "audited-user",
                "display_name": "审计用户",
                "status": "active",
                "created_at": "2026-09-19T15:00:00+00:00",
            }
        if "FROM users WHERE id = $1 FOR UPDATE" in query:
            return {
                "id": 21,
                "login": "audited-user",
                "display_name": "审计用户",
                "status": "active",
            }
        if "UPDATE users SET" in query:
            return {
                "id": "21",
                "login": "audited-user",
                "display_name": "审计用户",
                "status": "disabled",
                "last_login_at": None,
                "created_at": "2026-09-19T15:00:00+00:00",
            }
        raise AssertionError(f"未处理的 fetchrow 查询：{query}")

    async def execute(self, query: str, *args: object) -> None:
        """记录写语句及参数，供测试检查审计事件与敏感数据。"""
        self.execute_calls.append((query, *args))

    async def close(self) -> None:
        """模拟连接关闭；测试替身没有外部资源需要释放。"""
        return None


def _admin_context() -> dict[str, Any]:
    """返回具有平台用户管理权限的最小认证上下文。"""
    return {"user": {"id": "1", "platform_role": "platform_admin"}}


def test_create_user_records_platform_and_space_assignment_audits(monkeypatch: Any) -> None:
    """创建并分配空间时应同时生成平台用户事件和空间授权事件。"""
    connection = UserAuditConnection()
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=_admin_context()))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/admin/users",
            json={
                "login": "audited-user",
                "display_name": "审计用户",
                "password": "temporary-password",
                "tenant_id": 7,
                "tenant_role_code": "space_member",
            },
        )

    assert response.status_code == 201
    audit_calls = [call for call in connection.execute_calls if "INSERT INTO audit_logs" in call[0]]
    assert len(audit_calls) == 2
    membership_audit = next(call for call in audit_calls if call[3] == "space_member.add")
    assert membership_audit[1] == 7
    assert json.loads(membership_audit[6]) == {
        "role_code": "space_member",
        "source": "user.create",
    }
    user_audit = next(call for call in audit_calls if "'user.create'" in call[0])
    summary = json.loads(user_audit[3])
    assert summary["login"] == "audited-user"
    assert summary["tenant_id"] == "7"
    assert "temporary-password" not in str(connection.execute_calls)


def test_disable_user_records_before_after_and_revoked_sessions(monkeypatch: Any) -> None:
    """停用账号应保存状态变更证据，并记录被立即撤销的有效会话数量。"""
    connection = UserAuditConnection()
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=_admin_context()))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))

    with TestClient(create_app(Settings())) as client:
        response = client.patch("/api/v1/admin/users/21", json={"status": "disabled"})

    assert response.status_code == 200
    audit = next(call for call in connection.execute_calls if "'user.update'" in call[0])
    summary = json.loads(audit[3])
    assert summary == {
        "fields": ["status"],
        "before": {"status": "active"},
        "after": {"status": "disabled"},
        "password_reset": False,
        "revoked_sessions": 3,
    }


def test_admin_password_reset_audit_never_contains_plaintext(monkeypatch: Any) -> None:
    """管理员重置密码只记录操作标记，防止明文密码进入不可变审计日志。"""
    connection = UserAuditConnection()
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=_admin_context()))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))

    with TestClient(create_app(Settings())) as client:
        response = client.patch(
            "/api/v1/admin/users/21",
            json={"password": "replacement-password"},
        )

    assert response.status_code == 200
    audit = next(call for call in connection.execute_calls if "'user.update'" in call[0])
    summary = json.loads(audit[3])
    assert summary["fields"] == ["password"]
    assert summary["password_reset"] is True
    assert summary["revoked_sessions"] == 3
    assert "replacement-password" not in str(audit)
