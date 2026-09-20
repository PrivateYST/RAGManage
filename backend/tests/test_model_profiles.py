from typing import Any
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.jobs.tasks import _chunk_blocks
from app.main import create_app
from app.rag.parsing import Block, ParsedDocument


class FakeTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeModelConnection:
    def __init__(
        self,
        *,
        rows: list[dict[str, object]] | None = None,
        fetchrows: list[dict[str, object] | None] | None = None,
    ) -> None:
        self.rows = rows or []
        self.fetchrows = list(fetchrows or [])
        self.execute_calls: list[tuple[Any, ...]] = []
        self.closed = False

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        return self.rows

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if not self.fetchrows:
            raise AssertionError(f"未配置 fetchrow 返回值：{query}")
        return self.fetchrows.pop(0)

    async def execute(self, query: str, *args: object) -> str:
        self.execute_calls.append((query, *args))
        return "OK"

    async def close(self) -> None:
        self.closed = True


def _admin_context() -> dict[str, object]:
    return {"user": {"id": "7", "platform_role": "platform_admin"}, "spaces": []}


def test_model_endpoint_list_never_exposes_secret_reference(monkeypatch: Any) -> None:
    connection = FakeModelConnection(
        rows=[
            {
                "id": "2",
                "name": "内部嵌入网关",
                "allowed_models": '["qwen3-embedding:0.6b"]',
                "secret_ref": "env:MODEL_GATEWAY_API_KEY",
            }
        ]
    )
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=_admin_context()))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))

    with TestClient(create_app(Settings())) as client:
        response = client.get("/api/v1/model-endpoints")

    assert response.status_code == 200
    assert response.json()["items"][0]["allowed_models"] == ["qwen3-embedding:0.6b"]
    assert response.json()["items"][0]["secret_configured"] is True
    assert "secret_ref" not in response.json()["items"][0]


def test_endpoint_creation_rejects_model_outside_gateway_allowlist(monkeypatch: Any) -> None:
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=_admin_context()))

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/model-endpoints",
            json={
                "name": "未知模型网关",
                "provider": "open_webui",
                "endpoint_type": "embedding",
                "base_url": "http://gateway.internal:8080",
                "secret_ref": "env:MODEL_GATEWAY_API_KEY",
                "allowed_models": ["unapproved-model"],
            },
        )

    assert response.status_code == 422
    assert "不在网关白名单" in response.json()["detail"]


def test_embedding_health_check_persists_observed_dimension(monkeypatch: Any) -> None:
    connection = FakeModelConnection(
        fetchrows=[
            {
                "id": 2,
                "endpoint_type": "embedding",
                "base_url": "http://gateway.internal:8080",
                "secret_ref": "env:MODEL_GATEWAY_API_KEY",
                "allowed_models": '["qwen3-embedding:0.6b"]',
                "status": "active",
            }
        ]
    )
    probe = AsyncMock(
        return_value={"model": "qwen3-embedding:0.6b", "dimension": 1024, "latency_ms": 17}
    )
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=_admin_context()))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr("app.main.ModelGatewayClient.probe_embedding", probe)

    with TestClient(create_app(Settings(model_gateway_api_key="test-key"))) as client:
        response = client.post(
            "/api/v1/model-endpoints/2/health-check",
            json={"model_name": "qwen3-embedding:0.6b"},
        )

    assert response.status_code == 200
    assert response.json()["dimension"] == 1024
    assert any("observed_dimension = $3" in call[0] for call in connection.execute_calls)
    assert all("test-key" not in str(call) for call in connection.execute_calls)


def test_non_platform_user_cannot_manage_model_endpoints(monkeypatch: Any) -> None:
    context = {"user": {"id": "8", "platform_role": None}, "spaces": []}
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=context))

    with TestClient(create_app(Settings())) as client:
        response = client.get("/api/v1/model-endpoints")

    assert response.status_code == 403


def test_ingestion_profile_is_immutable_and_reports_reparse_scope(monkeypatch: Any) -> None:
    connection = FakeModelConnection(
        fetchrows=[
            {
                "id": "13",
                "definition": '{"chunking":{"max_chars":1200,"overlap_chars":100}}',
                "definition_hash": "a" * 64,
                "created_at": "2026-09-19T00:00:00Z",
            }
        ]
    )
    access = {"tenant_id": 9, "tenant_role": "space_admin"}
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=_admin_context()))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr("app.main._require_knowledge_base_role", AsyncMock(return_value=access))

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/ingestion-profiles",
            json={
                "knowledge_base_id": 4,
                "max_chars": 1200,
                "overlap_chars": 100,
                "preserve_locator": True,
            },
        )

    assert response.status_code == 201
    assert response.json()["effect_scope"] == "reparse_required"
    assert any("ingestion_profile.create" in call[0] for call in connection.execute_calls)


def test_runtime_activation_marks_embedding_change_as_rebuild_required(monkeypatch: Any) -> None:
    connection = FakeModelConnection(
        fetchrows=[
            {
                "id": 21,
                "tenant_id": 9,
                "knowledge_base_id": 4,
                "embedding_profile_id": 8,
                "definition_hash": "b" * 64,
                "previous_runtime_profile_id": 20,
                "active_release_id": 11,
                "release_embedding_profile_id": 7,
            }
        ]
    )
    access = {"tenant_id": 9, "tenant_role": "space_admin"}
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=_admin_context()))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr("app.main._require_knowledge_base_role", AsyncMock(return_value=access))

    with TestClient(create_app(Settings())) as client:
        response = client.post("/api/v1/runtime-profiles/21/activate")

    assert response.status_code == 200
    assert response.json()["effect_scope"] == "rebuild_required"
    assert any("active_runtime_id = $3" in call[0] for call in connection.execute_calls)
    assert any("runtime_profile.activate" in call[0] for call in connection.execute_calls)


def test_ingestion_profile_chunk_size_and_overlap_are_applied() -> None:
    document = ParsedDocument(
        name="规则.md",
        sha256="hash",
        parser="md:v1",
        blocks=[Block("abcdefghij", ("规则",), {"line_start": 3, "line_end": 3})],
    )

    chunks = _chunk_blocks(
        document,
        {"chunking": {"max_chars": 6, "overlap_chars": 2}},
    )

    assert [item["content"] for item in chunks] == ["abcdef", "efghij"]
    assert chunks[1]["locator"]["chunk_char_start"] == 4
