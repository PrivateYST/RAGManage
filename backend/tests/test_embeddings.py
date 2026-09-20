import asyncio
import math

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.rag.models import ModelGatewayClient, openai_embedding_values, validate_embeddings


@pytest.mark.parametrize(
    "value", [None, [], [[1]], [[0, 0]], [[math.nan, 1]], [[math.inf, 1]], [[True, 1]], [["1", 1]]]
)
def test_bad_embedding_is_rejected(value: object) -> None:
    with pytest.raises(ValueError):
        validate_embeddings(value, 1, 2)


def test_normalization() -> None:
    assert validate_embeddings([[3, 4]], 1, 2) == [[0.6, 0.8]]


def test_openai_embedding_response_is_restored_by_index() -> None:
    payload = {
        "data": [
            {"index": 1, "embedding": [0.0, 1.0]},
            {"index": 0, "embedding": [1.0, 0.0]},
        ]
    }
    assert openai_embedding_values(payload, 2) == [[1.0, 0.0], [0.0, 1.0]]


def test_model_client_sends_bearer_key_to_open_webui_gateway() -> None:
    seen_path = ""
    seen_authorization = ""

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_path, seen_authorization
        seen_path = request.url.path
        seen_authorization = request.headers.get("authorization", "")
        return httpx.Response(
            200,
            json={"models": [{"name": "qwen3-embedding:0.6b", "digest": "revision-value"}]},
        )

    settings = Settings(
        model_gateway_base_url="http://open-webui.internal",
        model_gateway_api_key=SecretStr("gateway-secret"),
    )
    client = ModelGatewayClient(settings, transport=httpx.MockTransport(handler))
    revision = asyncio.run(client.model_revision())

    assert revision == "revision-value"
    assert seen_path == "/ollama/api/tags"
    assert seen_authorization == "Bearer gateway-secret"


def test_model_client_streams_openai_chat_chunks() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat/completions"
        assert request.headers["authorization"] == "Bearer gateway-secret"
        return httpx.Response(
            200,
            content=(
                'data: {"choices":[{"delta":{"content":"办理"}}]}\n\n'
                'data: {"choices":[{"delta":{"content":"完成 [证据 1]"}}]}\n\n'
                "data: [DONE]\n\n"
            ).encode(),
            headers={"content-type": "text/event-stream"},
        )

    async def collect() -> list[str]:
        settings = Settings(
            model_gateway_base_url="http://open-webui.internal",
            model_gateway_api_key=SecretStr("gateway-secret"),
        )
        client = ModelGatewayClient(settings, transport=httpx.MockTransport(handler))
        return [token async for token in client.stream_chat([{"role": "user", "content": "问题"}])]

    assert asyncio.run(collect()) == ["办理", "完成 [证据 1]"]
