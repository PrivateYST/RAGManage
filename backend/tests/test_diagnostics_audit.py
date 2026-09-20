"""验证管理员诊断操作的审计闭环、租户范围和敏感信息边界。"""

import json
from typing import Any
from unittest.mock import AsyncMock

import httpx
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.rag.retrieval import RetrievalServiceError


class DiagnosticConnection:
    """为诊断接口提供最小数据库协议，并保留审计写入供断言。"""

    def __init__(self) -> None:
        """初始化端点数据和 SQL 调用记录。"""
        self.execute_calls: list[tuple[Any, ...]] = []
        self.closed = False

    def transaction(self) -> "FakeTransaction":
        """返回无副作用事务上下文，覆盖健康状态与审计的原子写入。"""
        return FakeTransaction()

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        """返回健康检查所需的平台模型端点，其他查询视为测试配置错误。"""
        if "FROM model_endpoints WHERE id = $1" in query:
            return {
                "id": 2,
                "endpoint_type": "embedding",
                "base_url": "http://gateway.test",
                "secret_ref": "env:MODEL_GATEWAY_API_KEY",
                "allowed_models": '["qwen3-embedding:0.6b"]',
                "status": "active",
            }
        raise AssertionError(f"未处理的 fetchrow 查询：{query}")

    async def execute(self, query: str, *args: object) -> str:
        """记录健康状态更新和审计写入，模拟 asyncpg execute。"""
        self.execute_calls.append((query, *args))
        return "OK"

    async def close(self) -> None:
        """标记连接已关闭，验证接口始终释放资源。"""
        self.closed = True


class FakeTransaction:
    """实现诊断测试需要的异步事务协议。"""

    async def __aenter__(self) -> None:
        """进入无副作用的测试事务。"""
        return None

    async def __aexit__(self, *args: object) -> None:
        """退出事务并保留接口产生的原始异常。"""
        return None


def _admin_context() -> dict[str, Any]:
    """返回能够执行平台诊断的最小认证上下文。"""
    return {"user": {"id": "7", "platform_role": "platform_admin"}, "spaces": []}


def _audit_summaries(connection: DiagnosticConnection, action: str) -> list[dict[str, Any]]:
    """提取指定动作的 JSON 摘要，集中断言审计边界。"""
    return [
        json.loads(str(call[-1]))
        for call in connection.execute_calls
        if "INSERT INTO audit_logs" in call[0] and (action in call[0] or action in call)
    ]


def test_model_health_check_success_audits_latency_and_dimension(monkeypatch: Any) -> None:
    """成功探测必须记录健康状态、耗时和维度，但不记录网关响应正文。"""
    connection = DiagnosticConnection()
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=_admin_context()))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr(
        "app.main.ModelGatewayClient.probe_embedding",
        AsyncMock(return_value={"dimension": 1024, "latency_ms": 18}),
    )

    with TestClient(create_app(Settings(model_gateway_api_key="secret-key"))) as client:
        response = client.post(
            "/api/v1/model-endpoints/2/health-check",
            json={"model_name": "qwen3-embedding:0.6b"},
        )

    assert response.status_code == 200
    summaries = _audit_summaries(connection, "model_endpoint.health_check")
    assert summaries == [
        {
            "model": "qwen3-embedding:0.6b",
            "status": "healthy",
            "latency_ms": 18,
            "dimension": 1024,
        }
    ]
    assert "secret-key" not in str(connection.execute_calls)


def test_model_health_check_failure_audits_stable_error_without_gateway_details(
    monkeypatch: Any,
) -> None:
    """探测失败也必须审计稳定错误码，并隐藏 API Key 和网关错误正文。"""
    connection = DiagnosticConnection()
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=_admin_context()))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr(
        "app.main.ModelGatewayClient.probe_embedding",
        AsyncMock(side_effect=httpx.ConnectError("gateway response contains secret-key")),
    )

    with TestClient(create_app(Settings(model_gateway_api_key="secret-key"))) as client:
        response = client.post(
            "/api/v1/model-endpoints/2/health-check",
            json={"model_name": "qwen3-embedding:0.6b"},
        )

    assert response.status_code == 200
    summaries = _audit_summaries(connection, "model_endpoint.health_check")
    assert summaries[0]["status"] == "unhealthy"
    assert summaries[0]["error_code"] == "ConnectError"
    assert "secret-key" not in str(connection.execute_calls)


def test_model_health_check_rejects_non_platform_user_without_database_access(
    monkeypatch: Any,
) -> None:
    """普通空间成员不能发起平台模型诊断，拒绝请求时不得读取端点或写审计。"""
    connection = DiagnosticConnection()
    context = {"user": {"id": "12", "platform_role": None}}
    database = AsyncMock(return_value=connection)
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=context))
    monkeypatch.setattr("app.main._database", database)

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/model-endpoints/2/health-check",
            json={"model_name": "qwen3-embedding:0.6b"},
        )

    assert response.status_code == 403
    database.assert_not_awaited()
    assert connection.execute_calls == []


def test_search_test_audits_result_without_query_or_document_text(monkeypatch: Any) -> None:
    """检索调试按空间写入 trace 状态和统计，不能保存问题或候选正文。"""
    connection = DiagnosticConnection()
    context = {"user": {"id": "11", "platform_role": None}}
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=context))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr(
        "app.main._knowledge_base_access",
        AsyncMock(return_value={"tenant_id": 7, "active_release_id": 5}),
    )
    monkeypatch.setattr(
        "app.main.execute_vector_search",
        AsyncMock(
            return_value={
                "trace_id": "31",
                "state": "completed",
                "items": [{"content": "敏感候选正文"}],
                "timings": {"total_ms": 12.5},
            }
        ),
    )

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/search-test",
            json={"knowledge_base_id": 9, "query": "包含敏感提问的内容"},
        )

    assert response.status_code == 200
    summaries = _audit_summaries(connection, "search_test.run")
    assert summaries == [
        {
            "knowledge_base_id": "9",
            "trace_id": "31",
            "state": "completed",
            "item_count": 1,
            "total_ms": 12.5,
        }
    ]
    assert "包含敏感提问的内容" not in str(connection.execute_calls)
    assert "敏感候选正文" not in str(connection.execute_calls)


def test_search_test_gateway_failure_audits_safe_terminal_state(monkeypatch: Any) -> None:
    """检索网关失败必须保留可查询终态，同时隐藏用户提问和底层异常详情。"""
    connection = DiagnosticConnection()
    context = {"user": {"id": "11", "platform_role": None}}
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=context))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr(
        "app.main._knowledge_base_access",
        AsyncMock(return_value={"tenant_id": 7, "active_release_id": 5}),
    )
    monkeypatch.setattr(
        "app.main.execute_vector_search",
        AsyncMock(side_effect=RetrievalServiceError("包含敏感网关详情", trace_id=41)),
    )

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/search-test",
            json={"knowledge_base_id": 9, "query": "不能写入日志的提问"},
        )

    assert response.status_code == 502
    summaries = _audit_summaries(connection, "search_test.run")
    assert summaries[0]["state"] == "failed"
    assert summaries[0]["error_code"] == "RETRIEVAL_SERVICE_ERROR"
    assert summaries[0]["trace_id"] == "41"
    assert "不能写入日志的提问" not in str(connection.execute_calls)
    assert "包含敏感网关详情" not in str(connection.execute_calls)
