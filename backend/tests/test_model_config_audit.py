"""验证模型端点与三类不可变 Profile 的配置审计、作用域和敏感字段边界。"""

import json
from typing import Any
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


class FakeTransaction:
    """提供配置接口测试所需的异步事务协议。"""

    async def __aenter__(self) -> None:
        """进入无副作用测试事务。"""
        return None

    async def __aexit__(self, *args: object) -> None:
        """退出测试事务并保留原始接口异常。"""
        return None


class ModelConfigAuditConnection:
    """按 SQL 意图返回模型配置记录，并保存审计写调用用于断言。"""

    def __init__(self) -> None:
        """初始化写调用列表和关闭状态。"""
        self.execute_calls: list[tuple[Any, ...]] = []
        self.closed = False

    def transaction(self) -> FakeTransaction:
        """返回测试事务上下文。"""
        return FakeTransaction()

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        """返回端点前后状态、端点依赖或新建 Profile。"""
        if "INSERT INTO model_endpoints" in query:
            return {
                "id": "2",
                "tenant_id": None,
                "name": "模型网关",
                "provider": "open_webui",
                "endpoint_type": "embedding",
                "base_url": "http://gateway.internal:8080",
                "allowed_models": '["qwen3-embedding:0.6b"]',
                "health_status": "unknown",
                "status": "active",
                "last_checked_at": None,
                "last_latency_ms": None,
                "last_error": None,
                "observed_dimension": None,
                "created_at": "2026-09-20T00:00:00Z",
                "updated_at": "2026-09-20T00:00:00Z",
            }
        if "FROM model_endpoints WHERE id = $1 FOR UPDATE" in query:
            return {
                "id": 2,
                "name": "旧网关",
                "base_url": "http://gateway.internal:8080",
                "allowed_models": '["qwen3-embedding:0.6b"]',
                "status": "active",
                "secret_ref": "env:MODEL_GATEWAY_API_KEY",
            }
        if "UPDATE model_endpoints" in query and "RETURNING" in query:
            return {
                "id": "2",
                "tenant_id": None,
                "name": "新网关",
                "provider": "open_webui",
                "endpoint_type": "embedding",
                "base_url": "http://gateway.internal:8080",
                "allowed_models": '["qwen3-embedding:0.6b"]',
                "health_status": "unknown",
                "status": "active",
                "last_checked_at": None,
                "last_latency_ms": None,
                "last_error": None,
                "observed_dimension": None,
                "created_at": "2026-09-20T00:00:00Z",
                "updated_at": "2026-09-20T00:01:00Z",
            }
        if "FROM model_endpoints WHERE id = $1" in query:
            return {
                "id": 2,
                "name": "模型网关",
                "endpoint_type": "embedding",
                "base_url": "http://gateway.internal:8080",
                "secret_ref": "env:MODEL_GATEWAY_API_KEY",
                "allowed_models": '["qwen3-embedding:0.6b"]',
                "status": "active",
                "health_status": "healthy",
            }
        if "INSERT INTO embedding_profiles" in query:
            return {
                "id": "8",
                "model_endpoint_id": "2",
                "model_name": "qwen3-embedding:0.6b",
                "model_revision": "revision-a",
                "dimension": 1024,
                "dtype": "float32",
                "instructions": "{}",
                "normalization": "l2",
                "definition_hash": "e" * 64,
                "created_at": "2026-09-20T00:00:00Z",
            }
        if "SELECT ep.id, ep.model_name" in query:
            return {
                "id": 8,
                "model_name": "qwen3-embedding:0.6b",
                "dimension": 1024,
                "endpoint_status": "active",
            }
        if "endpoint_type = 'generation'" in query:
            return {
                "id": 3,
                "name": "生成网关",
                "allowed_models": '["qwen3.8:27b"]',
                "status": "active",
            }
        if "INSERT INTO runtime_profiles" in query:
            return {
                "id": "21",
                "embedding_profile_id": "8",
                "definition": "{}",
                "definition_hash": "r" * 64,
                "created_at": "2026-09-20T00:00:00Z",
            }
        raise AssertionError(f"未处理的 fetchrow 查询：{query}")

    async def execute(self, query: str, *args: object) -> str:
        """记录配置与审计写调用。"""
        self.execute_calls.append((query, *args))
        return "OK"

    async def close(self) -> None:
        """标记测试连接已关闭。"""
        self.closed = True


def _admin_context() -> dict[str, Any]:
    """返回具有平台和空间配置权限的最小认证上下文。"""
    return {"user": {"id": "7", "platform_role": "platform_admin"}, "spaces": []}


def _audit_call(connection: ModelConfigAuditConnection, action: str) -> tuple[Any, ...]:
    """从数据库写调用中取得指定配置审计事件。"""
    return next(
        call
        for call in connection.execute_calls
        if "INSERT INTO audit_logs" in call[0] and action in call[0]
    )


def test_model_endpoint_create_and_update_audits_exclude_secret_values(
    monkeypatch: Any,
) -> None:
    """端点登记和更新应可追踪安全字段，但不得记录 API Key 或密钥引用值。"""
    connection = ModelConfigAuditConnection()
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=_admin_context()))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    settings = Settings(
        model_gateway_allowed_models="qwen3-embedding:0.6b",
        model_gateway_api_key="never-audit-this-key",
    )

    with TestClient(create_app(settings)) as client:
        created = client.post(
            "/api/v1/model-endpoints",
            json={
                "name": "模型网关",
                "provider": "open_webui",
                "endpoint_type": "embedding",
                "base_url": "http://gateway.internal:8080",
                "secret_ref": "env:MODEL_GATEWAY_API_KEY",
                "allowed_models": ["qwen3-embedding:0.6b"],
            },
        )
        updated = client.patch(
            "/api/v1/model-endpoints/2",
            json={
                "name": "新网关",
                "secret_ref": "env:MODEL_GATEWAY_API_KEY",
            },
        )

    assert created.status_code == 201
    assert updated.status_code == 200
    create_audit = _audit_call(connection, "model_endpoint.create")
    update_audit = _audit_call(connection, "model_endpoint.update")
    update_summary = json.loads(update_audit[3])
    assert update_summary["before"] == {"name": "旧网关"}
    assert update_summary["after"] == {"name": "新网关"}
    assert update_summary["secret_ref_changed"] is True
    assert "env:MODEL_GATEWAY_API_KEY" not in str(create_audit) + str(update_audit)
    assert "never-audit-this-key" not in str(connection.execute_calls)


def test_embedding_profile_audit_records_rebuild_scope_without_instructions(
    monkeypatch: Any,
) -> None:
    """嵌入 Profile 审计应记录实测版本和维度，但不保存查询或文档指令正文。"""
    connection = ModelConfigAuditConnection()
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=_admin_context()))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr(
        "app.main.ModelGatewayClient.probe_embedding",
        AsyncMock(return_value={"dimension": 1024, "latency_ms": 12}),
    )
    monkeypatch.setattr(
        "app.main.ModelGatewayClient.model_revision",
        AsyncMock(return_value="revision-a"),
    )

    with TestClient(create_app(Settings(model_gateway_api_key="test-key"))) as client:
        response = client.post(
            "/api/v1/embedding-profiles",
            json={
                "model_endpoint_id": 2,
                "model_name": "qwen3-embedding:0.6b",
                "expected_dimension": 1024,
                "normalization": "l2",
                "query_instruction": "private query instruction",
                "document_instruction": "private document instruction",
            },
        )

    assert response.status_code == 201
    audit = _audit_call(connection, "embedding_profile.create")
    summary = json.loads(audit[3])
    assert summary["model_revision"] == "revision-a"
    assert summary["dimension"] == 1024
    assert summary["effect_scope"] == "rebuild_required"
    assert "private query instruction" not in str(audit)
    assert "private document instruction" not in str(audit)


def test_runtime_profile_audit_is_tenant_scoped_and_excludes_answer_rules(
    monkeypatch: Any,
) -> None:
    """Runtime Profile 事件应归属知识库空间，并只保存引用、哈希与待激活影响。"""
    connection = ModelConfigAuditConnection()
    access = {"tenant_id": 9, "tenant_role": "space_admin"}
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=_admin_context()))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr(
        "app.main._require_knowledge_base_role",
        AsyncMock(return_value=access),
    )

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/runtime-profiles",
            json={
                "knowledge_base_id": 4,
                "embedding_profile_id": 8,
                "generation_endpoint_id": 3,
                "generation_model": "qwen3.8:27b",
                "top_k": 10,
                "context_max_chars": 8000,
                "temperature": 0.2,
                "answer_rules": "private answer rules",
            },
        )

    assert response.status_code == 201
    audit = _audit_call(connection, "runtime_profile.create")
    assert audit[1:3] == (9, 7)
    summary = json.loads(audit[4])
    assert summary["knowledge_base_id"] == "4"
    assert summary["embedding_profile_id"] == "8"
    assert summary["effect_scope"] == "activate_required"
    assert "private answer rules" not in str(audit)
