"""检索范围、证据组装和查询嵌入用量的回归测试。"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.rag.retrieval import _lexical_terms, assemble_evidence, execute_vector_search


class FakeTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeGateway:
    async def model_revision(self, model_name: str | None = None) -> str:
        assert model_name == "qwen3-embedding:0.6b"
        return "revision-1"

    async def embed_with_usage(self, texts: list[str]) -> dict[str, object]:
        """模拟网关同时返回向量和真实输入 Token。"""
        assert texts == ["如何办理出院？"]
        return {
            "embeddings": [[1.0, 0.0, 0.0]],
            "model_name": "qwen3-embedding:0.6b",
            "usage": {
                "prompt_tokens": 6,
                "completion_tokens": 0,
                "total_tokens": 6,
                "usage_source": "gateway",
            },
        }


class FakeRetrievalConnection:
    def __init__(self, *, valid_documents: int = 1, runtime_mismatch: bool = False) -> None:
        self.valid_documents = valid_documents
        self.runtime_mismatch = runtime_mismatch
        self.execute_calls: list[tuple[Any, ...]] = []
        self.search_query = ""
        self.search_args: tuple[object, ...] = ()

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()

    async def fetchval(self, query: str, *args: object) -> int:
        assert "INSERT INTO retrieval_traces" in query
        assert args[:4] == (7, 9, 11, "如何办理出院？")
        return 31

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "FROM kb_releases kr" in query:
            assert args == (5, 7, 9)
            return {
                "id": 5,
                "state": "ready",
                "embedding_profile_id": 4,
                "manifest_hash": "manifest",
                "model_name": "qwen3-embedding:0.6b",
                "model_revision": "revision-1",
                "dimension": 3,
                "embedding_definition_hash": "definition",
                "provider": "open_webui",
                "base_url": "http://gateway.test",
                "endpoint_status": "active",
                "active_runtime_id": 6 if self.runtime_mismatch else None,
                "expected_embedding_profile_id": 8 if self.runtime_mismatch else None,
            }
        if "count(DISTINCT ri.document_id)" in query:
            return {
                "total_documents": 1,
                "valid_documents": self.valid_documents,
                "invalid_documents": 1 - self.valid_documents,
                "valid_chunks": 2 if self.valid_documents else 0,
                "embedded_chunks": 2 if self.valid_documents else 0,
            }
        raise AssertionError(f"未处理的 fetchrow 查询：{query}")

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        self.search_query = query
        self.search_args = args
        return [
            {
                "chunk_id": "21",
                "content": "患者持出院通知单到结算窗口办理。",
                "section_path": '["住院服务", "出院"]',
                "locator": '{"line_start": 18, "line_end": 20}',
                "document_id": "13",
                "document_title": "住院服务指南.md",
                "document_version_id": "17",
                "version_no": 2,
                "similarity": 0.91,
                "vector_rank": 4,
                "lexical_rank": 1,
                "keyword_score": 4,
                "fused_score": 0.032,
                "route": "hybrid",
            },
            {
                "chunk_id": "22",
                "content": "患者持出院通知单到结算窗口办理。",
                "section_path": '["重复内容"]',
                "locator": '{"line_start": 30}',
                "document_id": "13",
                "document_title": "住院服务指南.md",
                "document_version_id": "17",
                "version_no": 2,
                "similarity": 0.87,
                "vector_rank": 5,
                "lexical_rank": None,
                "keyword_score": 0,
                "fused_score": 0.015,
                "route": "vector",
            },
        ]

    async def execute(self, query: str, *args: object) -> None:
        self.execute_calls.append((query, *args))


def test_assemble_evidence_deduplicates_content_and_keeps_locator() -> None:
    items, context = assemble_evidence(
        [
            {
                "chunk_id": "1",
                "content": "同一条规则。",
                "document_title": "规则.md",
                "version_no": 1,
                "section_path": ["办理规则"],
                "locator": {"line_start": 2, "line_end": 3},
            },
            {
                "chunk_id": "2",
                "content": "  同一条规则。 ",
                "document_title": "规则副本.md",
                "version_no": 1,
                "section_path": [],
                "locator": {"line_start": 8},
            },
        ],
        context_max_chars=1000,
    )

    assert len(items) == 1
    assert items[0]["evidence_no"] == 1
    assert items[0]["locator"] == {"line_start": 2, "line_end": 3}
    assert "[证据 1] 规则.md · v1 · 办理规则 · 第 2–3 行" in context


def test_lexical_terms_extracts_chinese_terms_and_latin_model_names() -> None:
    terms = _lexical_terms("当前按钮风格是什么？API Key 怎么配置？")

    assert "按钮" in terms
    assert "风格" in terms
    assert "配置" in terms
    assert "api" in terms
    assert "key" in terms
    assert "当前" not in terms
    assert "什么" not in terms


def test_vector_search_scopes_current_release_and_persists_trace() -> None:
    """成功检索必须先上报嵌入估算，再以网关真实 usage 覆盖并持久化 trace。"""
    connection = FakeRetrievalConnection()
    settings = Settings(
        model_gateway_base_url="http://gateway.test",
        embedding_model="qwen3-embedding:0.6b",
        embedding_dimensions=3,
    )
    observed_usage: list[dict[str, Any]] = []

    async def observe_usage(usage: dict[str, Any], model_name: str) -> None:
        """记录嵌入调用前后的可恢复用量快照。"""
        observed_usage.append({"model": model_name, **usage})

    result = asyncio.run(
        execute_vector_search(
            connection,  # type: ignore[arg-type]
            settings,
            tenant_id=7,
            knowledge_base_id=9,
            user_id=11,
            query="如何办理出院？",
            active_release_id=5,
            top_k=10,
            context_max_chars=2000,
            gateway=FakeGateway(),  # type: ignore[arg-type]
            on_embedding_usage=observe_usage,
        )
    )

    assert result["state"] == "completed"
    assert result["embedding_usage"]["prompt_tokens"] == 6
    assert [item["usage_source"] for item in observed_usage] == ["estimate", "gateway"]
    assert observed_usage[0]["prompt_tokens"] == len("如何办理出院？".encode())
    assert observed_usage[1]["prompt_tokens"] == 6
    assert result["trace_id"] == "31"
    assert len(result["items"]) == 1
    assert result["items"][0]["document_title"] == "住院服务指南.md"
    assert result["items"][0]["locator"] == {"line_start": 18, "line_end": 20}
    assert result["items"][0]["route"] == "hybrid"
    assert result["items"][0]["lexical_rank"] == 1
    assert connection.search_args[:4] == (5, 7, 9, 4)
    assert "办理" in connection.search_args[6]
    assert "出院" in connection.search_args[6]
    assert connection.search_args[7] == 60
    assert "ri.release_id = $1" in connection.search_query
    assert "ri.tenant_id = $2" in connection.search_query
    assert "ri.knowledge_base_id = $3" in connection.search_query
    assert "d.status = 'active'" in connection.search_query
    assert "fused_score" in connection.search_query
    assert any("INSERT INTO retrieval_trace_items" in call[0] for call in connection.execute_calls)
    assert any("UPDATE retrieval_traces" in call[0] for call in connection.execute_calls)


def test_vector_search_reports_invalid_sources_without_calling_gateway() -> None:
    connection = FakeRetrievalConnection(valid_documents=0)
    settings = Settings(
        model_gateway_base_url="http://gateway.test",
        embedding_model="qwen3-embedding:0.6b",
        embedding_dimensions=3,
    )

    result = asyncio.run(
        execute_vector_search(
            connection,  # type: ignore[arg-type]
            settings,
            tenant_id=7,
            knowledge_base_id=9,
            user_id=11,
            query="如何办理出院？",
            active_release_id=5,
            top_k=10,
            context_max_chars=2000,
            gateway=FakeGateway(),  # type: ignore[arg-type]
        )
    )

    assert result["state"] == "sources_invalid"
    assert result["items"] == []
    assert connection.search_query == ""


def test_vector_search_requires_new_release_after_embedding_profile_change() -> None:
    connection = FakeRetrievalConnection(runtime_mismatch=True)
    settings = Settings(
        model_gateway_base_url="http://gateway.test",
        embedding_model="qwen3-embedding:0.6b",
        embedding_dimensions=3,
    )

    result = asyncio.run(
        execute_vector_search(
            connection,  # type: ignore[arg-type]
            settings,
            tenant_id=7,
            knowledge_base_id=9,
            user_id=11,
            query="如何办理出院？",
            active_release_id=5,
            top_k=10,
            context_max_chars=2000,
            gateway=FakeGateway(),  # type: ignore[arg-type]
        )
    )

    assert result["state"] == "index_not_ready"
    assert "重新构建并发布" in result["message"]
    assert connection.search_query == ""


def test_search_test_requires_knowledge_base_access(monkeypatch: Any) -> None:
    connection = AsyncMock()
    connection.close = AsyncMock()
    context = {"user": {"id": "11"}}
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=context))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    access = AsyncMock(side_effect=HTTPException(status_code=404, detail="知识库不存在"))
    monkeypatch.setattr("app.main._knowledge_base_access", access)

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/search-test",
            json={"knowledge_base_id": 99, "query": "测试"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "知识库不存在"
    access.assert_awaited_once()
    assert connection.close.await_count == 1


def test_search_test_rejects_whitespace_only_query() -> None:
    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/search-test",
            json={"knowledge_base_id": 9, "query": "   "},
        )

    assert response.status_code == 422
