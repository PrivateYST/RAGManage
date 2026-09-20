from app.core.config import Settings
from app.jobs.builds import _vector_literal
from app.jobs.outbox import _payload_dict
from app.rag.profiles import embedding_profile_definition, profile_hash


def test_vector_literal_uses_pgvector_format() -> None:
    assert _vector_literal([0.6, -0.8, 0.0]) == "[0.6,-0.8,0]"


def test_outbox_payload_accepts_asyncpg_json_string() -> None:
    assert _payload_dict('{"task_id":"7"}') == {"task_id": "7"}
    assert _payload_dict(["invalid"]) == {}


def test_embedding_profile_hash_changes_with_model_revision() -> None:
    settings = Settings(
        model_gateway_base_url="http://open-webui.internal/",
        embedding_model="qwen3-embedding:0.6b",
        embedding_dimensions=1024,
    )
    first = embedding_profile_definition(settings, "revision-a")
    second = embedding_profile_definition(settings, "revision-b")

    assert first["provider"] == "open_webui"
    assert first["base_url"] == "http://open-webui.internal"
    assert first["secret_ref"] == "env:MODEL_GATEWAY_API_KEY"
    assert "gateway-secret" not in str(first)
    assert first["dimension"] == 1024
    assert profile_hash(first) != profile_hash(second)
