"""验证解析与索引 Worker 在成功和失败终态写入可追踪的空间审计。"""

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

from app.core.config import Settings
from app.jobs import builds, tasks
from app.rag.parsing import Block, ParsedDocument


class FakeTransaction:
    """提供 Worker 数据库替身所需的异步事务协议。"""

    async def __aenter__(self) -> None:
        """进入测试事务。"""
        return None

    async def __aexit__(self, *args: object) -> None:
        """退出测试事务并保留原始异常。"""
        return None


class ParseWorkerConnection:
    """模拟单个文档解析任务，并记录状态与审计写入。"""

    def __init__(self) -> None:
        """初始化 SQL 写调用列表。"""
        self.execute_calls: list[tuple[Any, ...]] = []

    def transaction(self) -> FakeTransaction:
        """返回测试事务上下文。"""
        return FakeTransaction()

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        """返回解析任务、文档版本和默认 Profile 查询结果。"""
        if "FROM tasks WHERE id" in query:
            return {
                "id": 51,
                "tenant_id": 1,
                "state": "queued",
                "knowledge_base_id": 2,
                "created_by": 7,
            }
        if "FROM document_versions" in query:
            return {
                "id": 41,
                "document_id": 31,
                "tenant_id": 1,
                "storage_key": "audit.md",
                "knowledge_base_id": 2,
            }
        if "FROM ingestion_profiles" in query:
            return None
        raise AssertionError(f"未处理的 fetchrow 查询：{query}")

    async def fetchval(self, query: str, *args: object) -> int:
        """返回新建切片 Profile 或产物 ID。"""
        if "INSERT INTO ingestion_profiles" in query:
            return 61
        if "INSERT INTO document_artifacts" in query:
            return 71
        raise AssertionError(f"未处理的 fetchval 查询：{query}")

    async def execute(self, query: str, *args: object) -> None:
        """保存 Worker 的状态、切片和审计写调用。"""
        self.execute_calls.append((query, *args))

    async def close(self) -> None:
        """模拟关闭数据库连接。"""
        return None


class BuildWorkerConnection:
    """模拟单文档单切片构建，并支持嵌入成功或失败两种终态。"""

    def __init__(self) -> None:
        """初始化 SQL 写调用列表。"""
        self.execute_calls: list[tuple[Any, ...]] = []

    def transaction(self) -> FakeTransaction:
        """返回测试事务上下文。"""
        return FakeTransaction()

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        """返回构建快照、向量计数或失败审计上下文。"""
        if "FROM index_builds ib" in query:
            return {
                "id": 81,
                "tenant_id": 1,
                "knowledge_base_id": 2,
                "created_by": 7,
                "embedding_profile_id": 91,
                "build_state": "queued",
                "task_state": "queued",
                "dimension": 2,
                "model_name": "embedding-test",
                "base_url": "http://model.test",
                "allowed_models": ["embedding-test"],
                "endpoint_status": "active",
            }
        if "count(c.id)::int AS expected_count" in query:
            return {"expected_count": 1, "embedded_count": 1}
        if "FROM index_builds WHERE id" in query:
            return {
                "tenant_id": 1,
                "knowledge_base_id": 2,
                "embedding_profile_id": 91,
                "created_by": 7,
            }
        raise AssertionError(f"未处理的 fetchrow 查询：{query}")

    async def fetch(self, query: str, *args: object) -> list[dict[str, Any]]:
        """返回一个构建项及其单个待嵌入切片。"""
        if "FROM build_items" in query:
            return [
                {
                    "build_id": 81,
                    "tenant_id": 1,
                    "knowledge_base_id": 2,
                    "document_id": 31,
                    "document_version_id": 41,
                    "artifact_id": 71,
                    "state": "queued",
                }
            ]
        if "SELECT id, embed_text FROM chunks" in query:
            return [{"id": 101, "embed_text": "audit chunk"}]
        raise AssertionError(f"未处理的 fetch 查询：{query}")

    async def fetchval(self, query: str, *args: object) -> str:
        """让构建项检查始终观察到运行中且未取消的任务。"""
        if "SELECT state FROM tasks" in query:
            return "running"
        raise AssertionError(f"未处理的 fetchval 查询：{query}")

    async def execute(self, query: str, *args: object) -> None:
        """保存构建状态、向量和审计写调用。"""
        self.execute_calls.append((query, *args))

    async def close(self) -> None:
        """模拟关闭数据库连接。"""
        return None


class SuccessfulModelClient:
    """返回与测试 Profile 维度一致的确定性向量。"""

    def __init__(self, settings: Settings) -> None:
        """接收运行配置以匹配真实客户端构造契约。"""
        self.settings = settings

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """为每段文本返回一个二维向量。"""
        return [[0.6, 0.8] for _ in texts]


class FailedModelClient(SuccessfulModelClient):
    """模拟模型端点拒绝构建，用于验证失败审计。"""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """抛出稳定业务错误，Worker 应持久化失败终态后继续向上抛出。"""
        raise ValueError("MODEL_NOT_ALLOWED")


def _audit_actions(calls: list[tuple[Any, ...]]) -> set[str]:
    """从数据库写调用中提取审计动作编码。"""
    return {str(call[3]) for call in calls if "INSERT INTO audit_logs" in call[0]}


def test_parse_worker_records_completed_audit(monkeypatch: Any, tmp_path: Path) -> None:
    """解析成功应记录文档、版本、产物、切片数及任务创建人。"""
    connection = ParseWorkerConnection()
    (tmp_path / "audit.md").write_text("audit body", encoding="utf-8")
    parsed = ParsedDocument(
        name="audit.md",
        sha256="hash",
        parser="markdown:test",
        blocks=[Block("audit body", ("Audit",), {"line_start": 1, "line_end": 1})],
    )
    monkeypatch.setattr(tasks.asyncpg, "connect", AsyncMock(return_value=connection))
    monkeypatch.setattr(
        tasks,
        "Settings",
        lambda: Settings(database_url="postgresql://test", storage_root=tmp_path),
    )
    monkeypatch.setattr(tasks, "parse_document", lambda _: parsed)

    asyncio.run(tasks._process_document(51))

    assert "document.parse.completed" in _audit_actions(connection.execute_calls)
    audit = next(
        call
        for call in connection.execute_calls
        if "INSERT INTO audit_logs" in call[0] and call[3] == "document.parse.completed"
    )
    assert audit[1:6] == (1, 7, "document.parse.completed", "document", "31")
    assert "audit body" not in str(audit)


def test_parse_worker_records_failed_audit(monkeypatch: Any, tmp_path: Path) -> None:
    """解析器返回失败状态时应保存稳定错误代码，且不把解析告警正文写入审计。"""
    connection = ParseWorkerConnection()
    (tmp_path / "audit.md").write_text("damaged input", encoding="utf-8")
    parsed = ParsedDocument(
        name="audit.md",
        sha256="hash",
        parser="markdown:test",
        status="failed",
        warnings=["sensitive parser detail"],
    )
    monkeypatch.setattr(tasks.asyncpg, "connect", AsyncMock(return_value=connection))
    monkeypatch.setattr(
        tasks,
        "Settings",
        lambda: Settings(database_url="postgresql://test", storage_root=tmp_path),
    )
    monkeypatch.setattr(tasks, "parse_document", lambda _: parsed)

    asyncio.run(tasks._process_document(51))

    assert "document.parse.failed" in _audit_actions(connection.execute_calls)
    audit = next(
        call
        for call in connection.execute_calls
        if "INSERT INTO audit_logs" in call[0] and call[3] == "document.parse.failed"
    )
    assert "DOCUMENT_PARSE_FAILED" in str(audit)
    assert "sensitive parser detail" not in str(audit)


def test_build_worker_records_completed_and_failed_audits(monkeypatch: Any) -> None:
    """构建成功与模型失败都必须形成带创建人归属的明确终态审计。"""
    settings_factory = lambda: Settings(  # noqa: E731 - 测试中需要可替换的零参数配置工厂。
        database_url="postgresql://test",
        model_gateway_api_key="test-key",
        model_gateway_allowed_models="embedding-test",
    )

    completed_connection = BuildWorkerConnection()
    monkeypatch.setattr(builds.asyncpg, "connect", AsyncMock(return_value=completed_connection))
    monkeypatch.setattr(builds, "Settings", settings_factory)
    monkeypatch.setattr(builds, "ModelGatewayClient", SuccessfulModelClient)

    asyncio.run(builds._process_index_build(51))

    assert "build.completed" in _audit_actions(completed_connection.execute_calls)

    failed_connection = BuildWorkerConnection()
    monkeypatch.setattr(builds.asyncpg, "connect", AsyncMock(return_value=failed_connection))
    monkeypatch.setattr(builds, "ModelGatewayClient", FailedModelClient)

    try:
        asyncio.run(builds._process_index_build(52))
    except ValueError as error:
        assert str(error) == "MODEL_NOT_ALLOWED"
    else:
        raise AssertionError("失败构建必须继续抛出原始错误供 Celery 标记任务失败")

    assert "build.failed" in _audit_actions(failed_connection.execute_calls)
