from typing import Any
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


class FakeTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeMembershipConnection:
    def __init__(
        self,
        *,
        fetchvals: list[object] | None = None,
        space_member: dict[str, object] | None = None,
        knowledge_base_access: dict[str, object] | None = None,
        knowledge_base_target: dict[str, object] | None = None,
        knowledge_base_member: dict[str, object] | None = None,
        rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.fetchvals = list(fetchvals or [])
        self.space_member = space_member
        self.knowledge_base_access = knowledge_base_access
        self.knowledge_base_target = knowledge_base_target
        self.knowledge_base_member = knowledge_base_member
        self.rows = rows or []
        self.execute_calls: list[tuple[Any, ...]] = []
        self.closed = False

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()

    async def fetchval(self, query: str, *args: object) -> object:
        if not self.fetchvals:
            raise AssertionError(f"未配置 fetchval 返回值：{query}")
        return self.fetchvals.pop(0)

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "SELECT kb.id, kb.tenant_id" in query:
            return self.knowledge_base_access
        if "FROM users WHERE login" in query:
            return self.space_member
        if "SELECT tm.status, r.code AS role_code" in query:
            return self.space_member
        if "SELECT tm.user_id, tm.status" in query:
            return self.knowledge_base_target
        if "SELECT km.status, r.code AS role_code" in query:
            return self.knowledge_base_member
        if "UPDATE tenant_members" in query:
            return {"id": str(args[1]), "status": args[3], "created_at": "2026-09-19"}
        raise AssertionError(f"未处理的 fetchrow 查询：{query}")

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        return self.rows

    async def execute(self, query: str, *args: object) -> str:
        self.execute_calls.append((query, *args))
        return "OK"

    async def close(self) -> None:
        self.closed = True


def _client(monkeypatch: Any, connection: FakeMembershipConnection) -> TestClient:
    context = {"user": {"id": "7", "platform_role": "platform_admin"}, "spaces": []}
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=context))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    return TestClient(create_app(Settings()))


def test_platform_admin_still_needs_explicit_space_membership(monkeypatch) -> None:
    connection = FakeMembershipConnection(fetchvals=[False])

    with _client(monkeypatch, connection) as client:
        response = client.get("/api/v1/spaces/91/members")

    assert response.status_code == 404
    assert response.json()["detail"] == "空间不存在"
    assert connection.closed


def test_space_admin_can_list_only_current_space_members(monkeypatch) -> None:
    connection = FakeMembershipConnection(
        fetchvals=[True, True],
        rows=[
            {
                "id": "8",
                "login": "editor-a",
                "display_name": "编辑甲",
                "user_status": "active",
                "status": "active",
                "role_code": "space_member",
                "role_name": "空间成员",
                "knowledge_base_count": 1,
            }
        ],
    )

    with _client(monkeypatch, connection) as client:
        response = client.get("/api/v1/spaces/91/members")

    assert response.status_code == 200
    assert response.json()["items"][0]["login"] == "editor-a"
    assert response.json()["items"][0]["role_code"] == "space_member"


def test_add_space_member_records_audit_and_auth_epoch(monkeypatch) -> None:
    connection = FakeMembershipConnection(
        fetchvals=[True, True, 12, False],
        space_member={
            "id": 8,
            "login": "editor-a",
            "display_name": "编辑甲",
            "status": "active",
        },
    )

    with _client(monkeypatch, connection) as client:
        response = client.post(
            "/api/v1/spaces/91/members",
            json={"login": "editor-a", "role_code": "space_member"},
        )

    assert response.status_code == 201
    assert response.json()["role_code"] == "space_member"
    assert any("INSERT INTO tenant_members" in call[0] for call in connection.execute_calls)
    assert any("auth_epoch = auth_epoch + 1" in call[0] for call in connection.execute_calls)
    assert any("INSERT INTO audit_logs" in call[0] for call in connection.execute_calls)


def test_last_space_admin_cannot_be_disabled(monkeypatch) -> None:
    connection = FakeMembershipConnection(
        fetchvals=[True, True, 1],
        space_member={"status": "active", "role_code": "space_admin"},
    )

    with _client(monkeypatch, connection) as client:
        response = client.patch(
            "/api/v1/spaces/91/members/7",
            json={"status": "disabled"},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "空间必须保留至少一名有效管理员"


def test_customer_reader_cannot_create_knowledge_base(monkeypatch) -> None:
    connection = FakeMembershipConnection(fetchvals=[True, False])

    with _client(monkeypatch, connection) as client:
        response = client.post(
            "/api/v1/knowledge-bases",
            json={
                "tenant_id": 91,
                "name": "客户规则",
                "description": "",
                "purpose": "rule",
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "当前角色不能创建知识库"


def test_customer_reader_cannot_receive_management_grant(monkeypatch) -> None:
    connection = FakeMembershipConnection(
        knowledge_base_access={
            "id": 31,
            "tenant_id": 91,
            "name": "医院服务",
            "status": "published",
            "active_release_id": 4,
            "tenant_role": "space_admin",
            "knowledge_base_role": None,
        },
        knowledge_base_target={
            "user_id": 8,
            "status": "active",
            "space_role_code": "customer_reader",
            "login": "customer-a",
            "display_name": "客户甲",
        },
    )

    with _client(monkeypatch, connection) as client:
        response = client.post(
            "/api/v1/knowledge-bases/31/members",
            json={"user_id": 8, "role_code": "kb_admin"},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "空间管理员或客户用户无需叠加知识库授权"


def test_customer_reader_cannot_restore_old_management_grant(monkeypatch) -> None:
    connection = FakeMembershipConnection(
        fetchvals=[False],
        knowledge_base_access={
            "id": 31,
            "tenant_id": 91,
            "name": "医院服务",
            "status": "published",
            "active_release_id": 4,
            "tenant_role": "space_admin",
            "knowledge_base_role": None,
        },
        knowledge_base_member={"status": "disabled", "role_code": "editor"},
    )

    with _client(monkeypatch, connection) as client:
        response = client.patch(
            "/api/v1/knowledge-bases/31/members/8",
            json={"status": "active"},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "只有有效内部空间成员可以恢复知识库授权"
