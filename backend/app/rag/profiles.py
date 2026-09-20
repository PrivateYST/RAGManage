from __future__ import annotations

import hashlib
import json
from typing import Any

from app.core.config import Settings


def embedding_profile_definition(settings: Settings, model_revision: str) -> dict[str, Any]:
    """生成可哈希、可审计的嵌入配置快照。"""
    return {
        "provider": "open_webui",
        "upstream_provider": "ollama",
        "base_url": settings.model_gateway_base_url.rstrip("/"),
        "secret_ref": "env:MODEL_GATEWAY_API_KEY",
        "model": settings.embedding_model,
        "model_revision": model_revision,
        "dimension": settings.embedding_dimensions,
        "dtype": "float32",
        "normalization": "l2",
        "instructions": {},
    }


def profile_hash(definition: dict[str, Any]) -> str:
    encoded = json.dumps(definition, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def gateway_settings(
    settings: Settings,
    *,
    base_url: str,
    allowed_models: list[str],
    embedding_model: str | None = None,
    embedding_dimensions: int | None = None,
    generation_model: str | None = None,
) -> Settings:
    """从不可变 Profile 生成一次调用使用的网关配置，密钥仍取自环境变量。"""
    updates: dict[str, Any] = {
        "model_gateway_base_url": base_url.rstrip("/"),
        "model_gateway_allowed_models": ",".join(allowed_models),
    }
    if embedding_model is not None:
        updates["embedding_model"] = embedding_model
    if embedding_dimensions is not None:
        updates["embedding_dimensions"] = embedding_dimensions
    if generation_model is not None:
        updates["generation_model"] = generation_model
    return settings.model_copy(update=updates)
