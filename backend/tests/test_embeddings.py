"""模型网关嵌入响应、Token 用量和向量校验测试。"""

import asyncio
import json
import math

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.rag.models import (
    ModelGatewayClient,
    estimate_token_count,
    normalize_embedding_usage,
    openai_embedding_values,
    validate_embeddings,
)


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


def test_model_client_emits_gateway_usage_tail_frame() -> None:
    """Open WebUI 最终 usage 帧必须原样进入结算事件，不能退回本地估算。"""

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["stream_options"] == {"include_usage": True}
        return httpx.Response(
            200,
            content=(
                'data: {"choices":[{"delta":{"content":"答案"}}]}\n\n'
                'data: {"choices":[],"usage":{"prompt_tokens":17,'
                '"completion_tokens":4,"total_tokens":21}}\n\n'
                "data: [DONE]\n\n"
            ).encode(),
            headers={"content-type": "text/event-stream"},
        )

    async def collect() -> list[dict[str, object]]:
        settings = Settings(
            model_gateway_base_url="http://open-webui.internal",
            model_gateway_api_key=SecretStr("gateway-secret"),
        )
        client = ModelGatewayClient(settings, transport=httpx.MockTransport(handler))
        return [
            event
            async for event in client.stream_chat_events(
                [{"role": "user", "content": "问题"}]
            )
        ]

    assert asyncio.run(collect()) == [
        {"text": "答案", "usage": None},
        {
            "text": "",
            "usage": {"prompt_tokens": 17, "completion_tokens": 4, "total_tokens": 21},
        },
    ]


def test_embedding_usage_is_read_from_gateway_response() -> None:
    """嵌入接口返回 usage 时必须使用真实输入 Token，而不是字符估算。"""
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/embeddings"
        return httpx.Response(
            200,
            json={
                "data": [{"index": 0, "embedding": [3.0, 4.0]}],
                "usage": {"prompt_tokens": 7, "total_tokens": 7},
            },
        )

    settings = Settings(
        model_gateway_base_url="http://open-webui.internal",
        model_gateway_api_key=SecretStr("gateway-secret"),
        embedding_dimensions=2,
    )
    result = asyncio.run(
        ModelGatewayClient(settings, transport=httpx.MockTransport(handler)).embed_with_usage(
            ["查询"]
        )
    )

    assert result["embeddings"] == [[0.6, 0.8]]
    assert result["usage"] == {
        "prompt_tokens": 7,
        "completion_tokens": 0,
        "total_tokens": 7,
        "usage_source": "gateway",
    }


def test_invalid_embedding_usage_is_rejected_for_billing() -> None:
    """负数或布尔值 usage 不能进入额度结算。"""
    assert normalize_embedding_usage({"prompt_tokens": -1, "total_tokens": -1}) is None
    assert normalize_embedding_usage({"prompt_tokens": True, "total_tokens": 1}) is None


def test_fallback_token_estimate_is_conservative_for_chinese() -> None:
    """网关缺失 usage 时，中文不能继续按四字符一个 Token 的英文经验低估。"""
    assert estimate_token_count("如何办理出院？") == len("如何办理出院？".encode())
