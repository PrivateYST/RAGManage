"""RAGManage HTTP API 入口，负责认证、租户业务接口与事务边界编排。"""

# 路由模块通过内部导出表复用这些符号；其余规则仍由 Ruff 检查。
# ruff: noqa: F401,I001,F841

import hashlib
import json
import logging
import secrets
import time
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, date, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Annotated, Any, cast
from urllib.parse import urlparse
from uuid import UUID, uuid4

import asyncpg
import httpx
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from redis.asyncio import Redis
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.api_keys import decrypt_api_key, encrypt_api_key, generate_api_key, hash_api_key
from app.core.audit import write_audit_event
from app.core.auth import (
    SESSION_COOKIE,
    authenticate,
    load_user_from_api_key,
    load_user_from_token,
    password_hasher,
    revoke_token,
)
from app.core.config import Settings
from app.core.health import check_dependencies, collect_runtime_metrics
from app.core.runtime_settings import (
    LEGACY_MODEL_GATEWAY_SECRET_REF,
    MODEL_GATEWAY_SECRET_REF,
    load_persisted_model_gateway_key,
    persist_model_gateway_key,
)
from app.core.security import (
    ManagementRateLimitMiddleware,
    RequestIDMiddleware,
    SessionCsrfMiddleware,
    StructuredRequestLoggingMiddleware,
    finish_login_attempt,
    login_client_ip,
    reserve_login_attempt,
    session_csrf_token,
)
from app.integrations.open_webui import OpenWebUIAdminClient, OpenWebUIProvisioningError
from app.rag.chat import load_run_snapshot, stream_generation_run
from app.rag.models import ModelGatewayClient
from app.rag.parsing import validate_document_container
from app.rag.profiles import embedding_profile_definition, gateway_settings, profile_hash
from app.rag.releases import release_diff, release_manifest_hash, rollback_candidate_ids
from app.rag.retrieval import RetrievalServiceError, execute_vector_search

ALLOWED_DOCUMENT_TYPES = {
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
}
# Markdown 在浏览器与常见 HTTP 客户端中可能以 text/plain 声明；其他类型使用规范 MIME。
ALLOWED_DOCUMENT_MIME_TYPES = {
    ".md": {"text/markdown", "text/plain"},
    ".txt": {"text/plain"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".pdf": {"application/pdf"},
}
MAX_DOCUMENT_SIZE = 50 * 1024 * 1024
# 管理页只加载最近流水，累计值始终由数据库对全部记录聚合。
API_KEY_USAGE_RECENT_LIMIT = 200
OPENAI_CHAT_REQUEST_MAX_BYTES = 1024 * 1024
# OpenAI 兼容入口的单次输出硬上限，即使平台默认预算配置得更高也不扩大客户请求。
OPENAI_CHAT_MAX_OUTPUT_TOKENS = 4096
# 同一客户 Key 同时执行的兼容问答上限；数据库 advisory lock 保证跨 Worker 计数原子。
OPENAI_CHAT_MAX_CONCURRENT_RUNS = 5
# 会话管理仅列出最近活动中的会话，避免账号长时间使用后返回无界结果。
SESSION_LIST_LIMIT = 100
logger = logging.getLogger(__name__)


def _standard_error_code(status_code: int) -> str:
    """将 HTTP 状态映射为稳定错误码；业务 detail 仍保留在响应体中。"""
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        413: "payload_too_large",
        415: "unsupported_media_type",
        422: "validation_error",
        429: "rate_limited",
        500: "internal_error",
        503: "service_unavailable",
    }.get(status_code, "http_error")


def _version_diff(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> dict[str, Any]:
    """按切片顺序生成稳定版本差异，只返回统计与短文本摘要。"""
    before_text = [str(item.get("content", "")) for item in before]
    after_text = [str(item.get("content", "")) for item in after]
    matcher = SequenceMatcher(a=before_text, b=after_text, autojunk=False)
    changes: list[dict[str, Any]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        changes.append(
            {
                "kind": "added" if tag == "insert" else "removed" if tag == "delete" else "changed",
                "before_ordinals": [int(item["ordinal"]) for item in before[i1:i2]],
                "after_ordinals": [int(item["ordinal"]) for item in after[j1:j2]],
                "before_preview": [text[:240] for text in before_text[i1:i2]],
                "after_preview": [text[:240] for text in after_text[j1:j2]],
            }
        )
    return {
        "before_chunk_count": len(before),
        "after_chunk_count": len(after),
        "added_chunks": sum(
            len(change["after_ordinals"]) for change in changes if change["kind"] == "added"
        ),
        "removed_chunks": sum(
            len(change["before_ordinals"]) for change in changes if change["kind"] == "removed"
        ),
        "changed_chunks": sum(1 for change in changes if change["kind"] == "changed"),
        "changes": changes,
    }


class TenantCreate(BaseModel):
    code: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]+$")
    name: str = Field(min_length=2, max_length=120)


class UserCreate(BaseModel):
    login: str = Field(min_length=3, max_length=120)
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=200)
    platform_role_code: str | None = None
    tenant_id: int | None = None
    tenant_role_code: str | None = None


class MenuPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    parent_id: int | None = None
    sort_order: int | None = Field(default=None, ge=0, le=9999)
    visible: bool | None = None
    status: str | None = Field(default=None, pattern=r"^(active|disabled)$")


class MenuCreate(BaseModel):
    """菜单创建契约；路由和权限标识由平台管理员明确提供并持久化。"""

    code: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=80)
    kind: str = Field(pattern=r"^(directory|menu|button)$")
    parent_id: int | None = None
    route: str | None = Field(default=None, max_length=200)
    icon: str | None = Field(default=None, max_length=80)
    permission_code: str = Field(min_length=2, max_length=120)
    sort_order: int = Field(default=0, ge=0, le=9999)
    visible: bool = True


class RoleMenuPatch(BaseModel):
    """平台角色权限编辑请求；菜单 ID 必须去重且全部属于系统菜单。"""

    menu_ids: list[int] = Field(default_factory=list, max_length=200)


class UserPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    status: str | None = Field(default=None, pattern=r"^(active|disabled)$")
    password: str | None = Field(default=None, min_length=8, max_length=200)
    platform_role_code: str | None = None
    tenant_id: int | None = None
    tenant_role_code: str | None = None


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class KnowledgeBaseCreate(BaseModel):
    tenant_id: int
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=1000)
    purpose: str = Field(default="general", min_length=2, max_length=80)
    business_scenario: str = Field(default="", max_length=240)
    target_users: str = Field(default="", max_length=240)
    owner_user_id: int | None = None
    trust_level: str = Field(default="medium", pattern=r"^(low|medium|high)$")
    valid_from: date | None = None
    valid_until: date | None = None
    source_system: str = Field(default="", max_length=160)
    business_tags: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def valid_period_is_ordered(self) -> "KnowledgeBaseCreate":
        """拒绝截止日在起始日前的治理元数据，避免检索边界含义不明确。"""
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("有效期截止日不能早于起始日")
        return self


class KnowledgeBasePatch(BaseModel):
    """知识库治理元数据的部分更新契约；空值用于清除可选字段。"""

    business_scenario: str | None = Field(default=None, max_length=240)
    target_users: str | None = Field(default=None, max_length=240)
    owner_user_id: int | None = None
    trust_level: str | None = Field(default=None, pattern=r"^(low|medium|high)$")
    valid_from: date | None = None
    valid_until: date | None = None
    source_system: str | None = Field(default=None, max_length=160)
    business_tags: list[str] | None = Field(default=None, max_length=30)

    @model_validator(mode="after")
    def valid_period_is_ordered(self) -> "KnowledgeBasePatch":
        """校验同一请求中同时提供的有效期边界。"""
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("有效期截止日不能早于起始日")
        return self


class SpaceMemberCreate(BaseModel):
    login: str = Field(min_length=3, max_length=120)
    role_code: str = Field(pattern=r"^(space_admin|space_member|customer_reader)$")


class SpaceMemberPatch(BaseModel):
    role_code: str | None = Field(
        default=None,
        pattern=r"^(space_admin|space_member|customer_reader)$",
    )
    status: str | None = Field(default=None, pattern=r"^(active|disabled)$")


class KnowledgeBaseMemberCreate(BaseModel):
    user_id: int
    role_code: str = Field(pattern=r"^(kb_admin|editor|reader)$")


class KnowledgeBaseMemberPatch(BaseModel):
    role_code: str | None = Field(default=None, pattern=r"^(kb_admin|editor|reader)$")
    status: str | None = Field(default=None, pattern=r"^(active|disabled)$")


class ReleasePublishRequest(BaseModel):
    expected_active_release_id: int | None = None


class ReleaseRollbackRequest(BaseModel):
    expected_active_release_id: int


class SearchTestRequest(BaseModel):
    """检索诊断请求；治理筛选用于验证知识库业务准入条件。"""
    knowledge_base_id: int
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=10, ge=1, le=20)
    context_max_chars: int = Field(default=6000, ge=1000, le=20000)
    target_users: str | None = Field(default=None, max_length=240)
    business_scenario: str | None = Field(default=None, max_length=240)
    source_system: str | None = Field(default=None, max_length=160)
    business_tags: list[str] = Field(default_factory=list, max_length=30)
    trust_levels: list[str] = Field(default_factory=list, max_length=3)

    @field_validator("query")
    @classmethod
    def query_must_contain_text(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("问题不能为空")
        return query


class ConversationCreate(BaseModel):
    """创建绑定单个知识库的传统会话；自动范围助理使用独立接口。"""

    knowledge_base_id: int
    title: str = Field(default="新会话", min_length=1, max_length=200)


class AssistantConversationCreate(BaseModel):
    """创建由 API Key 客户空间自动确定检索范围的助理会话。"""

    title: str = Field(default="新会话", min_length=1, max_length=200)


class RunCreate(BaseModel):
    """提交一个会话问题；运行范围从会话类型和调用 API Key 推导。"""

    question: str = Field(min_length=1, max_length=4000)
    request_id: UUID

    @field_validator("question")
    @classmethod
    def question_must_contain_text(cls, value: str) -> str:
        question = value.strip()
        if not question:
            raise ValueError("问题不能为空")
        return question


class OpenAIChatMessage(BaseModel):
    """客户单轮 RAG 请求中的消息；历史 assistant/tool 消息不属于当前契约。"""

    role: str = Field(min_length=1, max_length=20)
    content: str = Field(min_length=1, max_length=12000)

    model_config = {"extra": "forbid"}

    @field_validator("role")
    @classmethod
    def supported_role(cls, value: str) -> str:
        """接纳常见 system/user 形状，但拒绝模型输出或工具调用历史。"""
        role = value.strip().lower()
        if role not in {"system", "user"}:
            raise ValueError("兼容入口当前仅支持 system 和 user，且必须是单轮问答")
        return role

    @field_validator("content")
    @classmethod
    def non_empty_content(cls, value: str) -> str:
        """拒绝空消息，避免无意义调用消耗客户额度。"""
        content = value.strip()
        if not content:
            raise ValueError("消息内容不能为空")
        return content


class OpenAIChatCompletionRequest(BaseModel):
    """单轮 RAG 的 OpenAI 兼容请求；知识库 ID 是租户隔离所需的扩展字段。

    ``temperature`` 仅接纳 SDK 默认字段以保持形状兼容，实际采样值固定来自 Runtime
    Profile，不因客户请求改变已审批的知识库行为。
    """

    model: str = Field(min_length=1, max_length=160)
    messages: list[OpenAIChatMessage] = Field(min_length=1, max_length=32)
    stream: bool = False
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=OPENAI_CHAT_MAX_OUTPUT_TOKENS)
    knowledge_base_id: int = Field(gt=0)
    request_id: UUID | None = None

    model_config = {"extra": "forbid"}

    @field_validator("model")
    @classmethod
    def normalize_model(cls, value: str) -> str:
        """去除模型名首尾空白，后续只允许服务端生成模型白名单。"""
        model = value.strip()
        if not model:
            raise ValueError("模型名称不能为空")
        return model


class RunRetryRequest(BaseModel):
    request_id: UUID


class OpenAIRequestBodyLimitMiddleware:
    """在 OpenAI 请求进入 JSON 解析前限制正文大小，避免大请求占满 API 内存。"""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        """配置 ASGI 应用和兼容入口正文上限。"""
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """只为 OpenAI POST 预读不超过上限的正文，并将其完整重放给 FastAPI。"""
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path") != "/v1/chat/completions"
        ):
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_bytes:
                    await self._send_too_large(send)
                    return
            except ValueError:
                await self._send_too_large(send)
                return

        chunks: list[bytes] = []
        total_size = 0
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            total_size += len(chunk)
            if total_size > self.max_bytes:
                await self._send_too_large(send)
                return
            chunks.append(chunk)
            more_body = bool(message.get("more_body", False))

        body = b"".join(chunks)
        replayed = False

        async def replay_receive() -> Message:
            """重放已校验正文一次，之后继续转交真实 disconnect 事件。"""
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay_receive, send)

    async def _send_too_large(self, send: Send) -> None:
        """返回稳定 OpenAI 错误结构；拒绝原因不依赖具体 HTTP 服务器。"""
        body = json.dumps(
            _openai_error_payload("request_too_large", "请求正文超过 1 MiB 限制"),
            ensure_ascii=False,
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


class FeedbackCreate(BaseModel):
    rating: str = Field(pattern=r"^(helpful|not_helpful)$")
    reason: str | None = Field(default=None, max_length=200)


class ModelEndpointCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    provider: str = Field(default="open_webui", pattern=r"^[a-z0-9_-]{2,40}$")
    endpoint_type: str = Field(pattern=r"^(generation|embedding|reranker)$")
    base_url: str = Field(min_length=8, max_length=300)
    secret_ref: str = Field(default=MODEL_GATEWAY_SECRET_REF, max_length=200)
    allowed_models: list[str] = Field(min_length=1, max_length=30)

    @field_validator("base_url")
    @classmethod
    def valid_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("模型端点必须是有效的 HTTP(S) 地址")
        return normalized

    @field_validator("secret_ref")
    @classmethod
    def supported_secret_ref(cls, value: str) -> str:
        if value not in {MODEL_GATEWAY_SECRET_REF, LEGACY_MODEL_GATEWAY_SECRET_REF}:
            raise ValueError("当前仅支持平台模型网关密钥")
        return MODEL_GATEWAY_SECRET_REF

    @field_validator("allowed_models")
    @classmethod
    def normalized_models(cls, value: list[str]) -> list[str]:
        models = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        if not models:
            raise ValueError("至少配置一个模型")
        return models


class ModelEndpointPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    base_url: str | None = Field(default=None, min_length=8, max_length=300)
    secret_ref: str | None = Field(default=None, max_length=200)
    allowed_models: list[str] | None = Field(default=None, min_length=1, max_length=30)
    status: str | None = Field(default=None, pattern=r"^(active|disabled)$")

    @field_validator("base_url")
    @classmethod
    def valid_base_url(cls, value: str | None) -> str | None:
        return ModelEndpointCreate.valid_base_url(value) if value is not None else None

    @field_validator("secret_ref")
    @classmethod
    def supported_secret_ref(cls, value: str | None) -> str | None:
        return ModelEndpointCreate.supported_secret_ref(value) if value is not None else None

    @field_validator("allowed_models")
    @classmethod
    def normalized_models(cls, value: list[str] | None) -> list[str] | None:
        return ModelEndpointCreate.normalized_models(value) if value is not None else None


class ModelHealthCheckRequest(BaseModel):
    model_name: str = Field(min_length=1, max_length=160)


class ModelGatewayKeyUpdate(BaseModel):
    """平台管理员替换当前模型网关凭据；明文只用于本次写入，不会回显。"""

    api_key: SecretStr = Field(min_length=1, max_length=500)

    @field_validator("api_key")
    @classmethod
    def normalize_api_key(cls, value: SecretStr) -> SecretStr:
        """去除复制时常见的首尾空白，避免把无效空格写入鉴权头。"""
        normalized = value.get_secret_value().strip()
        if not normalized:
            raise ValueError("API Key 不能为空")
        return SecretStr(normalized)


class ApiKeyCreate(BaseModel):
    """平台管理员为客户创建公司下发的访问 Key。"""

    tenant_id: int
    name: str = Field(min_length=2, max_length=120)
    token_limit: int = Field(gt=0, le=10_000_000_000)
    expires_at: datetime | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """拒绝只含空白的显示名称，并统一持久化前后空格。"""
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("API Key 名称至少需要 2 个字符")
        return normalized

    @field_validator("expires_at")
    @classmethod
    def validate_expiry(cls, value: datetime | None) -> datetime | None:
        """Key 只能设置未来有效期，避免创建后立即不可用。"""
        if value is None:
            return None
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        if normalized <= datetime.now(UTC):
            raise ValueError("有效期必须晚于当前时间")
        return normalized


class TenantApiKeyConfiguration(BaseModel):
    """医院管理员提交系统分配的 Key 以确认交接；请求明文不会被持久化。"""

    api_key: SecretStr = Field(min_length=3, max_length=500)

    @field_validator("api_key")
    @classmethod
    def normalize_api_key(cls, value: SecretStr) -> SecretStr:
        """去掉复制时带入的首尾空白，并拒绝非平台签发格式。"""
        normalized = value.get_secret_value().strip()
        if not normalized.startswith("sk-"):
            raise ValueError("请粘贴系统管理员分配的 sk- 格式 Key")
        return SecretStr(normalized)

class OpenWebUIKeyProvisioningError(HTTPException):
    """把远端 Open WebUI 创建失败转换为稳定的管理接口错误。"""

    def __init__(self, detail: str) -> None:
        super().__init__(status_code=502, detail=detail)


class ApiKeyStatusPatch(BaseModel):
    """平台管理员快速切换公司 API Key 的启用状态。"""

    status: str = Field(pattern=r"^(active|disabled)$")


class ApiKeyQuotaPatch(BaseModel):
    """平台管理员按增减方向调整已有客户 Key 的 Token 总额度。"""

    direction: str = Field(pattern=r"^(add|subtract)$")
    amount: int = Field(gt=0, le=10_000_000_000)


class IngestionProfileCreate(BaseModel):
    knowledge_base_id: int
    max_chars: int = Field(default=1800, ge=400, le=8000)
    overlap_chars: int = Field(default=0, ge=0, le=1000)
    preserve_locator: bool = True

    @field_validator("overlap_chars")
    @classmethod
    def overlap_is_bounded(cls, value: int, info: Any) -> int:
        max_chars = info.data.get("max_chars", 1800)
        if value >= int(max_chars):
            raise ValueError("重叠字符数必须小于单片最大字符数")
        return value


class EmbeddingProfileCreate(BaseModel):
    model_endpoint_id: int
    model_name: str = Field(min_length=1, max_length=160)
    expected_dimension: int | None = Field(default=None, ge=1, le=65536)
    normalization: str = Field(default="l2", pattern=r"^(l2|none)$")
    query_instruction: str = Field(default="", max_length=500)
    document_instruction: str = Field(default="", max_length=500)


class RuntimeProfileCreate(BaseModel):
    knowledge_base_id: int
    embedding_profile_id: int
    generation_endpoint_id: int
    generation_model: str = Field(min_length=1, max_length=160)
    top_k: int = Field(default=10, ge=1, le=20)
    context_max_chars: int = Field(default=8000, ge=1000, le=30000)
    temperature: float = Field(default=0.2, ge=0, le=2)
    answer_rules: str = Field(default="仅依据已发布资料回答；没有依据时明确拒答。", max_length=2000)


async def _authenticated_user(settings: Settings, request: Request) -> dict[str, Any]:
    """解析调用身份；显式 Bearer 一旦出现就不得回退到权限更高的 Cookie。"""
    authorization = request.headers.get("authorization", "")
    scheme, _, raw_key = authorization.partition(" ")
    if scheme.lower() == "bearer":
        context = await load_user_from_api_key(settings, raw_key.strip())
    else:
        context = await load_user_from_token(settings, request.cookies.get(SESSION_COOKIE))
    if context is None:
        raise HTTPException(status_code=401, detail="未登录或 API Key 无效")
    if context.get("api_key_id") and not _api_key_route_allowed(request):
        raise HTTPException(status_code=403, detail="API Key 只能调用知识问答接口")
    return context


def _api_key_route_allowed(request: Request) -> bool:
    """限制公司 API Key 的接口面，防止它继承后台管理和配置能力。"""
    path = request.url.path
    if path == "/v1/chat/completions":
        return request.method == "POST"
    if path == "/api/v1/knowledge-bases":
        return request.method == "GET"
    if path == "/api/v1/conversations":
        return request.method in {"GET", "POST"}
    if path.startswith("/api/v1/conversations/"):
        return request.method in {"GET", "POST"}
    if path == "/api/v1/assistant/conversations":
        return request.method in {"GET", "POST"}
    if path.startswith("/api/v1/assistant/conversations/"):
        return request.method in {"GET", "POST", "DELETE"}
    if path.startswith("/api/v1/runs/"):
        return request.method in {"GET", "POST"}
    return False


async def _database(settings: Settings) -> asyncpg.Connection:
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="数据库未配置")
    try:
        return await asyncpg.connect(settings.database_url, timeout=5)
    except (OSError, asyncpg.PostgresError) as error:
        raise HTTPException(status_code=503, detail="数据库暂不可用") from error


def _require_platform_admin(context: dict[str, Any]) -> None:
    """仅允许浏览器登录的平台管理员管理平台级资源，禁止 API Key 提权。"""
    if context["user"]["platform_role"] != "platform_admin" or "api_key_id" in context:
        raise HTTPException(status_code=403, detail="只有平台管理员可以管理此资源")


def _require_hospital_account(context: dict[str, Any]) -> None:
    """医院凭据确认仅供浏览器登录的医院账号执行，平台账号负责签发。"""
    if context["user"].get("platform_role") == "platform_admin" or "api_key_id" in context:
        raise HTTPException(status_code=403, detail="只有医院管理员可以确认医院 API Key")


async def _require_space_management_actor(
    connection: asyncpg.Connection, context: dict[str, Any]
) -> bool:
    """允许平台管理员或至少一个空间管理员进入空间管理；返回是否为平台管理员。"""
    if context["user"].get("platform_role") == "platform_admin":
        return True
    is_admin = await connection.fetchval(
        """
        SELECT EXISTS (
          SELECT 1 FROM tenant_members tm JOIN roles r ON r.id = tm.role_id
          WHERE tm.user_id = $1 AND tm.status = 'active' AND r.code = 'space_admin'
        )
        """,
        int(context["user"]["id"]),
    )
    if not is_admin:
        raise HTTPException(status_code=403, detail="只有系统管理员或空间管理员可以管理空间")
    return False


async def _ensure_embedding_profile(
    connection: asyncpg.Connection,
    settings: Settings,
    model_revision: str,
) -> tuple[int, str]:
    definition = embedding_profile_definition(settings, model_revision)
    definition_hash = profile_hash(definition)
    endpoint_id = await connection.fetchval(
        """
        SELECT id FROM model_endpoints
        WHERE tenant_id IS NULL AND provider = $1 AND endpoint_type = 'embedding'
          AND base_url = $2
        """,
        definition["provider"],
        definition["base_url"],
    )
    if endpoint_id is None:
        endpoint_id = await connection.fetchval(
            """
            INSERT INTO model_endpoints(
              tenant_id, name, provider, endpoint_type, base_url,
              allowed_models, secret_ref, health_status
            ) VALUES (
              NULL, 'Open WebUI API Key 模型网关', $1, 'embedding', $2,
              $3::jsonb, $4, 'healthy'
            )
            RETURNING id
            """,
            definition["provider"],
            definition["base_url"],
            json.dumps([settings.embedding_model], ensure_ascii=False),
            definition["secret_ref"],
        )
    embedding_profile_id = await connection.fetchval(
        "SELECT id FROM embedding_profiles WHERE definition_hash = $1",
        definition_hash,
    )
    if embedding_profile_id is None:
        embedding_profile_id = await connection.fetchval(
            """
            INSERT INTO embedding_profiles(
              model_endpoint_id, model_name, model_revision, dimension, dtype,
              instructions, normalization, definition_hash
            ) VALUES ($1, $2, $3, $4, 'float32', '{}'::jsonb, 'l2', $5)
            RETURNING id
            """,
            endpoint_id,
            settings.embedding_model,
            model_revision,
            settings.embedding_dimensions,
            definition_hash,
        )
    return int(embedding_profile_id), definition_hash


async def _assert_tenant_access(
    connection: asyncpg.Connection,
    context: dict[str, Any],
    tenant_id: int,
) -> None:
    exists = await connection.fetchval(
        """
        SELECT EXISTS (
            SELECT 1 FROM tenant_members tm JOIN tenants t ON t.id = tm.tenant_id
            WHERE tm.tenant_id = $1 AND tm.user_id = $2 AND tm.status = 'active'
              AND t.status = 'active'
        )
        """,
        tenant_id,
        int(context["user"]["id"]),
    )
    if not exists:
        raise HTTPException(status_code=404, detail="空间不存在")


async def _require_space_admin(
    connection: asyncpg.Connection,
    context: dict[str, Any],
    tenant_id: int,
) -> None:
    """空间管理操作必须由该空间的显式空间管理员执行。"""
    await _assert_tenant_access(connection, context, tenant_id)
    is_admin = await connection.fetchval(
        """
        SELECT EXISTS (
          SELECT 1 FROM tenant_members tm JOIN roles r ON r.id = tm.role_id
          WHERE tm.tenant_id = $1 AND tm.user_id = $2
            AND tm.status = 'active' AND r.code = 'space_admin'
        )
        """,
        tenant_id,
        int(context["user"]["id"]),
    )
    if not is_admin:
        raise HTTPException(status_code=403, detail="只有空间管理员可以管理成员")


async def _write_membership_audit(
    connection: asyncpg.Connection,
    *,
    tenant_id: int,
    actor_id: int,
    action: str,
    target_type: str,
    target_id: int,
    summary: dict[str, Any],
) -> None:
    await connection.execute(
        """
        INSERT INTO audit_logs(
          tenant_id, actor_id, action, target_type, target_id, change_summary
        ) VALUES ($1, $2, $3, $4, $5, $6::jsonb)
        """,
        tenant_id,
        actor_id,
        action,
        target_type,
        str(target_id),
        json.dumps(summary, ensure_ascii=False),
    )


async def _assert_space_member_role_change(
    connection: asyncpg.Connection,
    *,
    tenant_id: int,
    user_id: int,
    current_role: str,
    next_role: str,
    next_status: str,
) -> None:
    """保护最后一名空间管理员，并防止客户只读角色叠加管理授权。"""
    if current_role == "space_admin" and (next_role != "space_admin" or next_status != "active"):
        active_admins = await connection.fetchval(
            """
            SELECT count(*) FROM tenant_members tm JOIN roles r ON r.id = tm.role_id
            WHERE tm.tenant_id = $1 AND tm.status = 'active' AND r.code = 'space_admin'
            """,
            tenant_id,
        )
        if int(active_admins or 0) <= 1:
            raise HTTPException(status_code=409, detail="空间必须保留至少一名有效管理员")
    if next_role == "customer_reader" and next_status == "active":
        has_kb_grants = await connection.fetchval(
            """
            SELECT EXISTS (
              SELECT 1 FROM kb_members
              WHERE tenant_id = $1 AND user_id = $2 AND status = 'active'
            )
            """,
            tenant_id,
            user_id,
        )
        if has_kb_grants:
            raise HTTPException(status_code=409, detail="请先撤销该成员的知识库管理授权")


async def _knowledge_base_access(
    connection: asyncpg.Connection,
    context: dict[str, Any],
    knowledge_base_id: int,
) -> asyncpg.Record:
    """返回当前用户对知识库的授权信息；未授权统一隐藏资源是否存在。"""
    if context.get("api_key_tenant_id"):
        row = await connection.fetchrow(
            """
            SELECT kb.id, kb.tenant_id, kb.name, kb.status, kb.active_release_id,
                   kb.active_runtime_id, rp.definition AS runtime_definition,
                   generation_endpoint.allowed_models AS generation_allowed_models,
                   generation_endpoint.status AS generation_endpoint_status,
                   'customer_reader' AS tenant_role, NULL::text AS knowledge_base_role
            FROM knowledge_bases kb
            JOIN tenants t ON t.id = kb.tenant_id AND t.status = 'active'
            LEFT JOIN runtime_profiles rp ON rp.id = kb.active_runtime_id
              AND rp.tenant_id = kb.tenant_id AND rp.knowledge_base_id = kb.id
            LEFT JOIN model_endpoints generation_endpoint
              ON generation_endpoint.id =
                 (rp.definition->'generation'->>'endpoint_id')::bigint
            WHERE kb.id = $1 AND kb.tenant_id = $2 AND kb.status <> 'disabled'
              AND kb.active_release_id IS NOT NULL
            """,
            knowledge_base_id,
            int(context["api_key_tenant_id"]),
        )
        if row is None:
            raise HTTPException(status_code=404, detail="知识库不存在")
        return row
    row = await connection.fetchrow(
        """
        SELECT kb.id, kb.tenant_id, kb.name, kb.status, kb.active_release_id,
               tm_role.code AS tenant_role, km_role.code AS knowledge_base_role
        FROM knowledge_bases kb
        JOIN tenant_members tm ON tm.tenant_id = kb.tenant_id
          AND tm.user_id = $2 AND tm.status = 'active'
        JOIN tenants t ON t.id = kb.tenant_id AND t.status = 'active'
        JOIN roles tm_role ON tm_role.id = tm.role_id
        LEFT JOIN kb_members km ON km.knowledge_base_id = kb.id
          AND km.tenant_id = kb.tenant_id AND km.user_id = $2 AND km.status = 'active'
        LEFT JOIN roles km_role ON km_role.id = km.role_id
        WHERE kb.id = $1 AND kb.status <> 'disabled'
          AND (tm_role.code IN ('space_admin', 'customer_reader') OR km_role.code IS NOT NULL)
        """,
        knowledge_base_id,
        int(context["user"]["id"]),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return row


async def _require_knowledge_base_role(
    connection: asyncpg.Connection,
    context: dict[str, Any],
    knowledge_base_id: int,
    allowed_roles: set[str],
) -> asyncpg.Record:
    row = await _knowledge_base_access(connection, context, knowledge_base_id)
    role = row["tenant_role"] if row["tenant_role"] == "space_admin" else row["knowledge_base_role"]
    if role not in allowed_roles:
        raise HTTPException(status_code=403, detail="当前角色没有执行此操作的权限")
    return row


async def _conversation_access(
    connection: asyncpg.Connection,
    context: dict[str, Any],
    conversation_id: int,
) -> asyncpg.Record:
    """只允许会话所有者在仍具备知识库权限时访问会话。"""
    if context.get("api_key_tenant_id"):
        row = await connection.fetchrow(
            """
            SELECT conversation.id, conversation.tenant_id, conversation.knowledge_base_id,
                   conversation.owner_user_id, conversation.title, conversation.status,
                   kb.name AS knowledge_base_name, kb.active_release_id, kb.active_runtime_id
            FROM conversations conversation
            JOIN knowledge_bases kb ON kb.id = conversation.knowledge_base_id
              AND kb.tenant_id = conversation.tenant_id AND kb.status <> 'disabled'
            JOIN tenants tenant ON tenant.id = conversation.tenant_id
              AND tenant.status = 'active'
            WHERE conversation.id = $1
              AND conversation.owner_user_id = $2
              AND conversation.tenant_id = $3
              AND conversation.status = 'active'
            """,
            conversation_id,
            int(context["user"]["id"]),
            int(context["api_key_tenant_id"]),
        )
        if row is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        return row
    row = await connection.fetchrow(
        """
        SELECT conversation.id, conversation.tenant_id, conversation.knowledge_base_id,
               conversation.owner_user_id, conversation.title, conversation.status,
               kb.name AS knowledge_base_name, kb.active_release_id, kb.active_runtime_id
        FROM conversations conversation
        JOIN knowledge_bases kb ON kb.id = conversation.knowledge_base_id
          AND kb.tenant_id = conversation.tenant_id AND kb.status <> 'disabled'
        JOIN tenant_members tm ON tm.tenant_id = conversation.tenant_id
          AND tm.user_id = $2 AND tm.status = 'active'
        JOIN tenants tenant ON tenant.id = conversation.tenant_id AND tenant.status = 'active'
        JOIN roles tenant_role ON tenant_role.id = tm.role_id
        LEFT JOIN kb_members km ON km.knowledge_base_id = conversation.knowledge_base_id
          AND km.tenant_id = conversation.tenant_id
          AND km.user_id = $2 AND km.status = 'active'
        WHERE conversation.id = $1 AND conversation.owner_user_id = $2
          AND conversation.status = 'active'
          AND (tenant_role.code IN ('space_admin', 'customer_reader') OR km.user_id IS NOT NULL)
        """,
        conversation_id,
        int(context["user"]["id"]),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return row


async def _conversation_id_from_public(
    connection: asyncpg.Connection, context: dict[str, Any], public_id: UUID | str
) -> int:
    """将前端 threadId 解析为内部 bigint，并复用现有租户/权限校验。"""
    row = await connection.fetchrow(
        "SELECT id FROM conversations WHERE public_id = $1::uuid",
        public_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return int(row["id"])


async def _run_id_from_public(connection: asyncpg.Connection, public_id: str) -> int:
    """将对外运行 ID 解析为内部 bigint；无效 UUID 不泄露数据库细节。"""
    row = await connection.fetchrow(
        "SELECT id FROM generation_runs WHERE public_id = $1::uuid",
        public_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="问答运行不存在")
    return int(row["id"])


def _public_run_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """在 HTTP 边界隐藏运行表 bigint，仅返回持久化的公开 run ID。"""
    result = dict(payload)
    if result.get("public_id"):
        result["id"] = result["public_id"]
    return result


def _openai_error_payload(code: str, message: str) -> dict[str, Any]:
    """构造 OpenAI 客户端可直接消费的错误包，不暴露内部 SQL 或上游正文。"""
    normalized_code = code.lower()
    if normalized_code == "invalid_api_key":
        error_type = "authentication_error"
    elif normalized_code == "api_key_scope_forbidden":
        error_type = "permission_error"
    elif normalized_code == "knowledge_base_not_found":
        error_type = "not_found_error"
    elif normalized_code in {"duplicate_request", "request_cancelled"}:
        error_type = "conflict_error"
    elif normalized_code in {"rate_limit_exceeded", "token_quota_exceeded"}:
        error_type = "rate_limit_error"
    elif normalized_code in {
        "request_too_large",
        "invalid_request",
        "max_tokens_exceeds_server_limit",
    }:
        error_type = "invalid_request_error"
    elif normalized_code in {"service_unavailable", "generation_failed", "generation_incomplete"}:
        error_type = "server_error"
    else:
        error_type = "invalid_request_error"
    if normalized_code == "generation_failed":
        message = "问答生成失败，可以重试。"
    return {"error": {"message": message, "type": error_type, "code": code}}


def _openai_question(messages: list[OpenAIChatMessage]) -> str:
    """提取唯一用户问题；服务端忽略客户端 system 规则以保持引用校验边界。"""
    user_messages = [message.content for message in messages if message.role == "user"]
    if len(user_messages) != 1:
        raise HTTPException(status_code=400, detail="兼容入口每次请求必须包含一个 user 消息")
    return user_messages[0]


async def _prepare_openai_run(
    connection: asyncpg.Connection,
    *,
    context: dict[str, Any],
    knowledge_base_id: int,
    model: str,
    question: str,
    request_id: UUID,
    max_tokens: int,
    default_model: str,
    default_allowed_models: frozenset[str],
) -> tuple[int, dict[str, Any]]:
    """在单个事务中创建兼容问答运行并冻结授权快照。

    参数包含已认证身份、知识库、白名单模型、唯一问题、幂等 UUID 与输出预算；
    返回数据库运行 ID 和公开运行快照。重复请求参数冲突或 Key 并发超限时抛出
    ``HTTPException``，且事务会回滚，不创建会话或消息。
    """
    api_key_id = context.get("api_key_id")
    api_key_tenant_id = context.get("api_key_tenant_id")
    if api_key_id is None or api_key_tenant_id is None:
        raise HTTPException(status_code=403, detail="只有客户 API Key 可以调用模型网关")
    request_fingerprint = hashlib.sha256(
        json.dumps(
            {
                "knowledge_base_id": knowledge_base_id,
                "model": model,
                "question": question,
                "max_tokens": max_tokens,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    async with connection.transaction():
        # 与原生运行创建共用 Key 锁，幂等查询与兼容运行创建保持原子边界。
        await connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
            f"openai-concurrency:{api_key_id}",
        )
        existing = await connection.fetchrow(
            """
            SELECT run.id::text, run.public_id::text AS public_id,
                   run.tenant_id::text, run.knowledge_base_id::text,
                   run.conversation_id::text, run.user_message_id::text,
                   run.assistant_message_id::text, user_message.content AS question,
                   run.request_fingerprint,
                   run.release_id::text, run.api_key_id::text, run.request_id::text,
                   run.state, run.outcome, run.cancel_requested,
                   run.error, run.created_at, run.updated_at
            FROM generation_runs run
            JOIN messages user_message ON user_message.id = run.user_message_id
              AND user_message.tenant_id = run.tenant_id
            WHERE run.api_key_id = $1 AND run.request_id = $2
            """,
            int(api_key_id),
            request_id,
        )
        if existing is not None:
            if (
                int(existing["knowledge_base_id"]) != knowledge_base_id
                or str(existing["question"]) != question
                or existing["request_fingerprint"] != request_fingerprint
            ):
                raise HTTPException(status_code=409, detail="request_id 已用于不同请求参数")
            return int(existing["id"]), dict(existing)

        access = await _knowledge_base_access(connection, context, knowledge_base_id)
        if int(access["tenant_id"]) != int(api_key_tenant_id):
            # 与知识库查询中的空间条件重复约束，避免后续查询修改扩大 Key 的授权范围。
            raise HTTPException(status_code=404, detail="知识库不存在")

        runtime_definition = _json_value(access.get("runtime_definition"), {})
        generation_definition = runtime_definition.get("generation", {})
        resolved_model = str(generation_definition.get("model") or default_model)
        if model != resolved_model:
            raise HTTPException(
                status_code=400,
                detail="请求模型不在所选知识库的 Runtime Profile 白名单中",
            )
        if access.get("active_runtime_id") is None and model not in default_allowed_models:
            raise HTTPException(status_code=400, detail="请求模型不在服务端生成模型白名单中")
        if access.get("active_runtime_id") is not None:
            allowed_models = _json_value(access.get("generation_allowed_models"), [])
            if isinstance(allowed_models, str):
                try:
                    allowed_models = json.loads(allowed_models)
                except json.JSONDecodeError:
                    allowed_models = []
            if (
                access.get("generation_endpoint_status") != "active"
                or not isinstance(allowed_models, list)
                or resolved_model not in allowed_models
            ):
                raise HTTPException(status_code=503, detail="知识库生成模型端点不可用")

        conversation = await connection.fetchrow(
            """
            INSERT INTO conversations(tenant_id, knowledge_base_id, owner_user_id, title)
            VALUES ($1, $2, $3, $4)
            RETURNING id, tenant_id, knowledge_base_id, title, status
            """,
            int(access["tenant_id"]),
            knowledge_base_id,
            int(context["user"]["id"]),
            question[:60],
        )
        if conversation is None:
            raise HTTPException(status_code=500, detail="会话创建失败")
        # conversations 不存 Profile 快照；运行消息必须冻结本次授权查询读取的知识库版本。
        conversation_snapshot = {
            **dict(conversation),
            "active_release_id": access["active_release_id"],
            "active_runtime_id": access.get("active_runtime_id"),
        }
        run = await _create_generation_run(
            connection,
            conversation=conversation_snapshot,
            user_id=int(context["user"]["id"]),
            request_id=request_id,
            question=question,
            api_key_id=str(api_key_id),
            request_fingerprint=request_fingerprint,
        )
    return int(run["id"]), _public_run_payload(run)


def _parse_internal_sse(raw_event: str) -> tuple[str, dict[str, Any]]:
    """解析现有 RAG SSE 事件，兼容事件数据跨网络分片后的完整单事件文本。"""
    event_name = "message"
    data_lines: list[str] = []
    for line in raw_event.splitlines():
        if line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())
    if not data_lines:
        return event_name, {}
    payload = json.loads("\n".join(data_lines))
    return event_name, payload if isinstance(payload, dict) else {}


def _openai_usage(run: Mapping[str, Any] | None) -> dict[str, Any]:
    """把内部回答 usage 转成 OpenAI 字段，并保留来源扩展供结算审计使用。"""
    usage = run.get("usage") if run is not None else None
    if not isinstance(usage, Mapping):
        usage = {}
    return {
        "prompt_tokens": max(0, int(usage.get("prompt_tokens", 0))),
        "completion_tokens": max(0, int(usage.get("completion_tokens", 0))),
        "total_tokens": max(0, int(usage.get("total_tokens", 0))),
        "usage_source": str(usage.get("usage_source", "unavailable")),
    }


def _openai_run_error(run: Mapping[str, Any]) -> dict[str, Any] | None:
    """把失败或取消的持久化终态转成稳定错误，不把它们伪装成成功回答。"""
    state = str(run.get("state", ""))
    if state == "completed":
        return None
    if state == "cancelled":
        return _openai_error_payload("request_cancelled", "问答运行已取消。")

    stored_error = run.get("error")
    stored_code = stored_error.get("code") if isinstance(stored_error, Mapping) else None
    if stored_code == "TOKEN_QUOTA_EXCEEDED":
        return _openai_error_payload(
            "TOKEN_QUOTA_EXCEEDED", "API Key Token 额度不足，请联系公司管理员。"
        )
    return _openai_error_payload("generation_failed", "问答生成失败，可以重试。")


def _openai_chunk(
    *,
    completion_id: str,
    model: str,
    created: int,
    delta: dict[str, Any] | None = None,
    finish_reason: str | None = None,
    usage: dict[str, Any] | None = None,
) -> str:
    """输出一个 OpenAI Chat Completions SSE data 帧。"""
    payload: dict[str, Any] = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta or {},
                "finish_reason": finish_reason,
            }
        ],
    }
    if usage is not None:
        payload["choices"] = []
        payload["usage"] = usage
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


async def _stream_openai_completion(
    source: AsyncIterator[str],
    *,
    completion_id: str,
    model: str,
    created: int,
) -> AsyncIterator[str]:
    """把可信的内部运行 SSE 转成 OpenAI 帧，并总以 ``[DONE]`` 结束。

    参数 ``source`` 必须是服务端 RAG 事件流；成功终态输出答案、finish reason 和 usage，
    失败终态输出脱敏错误帧。响应头发出后的异常只能映射为流内错误，不能更改 HTTP 状态。
    """
    emitted_text = False
    final_run: Mapping[str, Any] | None = None
    emitted_error = False
    yield _openai_chunk(
        completion_id=completion_id,
        model=model,
        created=created,
        delta={"role": "assistant"},
    )
    try:
        async for raw_event in source:
            event_name, payload = _parse_internal_sse(raw_event)
            if event_name == "token":
                text = payload.get("text")
                if isinstance(text, str) and text:
                    emitted_text = True
                    yield _openai_chunk(
                        completion_id=completion_id,
                        model=model,
                        created=created,
                        delta={"content": text},
                    )
            elif event_name == "done":
                run = payload.get("run")
                if isinstance(run, Mapping):
                    final_run = run
                    run_error = _openai_run_error(run)
                    if run_error is not None:
                        emitted_error = True
                        yield f"data: {json.dumps(run_error, ensure_ascii=False)}\n\n"
                        continue
                    answer = run.get("answer")
                    if not emitted_text and isinstance(answer, str) and answer:
                        emitted_text = True
                        yield _openai_chunk(
                            completion_id=completion_id,
                            model=model,
                            created=created,
                            delta={"content": answer},
                        )
                    yield _openai_chunk(
                        completion_id=completion_id,
                        model=model,
                        created=created,
                        finish_reason="stop",
                    )
                    yield _openai_chunk(
                        completion_id=completion_id,
                        model=model,
                        created=created,
                        usage=_openai_usage(run),
                    )
            elif event_name == "error":
                emitted_error = True
                code = str(payload.get("code", "generation_failed"))
                message = str(payload.get("message", "问答生成失败"))
                error_payload = json.dumps(_openai_error_payload(code, message), ensure_ascii=False)
                yield f"data: {error_payload}\n\n"
        if final_run is None and not emitted_error:
            error_payload = json.dumps(
                _openai_error_payload("generation_incomplete", "问答未返回终态"),
                ensure_ascii=False,
            )
            yield f"data: {error_payload}\n\n"
    except Exception:
        # HTTP 头已经发送后只能使用协议内错误帧，不能再修改响应状态码。
        if not emitted_error:
            error_payload = json.dumps(
                _openai_error_payload("generation_failed", "问答生成失败，可以重试。"),
                ensure_ascii=False,
            )
            yield f"data: {error_payload}\n\n"
    yield "data: [DONE]\n\n"


async def _collect_openai_completion(
    source: AsyncIterator[str],
    *,
    completion_id: str,
    model: str,
    created: int,
) -> dict[str, Any]:
    """消费服务端 RAG 事件流并返回一个非流式 OpenAI completion 或错误包。

    ``source`` 只接受内部 SSE；缺失终态、生成失败或取消不会被伪装成空成功响应，
    上游异常正文不会透传给客户。
    """
    parts: list[str] = []
    final_run: Mapping[str, Any] | None = None
    error: dict[str, Any] | None = None
    try:
        async for raw_event in source:
            event_name, payload = _parse_internal_sse(raw_event)
            if event_name == "token" and isinstance(payload.get("text"), str):
                parts.append(str(payload["text"]))
            elif event_name == "done" and isinstance(payload.get("run"), Mapping):
                final_run = payload["run"]
            elif event_name == "error":
                error = _openai_error_payload(
                    str(payload.get("code", "generation_failed")),
                    str(payload.get("message", "问答生成失败，可以重试。")),
                )
    except Exception:
        # 内部事件只来自受信服务，但仍不能把解析或生成异常泄露为默认 500 响应。
        return _openai_error_payload("generation_failed", "问答生成失败，可以重试。")
    if error is not None:
        return error
    if final_run is None:
        return _openai_error_payload("generation_incomplete", "问答未返回终态")
    run_error = _openai_run_error(final_run)
    if run_error is not None:
        return run_error
    content = final_run.get("answer")
    if not isinstance(content, str):
        content = "".join(parts)
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": _openai_usage(final_run),
    }


async def _create_generation_run(
    connection: asyncpg.Connection,
    *,
    conversation: asyncpg.Record,
    user_id: int,
    request_id: UUID,
    question: str,
    user_message_id: int | None = None,
    api_key_id: str | None = None,
    request_fingerprint: str | None = None,
) -> dict[str, Any]:
    """在调用方事务中创建幂等运行，并统一执行客户 Key 的并发门禁。

    调用方必须已打开事务。重复 ``request_id`` 先返回同会话的既有运行；新客户 Key
    运行按“每 Key 锁、每 request 锁”顺序串行化，再检查活跃数量，超限抛出
    ``HTTPException(429)``。返回持久化运行，消息、发布版本和 Runtime ID 均绑定会话快照。
    """
    if api_key_id is not None:
        # 原生与 OpenAI 路由遵守相同锁顺序，避免并行请求绕过 Key 限制或互相死锁。
        await connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
            f"openai-concurrency:{api_key_id}",
        )
        await connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
            f"api-key-run:{api_key_id}:{request_id}",
        )
        existing_for_key = await connection.fetchrow(
            """
            SELECT id::text, public_id::text AS public_id, tenant_id::text, knowledge_base_id::text,
                   conversation_id::text, user_message_id::text, assistant_message_id::text,
                   release_id::text, api_key_id::text, request_id::text,
                   state, outcome, cancel_requested,
                   error, created_at, updated_at
            FROM generation_runs
            WHERE api_key_id = $1 AND request_id = $2
            """,
            int(api_key_id),
            request_id,
        )
        if existing_for_key is not None:
            if int(existing_for_key["conversation_id"]) != int(conversation["id"]):
                raise HTTPException(
                    status_code=409,
                    detail="request_id 已由该 API Key 的其他会话使用",
                )
            return dict(existing_for_key)

    existing = await connection.fetchrow(
        """
        SELECT id::text, public_id::text AS public_id, tenant_id::text, knowledge_base_id::text,
               conversation_id::text, user_message_id::text, assistant_message_id::text,
               release_id::text, api_key_id::text, request_id::text,
               state, outcome, cancel_requested,
               error, created_at, updated_at
        FROM generation_runs
        WHERE tenant_id = $1 AND conversation_id = $2 AND request_id = $3
        """,
        conversation["tenant_id"],
        conversation["id"],
        request_id,
    )
    if existing is not None:
        existing_key_id = str(existing["api_key_id"]) if existing.get("api_key_id") else None
        if existing_key_id != api_key_id:
            raise HTTPException(status_code=409, detail="request_id 已由其他调用身份使用")
        return dict(existing)

    if api_key_id is not None:
        active_runs = await connection.fetchval(
            """
            SELECT count(*) FROM generation_runs
            WHERE api_key_id = $1 AND state IN ('queued', 'running')
            """,
            int(api_key_id),
        )
        if int(active_runs or 0) >= OPENAI_CHAT_MAX_CONCURRENT_RUNS:
            raise HTTPException(status_code=429, detail="当前 API Key 的并发问答数已达上限")

    if user_message_id is None:
        user_message_id = int(
            await connection.fetchval(
                """
                INSERT INTO messages(
                  tenant_id, conversation_id, role, content, state, request_id,
                  release_id, runtime_id
                ) VALUES ($1, $2, 'user', $3, 'complete', $4, $5, $6)
                RETURNING id
                """,
                conversation["tenant_id"],
                conversation["id"],
                question,
                request_id,
                conversation["active_release_id"],
                conversation.get("active_runtime_id"),
            )
        )
    assistant_message_id = int(
        await connection.fetchval(
            """
            INSERT INTO messages(
              tenant_id, conversation_id, role, content, state, release_id, runtime_id
            ) VALUES ($1, $2, 'assistant', '', 'pending', $3, $4)
            RETURNING id
            """,
            conversation["tenant_id"],
            conversation["id"],
            conversation["active_release_id"],
            conversation.get("active_runtime_id"),
        )
    )
    run = await connection.fetchrow(
        """
        INSERT INTO generation_runs(
          tenant_id, knowledge_base_id, conversation_id, user_message_id,
          assistant_message_id, release_id, request_id, api_key_id, request_fingerprint
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING id::text, public_id::text AS public_id, tenant_id::text,
                  knowledge_base_id::text,
                  conversation_id::text, user_message_id::text, assistant_message_id::text,
                  release_id::text, api_key_id::text, request_id::text,
                  state, outcome, cancel_requested,
                  error, created_at, updated_at
        """,
        conversation["tenant_id"],
        conversation["knowledge_base_id"],
        conversation["id"],
        user_message_id,
        assistant_message_id,
        conversation["active_release_id"],
        request_id,
        int(api_key_id) if api_key_id is not None else None,
        request_fingerprint,
    )
    if conversation["title"] == "新会话":
        await connection.execute(
            """
            UPDATE conversations SET title = $3, updated_at = now()
            WHERE id = $1 AND tenant_id = $2
            """,
            conversation["id"],
            conversation["tenant_id"],
            question[:60],
        )
    if run is None:
        raise HTTPException(status_code=500, detail="问答运行创建失败")
    return dict(run)


async def _document_access(
    connection: asyncpg.Connection,
    context: dict[str, Any],
    document_id: int,
) -> asyncpg.Record:
    row = await connection.fetchrow(
        """
        SELECT d.id, d.tenant_id, d.knowledge_base_id, d.title, d.status,
               kb.active_release_id, tm_role.code AS tenant_role,
               km_role.code AS knowledge_base_role
        FROM documents d
        JOIN knowledge_bases kb ON kb.id = d.knowledge_base_id
          AND kb.tenant_id = d.tenant_id AND kb.status <> 'disabled'
        JOIN tenant_members tm ON tm.tenant_id = d.tenant_id
          AND tm.user_id = $2 AND tm.status = 'active'
        JOIN tenants t ON t.id = d.tenant_id AND t.status = 'active'
        JOIN roles tm_role ON tm_role.id = tm.role_id
        LEFT JOIN kb_members km ON km.knowledge_base_id = d.knowledge_base_id
          AND km.tenant_id = d.tenant_id AND km.user_id = $2 AND km.status = 'active'
        LEFT JOIN roles km_role ON km_role.id = km.role_id
        WHERE d.id = $1
          AND (tm_role.code IN ('space_admin', 'customer_reader') OR km_role.code IS NOT NULL)
        """,
        document_id,
        int(context["user"]["id"]),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return row


def _role_for_access(row: asyncpg.Record) -> str:
    role = row["tenant_role"] if row["tenant_role"] == "space_admin" else row["knowledge_base_role"]
    return cast(str, role)


def _safe_filename(filename: str | None) -> str:
    """剥离路径信息并限制上传文件名长度，避免客户端路径进入业务标识。"""
    name = Path(filename or "未命名文档").name.strip()
    return name[:240] or "未命名文档"


def _validate_upload_type(filename: str, content_type: str | None) -> str:
    """要求文件扩展名与 multipart MIME 一致，并返回规范化扩展名。"""
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_DOCUMENT_TYPES:
        raise HTTPException(status_code=415, detail="仅支持 Markdown、TXT、DOCX 和电子 PDF")

    declared_type = (content_type or "").split(";", maxsplit=1)[0].strip().lower()
    if declared_type not in ALLOWED_DOCUMENT_MIME_TYPES[suffix]:
        raise HTTPException(status_code=415, detail="文件扩展名与 MIME 类型不匹配")
    return suffix


async def _read_upload(upload: UploadFile, suffix: str) -> bytes:
    """限量读取并验证文件内容特征；上传体超限时立即停止缓存后续字节。"""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_DOCUMENT_SIZE:
            raise HTTPException(status_code=413, detail="文件不能超过 50 MB")
        chunks.append(chunk)
    raw = b"".join(chunks)
    if not raw:
        raise HTTPException(status_code=422, detail="不能上传空文件")
    if suffix in {".md", ".txt"}:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise HTTPException(status_code=415, detail="文本文件必须使用 UTF-8 编码") from error
        if "\x00" in text or "\ufffd" in text:
            raise HTTPException(status_code=415, detail="文本文件包含不可读取的内容")
    elif suffix == ".pdf" and not raw.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="文件头不是有效的 PDF")
    elif suffix in {".docx", ".pdf"}:
        try:
            # 上传入口与 Worker 共用容器边界，避免文件落盘后才发现压缩炸弹。
            validate_document_container(raw, suffix)
        except ValueError as error:
            raise HTTPException(status_code=415, detail="文件容器结构不安全或已损坏") from error
    return raw


def _rows(rows: list[asyncpg.Record]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _json_value(value: Any, fallback: Any) -> Any:
    """将 asyncpg 返回的 JSONB 字符串恢复为 API 契约中的数组/对象。"""
    if value is None:
        return fallback
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return value


async def _load_release_preview(
    connection: asyncpg.Connection,
    build_id: int,
) -> dict[str, Any] | None:
    build = await connection.fetchrow(
        """
        SELECT ib.id, ib.tenant_id, ib.knowledge_base_id, ib.input_epoch,
               ib.ingestion_profile_id, ib.embedding_profile_id, ib.state,
               ib.created_at, ib.updated_at, kb.name AS knowledge_base_name,
               kb.status AS knowledge_base_status, kb.content_epoch,
               kb.active_release_id, ep.model_name, ep.model_revision, ep.dimension,
               ep.definition_hash AS embedding_definition_hash,
               me.provider, me.base_url, me.secret_ref,
               ip.definition_hash AS ingestion_definition_hash
        FROM index_builds ib
        JOIN knowledge_bases kb ON kb.id = ib.knowledge_base_id
          AND kb.tenant_id = ib.tenant_id
        JOIN embedding_profiles ep ON ep.id = ib.embedding_profile_id
        JOIN model_endpoints me ON me.id = ep.model_endpoint_id
        JOIN ingestion_profiles ip ON ip.id = ib.ingestion_profile_id
        WHERE ib.id = $1
        """,
        build_id,
    )
    if build is None:
        return None

    candidate_items = await connection.fetch(
        """
        SELECT bi.document_id, bi.document_version_id, bi.artifact_id,
               bi.state AS build_item_state, bi.chunk_count AS expected_chunk_count,
               bi.embedded_count, d.title, d.status AS document_status,
               d.desired_version_id, dv.version_no, dv.parse_status,
               da.state AS artifact_state,
               da.document_version_id AS artifact_document_version_id,
               da.ingestion_profile_id AS artifact_ingestion_profile_id,
               count(c.id)::int AS actual_chunk_count,
               count(ce.id)::int AS embedding_count,
               COALESCE(min(vector_dims(ce.embedding)), 0)::int AS min_dimension,
               COALESCE(max(vector_dims(ce.embedding)), 0)::int AS max_dimension
        FROM build_items bi
        JOIN documents d ON d.id = bi.document_id AND d.tenant_id = bi.tenant_id
          AND d.knowledge_base_id = bi.knowledge_base_id
        JOIN document_versions dv ON dv.id = bi.document_version_id
          AND dv.tenant_id = bi.tenant_id AND dv.document_id = bi.document_id
        JOIN document_artifacts da ON da.id = bi.artifact_id
          AND da.tenant_id = bi.tenant_id
          AND da.knowledge_base_id = bi.knowledge_base_id
        LEFT JOIN chunks c ON c.tenant_id = bi.tenant_id
          AND c.knowledge_base_id = bi.knowledge_base_id AND c.artifact_id = bi.artifact_id
        LEFT JOIN chunk_embeddings ce ON ce.tenant_id = bi.tenant_id
          AND ce.knowledge_base_id = bi.knowledge_base_id AND ce.chunk_id = c.id
          AND ce.embedding_profile_id = $2
        WHERE bi.build_id = $1
        GROUP BY bi.build_id, bi.document_id, bi.document_version_id, bi.artifact_id,
                 bi.state, bi.chunk_count, bi.embedded_count, d.id, dv.id, da.id
        ORDER BY bi.document_id
        """,
        build_id,
        build["embedding_profile_id"],
    )

    validation_errors: list[dict[str, Any]] = []
    if build["state"] != "ready":
        validation_errors.append({"code": "BUILD_NOT_READY", "message": "构建尚未完成"})
    if build["knowledge_base_status"] == "disabled":
        validation_errors.append({"code": "KNOWLEDGE_BASE_DISABLED", "message": "知识库已停用"})
    if int(build["input_epoch"]) != int(build["content_epoch"]):
        validation_errors.append({"code": "STALE_BUILD", "message": "知识库内容已变化，请重新构建"})
    if not candidate_items:
        validation_errors.append({"code": "EMPTY_BUILD", "message": "构建中没有可发布文档"})

    for item in candidate_items:
        title = str(item["title"])
        error: tuple[str, str] | None = None
        if item["build_item_state"] != "completed":
            error = ("BUILD_ITEM_INCOMPLETE", "文档构建尚未完成")
        elif item["document_status"] != "active":
            error = ("DOCUMENT_INACTIVE", "文档已停用或删除")
        elif item["parse_status"] != "complete" or item["artifact_state"] != "ready":
            error = ("ARTIFACT_NOT_READY", "文档解析产物不完整")
        elif int(item["artifact_document_version_id"]) != int(item["document_version_id"]):
            error = ("ARTIFACT_VERSION_MISMATCH", "解析产物与文档版本不一致")
        elif int(item["artifact_ingestion_profile_id"]) != int(build["ingestion_profile_id"]):
            error = ("INGESTION_PROFILE_MISMATCH", "切片配置不一致")
        elif int(item["actual_chunk_count"]) <= 0 or int(item["actual_chunk_count"]) != int(
            item["expected_chunk_count"]
        ):
            error = ("CHUNK_COUNT_MISMATCH", "切片数量不完整")
        elif int(item["embedding_count"]) != int(item["actual_chunk_count"]):
            error = ("EMBEDDING_COUNT_MISMATCH", "向量数量不完整")
        elif int(item["embedded_count"]) != int(item["actual_chunk_count"]):
            error = ("BUILD_PROGRESS_MISMATCH", "构建进度与向量数量不一致")
        elif int(item["min_dimension"]) != int(build["dimension"]) or int(
            item["max_dimension"]
        ) != int(build["dimension"]):
            error = ("EMBEDDING_DIMENSION_MISMATCH", "向量维度与模型配置不一致")
        if error:
            validation_errors.append(
                {
                    "code": error[0],
                    "message": error[1],
                    "document_id": str(item["document_id"]),
                    "title": title,
                }
            )

    current_release = None
    current_items: list[asyncpg.Record] = []
    if build["active_release_id"] is not None:
        current_release = await connection.fetchrow(
            """
            SELECT kr.id, kr.build_id, kr.embedding_profile_id, kr.manifest_hash,
                   kr.state, kr.created_at, ep.model_name, ep.model_revision,
                   ep.dimension, ep.definition_hash AS embedding_definition_hash,
                   me.provider, me.base_url
            FROM kb_releases kr
            JOIN embedding_profiles ep ON ep.id = kr.embedding_profile_id
            JOIN model_endpoints me ON me.id = ep.model_endpoint_id
            WHERE kr.id = $1 AND kr.tenant_id = $2 AND kr.knowledge_base_id = $3
            """,
            build["active_release_id"],
            build["tenant_id"],
            build["knowledge_base_id"],
        )
        current_items = list(
            await connection.fetch(
                """
                SELECT ri.document_id, ri.document_version_id, ri.artifact_id,
                       d.title, dv.version_no
                FROM release_items ri
                JOIN documents d ON d.id = ri.document_id AND d.tenant_id = ri.tenant_id
                JOIN document_versions dv ON dv.id = ri.document_version_id
                  AND dv.tenant_id = ri.tenant_id
                WHERE ri.release_id = $1 ORDER BY ri.document_id
                """,
                build["active_release_id"],
            )
        )

    candidate_dicts = [dict(item) for item in candidate_items]
    manifest_hash = release_manifest_hash(
        knowledge_base_id=int(build["knowledge_base_id"]),
        input_epoch=int(build["input_epoch"]),
        ingestion_profile_id=int(build["ingestion_profile_id"]),
        embedding_profile_id=int(build["embedding_profile_id"]),
        items=candidate_dicts,
    )
    return {
        "build_record": build,
        "candidate_records": candidate_items,
        "manifest_hash": manifest_hash,
        "validation": {"ready": not validation_errors, "errors": validation_errors},
        "diff": release_diff(candidate_dicts, [dict(item) for item in current_items]),
        "current_release_record": current_release,
    }


def _release_preview_response(preview: dict[str, Any]) -> dict[str, Any]:
    build = preview["build_record"]
    current = preview["current_release_record"]
    return {
        "build": {
            "id": str(build["id"]),
            "knowledge_base_id": str(build["knowledge_base_id"]),
            "knowledge_base_name": build["knowledge_base_name"],
            "input_epoch": build["input_epoch"],
            "embedding_profile_id": str(build["embedding_profile_id"]),
            "embedding_definition_hash": build["embedding_definition_hash"],
            "ingestion_profile_id": str(build["ingestion_profile_id"]),
            "ingestion_definition_hash": build["ingestion_definition_hash"],
            "model_name": build["model_name"],
            "model_revision": build["model_revision"],
            "dimension": build["dimension"],
            "provider": build["provider"],
            "base_url": build["base_url"],
            "manifest_hash": preview["manifest_hash"],
        },
        "current_release": (
            {
                "id": str(current["id"]),
                "build_id": str(current["build_id"]),
                "manifest_hash": current["manifest_hash"],
                "state": current["state"],
                "created_at": current["created_at"],
                "embedding_profile_id": str(current["embedding_profile_id"]),
                "embedding_definition_hash": current["embedding_definition_hash"],
                "model_name": current["model_name"],
                "model_revision": current["model_revision"],
                "dimension": current["dimension"],
                "provider": current["provider"],
                "base_url": current["base_url"],
            }
            if current is not None
            else None
        ),
        "expected_active_release_id": (
            str(build["active_release_id"]) if build["active_release_id"] is not None else None
        ),
        "validation": preview["validation"],
        "diff": preview["diff"],
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    app = FastAPI(title="RAGManage", version="0.2.0")
    app.add_middleware(
        RequestIDMiddleware,
    )
    app.add_middleware(StructuredRequestLoggingMiddleware)
    app.add_middleware(
        OpenAIRequestBodyLimitMiddleware,
        max_bytes=OPENAI_CHAT_REQUEST_MAX_BYTES,
    )
    app.add_middleware(
        SessionCsrfMiddleware,
        secret=config.csrf_secret_value,
    )
    app.add_middleware(
        ManagementRateLimitMiddleware,
        redis_url=config.redis_url,
    )

    @app.exception_handler(RequestValidationError)
    async def openai_validation_errors(
        request: Request,
        error: RequestValidationError,
    ) -> Response:
        """只改写 OpenAI 入口的验证错误，避免影响管理 API 的既有响应契约。"""
        if request.url.path == "/v1/chat/completions":
            return JSONResponse(
                status_code=422,
                content=_openai_error_payload("invalid_request", "请求参数无效"),
                headers={"X-Error-Code": "validation_error"},
            )
        response = await request_validation_exception_handler(request, error)
        response.headers["X-Error-Code"] = "validation_error"
        return response

    @app.exception_handler(HTTPException)
    async def standard_http_exception(request: Request, error: HTTPException) -> Response:
        """统一 HTTP 业务异常的错误码响应头，同时保留原 detail 契约。"""
        response = await http_exception_handler(request, error)
        response.headers["X-Error-Code"] = _standard_error_code(error.status_code)
        return response

    # 路由按领域拆分，应用工厂只负责基础设施和错误处理。
    from app.api.health_chat_routes import register as register_health_chat
    from app.api.identity_routes import register as register_identity
    from app.api.platform_routes import register as register_platform
    from app.api.knowledge_routes import register as register_knowledge
    from app.api.retrieval_routes import register as register_retrieval
    from app.api.lifecycle_routes import register as register_lifecycle
    from app.api.wiki_routes import register as register_wiki

    register_health_chat(app, config)
    register_identity(app, config)
    register_platform(app, config)
    register_knowledge(app, config)
    register_retrieval(app, config)
    register_lifecycle(app, config)
    register_wiki(app, config)

    return app


async def _create_knowledge_base(
    connection: asyncpg.Connection, payload: KnowledgeBaseCreate, user_id: int
) -> dict[str, Any]:
    row = await connection.fetchrow(
        """
        INSERT INTO knowledge_bases(
          tenant_id, name, description, purpose, business_scenario, target_users,
          owner_user_id, trust_level, valid_from, valid_until, source_system,
          business_tags, created_by
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
        RETURNING id, tenant_id, name, description, purpose, status, updated_at,
                  business_scenario, target_users, owner_user_id, trust_level,
                  valid_from, valid_until, source_system, business_tags
        """,
        payload.tenant_id,
        payload.name,
        payload.description,
        payload.purpose,
        payload.business_scenario,
        payload.target_users,
        payload.owner_user_id or user_id,
        payload.trust_level,
        payload.valid_from,
        payload.valid_until,
        payload.source_system,
        payload.business_tags,
        user_id,
    )
    if row is None:
        raise HTTPException(status_code=500, detail="知识库创建失败")
    kb_id = row["id"]
    dataset_id = await connection.fetchval(
        "INSERT INTO datasets(tenant_id, knowledge_base_id, name, is_default) "
        "VALUES ($1, $2, '默认数据集', true) RETURNING id",
        payload.tenant_id,
        kb_id,
    )
    role_id = await connection.fetchval("SELECT id FROM roles WHERE code = 'kb_admin'")
    await connection.execute(
        "INSERT INTO kb_members(tenant_id, knowledge_base_id, user_id, role_id) "
        "VALUES ($1, $2, $3, $4)",
        payload.tenant_id,
        kb_id,
        user_id,
        role_id,
    )
    return {
        **dict(row),
        "id": str(row["id"]),
        "tenant_id": str(row["tenant_id"]),
        "dataset_id": str(dataset_id),
    }


# 路由模块通过这个内部导出表共享稳定的应用契约，避免复制鉴权、数据访问和错误转换逻辑。
__all__ = [name for name in globals() if name != "__builtins__"]

app = create_app()
