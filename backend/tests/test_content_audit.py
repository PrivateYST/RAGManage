"""验证文档上传、停用和删除操作与租户审计在同一业务事务中完成。"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


class FakeTransaction:
    """提供与 asyncpg 兼容的无副作用事务上下文。"""

    async def __aenter__(self) -> None:
        """进入测试事务。"""
        return None

    async def __aexit__(self, *args: object) -> None:
        """退出测试事务并保留接口抛出的异常语义。"""
        return None


class ContentAuditConnection:
    """模拟内容写接口的数据访问，并保存所有 SQL 写调用供审计断言。"""

    def __init__(self) -> None:
        """初始化写调用记录和连接关闭状态。"""
        self.execute_calls: list[tuple[Any, ...]] = []
        self.closed = False

    def transaction(self) -> FakeTransaction:
        """返回测试事务上下文。"""
        return FakeTransaction()

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        """按上传流程返回文档、版本和解析任务记录。"""
        if "SELECT id FROM documents" in query:
            return None
        if "INSERT INTO documents" in query:
            return {"id": 31}
        if "INSERT INTO document_versions" in query:
            return {
                "id": 41,
                "version_no": 1,
                "parse_status": "queued",
                "created_at": "2026-09-19T16:00:00+00:00",
            }
        if "INSERT INTO tasks" in query:
            return {
                "id": 51,
                "state": "queued",
                "task_type": "document_parse",
                "created_at": "2026-09-19T16:00:00+00:00",
            }
        raise AssertionError(f"未处理的 fetchrow 查询：{query}")

    async def fetchval(self, query: str, *args: object) -> int:
        """返回新文档版本号。"""
        if "COALESCE(MAX(version_no)" in query:
            return 1
        raise AssertionError(f"未处理的 fetchval 查询：{query}")

    async def execute(self, query: str, *args: object) -> None:
        """记录业务写入和审计写入的 SQL 参数。"""
        self.execute_calls.append((query, *args))

    async def close(self) -> None:
        """标记连接已关闭。"""
        self.closed = True


def _context() -> dict[str, Any]:
    """返回执行内容管理操作的用户上下文。"""
    return {"user": {"id": "7"}}


def _document_access(*, role: str = "space_admin", status: str = "active") -> dict[str, Any]:
    """构造带空间、知识库、状态和发布版本的文档授权记录。"""
    return {
        "id": 31,
        "tenant_id": 1,
        "knowledge_base_id": 2,
        "title": "审计资料",
        "status": status,
        "active_release_id": 9,
        "tenant_role": role,
        "knowledge_base_role": None,
    }


def _audit_call(connection: ContentAuditConnection, action: str) -> tuple[Any, ...]:
    """从写调用中取得指定内容生命周期事件。"""
    return next(
        call
        for call in connection.execute_calls
        if "INSERT INTO audit_logs" in call[0] and call[3] == action
    )


def test_upload_records_sanitized_tenant_audit(monkeypatch: Any, tmp_path: Path) -> None:
    """上传成功应记录版本和任务标识，但不得把正文或存储路径写入审计。"""
    connection = ContentAuditConnection()
    access = {
        "id": 2,
        "tenant_id": 1,
        "name": "测试知识库",
        "tenant_role": "space_admin",
        "knowledge_base_role": None,
    }
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=_context()))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr(
        "app.main._require_knowledge_base_role",
        AsyncMock(return_value=access),
    )

    with TestClient(create_app(Settings(storage_root=tmp_path))) as client:
        response = client.post(
            "/api/v1/knowledge-bases/2/documents",
            files={"file": ("audit.md", b"private document body", "text/markdown")},
        )

    assert response.status_code == 202
    audit = _audit_call(connection, "document.upload")
    assert audit[1:6] == (1, 7, "document.upload", "document", "31")
    summary = json.loads(audit[6])
    assert summary["document_version_id"] == "41"
    assert summary["task_id"] == "51"
    assert summary["file_size"] == 21
    assert "private document body" not in str(audit)
    assert "storage_key" not in summary
    assert connection.closed


def test_disable_document_records_state_transition(monkeypatch: Any) -> None:
    """停用文档应与内容世代更新原子提交，并记录发布影响范围。"""
    connection = ContentAuditConnection()
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=_context()))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr(
        "app.main._document_access",
        AsyncMock(return_value=_document_access()),
    )

    with TestClient(create_app(Settings())) as client:
        response = client.post("/api/v1/documents/31/disable")

    assert response.status_code == 204
    audit = _audit_call(connection, "document.disable")
    summary = json.loads(audit[6])
    assert summary["before"] == {"status": "active"}
    assert summary["after"] == {"status": "disabled"}
    assert summary["active_release_id"] == "9"


def test_delete_document_requires_admin_and_records_soft_delete(monkeypatch: Any) -> None:
    """管理员删除应记录软删除；编辑者被拒绝时不得产生业务写入或审计。"""
    denied_connection = ContentAuditConnection()
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=_context()))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=denied_connection))
    monkeypatch.setattr(
        "app.main._document_access",
        AsyncMock(return_value=_document_access(role="space_member")),
    )
    monkeypatch.setattr("app.main._role_for_access", lambda _: "editor")

    with TestClient(create_app(Settings())) as client:
        denied = client.delete("/api/v1/documents/31")

    assert denied.status_code == 403
    assert not denied_connection.execute_calls

    allowed_connection = ContentAuditConnection()
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=allowed_connection))
    monkeypatch.setattr("app.main._role_for_access", lambda _: "space_admin")

    with TestClient(create_app(Settings())) as client:
        allowed = client.delete("/api/v1/documents/31")

    assert allowed.status_code == 204
    audit = _audit_call(allowed_connection, "document.delete")
    summary = json.loads(audit[6])
    assert summary["before"] == {"status": "active"}
    assert summary["after"] == {"status": "deleted"}


def test_delete_conversation_records_owner_scoped_soft_delete(monkeypatch: Any) -> None:
    """会话删除应复用所有者授权，并在同一事务记录知识库范围审计。"""
    connection = ContentAuditConnection()
    conversation = {
        "id": 13,
        "tenant_id": 1,
        "knowledge_base_id": 2,
        "title": "待删除会话",
        "status": "active",
    }
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=_context()))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr("app.main._conversation_id_from_public", AsyncMock(return_value=13))
    monkeypatch.setattr("app.main._conversation_access", AsyncMock(return_value=conversation))

    with TestClient(create_app(Settings())) as client:
        response = client.delete("/api/v1/conversations/11111111-1111-4111-8111-111111111111")

    assert response.status_code == 204
    assert any("UPDATE conversations" in call[0] for call in connection.execute_calls)
    audit = _audit_call(connection, "conversation.delete")
    summary = json.loads(audit[6])
    assert summary["knowledge_base_id"] == "2"
    assert summary["before"] == {"status": "active"}
    assert summary["after"] == {"status": "deleted"}
