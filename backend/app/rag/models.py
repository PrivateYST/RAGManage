from __future__ import annotations

import json
import math
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config import Settings


class ModelGatewayClient:
    """使用 API Key 调用内部模型网关，不直接访问 Ollama。"""

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport

    def _headers(self) -> dict[str, str]:
        api_key = self.settings.model_gateway_api_key.get_secret_value()
        if not api_key:
            raise ValueError("MODEL_GATEWAY_API_KEY_NOT_CONFIGURED")
        return {"Authorization": f"Bearer {api_key}"}

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=timeout,
            headers=self._headers(),
            transport=self.transport,
        )

    async def probe_generation(self, base_url: str, model_name: str) -> dict[str, Any]:
        """执行一次最小非流式生成，确认网关鉴权、白名单和模型均可用。"""
        started = time.perf_counter()
        async with self._client(timeout=60) as client:
            response = await client.post(
                f"{base_url.rstrip('/')}/api/chat/completions",
                json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": "仅回复 OK"}],
                    "stream": False,
                    "temperature": 0,
                    "max_tokens": 8,
                },
            )
            response.raise_for_status()
        payload = response.json()
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not isinstance(choices, list) or not choices:
            raise ValueError("INVALID_CHAT_RESPONSE")
        return {
            "model": model_name,
            "latency_ms": round((time.perf_counter() - started) * 1000),
        }

    async def probe_embedding(self, base_url: str, model_name: str) -> dict[str, Any]:
        """执行一次单文本嵌入并返回实测维度，不依赖预设维度。"""
        started = time.perf_counter()
        async with self._client(timeout=60) as client:
            response = await client.post(
                f"{base_url.rstrip('/')}/api/embeddings",
                json={"model": model_name, "input": ["RAGManage 模型连通性检查"]},
            )
            response.raise_for_status()
        values = openai_embedding_values(response.json(), 1)
        vector = values[0]
        if not isinstance(vector, list) or not vector:
            raise ValueError("INVALID_EMBEDDING_RESPONSE")
        if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in vector):
            raise ValueError("INVALID_EMBEDDING_VALUE")
        return {
            "model": model_name,
            "dimension": len(vector),
            "latency_ms": round((time.perf_counter() - started) * 1000),
        }

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts or any(not text.strip() for text in texts):
            raise ValueError("EMPTY_EMBEDDING_INPUT")
        if self.settings.embedding_model not in self.settings.allowed_model_names:
            raise ValueError("MODEL_NOT_ALLOWED")
        async with self._client(timeout=120) as client:
            response = await client.post(
                f"{self.settings.model_gateway_base_url.rstrip('/')}/api/embeddings",
                json={"model": self.settings.embedding_model, "input": texts},
            )
            response.raise_for_status()
            return validate_embeddings(
                openai_embedding_values(response.json(), len(texts)),
                len(texts),
                self.settings.embedding_dimensions,
            )

    async def model_revision(
        self,
        model_name: str | None = None,
        base_url: str | None = None,
    ) -> str:
        """返回 Ollama 模型内容摘要，确保构建快照能识别模型实际变化。"""
        expected_name = model_name or self.settings.embedding_model
        async with self._client(timeout=15) as client:
            response = await client.get(
                f"{(base_url or self.settings.model_gateway_base_url).rstrip('/')}/ollama/api/tags"
            )
            response.raise_for_status()
        models = response.json().get("models")
        if not isinstance(models, list):
            raise ValueError("INVALID_MODEL_LIST")
        for model in models:
            if not isinstance(model, dict) or model.get("name") != expected_name:
                continue
            digest = model.get("digest")
            if isinstance(digest, str) and digest:
                return digest
        raise ValueError("MODEL_NOT_FOUND")

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        """通过 OpenAI 兼容网关流式返回生成文本，不向上层暴露模型来源字段。"""
        if not messages or any(not item.get("content", "").strip() for item in messages):
            raise ValueError("EMPTY_CHAT_MESSAGES")
        if self.settings.generation_model not in self.settings.allowed_model_names:
            raise ValueError("MODEL_NOT_ALLOWED")
        async with self._client(timeout=180) as client:
            async with client.stream(
                "POST",
                f"{self.settings.model_gateway_base_url.rstrip('/')}/api/chat/completions",
                json={
                    "model": self.settings.generation_model,
                    "messages": messages,
                    "stream": True,
                    "temperature": temperature,
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if not payload or payload == "[DONE]":
                        continue
                    try:
                        data: Any = json.loads(payload)
                    except json.JSONDecodeError as error:
                        raise ValueError("INVALID_CHAT_STREAM") from error
                    choices = data.get("choices") if isinstance(data, dict) else None
                    if not isinstance(choices, list) or not choices:
                        continue
                    choice = choices[0]
                    delta = choice.get("delta") if isinstance(choice, dict) else None
                    content = delta.get("content") if isinstance(delta, dict) else None
                    if isinstance(content, str) and content:
                        yield content


def openai_embedding_values(payload: object, count: int) -> list[object]:
    """按 OpenAI 响应中的 index 恢复输入顺序，并拒绝缺项或重复项。"""
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("INVALID_EMBEDDING_RESPONSE")
    data = payload["data"]
    if len(data) != count:
        raise ValueError("EMBEDDING_COUNT_MISMATCH")
    ordered: list[object | None] = [None] * count
    for position, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError("INVALID_EMBEDDING_RESPONSE")
        index = item.get("index", position)
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < count:
            raise ValueError("INVALID_EMBEDDING_INDEX")
        if ordered[index] is not None:
            raise ValueError("DUPLICATE_EMBEDDING_INDEX")
        ordered[index] = item.get("embedding")
    if any(value is None for value in ordered):
        raise ValueError("EMBEDDING_COUNT_MISMATCH")
    return [value for value in ordered if value is not None]


def validate_embeddings(value: object, count: int, dimensions: int) -> list[list[float]]:
    if not isinstance(value, list) or len(value) != count:
        raise ValueError("EMBEDDING_COUNT_MISMATCH")
    result = []
    for row in value:
        if not isinstance(row, list) or len(row) != dimensions:
            raise ValueError("EMBEDDING_DIMENSION_MISMATCH")
        if any(isinstance(x, bool) or not isinstance(x, (float, int)) for x in row):
            raise ValueError("INVALID_EMBEDDING_VALUE")
        vector = [float(x) for x in row]
        if not all(math.isfinite(x) for x in vector):
            raise ValueError("NONFINITE_EMBEDDING")
        norm = math.hypot(*vector)
        if not math.isfinite(norm) or norm == 0:
            raise ValueError("INVALID_EMBEDDING_NORM")
        result.append([x / norm for x in vector])
    return result
