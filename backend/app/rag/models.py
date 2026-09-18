from __future__ import annotations

import math

import httpx

from app.core.config import Settings


class OllamaClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts or any(not text.strip() for text in texts):
            raise ValueError("EMPTY_EMBEDDING_INPUT")
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.settings.ollama_base_url}/api/embed",
                json={"model": self.settings.embedding_model, "input": texts, "truncate": False},
            )
            response.raise_for_status()
            return validate_embeddings(
                response.json().get("embeddings"),
                len(texts),
                self.settings.embedding_dimensions,
            )


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
