"""RAGManage HTTP API 入口，负责认证、租户业务接口与事务边界编排。"""

import hashlib
import json
import secrets
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, cast
from urllib.parse import urlparse
from uuid import UUID

import asyncpg
import httpx
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, SecretStr, field_validator

from app.core.api_keys import decrypt_api_key, encrypt_api_key, generate_api_key
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
from app.core.health import check_dependencies
from app.core.runtime_settings import load_persisted_model_gateway_key, persist_model_gateway_key
from app.integrations.open_webui import OpenWebUIAdminClient, OpenWebUIProvisioningError
from app.rag.chat import load_run_snapshot, stream_generation_run
from app.rag.models import ModelGatewayClient
from app.rag.profiles import embedding_profile_definition, gateway_settings, profile_hash
from app.rag.releases import release_diff, release_manifest_hash, rollback_candidate_ids
from app.rag.retrieval import RetrievalServiceError, execute_vector_search

ALLOWED_DOCUMENT_TYPES = {
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
}
MAX_DOCUMENT_SIZE = 50 * 1024 * 1024
# 管理页只加载最近流水，累计值始终由数据库对全部记录聚合。
API_KEY_USAGE_RECENT_LIMIT = 200


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
    sort_order: int | None = Field(default=None, ge=0, le=9999)
    visible: bool | None = None
    status: str | None = Field(default=None, pattern=r"^(active|disabled)$")


class UserPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    status: str | None = Field(default=None, pattern=r"^(active|disabled)$")
    password: str | None = Field(default=None, min_length=8, max_length=200)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class KnowledgeBaseCreate(BaseModel):
    tenant_id: int
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=1000)
    purpose: str = Field(default="general", min_length=2, max_length=80)


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
    knowledge_base_id: int
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=10, ge=1, le=20)
    context_max_chars: int = Field(default=6000, ge=1000, le=20000)

    @field_validator("query")
    @classmethod
    def query_must_contain_text(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("问题不能为空")
        return query


class ConversationCreate(BaseModel):
    knowledge_base_id: int
    title: str = Field(default="新会话", min_length=1, max_length=200)


class RunCreate(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    request_id: UUID

    @field_validator("question")
    @classmethod
    def question_must_contain_text(cls, value: str) -> str:
        question = value.strip()
        if not question:
            raise ValueError("问题不能为空")
        return question


class RunRetryRequest(BaseModel):
    request_id: UUID


class FeedbackCreate(BaseModel):
    rating: str = Field(pattern=r"^(helpful|not_helpful)$")
    reason: str | None = Field(default=None, max_length=200)


class ModelEndpointCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    provider: str = Field(default="open_webui", pattern=r"^[a-z0-9_-]{2,40}$")
    endpoint_type: str = Field(pattern=r"^(generation|embedding|reranker)$")
    base_url: str = Field(min_length=8, max_length=300)
    secret_ref: str = Field(default="env:MODEL_GATEWAY_API_KEY", max_length=200)
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
        if value != "env:MODEL_GATEWAY_API_KEY":
            raise ValueError("当前仅支持环境变量 MODEL_GATEWAY_API_KEY")
        return value

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


class OpenWebUIKeyProvisioningError(HTTPException):
    """把远端 Open WebUI 创建失败转换为稳定的管理接口错误。"""

    def __init__(self, detail: str) -> None:
        super().__init__(status_code=502, detail=detail)


class ApiKeyStatusPatch(BaseModel):
    """平台管理员快速切换公司 API Key 的启用状态。"""

    status: str = Field(pattern=r"^(active|disabled)$")


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
    if path == "/api/v1/knowledge-bases":
        return request.method == "GET"
    if path == "/api/v1/conversations":
        return request.method in {"GET", "POST"}
    if path.startswith("/api/v1/conversations/"):
        return request.method in {"GET", "POST"}
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
    """仅允许浏览器登录的平台管理员管理系统凭据，禁止 API Key 提权。"""
    if context["user"]["platform_role"] != "platform_admin" or "api_key_id" in context:
        raise HTTPException(status_code=403, detail="只有超级管理员可以管理公司 API Key")


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
                   'customer_reader' AS tenant_role, NULL::text AS knowledge_base_role
            FROM knowledge_bases kb
            JOIN tenants t ON t.id = kb.tenant_id AND t.status = 'active'
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


async def _create_generation_run(
    connection: asyncpg.Connection,
    *,
    conversation: asyncpg.Record,
    user_id: int,
    request_id: UUID,
    question: str,
    user_message_id: int | None = None,
    api_key_id: str | None = None,
) -> dict[str, Any]:
    """创建幂等问答运行，并把客户调用固定绑定到发起请求的 API Key。"""
    if api_key_id is not None:
        # 同一 Key/request_id 的并发创建在查询前串行化，避免两边都创建消息后才撞唯一索引。
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
          assistant_message_id, release_id, request_id, api_key_id
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
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
    name = Path(filename or "未命名文档").name.strip()
    return name[:240] or "未命名文档"


async def _read_upload(upload: UploadFile, suffix: str) -> bytes:
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
    if suffix in {".md", ".txt"}:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise HTTPException(status_code=415, detail="文本文件必须使用 UTF-8 编码") from error
        if "\x00" in text or "\ufffd" in text:
            raise HTTPException(status_code=415, detail="文本文件包含不可读取的内容")
    elif suffix == ".pdf" and not raw.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="文件头不是有效的 PDF")
    elif suffix == ".docx" and not raw.startswith(b"PK"):
        raise HTTPException(status_code=415, detail="文件头不是有效的 DOCX")
    if not raw:
        raise HTTPException(status_code=422, detail="不能上传空文件")
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
    # 系统内替换的密钥只驻留当前 API 进程，接口永不返回明文；重启后回退到环境变量。
    runtime_gateway_key_configured = False

    app = FastAPI(title="RAGManage", version="0.2.0")

    @app.get("/api/v1/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/health/ready")
    async def ready() -> JSONResponse:
        checks = await check_dependencies(config)
        healthy = all(value == "ok" for value in checks.values())
        return JSONResponse(
            status_code=200 if healthy else 503,
            content={"status": "ready" if healthy else "not_ready", "checks": checks},
        )

    @app.post("/api/v1/auth/login")
    async def login(payload: dict[str, str], response: Response) -> dict[str, Any]:
        context = await authenticate(config, payload.get("login", ""), payload.get("password", ""))
        if context is None:
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        token = context.pop("token")
        response.set_cookie(
            SESSION_COOKIE,
            token,
            httponly=True,
            samesite="lax",
            secure=config.cookie_secure,
            max_age=config.session_ttl_hours * 3600,
        )
        return context

    @app.post("/api/v1/auth/logout", status_code=204)
    async def logout(request: Request, response: Response) -> None:
        await revoke_token(config, request.cookies.get(SESSION_COOKIE))
        response.delete_cookie(SESSION_COOKIE)

    @app.get("/api/v1/auth/me")
    async def me(request: Request) -> dict[str, Any]:
        return await _authenticated_user(config, request)

    @app.post("/api/v1/auth/password", status_code=204)
    async def change_password(
        payload: PasswordChange, request: Request, response: Response
    ) -> None:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            user_id = int(context["user"]["id"])
            password_hash = await connection.fetchval(
                "SELECT password_hash FROM users WHERE id = $1", user_id
            )
            try:
                password_hasher.verify(password_hash, payload.current_password)
            except (VerifyMismatchError, VerificationError, InvalidHashError) as error:
                raise HTTPException(status_code=400, detail="当前密码不正确") from error
            if payload.current_password == payload.new_password:
                raise HTTPException(status_code=400, detail="新密码不能与当前密码相同")
            async with connection.transaction():
                await connection.execute(
                    "UPDATE users SET password_hash = $2, updated_at = now() WHERE id = $1",
                    user_id,
                    password_hasher.hash(payload.new_password),
                )
                revoked_sessions = await connection.fetchval(
                    """
                    WITH revoked AS (
                      UPDATE sessions SET revoked_at = now()
                      WHERE user_id = $1 AND revoked_at IS NULL
                      RETURNING id
                    ) SELECT count(*)::int FROM revoked
                    """,
                    user_id,
                )
                await connection.execute(
                    """
                    INSERT INTO audit_logs(
                      actor_id, action, target_type, target_id, change_summary
                    ) VALUES ($1, 'auth.password.changed', 'user', $2, $3::jsonb)
                    """,
                    user_id,
                    str(user_id),
                    json.dumps(
                        {"revoked_sessions": int(revoked_sessions or 0)},
                        ensure_ascii=False,
                    ),
                )
            response.delete_cookie(SESSION_COOKIE)
        finally:
            await connection.close()

    @app.get("/api/v1/api-keys")
    async def list_api_keys(request: Request) -> dict[str, Any]:
        """列出公司发放的 Key 及输入/输出/总额度，不返回明文 Key。"""
        context = await _authenticated_user(config, request)
        _require_platform_admin(context)
        connection = await _database(config)
        try:
            rows = await connection.fetch(
                """
                SELECT ak.id::text, ak.tenant_id::text, t.name AS tenant_name,
                       ak.name, ak.provider, ak.key_prefix, ak.token_limit, ak.token_used,
                       ak.token_reserved,
                       GREATEST(0, ak.token_limit - ak.token_used - ak.token_reserved)
                         AS token_remaining,
                       CASE WHEN ak.status = 'active' AND ak.expires_at IS NOT NULL
                                  AND ak.expires_at <= now()
                            THEN 'expired' ELSE ak.status END AS status,
                       COALESCE(usage_totals.prompt_tokens, 0)::bigint AS prompt_tokens,
                       COALESCE(usage_totals.completion_tokens, 0)::bigint
                         AS completion_tokens,
                       ak.expires_at, ak.last_used_at, ak.created_at, ak.revoked_at
                FROM api_keys ak
                JOIN tenants t ON t.id = ak.tenant_id
                LEFT JOIN LATERAL (
                  SELECT sum(usage.prompt_tokens) AS prompt_tokens,
                         sum(usage.completion_tokens) AS completion_tokens
                  FROM api_key_usage usage WHERE usage.api_key_id = ak.id
                ) usage_totals ON true
                WHERE ak.deleted_at IS NULL
                ORDER BY ak.created_at DESC, ak.id DESC
                """
            )
            return {"items": [dict(row) for row in rows]}
        finally:
            await connection.close()

    @app.post("/api/v1/api-keys", status_code=201)
    async def create_api_key(payload: ApiKeyCreate, request: Request) -> dict[str, Any]:
        """为医院创建一次性展示的 Open WebUI 原生 Key，并绑定 Token 配额。

        启用 Open WebUI provisioning 时，远端服务账号和 ``sk-`` Key 是真实来源；
        未启用时保留本地生成模式，便于开发环境和迁移期间继续运行旧数据。
        """
        context = await _authenticated_user(config, request)
        _require_platform_admin(context)
        connection = await _database(config)
        raw_key: str
        provider = "local"
        provider_user_id: str | None = None
        provider_user_email: str | None = None
        provider_user_password: str | None = None
        existing_service_email: str | None = None
        existing_service_password: str | None = None
        try:
            tenant_name = await connection.fetchval(
                "SELECT name FROM tenants WHERE id = $1 AND status = 'active'",
                payload.tenant_id,
            )
            if tenant_name is None:
                raise HTTPException(status_code=404, detail="客户空间不存在或已停用")
            if config.open_webui_provisioning_enabled:
                # 服务账号由平台级网关 Key 通过管理员接口创建；医院不会接触该 Key。
                await load_persisted_model_gateway_key(config)
                if not config.model_gateway_api_key.get_secret_value().strip():
                    raise OpenWebUIKeyProvisioningError("全局模型网关 Key 未配置")
                existing = await connection.fetchval(
                    """
                    SELECT id FROM api_keys
                    WHERE tenant_id = $1 AND provider = 'open_webui' AND deleted_at IS NULL
                    """,
                    payload.tenant_id,
                )
                if existing is not None:
                    raise HTTPException(
                        status_code=409, detail="该医院已经存在模型网关 Key，请先删除或轮换"
                    )
                previous = await connection.fetchrow(
                    """
                    SELECT provider_user_email, provider_user_password
                    FROM api_keys
                    WHERE tenant_id = $1 AND provider = 'open_webui' AND deleted_at IS NOT NULL
                    ORDER BY deleted_at DESC
                    LIMIT 1
                    """,
                    payload.tenant_id,
                )
                if previous is not None:
                    if not isinstance(previous.get("provider_user_email"), str) or not isinstance(
                        previous.get("provider_user_password"), str
                    ):
                        raise OpenWebUIKeyProvisioningError("历史 Open WebUI 服务账号信息不完整")
                    try:
                        existing_service_password = decrypt_api_key(
                            str(previous["provider_user_password"]),
                            config.api_key_encryption_secret_value,
                        )
                    except ValueError as error:
                        raise HTTPException(
                            status_code=503, detail="API Key 加密配置不可用"
                        ) from error
                    existing_service_email = str(previous["provider_user_email"])
                try:
                    provisioned = await OpenWebUIAdminClient(config).provision_service_key(
                        tenant_id=payload.tenant_id,
                        tenant_name=str(tenant_name),
                        existing_user_email=existing_service_email,
                        existing_user_password=existing_service_password,
                    )
                except (OpenWebUIProvisioningError, httpx.HTTPError) as error:
                    raise OpenWebUIKeyProvisioningError(
                        "Open WebUI 服务账号或 API Key 创建失败"
                    ) from error
                raw_key = provisioned.api_key
                provider = "open_webui"
                provider_user_id = provisioned.user_id
                provider_user_email = provisioned.user_email
                provider_user_password = encrypt_api_key(
                    provisioned.user_password,
                    config.api_key_encryption_secret_value,
                )
            else:
                raw_key, _, _ = generate_api_key()
            key_prefix = f"{raw_key[:12]}…{raw_key[-4:]}"
            key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
            async with connection.transaction():
                if provider == "open_webui":
                    existing = await connection.fetchval(
                        "SELECT id FROM api_keys WHERE tenant_id = $1 AND deleted_at IS NULL",
                        payload.tenant_id,
                    )
                    if existing is not None:
                        raise HTTPException(
                            status_code=409, detail="该医院已经存在模型网关 Key，请先删除或轮换"
                        )
                row = await connection.fetchrow(
                    """
                    INSERT INTO api_keys(
                      tenant_id, name, key_prefix, key_hash, encrypted_key,
                      token_limit, expires_at, created_by, provider,
                      provider_user_id, provider_user_email, provider_user_password
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    RETURNING id::text, tenant_id::text, name, key_prefix, token_limit,
                              token_used, token_reserved, expires_at, created_at
                    """,
                    payload.tenant_id,
                    payload.name,
                    key_prefix,
                    key_hash,
                    encrypt_api_key(raw_key, config.api_key_encryption_secret_value),
                    payload.token_limit,
                    payload.expires_at,
                    int(context["user"]["id"]),
                    provider,
                    provider_user_id,
                    provider_user_email,
                    provider_user_password,
                )
                if row is None:
                    raise HTTPException(status_code=500, detail="API Key 创建失败")
                await write_audit_event(
                    connection,
                    tenant_id=payload.tenant_id,
                    actor_id=int(context["user"]["id"]),
                    action="api_key.create",
                    target_type="api_key",
                    target_id=row["id"],
                    summary={"name": payload.name, "token_limit": payload.token_limit},
                )
            return {
                **dict(row),
                "tenant_name": tenant_name,
                "provider": provider,
                "token_remaining": payload.token_limit,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "last_used_at": None,
                "revoked_at": None,
                "status": "active",
                "raw_key": raw_key,
            }
        finally:
            await connection.close()

    @app.get("/api/v1/api-keys/{api_key_id}/key")
    async def reveal_api_key(api_key_id: int, request: Request) -> dict[str, Any]:
        """仅平台管理员通过显式接口复制完整 Key，并记录一次读取审计。"""
        context = await _authenticated_user(config, request)
        _require_platform_admin(context)
        connection = await _database(config)
        try:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    SELECT id::text, tenant_id, name, encrypted_key
                    FROM api_keys WHERE id = $1 AND deleted_at IS NULL
                    FOR SHARE
                    """,
                    api_key_id,
                )
                if row is None:
                    raise HTTPException(status_code=404, detail="API Key 不存在")
                if not row["encrypted_key"]:
                    raise HTTPException(
                        status_code=409,
                        detail="该 Key 创建于复制功能上线前，请重新发放 API Key",
                    )
                try:
                    raw_key = decrypt_api_key(
                        str(row["encrypted_key"]), config.api_key_encryption_secret_value
                    )
                except ValueError as error:
                    raise HTTPException(status_code=503, detail="API Key 加密配置不可用") from error
                await write_audit_event(
                    connection,
                    tenant_id=int(row["tenant_id"]),
                    actor_id=int(context["user"]["id"]),
                    action="api_key.reveal",
                    target_type="api_key",
                    target_id=row["id"],
                    summary={"name": row["name"]},
                )
            return {"id": row["id"], "name": row["name"], "raw_key": raw_key}
        finally:
            await connection.close()

    @app.patch("/api/v1/api-keys/{api_key_id}/status")
    async def update_api_key_status(
        api_key_id: int,
        payload: ApiKeyStatusPatch,
        request: Request,
    ) -> dict[str, Any]:
        """管理员快速启用或停用 Key；停用不会清除历史用量。"""
        context = await _authenticated_user(config, request)
        _require_platform_admin(context)
        connection = await _database(config)
        try:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    UPDATE api_keys
                    SET status = $2::varchar,
                        revoked_at = CASE WHEN $2::varchar = 'active' THEN NULL ELSE revoked_at END
                    WHERE id = $1 AND deleted_at IS NULL AND status IN ('active', 'disabled')
                    RETURNING id::text, tenant_id::text, name, status, revoked_at
                    """,
                    api_key_id,
                    payload.status,
                )
                if row is None:
                    raise HTTPException(
                        status_code=409,
                        detail="只有启用或停用状态的 API Key 可以切换",
                    )
                await write_audit_event(
                    connection,
                    tenant_id=int(row["tenant_id"]),
                    actor_id=int(context["user"]["id"]),
                    action="api_key.status.update",
                    target_type="api_key",
                    target_id=row["id"],
                    summary={"name": row["name"], "status": payload.status},
                )
            return dict(row)
        finally:
            await connection.close()

    @app.delete("/api/v1/api-keys/{api_key_id}")
    async def delete_api_key(api_key_id: int, request: Request) -> dict[str, Any]:
        """管理员删除 Key；远端撤销成功后再软删除并保留 Token 历史。"""
        context = await _authenticated_user(config, request)
        _require_platform_admin(context)
        connection = await _database(config)
        try:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    UPDATE api_keys
                    SET deleted_at = now(), status = 'revoked',
                        revoked_at = COALESCE(revoked_at, now())
                    WHERE id = $1 AND deleted_at IS NULL
                    RETURNING id::text, tenant_id::text, name, status, deleted_at,
                              provider, provider_user_email, provider_user_password
                    """,
                    api_key_id,
                )
                if row is None:
                    raise HTTPException(status_code=404, detail="API Key 不存在或已删除")
                if row.get("provider", "local") == "open_webui":
                    email = row.get("provider_user_email")
                    encrypted_password = row.get("provider_user_password")
                    if not isinstance(email, str) or not isinstance(encrypted_password, str):
                        raise HTTPException(status_code=503, detail="Open WebUI 服务账号信息不完整")
                    try:
                        password = decrypt_api_key(
                            encrypted_password,
                            config.api_key_encryption_secret_value,
                        )
                    except ValueError as error:
                        raise HTTPException(
                            status_code=503, detail="API Key 加密配置不可用"
                        ) from error
                    try:
                        await OpenWebUIAdminClient(config).revoke_service_key(
                            user_email=email,
                            user_password=password,
                        )
                    except (OpenWebUIProvisioningError, httpx.HTTPError) as error:
                        raise OpenWebUIKeyProvisioningError(
                            "Open WebUI 原生 API Key 撤销失败，本地 Key 未删除"
                        ) from error
                await write_audit_event(
                    connection,
                    tenant_id=int(row["tenant_id"]),
                    actor_id=int(context["user"]["id"]),
                    action="api_key.delete",
                    target_type="api_key",
                    target_id=row["id"],
                    summary={"name": row["name"]},
                )
            return dict(row)
        finally:
            await connection.close()

    @app.post("/api/v1/api-keys/{api_key_id}/revoke")
    async def revoke_api_key(api_key_id: int, request: Request) -> dict[str, Any]:
        """撤销公司 API Key；撤销后已发放的明文 Key 立即失效。"""
        context = await _authenticated_user(config, request)
        _require_platform_admin(context)
        connection = await _database(config)
        try:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    UPDATE api_keys SET status = 'revoked', revoked_at = now()
                    WHERE id = $1 AND status = 'active'
                    RETURNING id::text, tenant_id::text, name, status, revoked_at
                    """,
                    api_key_id,
                )
                if row is None:
                    raise HTTPException(status_code=404, detail="可撤销的 API Key 不存在")
                await write_audit_event(
                    connection,
                    tenant_id=int(row["tenant_id"]),
                    actor_id=int(context["user"]["id"]),
                    action="api_key.revoke",
                    target_type="api_key",
                    target_id=row["id"],
                    summary={"name": row["name"]},
                )
            return dict(row)
        finally:
            await connection.close()

    @app.get("/api/v1/api-keys/{api_key_id}/usage")
    async def list_api_key_usage(api_key_id: int, request: Request) -> dict[str, Any]:
        """返回某个公司 API Key 的输入、输出、总 Token 用量流水。"""
        context = await _authenticated_user(config, request)
        _require_platform_admin(context)
        connection = await _database(config)
        try:
            summary = await connection.fetchrow(
                """
                SELECT count(usage.id)::int AS request_count,
                       COALESCE(sum(usage.prompt_tokens), 0)::bigint AS prompt_tokens,
                       COALESCE(sum(usage.completion_tokens), 0)::bigint AS completion_tokens,
                       COALESCE(sum(usage.total_tokens), 0)::bigint AS total_tokens
                FROM api_keys key
                LEFT JOIN api_key_usage usage ON usage.api_key_id = key.id
                WHERE key.id = $1
                GROUP BY key.id
                """,
                api_key_id,
            )
            if summary is None:
                raise HTTPException(status_code=404, detail="API Key 不存在")
            rows = await connection.fetch(
                """
                SELECT request_id::text, model_name, prompt_tokens, completion_tokens,
                       total_tokens, usage_source, model_usage, status,
                       created_at, completed_at
                FROM api_key_usage WHERE api_key_id = $1
                ORDER BY created_at DESC LIMIT 200
                """,
                api_key_id,
            )
            return {
                "summary": dict(summary),
                "recent_limit": API_KEY_USAGE_RECENT_LIMIT,
                "items": [dict(row) for row in rows],
            }
        finally:
            await connection.close()

    @app.get("/api/v1/model-endpoints")
    async def list_model_endpoints(request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        if context["user"]["platform_role"] != "platform_admin":
            raise HTTPException(status_code=403, detail="只有平台管理员可以管理模型端点")
        connection = await _database(config)
        try:
            rows = await connection.fetch(
                """
                SELECT id::text, tenant_id::text, name, provider, endpoint_type, base_url,
                       secret_ref, allowed_models, health_status, status, last_checked_at,
                       last_latency_ms, last_error, observed_dimension, created_at, updated_at
                FROM model_endpoints
                ORDER BY status, endpoint_type, updated_at DESC, id DESC
                """
            )
            items = []
            for row in rows:
                item = dict(row)
                item["allowed_models"] = _json_value(item["allowed_models"], [])
                item["secret_configured"] = bool(item.pop("secret_ref", None))
                items.append(item)
            return {"items": items}
        finally:
            await connection.close()

    @app.get("/api/v1/model-gateway-key")
    async def get_model_gateway_key(request: Request) -> dict[str, Any]:
        """返回模型网关密钥的脱敏状态，供超级管理员确认当前生效来源。"""
        context = await _authenticated_user(config, request)
        _require_platform_admin(context)
        # 页面打开时同步数据库覆盖环境变量，确保重启后的系统状态可见。
        from app.core.runtime_settings import load_persisted_model_gateway_key

        await load_persisted_model_gateway_key(config)
        value = config.model_gateway_api_key.get_secret_value()
        source = "system" if runtime_gateway_key_configured else "environment"
        return {
            "configured": bool(value),
            "source": source,
            "masked": f"••••••••{value[-4:]}" if len(value) >= 4 else ("••••" if value else ""),
        }

    @app.put("/api/v1/model-gateway-key")
    async def update_model_gateway_key(
        payload: ModelGatewayKeyUpdate,
        request: Request,
    ) -> dict[str, Any]:
        """替换当前 API 进程使用的模型网关密钥，成功后后续请求立即使用新值。"""
        nonlocal runtime_gateway_key_configured
        context = await _authenticated_user(config, request)
        _require_platform_admin(context)
        config.model_gateway_api_key = payload.api_key
        await persist_model_gateway_key(
            config,
            payload.api_key.get_secret_value(),
            int(context["user"]["id"]),
        )
        config.model_gateway_key_refresh_attempted = True
        runtime_gateway_key_configured = True
        value = payload.api_key.get_secret_value()
        return {
            "configured": True,
            "source": "system",
            "masked": f"••••••••{value[-4:]}",
        }

    @app.post("/api/v1/model-endpoints", status_code=201)
    async def create_model_endpoint(
        payload: ModelEndpointCreate,
        request: Request,
    ) -> dict[str, Any]:
        """登记平台级模型端点，并记录不包含密钥引用值的配置审计。"""
        context = await _authenticated_user(config, request)
        if context["user"]["platform_role"] != "platform_admin":
            raise HTTPException(status_code=403, detail="只有平台管理员可以登记模型端点")
        unknown_models = set(payload.allowed_models) - config.allowed_model_names
        if unknown_models:
            raise HTTPException(
                status_code=422,
                detail=f"模型不在网关白名单中：{'、'.join(sorted(unknown_models))}",
            )
        connection = await _database(config)
        try:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    INSERT INTO model_endpoints(
                      tenant_id, name, provider, endpoint_type, base_url,
                      secret_ref, allowed_models, status
                    ) VALUES (NULL, $1, $2, $3, $4, $5, $6::jsonb, 'active')
                    RETURNING id::text, tenant_id::text, name, provider, endpoint_type,
                              base_url, allowed_models, health_status, status,
                              last_checked_at, last_latency_ms, last_error,
                              observed_dimension, created_at, updated_at
                    """,
                    payload.name,
                    payload.provider,
                    payload.endpoint_type,
                    payload.base_url,
                    payload.secret_ref,
                    json.dumps(payload.allowed_models, ensure_ascii=False),
                )
                await connection.execute(
                    """
                    INSERT INTO audit_logs(
                      actor_id, action, target_type, target_id, change_summary
                    ) VALUES ($1, 'model_endpoint.create', 'model_endpoint', $2, $3::jsonb)
                    """,
                    int(context["user"]["id"]),
                    row["id"],
                    json.dumps(
                        {
                            "name": payload.name,
                            "endpoint_type": payload.endpoint_type,
                            "allowed_models": payload.allowed_models,
                        },
                        ensure_ascii=False,
                    ),
                )
            result = dict(row)
            result["allowed_models"] = _json_value(result["allowed_models"], [])
            result["secret_configured"] = True
            return result
        except asyncpg.UniqueViolationError as error:
            raise HTTPException(status_code=409, detail="相同用途和地址的端点已经存在") from error
        finally:
            await connection.close()

    @app.patch("/api/v1/model-endpoints/{endpoint_id}")
    async def update_model_endpoint(
        endpoint_id: int,
        payload: ModelEndpointPatch,
        request: Request,
    ) -> dict[str, Any]:
        """更新模型端点安全字段，并在同一事务记录脱敏的配置前后状态。"""
        context = await _authenticated_user(config, request)
        if context["user"]["platform_role"] != "platform_admin":
            raise HTTPException(status_code=403, detail="只有平台管理员可以编辑模型端点")
        values = payload.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=400, detail="没有需要修改的字段")
        models = values.get("allowed_models")
        if models is not None:
            unknown_models = set(models) - config.allowed_model_names
            if unknown_models:
                raise HTTPException(
                    status_code=422,
                    detail=f"模型不在网关白名单中：{'、'.join(sorted(unknown_models))}",
                )
            values["allowed_models"] = json.dumps(models, ensure_ascii=False)
        assignments: list[str] = []
        parameters: list[Any] = [endpoint_id]
        for index, (key, value) in enumerate(values.items(), 2):
            cast_suffix = "::jsonb" if key == "allowed_models" else ""
            assignments.append(f"{key} = ${index}{cast_suffix}")
            parameters.append(value)
        connection = await _database(config)
        try:
            async with connection.transaction():
                # 锁定端点确保审计 before 与本次更新属于同一并发版本；密钥引用值不进入摘要。
                before = await connection.fetchrow(
                    """
                    SELECT id, name, base_url, allowed_models, status, secret_ref
                    FROM model_endpoints WHERE id = $1 FOR UPDATE
                    """,
                    endpoint_id,
                )
                if before is None:
                    raise HTTPException(status_code=404, detail="模型端点不存在")
                row = await connection.fetchrow(
                    f"""
                    UPDATE model_endpoints
                    SET {", ".join(assignments)}, health_status = 'unknown',
                        last_error = NULL, updated_at = now()
                    WHERE id = $1
                    RETURNING id::text, tenant_id::text, name, provider, endpoint_type,
                              base_url, allowed_models, health_status, status,
                              last_checked_at, last_latency_ms, last_error,
                              observed_dimension, created_at, updated_at
                    """,
                    *parameters,
                )
                if row is None:
                    raise HTTPException(status_code=404, detail="模型端点不存在")
                safe_fields = {"name", "base_url", "allowed_models", "status"}
                before_state = {
                    field: (
                        _json_value(before[field], [])
                        if field == "allowed_models"
                        else before[field]
                    )
                    for field in sorted(values)
                    if field in safe_fields
                }
                after_state = {
                    field: (
                        _json_value(row[field], []) if field == "allowed_models" else row[field]
                    )
                    for field in sorted(values)
                    if field in safe_fields
                }
                await connection.execute(
                    """
                    INSERT INTO audit_logs(
                      actor_id, action, target_type, target_id, change_summary
                    ) VALUES ($1, 'model_endpoint.update', 'model_endpoint', $2, $3::jsonb)
                    """,
                    int(context["user"]["id"]),
                    str(endpoint_id),
                    json.dumps(
                        {
                            "fields": sorted(values),
                            "before": before_state,
                            "after": after_state,
                            "secret_ref_changed": "secret_ref" in values,
                        },
                        ensure_ascii=False,
                    ),
                )
            result = dict(row)
            result["allowed_models"] = _json_value(result["allowed_models"], [])
            result["secret_configured"] = True
            return result
        except asyncpg.UniqueViolationError as error:
            raise HTTPException(status_code=409, detail="相同用途和地址的端点已经存在") from error
        finally:
            await connection.close()

    @app.post("/api/v1/model-endpoints/{endpoint_id}/health-check")
    async def check_model_endpoint(
        endpoint_id: int,
        payload: ModelHealthCheckRequest,
        request: Request,
    ) -> dict[str, Any]:
        """真实探测模型端点并保存健康状态；失败只返回统一错误，不泄露网关响应。"""
        context = await _authenticated_user(config, request)
        if context["user"]["platform_role"] != "platform_admin":
            raise HTTPException(status_code=403, detail="只有平台管理员可以检查模型端点")
        connection = await _database(config)
        try:
            endpoint = await connection.fetchrow(
                """
                SELECT id, endpoint_type, base_url, secret_ref, allowed_models, status
                FROM model_endpoints WHERE id = $1
                """,
                endpoint_id,
            )
            if endpoint is None:
                raise HTTPException(status_code=404, detail="模型端点不存在")
            if endpoint["status"] != "active":
                raise HTTPException(status_code=409, detail="已停用端点不能执行健康检查")
            allowed_models = _json_value(endpoint["allowed_models"], [])
            if payload.model_name not in allowed_models:
                raise HTTPException(status_code=422, detail="所选模型不在端点白名单中")
            if endpoint["secret_ref"] != "env:MODEL_GATEWAY_API_KEY":
                raise HTTPException(status_code=409, detail="端点密钥引用当前不可用")
            client = ModelGatewayClient(config)
            # 诊断审计只保留耗时、状态和稳定错误码；探测响应与密钥永远不进入日志。
            check_started = time.perf_counter()
            try:
                if endpoint["endpoint_type"] == "generation":
                    probe = await client.probe_generation(endpoint["base_url"], payload.model_name)
                elif endpoint["endpoint_type"] == "embedding":
                    probe = await client.probe_embedding(endpoint["base_url"], payload.model_name)
                else:
                    await connection.execute(
                        """
                        INSERT INTO audit_logs(
                          tenant_id, actor_id, action, target_type, target_id, change_summary
                        ) VALUES (
                          NULL, $1, 'model_endpoint.health_check',
                          'model_endpoint', $2, $3::jsonb
                        )
                        """,
                        int(context["user"]["id"]),
                        str(endpoint_id),
                        json.dumps(
                            {
                                "model": payload.model_name,
                                "status": "unsupported",
                                "error_code": "UNSUPPORTED_ENDPOINT_TYPE",
                                "latency_ms": round(
                                    (time.perf_counter() - check_started) * 1000,
                                    2,
                                ),
                            },
                            ensure_ascii=False,
                        ),
                    )
                    raise HTTPException(status_code=422, detail="重排端点检查将在后续版本提供")
            except (httpx.HTTPError, ValueError) as error:
                error_code = type(error).__name__
                latency_ms = round((time.perf_counter() - check_started) * 1000, 2)
                # 健康状态和对应审计必须原子提交，避免页面状态变化却没有操作证据。
                async with connection.transaction():
                    await connection.execute(
                        """
                        UPDATE model_endpoints
                        SET health_status = 'unhealthy', last_checked_at = now(),
                            last_error = $2, last_latency_ms = NULL,
                            observed_dimension = NULL, updated_at = now()
                        WHERE id = $1
                        """,
                        endpoint_id,
                        error_code,
                    )
                    await connection.execute(
                        """
                        INSERT INTO audit_logs(
                          tenant_id, actor_id, action, target_type, target_id, change_summary
                        ) VALUES (
                          NULL, $1, 'model_endpoint.health_check',
                          'model_endpoint', $2, $3::jsonb
                        )
                        """,
                        int(context["user"]["id"]),
                        str(endpoint_id),
                        json.dumps(
                            {
                                "model": payload.model_name,
                                "status": "unhealthy",
                                "error_code": error_code,
                                "latency_ms": latency_ms,
                            },
                            ensure_ascii=False,
                        ),
                    )
                return {
                    "status": "unhealthy",
                    "model": payload.model_name,
                    "error": "模型调用失败，请检查地址、密钥和模型服务状态",
                }
            observed_dimension = probe.get("dimension")
            # 成功状态与审计使用同一事务，且平台事件显式保持 tenant_id 为空。
            async with connection.transaction():
                await connection.execute(
                    """
                    UPDATE model_endpoints
                    SET health_status = 'healthy', last_checked_at = now(),
                        last_latency_ms = $2, last_error = NULL,
                        observed_dimension = $3, updated_at = now()
                    WHERE id = $1
                    """,
                    endpoint_id,
                    probe["latency_ms"],
                    observed_dimension,
                )
                await connection.execute(
                    """
                    INSERT INTO audit_logs(
                      tenant_id, actor_id, action, target_type, target_id, change_summary
                    ) VALUES (
                      NULL, $1, 'model_endpoint.health_check',
                      'model_endpoint', $2, $3::jsonb
                    )
                    """,
                    int(context["user"]["id"]),
                    str(endpoint_id),
                    json.dumps(
                        {
                            "model": payload.model_name,
                            "status": "healthy",
                            "latency_ms": probe["latency_ms"],
                            "dimension": observed_dimension,
                        },
                        ensure_ascii=False,
                    ),
                )
            return {"status": "healthy", **probe}
        finally:
            await connection.close()

    @app.get("/api/v1/profiles")
    async def list_profiles(knowledge_base_id: int, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _require_knowledge_base_role(
                connection,
                context,
                knowledge_base_id,
                {"space_admin", "kb_admin"},
            )
            ingestion_rows = await connection.fetch(
                """
                SELECT id::text, definition, definition_hash, created_by::text, created_at
                FROM ingestion_profiles
                WHERE tenant_id = $1 AND knowledge_base_id = $2
                ORDER BY created_at DESC, id DESC
                """,
                access["tenant_id"],
                knowledge_base_id,
            )
            embedding_rows = await connection.fetch(
                """
                SELECT ep.id::text, ep.model_endpoint_id::text, ep.model_name,
                       ep.model_revision, ep.dimension, ep.dtype, ep.instructions,
                       ep.normalization, ep.definition_hash, ep.created_at,
                       me.name AS endpoint_name, me.status AS endpoint_status
                FROM embedding_profiles ep
                JOIN model_endpoints me ON me.id = ep.model_endpoint_id
                WHERE me.tenant_id IS NULL OR me.tenant_id = $1
                ORDER BY ep.created_at DESC, ep.id DESC
                """,
                access["tenant_id"],
            )
            runtime_rows = await connection.fetch(
                """
                SELECT rp.id::text, rp.embedding_profile_id::text, rp.definition,
                       rp.definition_hash, rp.created_by::text, rp.created_at,
                       (kb.active_runtime_id = rp.id) AS active
                FROM runtime_profiles rp
                JOIN knowledge_bases kb ON kb.id = rp.knowledge_base_id
                  AND kb.tenant_id = rp.tenant_id
                WHERE rp.tenant_id = $1 AND rp.knowledge_base_id = $2
                ORDER BY rp.created_at DESC, rp.id DESC
                """,
                access["tenant_id"],
                knowledge_base_id,
            )
            ingestion = []
            for row in ingestion_rows:
                item = dict(row)
                item["definition"] = _json_value(item["definition"], {})
                item["effect_scope"] = "reparse_required"
                ingestion.append(item)
            embedding = []
            for row in embedding_rows:
                item = dict(row)
                item["instructions"] = _json_value(item["instructions"], {})
                item["effect_scope"] = "rebuild_required"
                embedding.append(item)
            runtime = []
            for row in runtime_rows:
                item = dict(row)
                item["definition"] = _json_value(item["definition"], {})
                item["effect_scope"] = "immediate" if item["active"] else "activate_required"
                runtime.append(item)
            return {
                "knowledge_base_id": str(knowledge_base_id),
                "ingestion_profiles": ingestion,
                "embedding_profiles": embedding,
                "runtime_profiles": runtime,
            }
        finally:
            await connection.close()

    @app.post("/api/v1/ingestion-profiles", status_code=201)
    async def create_ingestion_profile(
        payload: IngestionProfileCreate,
        request: Request,
    ) -> dict[str, Any]:
        """创建知识库不可变解析 Profile；重复定义复用且不重复写审计。"""
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _require_knowledge_base_role(
                connection,
                context,
                payload.knowledge_base_id,
                {"space_admin", "kb_admin"},
            )
            definition = {
                "parser": "markdown-it/docx/pdfplumber:v1",
                "chunking": {
                    "strategy": "source-block",
                    "max_chars": payload.max_chars,
                    "overlap_chars": payload.overlap_chars,
                },
                "preserve_locator": payload.preserve_locator,
            }
            definition_hash = profile_hash(definition)
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    INSERT INTO ingestion_profiles(
                      tenant_id, knowledge_base_id, definition, definition_hash, created_by
                    ) VALUES ($1, $2, $3::jsonb, $4, $5)
                    ON CONFLICT (knowledge_base_id, definition_hash) DO NOTHING
                    RETURNING id::text, definition, definition_hash, created_at
                    """,
                    access["tenant_id"],
                    payload.knowledge_base_id,
                    json.dumps(definition, ensure_ascii=False),
                    definition_hash,
                    int(context["user"]["id"]),
                )
                reused = row is None
                if row is None:
                    row = await connection.fetchrow(
                        """
                        SELECT id::text, definition, definition_hash, created_at
                        FROM ingestion_profiles
                        WHERE knowledge_base_id = $1 AND definition_hash = $2
                        """,
                        payload.knowledge_base_id,
                        definition_hash,
                    )
                if not reused:
                    await connection.execute(
                        """
                        INSERT INTO audit_logs(
                          tenant_id, actor_id, action, target_type, target_id, change_summary
                        ) VALUES ($1, $2, 'ingestion_profile.create',
                                  'ingestion_profile', $3, $4::jsonb)
                        """,
                        access["tenant_id"],
                        int(context["user"]["id"]),
                        row["id"],
                        json.dumps(
                            {
                                "knowledge_base_id": str(payload.knowledge_base_id),
                                "definition_hash": definition_hash,
                                "effect_scope": "reparse_required",
                            },
                            ensure_ascii=False,
                        ),
                    )
            result = dict(row)
            result["definition"] = _json_value(result["definition"], {})
            return {**result, "reused": reused, "effect_scope": "reparse_required"}
        finally:
            await connection.close()

    @app.post("/api/v1/embedding-profiles", status_code=201)
    async def create_embedding_profile(
        payload: EmbeddingProfileCreate,
        request: Request,
    ) -> dict[str, Any]:
        """实测嵌入模型后创建平台级不可变 Profile，并记录重建索引影响。"""
        context = await _authenticated_user(config, request)
        if context["user"]["platform_role"] != "platform_admin":
            raise HTTPException(status_code=403, detail="只有平台管理员可以创建嵌入 Profile")
        connection = await _database(config)
        try:
            endpoint = await connection.fetchrow(
                """
                SELECT id, name, endpoint_type, base_url, secret_ref, allowed_models,
                       status, health_status
                FROM model_endpoints WHERE id = $1
                """,
                payload.model_endpoint_id,
            )
            if endpoint is None or endpoint["endpoint_type"] != "embedding":
                raise HTTPException(status_code=404, detail="嵌入模型端点不存在")
            if endpoint["status"] != "active":
                raise HTTPException(status_code=409, detail="嵌入模型端点已停用")
            if payload.model_name not in _json_value(endpoint["allowed_models"], []):
                raise HTTPException(status_code=422, detail="模型不在端点白名单中")
            client = ModelGatewayClient(config)
            try:
                probe = await client.probe_embedding(endpoint["base_url"], payload.model_name)
                revision = await client.model_revision(payload.model_name, endpoint["base_url"])
            except (httpx.HTTPError, ValueError) as error:
                raise HTTPException(status_code=503, detail="嵌入模型实测失败") from error
            dimension = int(probe["dimension"])
            if payload.expected_dimension is not None and payload.expected_dimension != dimension:
                raise HTTPException(
                    status_code=409,
                    detail=f"实测维度为 {dimension}，与期望维度不一致",
                )
            definition = {
                "provider": "open_webui",
                "base_url": str(endpoint["base_url"]).rstrip("/"),
                "secret_ref": "env:MODEL_GATEWAY_API_KEY",
                "model": payload.model_name,
                "model_revision": revision,
                "dimension": dimension,
                "dtype": "float32",
                "normalization": payload.normalization,
                "instructions": {
                    "query": payload.query_instruction,
                    "document": payload.document_instruction,
                },
            }
            definition_hash = profile_hash(definition)
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    INSERT INTO embedding_profiles(
                      model_endpoint_id, model_name, model_revision, dimension, dtype,
                      instructions, normalization, definition_hash
                    ) VALUES ($1, $2, $3, $4, 'float32', $5::jsonb, $6, $7)
                    ON CONFLICT (definition_hash) DO NOTHING
                    RETURNING id::text, model_endpoint_id::text, model_name, model_revision,
                              dimension, dtype, instructions, normalization,
                              definition_hash, created_at
                    """,
                    payload.model_endpoint_id,
                    payload.model_name,
                    revision,
                    dimension,
                    json.dumps(definition["instructions"], ensure_ascii=False),
                    payload.normalization,
                    definition_hash,
                )
                reused = row is None
                if row is None:
                    row = await connection.fetchrow(
                        """
                        SELECT id::text, model_endpoint_id::text, model_name, model_revision,
                               dimension, dtype, instructions, normalization,
                               definition_hash, created_at
                        FROM embedding_profiles WHERE definition_hash = $1
                        """,
                        definition_hash,
                    )
                if not reused:
                    await connection.execute(
                        """
                        INSERT INTO audit_logs(
                          actor_id, action, target_type, target_id, change_summary
                        ) VALUES ($1, 'embedding_profile.create',
                                  'embedding_profile', $2, $3::jsonb)
                        """,
                        int(context["user"]["id"]),
                        row["id"],
                        json.dumps(
                            {
                                "model_endpoint_id": str(payload.model_endpoint_id),
                                "model": payload.model_name,
                                "model_revision": revision,
                                "dimension": dimension,
                                "definition_hash": definition_hash,
                                "effect_scope": "rebuild_required",
                            },
                            ensure_ascii=False,
                        ),
                    )
            result = dict(row)
            result["instructions"] = _json_value(result["instructions"], {})
            return {**result, "reused": reused, "effect_scope": "rebuild_required"}
        finally:
            await connection.close()

    @app.post("/api/v1/runtime-profiles", status_code=201)
    async def create_runtime_profile(
        payload: RuntimeProfileCreate,
        request: Request,
    ) -> dict[str, Any]:
        """创建知识库不可变运行 Profile，审计只记录引用和哈希而不保存回答规则正文。"""
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _require_knowledge_base_role(
                connection,
                context,
                payload.knowledge_base_id,
                {"space_admin", "kb_admin"},
            )
            embedding = await connection.fetchrow(
                """
                SELECT ep.id, ep.model_name, ep.dimension, me.status AS endpoint_status
                FROM embedding_profiles ep
                JOIN model_endpoints me ON me.id = ep.model_endpoint_id
                WHERE ep.id = $1 AND (me.tenant_id IS NULL OR me.tenant_id = $2)
                """,
                payload.embedding_profile_id,
                access["tenant_id"],
            )
            generation = await connection.fetchrow(
                """
                SELECT id, name, allowed_models, status
                FROM model_endpoints
                WHERE id = $1 AND endpoint_type = 'generation'
                  AND (tenant_id IS NULL OR tenant_id = $2)
                """,
                payload.generation_endpoint_id,
                access["tenant_id"],
            )
            if embedding is None or embedding["endpoint_status"] != "active":
                raise HTTPException(status_code=409, detail="嵌入 Profile 或端点不可用")
            if generation is None or generation["status"] != "active":
                raise HTTPException(status_code=409, detail="生成模型端点不可用")
            if payload.generation_model not in _json_value(generation["allowed_models"], []):
                raise HTTPException(status_code=422, detail="生成模型不在端点白名单中")
            definition = {
                "retrieval": {
                    "mode": "vector",
                    "top_k": payload.top_k,
                    "context_max_chars": payload.context_max_chars,
                },
                "generation": {
                    "endpoint_id": payload.generation_endpoint_id,
                    "model": payload.generation_model,
                    "temperature": payload.temperature,
                },
                "answer_rules": payload.answer_rules,
            }
            definition_hash = profile_hash(
                {**definition, "embedding_profile_id": payload.embedding_profile_id}
            )
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    INSERT INTO runtime_profiles(
                      tenant_id, knowledge_base_id, embedding_profile_id,
                      definition, definition_hash, created_by
                    ) VALUES ($1, $2, $3, $4::jsonb, $5, $6)
                    ON CONFLICT (knowledge_base_id, definition_hash) DO NOTHING
                    RETURNING id::text, embedding_profile_id::text, definition,
                              definition_hash, created_at
                    """,
                    access["tenant_id"],
                    payload.knowledge_base_id,
                    payload.embedding_profile_id,
                    json.dumps(definition, ensure_ascii=False),
                    definition_hash,
                    int(context["user"]["id"]),
                )
                reused = row is None
                if row is None:
                    row = await connection.fetchrow(
                        """
                        SELECT id::text, embedding_profile_id::text, definition,
                               definition_hash, created_at
                        FROM runtime_profiles
                        WHERE knowledge_base_id = $1 AND definition_hash = $2
                        """,
                        payload.knowledge_base_id,
                        definition_hash,
                    )
                if not reused:
                    await connection.execute(
                        """
                        INSERT INTO audit_logs(
                          tenant_id, actor_id, action, target_type, target_id, change_summary
                        ) VALUES ($1, $2, 'runtime_profile.create',
                                  'runtime_profile', $3, $4::jsonb)
                        """,
                        access["tenant_id"],
                        int(context["user"]["id"]),
                        row["id"],
                        json.dumps(
                            {
                                "knowledge_base_id": str(payload.knowledge_base_id),
                                "embedding_profile_id": str(payload.embedding_profile_id),
                                "generation_endpoint_id": str(payload.generation_endpoint_id),
                                "generation_model": payload.generation_model,
                                "definition_hash": definition_hash,
                                "effect_scope": "activate_required",
                            },
                            ensure_ascii=False,
                        ),
                    )
            result = dict(row)
            result["definition"] = _json_value(result["definition"], {})
            return {**result, "reused": reused, "effect_scope": "activate_required"}
        finally:
            await connection.close()

    @app.post("/api/v1/runtime-profiles/{profile_id}/activate")
    async def activate_runtime_profile(profile_id: int, request: Request) -> dict[str, Any]:
        """激活知识库 Runtime Profile，并记录旧值、新值及是否需要重新构建。"""
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            target = await connection.fetchrow(
                """
                SELECT rp.id, rp.tenant_id, rp.knowledge_base_id,
                       rp.embedding_profile_id, rp.definition_hash,
                       kb.active_runtime_id AS previous_runtime_profile_id,
                       kb.active_release_id, kr.embedding_profile_id AS release_embedding_profile_id
                FROM runtime_profiles rp
                JOIN knowledge_bases kb ON kb.id = rp.knowledge_base_id
                  AND kb.tenant_id = rp.tenant_id
                LEFT JOIN kb_releases kr ON kr.id = kb.active_release_id
                  AND kr.tenant_id = kb.tenant_id
                WHERE rp.id = $1
                """,
                profile_id,
            )
            if target is None:
                raise HTTPException(status_code=404, detail="Runtime Profile 不存在")
            access = await _require_knowledge_base_role(
                connection,
                context,
                int(target["knowledge_base_id"]),
                {"space_admin", "kb_admin"},
            )
            if int(access["tenant_id"]) != int(target["tenant_id"]):
                raise HTTPException(status_code=404, detail="Runtime Profile 不存在")
            effect_scope = (
                "immediate"
                if target["active_release_id"] is None
                or target["release_embedding_profile_id"] == target["embedding_profile_id"]
                else "rebuild_required"
            )
            async with connection.transaction():
                await connection.execute(
                    """
                    UPDATE knowledge_bases SET active_runtime_id = $3, updated_at = now()
                    WHERE id = $1 AND tenant_id = $2
                    """,
                    target["knowledge_base_id"],
                    target["tenant_id"],
                    profile_id,
                )
                await connection.execute(
                    """
                    INSERT INTO audit_logs(
                      tenant_id, actor_id, action, target_type, target_id, change_summary
                    ) VALUES ($1, $2, 'runtime_profile.activate',
                              'knowledge_base', $3, $4::jsonb)
                    """,
                    target["tenant_id"],
                    int(context["user"]["id"]),
                    str(target["knowledge_base_id"]),
                    json.dumps(
                        {
                            "before": {
                                "runtime_profile_id": (
                                    str(target["previous_runtime_profile_id"])
                                    if target["previous_runtime_profile_id"] is not None
                                    else None
                                )
                            },
                            "after": {"runtime_profile_id": str(profile_id)},
                            "effect_scope": effect_scope,
                        },
                        ensure_ascii=False,
                    ),
                )
            return {
                "id": str(profile_id),
                "knowledge_base_id": str(target["knowledge_base_id"]),
                "active": True,
                "effect_scope": effect_scope,
            }
        finally:
            await connection.close()

    @app.get("/api/v1/admin/menus")
    async def admin_menus(request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        if context["user"]["platform_role"] != "platform_admin":
            raise HTTPException(status_code=403, detail="只有平台管理员可以管理菜单")
        connection = await _database(config)
        try:
            rows = await connection.fetch(
                """
                SELECT id::text, code, name, kind, parent_id::text, route, icon,
                       permission_code, sort_order, visible, status
                FROM menus ORDER BY sort_order, id
                """
            )
            return {"items": _rows(rows)}
        finally:
            await connection.close()

    @app.patch("/api/v1/admin/menus/{menu_id}")
    async def update_menu(menu_id: int, payload: MenuPatch, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        if context["user"]["platform_role"] != "platform_admin":
            raise HTTPException(status_code=403, detail="只有平台管理员可以管理菜单")
        values = payload.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=400, detail="没有需要修改的字段")
        connection = await _database(config)
        try:
            assignments = []
            parameters: list[Any] = [menu_id]
            for index, (key, value) in enumerate(values.items(), 2):
                assignments.append(f"{key} = ${index}")
                parameters.append(value)
            row = await connection.fetchrow(
                f"""
                UPDATE menus SET {", ".join(assignments)}, updated_at = now() WHERE id = $1
                RETURNING id::text, code, name, kind, parent_id::text, route, icon,
                          permission_code, sort_order, visible, status
                """,
                *parameters,
            )
            if row is None:
                raise HTTPException(status_code=404, detail="菜单不存在")
            return dict(row)
        finally:
            await connection.close()

    @app.get("/api/v1/admin/roles")
    async def admin_roles(request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        if context["user"]["platform_role"] != "platform_admin":
            raise HTTPException(status_code=403, detail="只有平台管理员可以查看系统角色")
        connection = await _database(config)
        try:
            rows = await connection.fetch(
                "SELECT id::text, code, name, scope, description, is_system "
                "FROM roles ORDER BY scope, id"
            )
            return {"items": _rows(rows)}
        finally:
            await connection.close()

    @app.get("/api/v1/admin/users")
    async def admin_users(request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        if context["user"]["platform_role"] != "platform_admin":
            raise HTTPException(status_code=403, detail="只有平台管理员可以管理用户")
        connection = await _database(config)
        try:
            rows = await connection.fetch(
                """
                SELECT u.id::text, u.login, u.display_name, u.status,
                       pr.code AS platform_role, count(DISTINCT tm.tenant_id)::int AS space_count,
                       u.last_login_at, u.created_at
                FROM users u LEFT JOIN roles pr ON pr.id = u.platform_role_id
                LEFT JOIN tenant_members tm ON tm.user_id = u.id AND tm.status = 'active'
                GROUP BY u.id, pr.code ORDER BY u.created_at DESC
                """
            )
            return {"items": _rows(rows)}
        finally:
            await connection.close()

    @app.post("/api/v1/admin/users", status_code=201)
    async def create_user(payload: UserCreate, request: Request) -> dict[str, Any]:
        """创建平台账号，并在同一事务中保存可选空间授权及两级审计事件。"""
        context = await _authenticated_user(config, request)
        if context["user"]["platform_role"] != "platform_admin":
            raise HTTPException(status_code=403, detail="只有平台管理员可以创建用户")
        if payload.tenant_id is not None and payload.tenant_role_code is None:
            raise HTTPException(status_code=400, detail="分配空间时必须指定空间角色")
        connection = await _database(config)
        try:
            # 用户、空间成员关系和对应审计必须原子提交，避免出现已授权但无法追责的状态。
            async with connection.transaction():
                platform_role_id = None
                if payload.platform_role_code:
                    platform_role_id = await connection.fetchval(
                        "SELECT id FROM roles WHERE code = $1 AND scope = 'platform'",
                        payload.platform_role_code,
                    )
                    if platform_role_id is None:
                        raise HTTPException(status_code=400, detail="平台角色不存在")
                tenant_role_id = None
                if payload.tenant_id is not None:
                    tenant_role_id = await connection.fetchval(
                        "SELECT id FROM roles WHERE code = $1 AND scope = 'tenant'",
                        payload.tenant_role_code,
                    )
                    tenant_exists = await connection.fetchval(
                        "SELECT EXISTS (SELECT 1 FROM tenants WHERE id = $1 AND status = 'active')",
                        payload.tenant_id,
                    )
                    if tenant_role_id is None or not tenant_exists:
                        raise HTTPException(status_code=400, detail="空间或空间角色不存在")
                user_row = await connection.fetchrow(
                    """
                    INSERT INTO users(login, display_name, password_hash, platform_role_id)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id, login, display_name, status, created_at
                    """,
                    payload.login,
                    payload.display_name,
                    password_hasher.hash(payload.password),
                    platform_role_id,
                )
                if payload.tenant_id is not None and tenant_role_id is not None:
                    await connection.execute(
                        """
                        INSERT INTO tenant_members(tenant_id, user_id, role_id)
                        VALUES ($1, $2, $3)
                        """,
                        payload.tenant_id,
                        user_row["id"],
                        tenant_role_id,
                    )
                    await _write_membership_audit(
                        connection,
                        tenant_id=payload.tenant_id,
                        actor_id=int(context["user"]["id"]),
                        action="space_member.add",
                        target_type="user",
                        target_id=int(user_row["id"]),
                        summary={
                            "role_code": payload.tenant_role_code,
                            "source": "user.create",
                        },
                    )
                await connection.execute(
                    """
                    INSERT INTO audit_logs(
                      actor_id, action, target_type, target_id, change_summary
                    ) VALUES ($1, 'user.create', 'user', $2, $3::jsonb)
                    """,
                    int(context["user"]["id"]),
                    str(user_row["id"]),
                    json.dumps(
                        {
                            "login": payload.login,
                            "display_name": payload.display_name,
                            "platform_role_code": payload.platform_role_code,
                            "tenant_id": (
                                str(payload.tenant_id) if payload.tenant_id is not None else None
                            ),
                            "tenant_role_code": payload.tenant_role_code,
                        },
                        ensure_ascii=False,
                    ),
                )
                return {**dict(user_row), "id": str(user_row["id"])}
        except asyncpg.UniqueViolationError as error:
            raise HTTPException(status_code=409, detail="登录名已存在") from error
        finally:
            await connection.close()

    @app.patch("/api/v1/admin/users/{user_id}")
    async def update_user(user_id: int, payload: UserPatch, request: Request) -> dict[str, Any]:
        """更新用户资料或状态，并记录安全脱敏的前后状态与会话失效结果。"""
        context = await _authenticated_user(config, request)
        if context["user"]["platform_role"] != "platform_admin":
            raise HTTPException(status_code=403, detail="只有平台管理员可以管理用户")
        values = payload.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=400, detail="没有需要修改的字段")
        if user_id == int(context["user"]["id"]) and values.get("status") == "disabled":
            raise HTTPException(status_code=400, detail="不能停用当前登录账号")
        assignments: list[str] = []
        parameters: list[Any] = [user_id]
        for index, (key, value) in enumerate(values.items(), 2):
            column = "password_hash" if key == "password" else key
            value = password_hasher.hash(value) if key == "password" else value
            assignments.append(f"{column} = ${index}")
            parameters.append(value)
        connection = await _database(config)
        try:
            async with connection.transaction():
                # 锁定用户行，保证审计中的 before 与本次更新属于同一并发版本。
                before = await connection.fetchrow(
                    """
                    SELECT id, login, display_name, status
                    FROM users WHERE id = $1 FOR UPDATE
                    """,
                    user_id,
                )
                if before is None:
                    raise HTTPException(status_code=404, detail="用户不存在")
                row = await connection.fetchrow(
                    f"""
                    UPDATE users SET {", ".join(assignments)}, updated_at = now()
                    WHERE id = $1
                    RETURNING id::text, login, display_name, status, last_login_at, created_at
                    """,
                    *parameters,
                )
                if row is None:
                    raise HTTPException(status_code=404, detail="用户不存在")
                revoked_sessions = 0
                if "password" in values or values.get("status") == "disabled":
                    # 密码重置或账号停用必须立即使现有会话失效，撤销数量用于运维核验。
                    revoked_sessions = int(
                        await connection.fetchval(
                            """
                            WITH revoked AS (
                              UPDATE sessions SET revoked_at = now()
                              WHERE user_id = $1 AND revoked_at IS NULL
                              RETURNING id
                            ) SELECT count(*)::int FROM revoked
                            """,
                            user_id,
                        )
                        or 0
                    )
                changed_fields = sorted(values)
                # 密码只记录“发生过重置”，绝不写入明文或哈希；前后值仅允许非敏感字段。
                summary_fields = {"display_name", "status"}
                await connection.execute(
                    """
                    INSERT INTO audit_logs(
                      actor_id, action, target_type, target_id, change_summary
                    ) VALUES ($1, 'user.update', 'user', $2, $3::jsonb)
                    """,
                    int(context["user"]["id"]),
                    str(user_id),
                    json.dumps(
                        {
                            "fields": changed_fields,
                            "before": {
                                field: before[field]
                                for field in changed_fields
                                if field in summary_fields
                            },
                            "after": {
                                field: row[field]
                                for field in changed_fields
                                if field in summary_fields
                            },
                            "password_reset": "password" in values,
                            "revoked_sessions": revoked_sessions,
                        },
                        ensure_ascii=False,
                    ),
                )
            return dict(row)
        finally:
            await connection.close()

    @app.post("/api/v1/admin/tenants", status_code=201)
    async def create_tenant(payload: TenantCreate, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        if context["user"]["platform_role"] != "platform_admin":
            raise HTTPException(status_code=403, detail="只有平台管理员可以创建客户空间")
        connection = await _database(config)
        try:
            try:
                async with connection.transaction():
                    row = await connection.fetchrow(
                        "INSERT INTO tenants(code, name) VALUES ($1, $2) "
                        "RETURNING id::text, code, name, status, created_at",
                        payload.code,
                        payload.name,
                    )
                    space_admin_role_id = await connection.fetchval(
                        "SELECT id FROM roles WHERE code = 'space_admin'"
                    )
                    if row is None or space_admin_role_id is None:
                        raise HTTPException(status_code=500, detail="空间管理员角色未初始化")
                    await connection.execute(
                        """
                        INSERT INTO tenant_members(tenant_id, user_id, role_id)
                        VALUES ($1, $2, $3)
                        """,
                        int(row["id"]),
                        int(context["user"]["id"]),
                        space_admin_role_id,
                    )
            except asyncpg.UniqueViolationError as error:
                raise HTTPException(status_code=409, detail="空间编码已存在") from error
            return dict(row)
        finally:
            await connection.close()

    @app.get("/api/v1/admin/tenants")
    async def admin_tenants(request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        if context["user"]["platform_role"] != "platform_admin":
            raise HTTPException(status_code=403, detail="只有平台管理员可以查看客户空间")
        connection = await _database(config)
        try:
            rows = await connection.fetch(
                """
                SELECT t.id::text, t.code, t.name, t.status, t.created_at,
                       count(DISTINCT tm.user_id)::int AS member_count,
                       count(DISTINCT kb.id)::int AS knowledge_base_count
                FROM tenants t LEFT JOIN tenant_members tm
                  ON tm.tenant_id = t.id AND tm.status = 'active'
                LEFT JOIN knowledge_bases kb ON kb.tenant_id = t.id AND kb.status <> 'disabled'
                GROUP BY t.id ORDER BY t.created_at DESC
                """
            )
            return {"items": _rows(rows)}
        finally:
            await connection.close()

    @app.get("/api/v1/knowledge-bases")
    async def list_knowledge_bases(
        request: Request, tenant_id: int | None = None
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            api_key_tenant_id = context.get("api_key_tenant_id")
            if api_key_tenant_id is not None:
                if tenant_id is not None and tenant_id != int(api_key_tenant_id):
                    raise HTTPException(status_code=404, detail="客户空间不存在")
                tenant_ids = [int(api_key_tenant_id)]
            elif tenant_id is None:
                tenant_ids = [int(space["id"]) for space in context["spaces"]]
            else:
                await _assert_tenant_access(connection, context, tenant_id)
                tenant_ids = [tenant_id]
            if not tenant_ids:
                return {"items": []}
            if api_key_tenant_id is not None:
                rows = await connection.fetch(
                    """
                    SELECT kb.id::text, kb.tenant_id::text, kb.name, kb.description,
                           kb.purpose, kb.status, kb.active_release_id::text, kb.updated_at,
                           count(DISTINCT d.id)::int AS document_count
                    FROM knowledge_bases kb
                    JOIN tenants tenant ON tenant.id = kb.tenant_id AND tenant.status = 'active'
                    LEFT JOIN documents d
                      ON d.tenant_id = kb.tenant_id AND d.knowledge_base_id = kb.id
                     AND d.status <> 'deleted'
                    WHERE kb.tenant_id = $1 AND kb.status <> 'disabled'
                      AND kb.active_release_id IS NOT NULL
                    GROUP BY kb.id ORDER BY kb.updated_at DESC
                    """,
                    int(api_key_tenant_id),
                )
                return {"items": _rows(rows)}
            rows = await connection.fetch(
                """
                SELECT kb.id::text, kb.tenant_id::text, kb.name, kb.description, kb.purpose,
                       kb.status, kb.active_release_id::text, kb.updated_at,
                       count(DISTINCT d.id)::int AS document_count
                FROM knowledge_bases kb LEFT JOIN documents d
                  ON d.tenant_id = kb.tenant_id AND d.knowledge_base_id = kb.id
                 AND d.status <> 'deleted'
                WHERE kb.tenant_id = ANY($1::bigint[]) AND kb.status <> 'disabled'
                  AND EXISTS (
                    SELECT 1 FROM tenant_members tm JOIN roles r ON r.id = tm.role_id
                    WHERE tm.tenant_id = kb.tenant_id AND tm.user_id = $2
                       AND tm.status = 'active' AND (
                         r.code IN ('space_admin', 'customer_reader') OR EXISTS (
                           SELECT 1 FROM kb_members km
                          WHERE km.knowledge_base_id = kb.id AND km.tenant_id = kb.tenant_id
                            AND km.user_id = tm.user_id AND km.status = 'active'
                         )
                       ) AND (r.code <> 'customer_reader' OR kb.active_release_id IS NOT NULL)
                  )
                GROUP BY kb.id ORDER BY kb.updated_at DESC
                """,
                tenant_ids,
                int(context["user"]["id"]),
            )
            return {"items": _rows(rows)}
        finally:
            await connection.close()

    @app.post("/api/v1/knowledge-bases", status_code=201)
    async def create_knowledge_base(
        payload: KnowledgeBaseCreate,
        request: Request,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            await _assert_tenant_access(connection, context, payload.tenant_id)
            user_id = int(context["user"]["id"])
            can_create = await connection.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM tenant_members tm JOIN roles r ON r.id = tm.role_id
                    WHERE tm.tenant_id = $1 AND tm.user_id = $2 AND tm.status = 'active'
                      AND r.code = 'space_admin'
                )
                """,
                payload.tenant_id,
                user_id,
            )
            if not can_create:
                raise HTTPException(status_code=403, detail="当前角色不能创建知识库")
            async with connection.transaction():
                return await _create_knowledge_base(connection, payload, user_id)
        except asyncpg.UniqueViolationError as error:
            raise HTTPException(status_code=409, detail="该空间已存在同名知识库") from error
        finally:
            await connection.close()

    @app.get("/api/v1/spaces/{tenant_id}/members")
    async def list_space_members(tenant_id: int, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            await _require_space_admin(connection, context, tenant_id)
            rows = await connection.fetch(
                """
                SELECT u.id::text, u.login, u.display_name, u.status AS user_status,
                       tm.status, r.code AS role_code, r.name AS role_name,
                       tm.created_at,
                       count(DISTINCT km.knowledge_base_id) FILTER (
                         WHERE km.status = 'active'
                       )::int AS knowledge_base_count
                FROM tenant_members tm
                JOIN users u ON u.id = tm.user_id
                JOIN roles r ON r.id = tm.role_id
                LEFT JOIN kb_members km ON km.tenant_id = tm.tenant_id
                  AND km.user_id = tm.user_id
                WHERE tm.tenant_id = $1
                GROUP BY u.id, tm.status, r.code, r.name, tm.created_at
                ORDER BY (tm.status = 'active') DESC, tm.created_at, u.id
                """,
                tenant_id,
            )
            return {"items": _rows(rows)}
        finally:
            await connection.close()

    @app.post("/api/v1/spaces/{tenant_id}/members", status_code=201)
    async def add_space_member(
        tenant_id: int,
        payload: SpaceMemberCreate,
        request: Request,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            await _require_space_admin(connection, context, tenant_id)
            async with connection.transaction():
                user = await connection.fetchrow(
                    "SELECT id, login, display_name, status FROM users WHERE login = $1",
                    payload.login,
                )
                if user is None or user["status"] != "active":
                    raise HTTPException(status_code=404, detail="可用账号不存在")
                role_id = await connection.fetchval(
                    "SELECT id FROM roles WHERE code = $1 AND scope = 'tenant'",
                    payload.role_code,
                )
                if role_id is None:
                    raise HTTPException(status_code=400, detail="空间角色不存在")
                exists = await connection.fetchval(
                    """
                    SELECT EXISTS (
                      SELECT 1 FROM tenant_members WHERE tenant_id = $1 AND user_id = $2
                    )
                    """,
                    tenant_id,
                    user["id"],
                )
                if exists:
                    raise HTTPException(status_code=409, detail="该账号已经是空间成员")
                await connection.execute(
                    "INSERT INTO tenant_members(tenant_id, user_id, role_id) VALUES ($1, $2, $3)",
                    tenant_id,
                    user["id"],
                    role_id,
                )
                await connection.execute(
                    """
                    UPDATE knowledge_bases SET auth_epoch = auth_epoch + 1, updated_at = now()
                    WHERE tenant_id = $1
                    """,
                    tenant_id,
                )
                await _write_membership_audit(
                    connection,
                    tenant_id=tenant_id,
                    actor_id=int(context["user"]["id"]),
                    action="space_member.add",
                    target_type="user",
                    target_id=int(user["id"]),
                    summary={"role_code": payload.role_code, "status": "active"},
                )
            return {
                "id": str(user["id"]),
                "login": user["login"],
                "display_name": user["display_name"],
                "user_status": user["status"],
                "status": "active",
                "role_code": payload.role_code,
                "knowledge_base_count": 0,
            }
        finally:
            await connection.close()

    @app.patch("/api/v1/spaces/{tenant_id}/members/{user_id}")
    async def update_space_member(
        tenant_id: int,
        user_id: int,
        payload: SpaceMemberPatch,
        request: Request,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        values = payload.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=400, detail="没有需要修改的字段")
        connection = await _database(config)
        try:
            await _require_space_admin(connection, context, tenant_id)
            async with connection.transaction():
                current = await connection.fetchrow(
                    """
                    SELECT tm.status, r.code AS role_code
                    FROM tenant_members tm JOIN roles r ON r.id = tm.role_id
                    WHERE tm.tenant_id = $1 AND tm.user_id = $2
                    FOR UPDATE OF tm
                    """,
                    tenant_id,
                    user_id,
                )
                if current is None:
                    raise HTTPException(status_code=404, detail="空间成员不存在")
                next_role = payload.role_code or str(current["role_code"])
                next_status = payload.status or str(current["status"])
                await _assert_space_member_role_change(
                    connection,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    current_role=str(current["role_code"]),
                    next_role=next_role,
                    next_status=next_status,
                )
                role_id = await connection.fetchval(
                    "SELECT id FROM roles WHERE code = $1 AND scope = 'tenant'",
                    next_role,
                )
                row = await connection.fetchrow(
                    """
                    UPDATE tenant_members SET role_id = $3, status = $4
                    WHERE tenant_id = $1 AND user_id = $2
                    RETURNING user_id::text AS id, status, created_at
                    """,
                    tenant_id,
                    user_id,
                    role_id,
                    next_status,
                )
                await connection.execute(
                    """
                    UPDATE knowledge_bases SET auth_epoch = auth_epoch + 1, updated_at = now()
                    WHERE tenant_id = $1
                    """,
                    tenant_id,
                )
                await _write_membership_audit(
                    connection,
                    tenant_id=tenant_id,
                    actor_id=int(context["user"]["id"]),
                    action=(
                        "space_member.disable"
                        if next_status == "disabled"
                        else "space_member.update"
                    ),
                    target_type="user",
                    target_id=user_id,
                    summary={
                        "before": {
                            "role_code": current["role_code"],
                            "status": current["status"],
                        },
                        "after": {"role_code": next_role, "status": next_status},
                    },
                )
            if row is None:
                raise HTTPException(status_code=404, detail="空间成员不存在")
            return {**dict(row), "role_code": next_role}
        finally:
            await connection.close()

    @app.get("/api/v1/spaces/{tenant_id}/membership-audit")
    async def list_membership_audit(tenant_id: int, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            await _require_space_admin(connection, context, tenant_id)
            rows = await connection.fetch(
                """
                SELECT al.id::text, al.action, al.target_type, al.target_id,
                       al.change_summary, al.created_at,
                       actor.display_name AS actor_name,
                       target.display_name AS target_name
                FROM audit_logs al
                LEFT JOIN users actor ON actor.id = al.actor_id
                LEFT JOIN users target ON al.target_type = 'user'
                  AND target.id::text = al.target_id
                WHERE al.tenant_id = $1
                  AND al.action IN (
                    'space_member.add', 'space_member.update', 'space_member.disable',
                    'knowledge_base_member.add', 'knowledge_base_member.update',
                    'knowledge_base_member.revoke'
                  )
                ORDER BY al.created_at DESC, al.id DESC LIMIT 100
                """,
                tenant_id,
            )
            items = []
            for row in rows:
                item = dict(row)
                item["change_summary"] = _json_value(item["change_summary"], {})
                items.append(item)
            return {"items": items}
        finally:
            await connection.close()

    @app.get("/api/v1/audit-logs")
    async def list_audit_logs(
        request: Request,
        tenant_id: int | None = None,
        action_prefix: str = Query(default="", max_length=100),
        actor: str = Query(default="", max_length=100),
        target_type: str = Query(default="", max_length=80),
        cursor: int | None = Query(default=None, ge=1),
        limit: int = Query(default=30, ge=1, le=100),
    ) -> dict[str, Any]:
        """按平台或显式授权空间查询不可变审计事件，并使用 ID 游标分页。"""
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            if tenant_id is None:
                if context["user"]["platform_role"] != "platform_admin":
                    raise HTTPException(status_code=403, detail="只有平台管理员可以查看平台日志")
            else:
                await _require_space_admin(connection, context, tenant_id)

            rows = await connection.fetch(
                """
                SELECT al.id::text, al.tenant_id::text, tenant.name AS tenant_name,
                       al.actor_id::text, actor.display_name AS actor_name,
                       actor.login AS actor_login, al.action, al.target_type,
                       al.target_id, al.change_summary, al.request_id::text,
                       al.created_at
                FROM audit_logs al
                LEFT JOIN tenants tenant ON tenant.id = al.tenant_id
                LEFT JOIN users actor ON actor.id = al.actor_id
                WHERE (($1::bigint IS NULL AND al.tenant_id IS NULL) OR al.tenant_id = $1)
                  AND ($2 = '' OR al.action LIKE $2 || '%')
                  AND (
                    $3 = '' OR actor.display_name ILIKE '%' || $3 || '%'
                    OR actor.login ILIKE '%' || $3 || '%'
                  )
                  AND ($4 = '' OR al.target_type = $4)
                  AND ($5::bigint IS NULL OR al.id < $5)
                ORDER BY al.id DESC
                LIMIT $6
                """,
                tenant_id,
                action_prefix.strip(),
                actor.strip(),
                target_type.strip(),
                cursor,
                limit + 1,
            )
            has_more = len(rows) > limit
            visible_rows = rows[:limit]
            items = []
            for row in visible_rows:
                item = dict(row)
                item["change_summary"] = _json_value(item["change_summary"], {})
                items.append(item)
            return {
                "items": items,
                "next_cursor": items[-1]["id"] if has_more and items else None,
            }
        finally:
            await connection.close()

    @app.get("/api/v1/knowledge-bases/{knowledge_base_id}/documents")
    async def list_documents(knowledge_base_id: int, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _knowledge_base_access(connection, context, knowledge_base_id)
            role = _role_for_access(access)
            published_only = role in {"reader", "customer_reader"}
            rows = await connection.fetch(
                """
                SELECT d.id::text, d.title, d.status, d.created_at, d.updated_at,
                       dv.id::text AS version_id, dv.version_no, dv.parse_status,
                       dv.file_size, dv.mime_type, dv.created_at AS version_created_at,
                       CASE WHEN d.status = 'active'
                         AND kb.active_release_id IS NOT NULL AND EXISTS (
                         SELECT 1 FROM release_items ri
                         WHERE ri.release_id = kb.active_release_id AND ri.document_id = d.id
                           AND ri.document_version_id = dv.id
                       ) THEN true ELSE false END AS published
                FROM documents d
                JOIN knowledge_bases kb ON kb.id = d.knowledge_base_id
                LEFT JOIN LATERAL (
                  SELECT id, version_no, parse_status, file_size, mime_type, created_at
                  FROM document_versions
                  WHERE document_id = d.id
                  ORDER BY version_no DESC LIMIT 1
                ) dv ON true
                WHERE d.tenant_id = $1 AND d.knowledge_base_id = $2
                  AND d.status <> 'deleted'
                  AND ($3::boolean = false OR (d.status = 'active' AND EXISTS (
                    SELECT 1 FROM release_items ri
                    WHERE ri.release_id = kb.active_release_id AND ri.document_id = d.id
                      AND ri.document_version_id = dv.id
                  )))
                ORDER BY d.updated_at DESC, d.id DESC
                """,
                access["tenant_id"],
                knowledge_base_id,
                published_only,
            )
            return {
                "items": _rows(rows),
                "knowledge_base": {"id": str(access["id"]), "name": access["name"]},
            }
        finally:
            await connection.close()

    @app.get("/api/v1/knowledge-bases/{knowledge_base_id}/members")
    async def list_knowledge_base_members(
        knowledge_base_id: int,
        request: Request,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _require_knowledge_base_role(
                connection,
                context,
                knowledge_base_id,
                {"space_admin", "kb_admin"},
            )
            rows = await connection.fetch(
                """
                SELECT u.id::text, u.login, u.display_name,
                       tm.status AS space_status, tenant_role.code AS space_role_code,
                       km.status, kb_role.code AS role_code, kb_role.name AS role_name,
                       km.created_at
                FROM kb_members km
                JOIN users u ON u.id = km.user_id
                JOIN tenant_members tm ON tm.tenant_id = km.tenant_id
                  AND tm.user_id = km.user_id
                JOIN roles tenant_role ON tenant_role.id = tm.role_id
                JOIN roles kb_role ON kb_role.id = km.role_id
                WHERE km.tenant_id = $1 AND km.knowledge_base_id = $2
                ORDER BY (km.status = 'active') DESC, km.created_at, u.id
                """,
                access["tenant_id"],
                knowledge_base_id,
            )
            return {"items": _rows(rows)}
        finally:
            await connection.close()

    @app.get("/api/v1/knowledge-bases/{knowledge_base_id}/member-candidates")
    async def list_knowledge_base_member_candidates(
        knowledge_base_id: int,
        request: Request,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _require_knowledge_base_role(
                connection,
                context,
                knowledge_base_id,
                {"space_admin", "kb_admin"},
            )
            rows = await connection.fetch(
                """
                SELECT u.id::text, u.login, u.display_name,
                       km.status AS grant_status, kb_role.code AS grant_role_code
                FROM tenant_members tm
                JOIN users u ON u.id = tm.user_id AND u.status = 'active'
                JOIN roles tenant_role ON tenant_role.id = tm.role_id
                LEFT JOIN kb_members km ON km.tenant_id = tm.tenant_id
                  AND km.knowledge_base_id = $2 AND km.user_id = tm.user_id
                LEFT JOIN roles kb_role ON kb_role.id = km.role_id
                WHERE tm.tenant_id = $1 AND tm.status = 'active'
                  AND tenant_role.code = 'space_member'
                ORDER BY u.display_name, u.id
                """,
                access["tenant_id"],
                knowledge_base_id,
            )
            return {"items": _rows(rows)}
        finally:
            await connection.close()

    @app.post("/api/v1/knowledge-bases/{knowledge_base_id}/members", status_code=201)
    async def add_knowledge_base_member(
        knowledge_base_id: int,
        payload: KnowledgeBaseMemberCreate,
        request: Request,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _require_knowledge_base_role(
                connection,
                context,
                knowledge_base_id,
                {"space_admin", "kb_admin"},
            )
            async with connection.transaction():
                member = await connection.fetchrow(
                    """
                    SELECT tm.user_id, tm.status, r.code AS space_role_code,
                           u.login, u.display_name
                    FROM tenant_members tm
                    JOIN roles r ON r.id = tm.role_id
                    JOIN users u ON u.id = tm.user_id AND u.status = 'active'
                    WHERE tm.tenant_id = $1 AND tm.user_id = $2
                    """,
                    access["tenant_id"],
                    payload.user_id,
                )
                if member is None or member["status"] != "active":
                    raise HTTPException(status_code=400, detail="用户不是当前空间的有效成员")
                if member["space_role_code"] in {"space_admin", "customer_reader"}:
                    raise HTTPException(
                        status_code=409,
                        detail="空间管理员或客户用户无需叠加知识库授权",
                    )
                role_id = await connection.fetchval(
                    "SELECT id FROM roles WHERE code = $1 AND scope = 'knowledge_base'",
                    payload.role_code,
                )
                exists = await connection.fetchval(
                    """
                    SELECT EXISTS (
                      SELECT 1 FROM kb_members
                      WHERE knowledge_base_id = $1 AND user_id = $2
                    )
                    """,
                    knowledge_base_id,
                    payload.user_id,
                )
                if exists:
                    raise HTTPException(status_code=409, detail="该成员已有知识库授权")
                await connection.execute(
                    """
                    INSERT INTO kb_members(
                      tenant_id, knowledge_base_id, user_id, role_id
                    ) VALUES ($1, $2, $3, $4)
                    """,
                    access["tenant_id"],
                    knowledge_base_id,
                    payload.user_id,
                    role_id,
                )
                await connection.execute(
                    """
                    UPDATE knowledge_bases SET auth_epoch = auth_epoch + 1, updated_at = now()
                    WHERE id = $1 AND tenant_id = $2
                    """,
                    knowledge_base_id,
                    access["tenant_id"],
                )
                await _write_membership_audit(
                    connection,
                    tenant_id=int(access["tenant_id"]),
                    actor_id=int(context["user"]["id"]),
                    action="knowledge_base_member.add",
                    target_type="user",
                    target_id=payload.user_id,
                    summary={
                        "knowledge_base_id": str(knowledge_base_id),
                        "role_code": payload.role_code,
                        "status": "active",
                    },
                )
            return {
                "id": str(payload.user_id),
                "login": member["login"],
                "display_name": member["display_name"],
                "status": "active",
                "role_code": payload.role_code,
            }
        finally:
            await connection.close()

    @app.patch("/api/v1/knowledge-bases/{knowledge_base_id}/members/{user_id}")
    async def update_knowledge_base_member(
        knowledge_base_id: int,
        user_id: int,
        payload: KnowledgeBaseMemberPatch,
        request: Request,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        values = payload.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=400, detail="没有需要修改的字段")
        connection = await _database(config)
        try:
            access = await _require_knowledge_base_role(
                connection,
                context,
                knowledge_base_id,
                {"space_admin", "kb_admin"},
            )
            async with connection.transaction():
                current = await connection.fetchrow(
                    """
                    SELECT km.status, r.code AS role_code
                    FROM kb_members km JOIN roles r ON r.id = km.role_id
                    WHERE km.tenant_id = $1 AND km.knowledge_base_id = $2
                      AND km.user_id = $3
                    FOR UPDATE OF km
                    """,
                    access["tenant_id"],
                    knowledge_base_id,
                    user_id,
                )
                if current is None:
                    raise HTTPException(status_code=404, detail="知识库成员不存在")
                next_role = payload.role_code or str(current["role_code"])
                next_status = payload.status or str(current["status"])
                if next_status == "active":
                    eligible = await connection.fetchval(
                        """
                        SELECT EXISTS (
                          SELECT 1 FROM tenant_members tm
                          JOIN roles r ON r.id = tm.role_id
                          JOIN users u ON u.id = tm.user_id
                          WHERE tm.tenant_id = $1 AND tm.user_id = $2
                            AND tm.status = 'active' AND u.status = 'active'
                            AND r.code IN ('space_admin', 'space_member')
                        )
                        """,
                        access["tenant_id"],
                        user_id,
                    )
                    if not eligible:
                        raise HTTPException(
                            status_code=409,
                            detail="只有有效内部空间成员可以恢复知识库授权",
                        )
                role_id = await connection.fetchval(
                    "SELECT id FROM roles WHERE code = $1 AND scope = 'knowledge_base'",
                    next_role,
                )
                row = await connection.fetchrow(
                    """
                    UPDATE kb_members SET role_id = $4, status = $5
                    WHERE tenant_id = $1 AND knowledge_base_id = $2 AND user_id = $3
                    RETURNING user_id::text AS id, status, created_at
                    """,
                    access["tenant_id"],
                    knowledge_base_id,
                    user_id,
                    role_id,
                    next_status,
                )
                await connection.execute(
                    """
                    UPDATE knowledge_bases SET auth_epoch = auth_epoch + 1, updated_at = now()
                    WHERE id = $1 AND tenant_id = $2
                    """,
                    knowledge_base_id,
                    access["tenant_id"],
                )
                await _write_membership_audit(
                    connection,
                    tenant_id=int(access["tenant_id"]),
                    actor_id=int(context["user"]["id"]),
                    action=(
                        "knowledge_base_member.revoke"
                        if next_status == "disabled"
                        else "knowledge_base_member.update"
                    ),
                    target_type="user",
                    target_id=user_id,
                    summary={
                        "knowledge_base_id": str(knowledge_base_id),
                        "before": {
                            "role_code": current["role_code"],
                            "status": current["status"],
                        },
                        "after": {"role_code": next_role, "status": next_status},
                    },
                )
            if row is None:
                raise HTTPException(status_code=404, detail="知识库成员不存在")
            return {**dict(row), "role_code": next_role}
        finally:
            await connection.close()

    @app.post("/api/v1/knowledge-bases/{knowledge_base_id}/documents", status_code=202)
    async def upload_document(
        knowledge_base_id: int,
        request: Request,
        file: Annotated[UploadFile, File(...)],
    ) -> dict[str, Any]:
        """保存一个不可变文档版本，投递解析任务，并原子记录上传审计。"""
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        storage_path: Path | None = None
        try:
            access = await _require_knowledge_base_role(
                connection,
                context,
                knowledge_base_id,
                {"space_admin", "kb_admin", "editor"},
            )
            filename = _safe_filename(file.filename)
            suffix = Path(filename).suffix.lower()
            if suffix not in ALLOWED_DOCUMENT_TYPES:
                raise HTTPException(status_code=415, detail="仅支持 Markdown、TXT、DOCX 和电子 PDF")
            raw = await _read_upload(file, suffix)
            title = Path(filename).stem[:240] or "未命名文档"
            storage_key = (
                f"tenant/{access['tenant_id']}/knowledge-base/{knowledge_base_id}/"
                f"{secrets.token_hex(16)}{suffix}"
            )
            storage_path = config.storage_root / storage_key
            storage_path.parent.mkdir(parents=True, exist_ok=True)
            storage_path.write_bytes(raw)
            user_id = int(context["user"]["id"])
            async with connection.transaction():
                document = await connection.fetchrow(
                    """
                    SELECT id FROM documents
                    WHERE tenant_id = $1 AND knowledge_base_id = $2 AND title = $3
                      AND status <> 'deleted'
                    ORDER BY id LIMIT 1
                    FOR UPDATE
                    """,
                    access["tenant_id"],
                    knowledge_base_id,
                    title,
                )
                if document is None:
                    document = await connection.fetchrow(
                        """
                        INSERT INTO documents(
                          tenant_id, knowledge_base_id, dataset_id, title, created_by
                        )
                        SELECT kb.tenant_id, kb.id, ds.id, $3, $4
                        FROM knowledge_bases kb JOIN datasets ds
                          ON ds.knowledge_base_id = kb.id AND ds.tenant_id = kb.tenant_id
                          AND ds.is_default = true
                        WHERE kb.id = $1 AND kb.tenant_id = $2
                        RETURNING id
                        """,
                        access["id"],
                        access["tenant_id"],
                        title,
                        user_id,
                    )
                if document is None:
                    raise HTTPException(status_code=409, detail="知识库默认数据集不存在")
                version_no = await connection.fetchval(
                    """
                    SELECT COALESCE(MAX(version_no), 0) + 1
                    FROM document_versions WHERE document_id = $1
                    """,
                    document["id"],
                )
                version = await connection.fetchrow(
                    """
                    INSERT INTO document_versions(
                      tenant_id, document_id, version_no, storage_key, sha256,
                      mime_type, file_size, parse_status, created_by
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, 'queued', $8)
                    RETURNING id, version_no, parse_status, created_at
                    """,
                    access["tenant_id"],
                    document["id"],
                    version_no,
                    storage_key,
                    hashlib.sha256(raw).hexdigest(),
                    ALLOWED_DOCUMENT_TYPES[suffix],
                    len(raw),
                    user_id,
                )
                await connection.execute(
                    """
                    UPDATE documents
                    SET desired_version_id = $1, updated_at = now()
                    WHERE id = $2
                    """,
                    version["id"],
                    document["id"],
                )
                await connection.execute(
                    """
                    UPDATE knowledge_bases SET content_epoch = content_epoch + 1,
                        updated_at = now() WHERE id = $1
                    """,
                    knowledge_base_id,
                )
                task = await connection.fetchrow(
                    """
                    INSERT INTO tasks(
                      tenant_id, knowledge_base_id, task_type, state,
                      idempotency_key, created_by
                    )
                    VALUES ($1, $2, 'document_parse', 'queued', $3, $4)
                    RETURNING id, state, task_type, created_at
                    """,
                    access["tenant_id"],
                    knowledge_base_id,
                    f"document-version:{version['id']}",
                    user_id,
                )
                await connection.execute(
                    """
                    INSERT INTO task_items(task_id, target_id, stage, state)
                    VALUES ($1, $2, 'parse', 'queued')
                    """,
                    task["id"],
                    version["id"],
                )
                await connection.execute(
                    """
                    INSERT INTO outbox_events(tenant_id, event_type, payload)
                    VALUES ($1, 'document.parse.requested', $2::jsonb)
                    """,
                    access["tenant_id"],
                    json.dumps(
                        {"task_id": str(task["id"]), "document_version_id": str(version["id"])}
                    ),
                )
                # 审计与版本、任务和 Outbox 同事务提交，避免出现无法追责的已入库文件。
                await write_audit_event(
                    connection,
                    tenant_id=int(access["tenant_id"]),
                    actor_id=user_id,
                    action="document.upload",
                    target_type="document",
                    target_id=int(document["id"]),
                    summary={
                        "knowledge_base_id": str(knowledge_base_id),
                        "document_version_id": str(version["id"]),
                        "version_no": int(version["version_no"]),
                        "task_id": str(task["id"]),
                        "mime_type": ALLOWED_DOCUMENT_TYPES[suffix],
                        "file_size": len(raw),
                    },
                )
            return {
                "document": {"id": str(document["id"]), "title": title},
                "version": {**dict(version), "id": str(version["id"])},
                "task": {**dict(task), "id": str(task["id"])},
            }
        except HTTPException:
            if storage_path is not None:
                storage_path.unlink(missing_ok=True)
            raise
        except asyncpg.UniqueViolationError as error:
            if storage_path is not None:
                storage_path.unlink(missing_ok=True)
            raise HTTPException(status_code=409, detail="该文档已有相同版本任务") from error
        except Exception:
            if storage_path is not None:
                storage_path.unlink(missing_ok=True)
            raise
        finally:
            await file.close()
            await connection.close()

    @app.get("/api/v1/documents/{document_id}")
    async def document_detail(document_id: int, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _document_access(connection, context, document_id)
            role = _role_for_access(access)
            rows = await connection.fetch(
                """
                SELECT id::text, version_no, sha256, mime_type, file_size, parse_status,
                       warnings, created_at
                FROM document_versions WHERE document_id = $1 ORDER BY version_no DESC
                """,
                document_id,
            )
            if role in {"reader", "customer_reader"}:
                if access["active_release_id"] is None or access["status"] != "active":
                    rows = []
                else:
                    visible_rows: list[asyncpg.Record] = []
                    for row in rows:
                        visible = await connection.fetchval(
                            """
                            SELECT EXISTS (
                              SELECT 1 FROM release_items
                              WHERE release_id = $1 AND document_id = $2
                                AND document_version_id = $3
                            )
                            """,
                            access["active_release_id"],
                            document_id,
                            int(row["id"]),
                        )
                        if visible:
                            visible_rows.append(row)
                    rows = visible_rows
            return {
                "document": {
                    "id": str(access["id"]),
                    "title": access["title"],
                    "status": access["status"],
                    "tenant_id": str(access["tenant_id"]),
                    "knowledge_base_id": str(access["knowledge_base_id"]),
                },
                "versions": [
                    {
                        **dict(row),
                        "warnings": _json_value(row["warnings"], []),
                    }
                    for row in rows
                ],
            }
        finally:
            await connection.close()

    @app.get("/api/v1/document-versions/{version_id}/preview")
    async def document_version_preview(version_id: int, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            version = await connection.fetchrow(
                """
                SELECT dv.id, dv.document_id, dv.version_no, dv.parse_status, dv.warnings,
                       d.title, d.tenant_id, d.knowledge_base_id
                FROM document_versions dv JOIN documents d ON d.id = dv.document_id
                WHERE dv.id = $1
                """,
                version_id,
            )
            if version is None:
                raise HTTPException(status_code=404, detail="文档版本不存在")
            access = await _document_access(connection, context, int(version["document_id"]))
            role = _role_for_access(access)
            if role in {"reader", "customer_reader"}:
                if access["status"] != "active":
                    raise HTTPException(status_code=404, detail="文档版本不存在")
                visible = (
                    await connection.fetchval(
                        """
                        SELECT EXISTS (
                          SELECT 1 FROM release_items
                          WHERE release_id = $1 AND document_id = $2
                            AND document_version_id = $3
                        )
                        """,
                        access["active_release_id"],
                        version["document_id"],
                        version_id,
                    )
                    if access["active_release_id"] is not None
                    else False
                )
                if not visible:
                    raise HTTPException(status_code=404, detail="文档版本不存在")
            chunks = await connection.fetch(
                """
                SELECT c.id::text, c.ordinal, c.content, c.section_path, c.locator,
                       c.token_count, da.state AS artifact_state
                FROM chunks c JOIN document_artifacts da ON da.id = c.artifact_id
                WHERE da.document_version_id = $1 ORDER BY c.ordinal
                """,
                version_id,
            )
            return {
                "document": {"id": str(version["document_id"]), "title": version["title"]},
                "version": {
                    "id": str(version["id"]),
                    "version_no": version["version_no"],
                    "parse_status": version["parse_status"],
                    "warnings": _json_value(version["warnings"], []),
                },
                "chunks": [
                    {
                        **dict(chunk),
                        "section_path": _json_value(chunk["section_path"], []),
                        "locator": _json_value(chunk["locator"], {}),
                    }
                    for chunk in chunks
                ],
            }
        finally:
            await connection.close()

    @app.get("/api/v1/artifacts/{artifact_id}/chunks")
    async def artifact_chunks(artifact_id: int, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            artifact = await connection.fetchrow(
                """
                SELECT document_version_id, knowledge_base_id
                FROM document_artifacts WHERE id = $1
                """,
                artifact_id,
            )
            if artifact is None:
                raise HTTPException(status_code=404, detail="处理产物不存在")
            version = await connection.fetchrow(
                "SELECT document_id FROM document_versions WHERE id = $1",
                artifact["document_version_id"],
            )
            if version is None:
                raise HTTPException(status_code=404, detail="处理产物不存在")
            access = await _document_access(connection, context, int(version["document_id"]))
            if _role_for_access(access) in {
                "reader",
                "customer_reader",
            }:
                visible = await connection.fetchval(
                    """
                    SELECT EXISTS (
                      SELECT 1 FROM release_items ri
                      JOIN documents d ON d.id = ri.document_id
                      WHERE ri.release_id = (
                        SELECT active_release_id FROM knowledge_bases WHERE id = $1
                      )
                        AND ri.document_id = $2 AND ri.document_version_id = $3
                        AND d.status = 'active'
                    )
                    """,
                    artifact["knowledge_base_id"],
                    int(version["document_id"]),
                    artifact["document_version_id"],
                )
                if not visible:
                    raise HTTPException(status_code=404, detail="处理产物不存在")
            rows = await connection.fetch(
                """
                SELECT id::text, ordinal, content, section_path, locator, token_count
                FROM chunks WHERE artifact_id = $1 ORDER BY ordinal
                """,
                artifact_id,
            )
            return {"items": _rows(rows)}
        finally:
            await connection.close()

    @app.get("/api/v1/builds")
    async def list_builds(
        request: Request,
        tenant_id: int | None = None,
        knowledge_base_id: int | None = None,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            if knowledge_base_id is not None:
                access = await _knowledge_base_access(connection, context, knowledge_base_id)
                if tenant_id is not None and int(access["tenant_id"]) != tenant_id:
                    raise HTTPException(status_code=404, detail="构建不存在")
                tenant_ids = [int(access["tenant_id"])]
            elif tenant_id is not None:
                await _assert_tenant_access(connection, context, tenant_id)
                tenant_ids = [tenant_id]
            else:
                tenant_ids = [int(space["id"]) for space in context["spaces"]]
            if not tenant_ids:
                return {"items": []}
            rows = await connection.fetch(
                """
                SELECT ib.id::text, ib.tenant_id::text, ib.knowledge_base_id::text,
                       kb.name AS knowledge_base_name, ib.input_epoch, ib.state, ib.error,
                       ib.created_at, ib.updated_at, ib.task_id::text,
                       ib.embedding_profile_id::text, ep.model_name, ep.model_revision,
                       ep.dimension, ep.definition_hash AS embedding_definition_hash,
                       me.provider, me.base_url, kr.id::text AS release_id,
                       CASE WHEN kb.active_release_id = kr.id THEN true ELSE false END
                         AS is_active_release,
                       count(bi.document_id)::int AS document_count,
                       count(bi.document_id) FILTER (WHERE bi.state = 'completed')::int
                         AS completed_documents,
                       COALESCE(sum(bi.chunk_count), 0)::int AS chunk_count,
                       COALESCE(sum(bi.embedded_count), 0)::int AS embedded_count
                FROM index_builds ib
                JOIN knowledge_bases kb ON kb.id = ib.knowledge_base_id
                  AND kb.tenant_id = ib.tenant_id
                JOIN embedding_profiles ep ON ep.id = ib.embedding_profile_id
                JOIN model_endpoints me ON me.id = ep.model_endpoint_id
                LEFT JOIN kb_releases kr ON kr.build_id = ib.id
                LEFT JOIN build_items bi ON bi.build_id = ib.id AND bi.tenant_id = ib.tenant_id
                WHERE ib.tenant_id = ANY($1::bigint[])
                  AND ($2::bigint IS NULL OR ib.knowledge_base_id = $2)
                GROUP BY ib.id, kb.name, kb.active_release_id, ep.id, me.id, kr.id
                ORDER BY ib.created_at DESC, ib.id DESC
                """,
                tenant_ids,
                knowledge_base_id,
            )
            return {
                "items": [{**dict(row), "error": _json_value(row["error"], None)} for row in rows]
            }
        finally:
            await connection.close()

    @app.get("/api/v1/builds/{build_id}")
    async def build_detail(build_id: int, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            build = await connection.fetchrow(
                """
                SELECT ib.id::text, ib.tenant_id::text, ib.knowledge_base_id::text,
                       ib.input_epoch, ib.state, ib.error, ib.created_at, ib.updated_at,
                       ib.task_id::text, ib.embedding_profile_id::text,
                       ep.model_name, ep.model_revision, ep.dimension,
                       ep.definition_hash AS embedding_definition_hash,
                       me.provider, me.base_url, kr.id::text AS release_id,
                       CASE WHEN kb.active_release_id = kr.id THEN true ELSE false END
                         AS is_active_release
                FROM index_builds ib
                JOIN knowledge_bases kb ON kb.id = ib.knowledge_base_id
                  AND kb.tenant_id = ib.tenant_id
                JOIN embedding_profiles ep ON ep.id = ib.embedding_profile_id
                JOIN model_endpoints me ON me.id = ep.model_endpoint_id
                LEFT JOIN kb_releases kr ON kr.build_id = ib.id
                WHERE ib.id = $1
                """,
                build_id,
            )
            if build is None:
                raise HTTPException(status_code=404, detail="构建不存在")
            await _knowledge_base_access(connection, context, int(build["knowledge_base_id"]))
            items = await connection.fetch(
                """
                SELECT bi.document_id::text, d.title, bi.document_version_id::text,
                       dv.version_no, bi.artifact_id::text, bi.state, bi.chunk_count,
                       bi.embedded_count, bi.error, bi.updated_at
                FROM build_items bi
                JOIN documents d ON d.id = bi.document_id AND d.tenant_id = bi.tenant_id
                JOIN document_versions dv ON dv.id = bi.document_version_id
                  AND dv.tenant_id = bi.tenant_id
                WHERE bi.build_id = $1 ORDER BY d.title, bi.document_id
                """,
                build_id,
            )
            return {
                "build": {**dict(build), "error": _json_value(build["error"], None)},
                "items": [
                    {**dict(item), "error": _json_value(item["error"], None)} for item in items
                ],
            }
        finally:
            await connection.close()

    @app.get("/api/v1/knowledge-bases/{knowledge_base_id}/releases")
    async def list_releases(knowledge_base_id: int, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _knowledge_base_access(connection, context, knowledge_base_id)
            rows = await connection.fetch(
                """
                SELECT kr.id::text, kr.build_id::text, kr.manifest_hash, kr.state,
                       kr.created_at, kr.embedding_profile_id::text,
                       ep.model_name, ep.model_revision, ep.dimension,
                       ep.definition_hash AS embedding_definition_hash,
                       me.provider, me.base_url,
                       count(ri.document_id)::int AS document_count,
                       CASE WHEN kb.active_release_id = kr.id THEN true ELSE false END
                         AS is_active
                FROM kb_releases kr
                JOIN knowledge_bases kb ON kb.id = kr.knowledge_base_id
                  AND kb.tenant_id = kr.tenant_id
                JOIN embedding_profiles ep ON ep.id = kr.embedding_profile_id
                JOIN model_endpoints me ON me.id = ep.model_endpoint_id
                LEFT JOIN release_items ri ON ri.release_id = kr.id
                  AND ri.tenant_id = kr.tenant_id
                WHERE kr.tenant_id = $1 AND kr.knowledge_base_id = $2
                GROUP BY kr.id, kb.active_release_id, ep.id, me.id
                ORDER BY kr.created_at DESC, kr.id DESC
                """,
                access["tenant_id"],
                knowledge_base_id,
            )
            items = _rows(rows)
            current_release_id = (
                int(access["active_release_id"])
                if access["active_release_id"] is not None
                else None
            )
            rollback_ids = (
                rollback_candidate_ids(items, current_release_id=current_release_id)
                if _role_for_access(access) in {"space_admin", "kb_admin"}
                else set()
            )
            for item in items:
                item["rollback_available"] = int(item["id"]) in rollback_ids
            return {
                "active_release_id": (
                    str(access["active_release_id"])
                    if access["active_release_id"] is not None
                    else None
                ),
                "items": items,
            }
        finally:
            await connection.close()

    @app.get("/api/v1/builds/{build_id}/release-preview")
    async def release_preview(build_id: int, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            preview = await _load_release_preview(connection, build_id)
            if preview is None:
                raise HTTPException(status_code=404, detail="构建不存在")
            build = preview["build_record"]
            await _require_knowledge_base_role(
                connection,
                context,
                int(build["knowledge_base_id"]),
                {"space_admin", "kb_admin"},
            )
            return _release_preview_response(preview)
        finally:
            await connection.close()

    @app.post("/api/v1/search-test")
    async def search_test(payload: SearchTestRequest, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _knowledge_base_access(
                connection,
                context,
                payload.knowledge_base_id,
            )
            diagnostic_started = time.perf_counter()
            try:
                result = await execute_vector_search(
                    connection,
                    config,
                    tenant_id=int(access["tenant_id"]),
                    knowledge_base_id=payload.knowledge_base_id,
                    user_id=int(context["user"]["id"]),
                    query=payload.query,
                    active_release_id=(
                        int(access["active_release_id"])
                        if access["active_release_id"] is not None
                        else None
                    ),
                    top_k=payload.top_k,
                    context_max_chars=payload.context_max_chars,
                )
            except RetrievalServiceError as error:
                # 只记录检索状态和 trace 关联信息，不记录问题正文、候选片段或模型响应。
                trace_id = error.trace_id
                await write_audit_event(
                    connection,
                    tenant_id=int(access["tenant_id"]),
                    actor_id=int(context["user"]["id"]),
                    action="search_test.run",
                    target_type="retrieval_trace" if trace_id else "knowledge_base",
                    target_id=trace_id or payload.knowledge_base_id,
                    summary={
                        "knowledge_base_id": str(payload.knowledge_base_id),
                        "trace_id": str(trace_id) if trace_id else None,
                        "state": "failed",
                        "error_code": "RETRIEVAL_SERVICE_ERROR",
                        "total_ms": round((time.perf_counter() - diagnostic_started) * 1000, 2),
                    },
                )
                raise HTTPException(status_code=502, detail=str(error)) from error
            trace_id = result.get("trace_id")
            await write_audit_event(
                connection,
                tenant_id=int(access["tenant_id"]),
                actor_id=int(context["user"]["id"]),
                action="search_test.run",
                target_type="retrieval_trace" if trace_id else "knowledge_base",
                target_id=trace_id or payload.knowledge_base_id,
                summary={
                    "knowledge_base_id": str(payload.knowledge_base_id),
                    "trace_id": trace_id,
                    "state": str(result.get("state", "unknown")),
                    "item_count": len(result.get("items") or []),
                    "total_ms": (result.get("timings") or {}).get(
                        "total_ms",
                        round((time.perf_counter() - diagnostic_started) * 1000, 2),
                    ),
                },
            )
            return result
        finally:
            await connection.close()

    @app.get("/api/v1/conversations")
    async def list_conversations(
        request: Request,
        knowledge_base_id: int,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _knowledge_base_access(connection, context, knowledge_base_id)
            rows = await connection.fetch(
                """
                SELECT conversation.public_id::text AS id, conversation.tenant_id::text,
                       conversation.knowledge_base_id::text, conversation.title,
                       conversation.status, conversation.created_at, conversation.updated_at,
                       count(message.id)::int AS message_count
                FROM conversations conversation
                LEFT JOIN messages message ON message.conversation_id = conversation.id
                  AND message.tenant_id = conversation.tenant_id
                WHERE conversation.tenant_id = $1
                  AND conversation.knowledge_base_id = $2
                  AND conversation.owner_user_id = $3
                  AND conversation.status = 'active'
                GROUP BY conversation.id
                ORDER BY conversation.updated_at DESC, conversation.id DESC
                """,
                access["tenant_id"],
                knowledge_base_id,
                int(context["user"]["id"]),
            )
            return {"items": _rows(rows)}
        finally:
            await connection.close()

    @app.post("/api/v1/conversations", status_code=201)
    async def create_conversation(
        payload: ConversationCreate,
        request: Request,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _knowledge_base_access(connection, context, payload.knowledge_base_id)
            row = await connection.fetchrow(
                """
                INSERT INTO conversations(
                  tenant_id, knowledge_base_id, owner_user_id, title
                ) VALUES ($1, $2, $3, $4)
                RETURNING public_id::text AS id, tenant_id::text, knowledge_base_id::text,
                          title, status, created_at, updated_at
                """,
                access["tenant_id"],
                payload.knowledge_base_id,
                int(context["user"]["id"]),
                payload.title,
            )
            if row is None:
                raise HTTPException(status_code=500, detail="会话创建失败")
            return dict(row)
        finally:
            await connection.close()

    @app.delete("/api/v1/conversations/{conversation_id}", status_code=204)
    async def delete_conversation(conversation_id: UUID, request: Request) -> None:
        """软删除当前用户拥有的会话，保留消息历史并写入租户审计日志。"""
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            internal_id = await _conversation_id_from_public(connection, context, conversation_id)
            conversation = await _conversation_access(connection, context, internal_id)
            # 会话只能由其所有者删除；复用访问检查可同时保证知识库权限和租户隔离。
            async with connection.transaction():
                await connection.execute(
                    """
                    UPDATE conversations
                    SET status = 'deleted', updated_at = now()
                    WHERE id = $1 AND tenant_id = $2 AND status = 'active'
                    """,
                    internal_id,
                    conversation["tenant_id"],
                )
                await write_audit_event(
                    connection,
                    tenant_id=int(conversation["tenant_id"]),
                    actor_id=int(context["user"]["id"]),
                    action="conversation.delete",
                    target_type="conversation",
                    target_id=conversation_id,
                    summary={
                        "knowledge_base_id": str(conversation["knowledge_base_id"]),
                        "before": {"status": str(conversation["status"])},
                        "after": {"status": "deleted"},
                    },
                )
        finally:
            await connection.close()

    @app.get("/api/v1/conversations/{conversation_id}")
    async def get_conversation(conversation_id: UUID, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            conversation_id_int = await _conversation_id_from_public(
                connection, context, conversation_id
            )
            conversation = await _conversation_access(
                connection,
                context,
                conversation_id_int,
            )
            rows = await connection.fetch(
                """
                SELECT message.id::text, message.role, message.content, message.state,
                       message.release_id::text, message.created_at,
                       run.id::text AS run_id, feedback.rating AS feedback_rating,
                       feedback.reason AS feedback_reason
                FROM messages message
                LEFT JOIN generation_runs run ON run.assistant_message_id = message.id
                  AND run.tenant_id = message.tenant_id
                LEFT JOIN feedback ON feedback.message_id = message.id
                  AND feedback.tenant_id = message.tenant_id AND feedback.user_id = $3
                WHERE message.tenant_id = $1 AND message.conversation_id = $2
                ORDER BY message.created_at, message.id
                """,
                conversation["tenant_id"],
                conversation_id_int,
                int(context["user"]["id"]),
            )
            messages = []
            for row in rows:
                item = dict(row)
                item["citations"] = []
                item["hidden"] = False
                if item["run_id"] is not None:
                    snapshot = await load_run_snapshot(
                        connection,
                        run_id=int(item["run_id"]),
                        user_id=int(context["user"]["id"]),
                        api_key_tenant_id=context.get("api_key_tenant_id"),
                        api_key_id=context.get("api_key_id"),
                    )
                    if snapshot is not None:
                        item["content"] = snapshot["answer"]
                        item["state"] = snapshot["message_state"]
                        item["citations"] = snapshot["citations"]
                        item["hidden"] = snapshot["hidden"]
                        item["run_state"] = snapshot["state"]
                        item["outcome"] = snapshot["outcome"]
                messages.append(item)
            return {
                "conversation": {
                    "id": str(conversation_id),
                    "tenant_id": str(conversation["tenant_id"]),
                    "knowledge_base_id": str(conversation["knowledge_base_id"]),
                    "knowledge_base_name": conversation["knowledge_base_name"],
                    "title": conversation["title"],
                    "status": conversation["status"],
                    "active_release_id": (
                        str(conversation["active_release_id"])
                        if conversation["active_release_id"] is not None
                        else None
                    ),
                },
                "messages": messages,
            }
        finally:
            await connection.close()

    @app.post("/api/v1/conversations/{conversation_id}/runs", status_code=202)
    async def create_run(
        conversation_id: UUID,
        payload: RunCreate,
        request: Request,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            conversation_id_int = await _conversation_id_from_public(
                connection, context, conversation_id
            )
            conversation = await _conversation_access(connection, context, conversation_id_int)
            async with connection.transaction():
                result = await _create_generation_run(
                    connection,
                    conversation=conversation,
                    user_id=int(context["user"]["id"]),
                    request_id=payload.request_id,
                    question=payload.question,
                    api_key_id=context.get("api_key_id"),
                )
                return _public_run_payload(result)
        finally:
            await connection.close()

    @app.get("/api/v1/runs/{run_id}")
    async def get_run(run_id: UUID, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            run_id_int = await _run_id_from_public(connection, str(run_id))
            snapshot = await load_run_snapshot(
                connection,
                run_id=run_id_int,
                user_id=int(context["user"]["id"]),
                api_key_tenant_id=context.get("api_key_tenant_id"),
                api_key_id=context.get("api_key_id"),
            )
            if snapshot is None:
                raise HTTPException(status_code=404, detail="问答运行不存在")
            return _public_run_payload(snapshot)
        finally:
            await connection.close()

    @app.get("/api/v1/runs/{run_id}/events")
    async def stream_run_events(run_id: UUID, request: Request) -> StreamingResponse:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            run_id_int = await _run_id_from_public(connection, str(run_id))
        finally:
            await connection.close()
        return StreamingResponse(
            stream_generation_run(
                config,
                run_id=run_id_int,
                user_id=int(context["user"]["id"]),
                api_key_id=context.get("api_key_id"),
                api_key_tenant_id=context.get("api_key_tenant_id"),
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/api/v1/runs/{run_id}/cancel")
    async def cancel_run(run_id: UUID, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            run_id_int = await _run_id_from_public(connection, str(run_id))
            snapshot = await load_run_snapshot(
                connection,
                run_id=run_id_int,
                user_id=int(context["user"]["id"]),
                api_key_tenant_id=context.get("api_key_tenant_id"),
                api_key_id=context.get("api_key_id"),
            )
            if snapshot is None:
                raise HTTPException(status_code=404, detail="问答运行不存在")
            if snapshot["state"] in {"completed", "failed", "cancelled"}:
                return _public_run_payload(snapshot)
            async with connection.transaction():
                cancelled_run_id = await connection.fetchval(
                    """
                    UPDATE generation_runs SET cancel_requested = true,
                        state = 'cancelled', completed_at = now(),
                        updated_at = now()
                    WHERE id = $1 AND tenant_id = $2 AND state IN ('queued','running')
                    RETURNING id
                    """,
                    run_id_int,
                    int(snapshot["tenant_id"]),
                )
                if cancelled_run_id is not None:
                    await connection.execute(
                        """
                        UPDATE retrieval_traces SET state = 'cancelled'
                        WHERE tenant_id = $1 AND message_id = $2 AND state = 'running'
                        """,
                        int(snapshot["tenant_id"]),
                        int(snapshot["assistant_message_id"]),
                    )
                    await connection.execute(
                        """
                        UPDATE messages SET state = 'cancelled'
                        WHERE id = $1 AND tenant_id = $2
                        """,
                        int(snapshot["assistant_message_id"]),
                        int(snapshot["tenant_id"]),
                    )
            latest = await load_run_snapshot(
                connection,
                run_id=run_id_int,
                user_id=int(context["user"]["id"]),
                api_key_tenant_id=context.get("api_key_tenant_id"),
                api_key_id=context.get("api_key_id"),
            )
            if latest is None:
                raise HTTPException(status_code=404, detail="问答运行不存在")
            return _public_run_payload(latest)
        finally:
            await connection.close()

    @app.post("/api/v1/runs/{run_id}/retry", status_code=202)
    async def retry_run(
        run_id: UUID,
        payload: RunRetryRequest,
        request: Request,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            run_id_int = await _run_id_from_public(connection, str(run_id))
            snapshot = await load_run_snapshot(
                connection,
                run_id=run_id_int,
                user_id=int(context["user"]["id"]),
                api_key_tenant_id=context.get("api_key_tenant_id"),
                api_key_id=context.get("api_key_id"),
            )
            if snapshot is None:
                raise HTTPException(status_code=404, detail="问答运行不存在")
            if snapshot["state"] not in {"failed", "cancelled"}:
                raise HTTPException(status_code=409, detail="只有失败或已取消的运行可以重试")
            conversation = await _conversation_access(
                connection,
                context,
                int(snapshot["conversation_id"]),
            )
            async with connection.transaction():
                result = await _create_generation_run(
                    connection,
                    conversation=conversation,
                    user_id=int(context["user"]["id"]),
                    request_id=payload.request_id,
                    question=str(snapshot["question"]),
                    user_message_id=int(snapshot["user_message_id"]),
                    api_key_id=context.get("api_key_id"),
                )
                return _public_run_payload(result)
        finally:
            await connection.close()

    @app.post("/api/v1/messages/{message_id}/feedback")
    async def save_feedback(
        message_id: int,
        payload: FeedbackCreate,
        request: Request,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            message = await connection.fetchrow(
                """
                SELECT message.id, message.tenant_id, message.conversation_id
                FROM messages message
                WHERE message.id = $1 AND message.role = 'assistant'
                """,
                message_id,
            )
            if message is None:
                raise HTTPException(status_code=404, detail="回答不存在")
            await _conversation_access(connection, context, int(message["conversation_id"]))
            row = await connection.fetchrow(
                """
                INSERT INTO feedback(tenant_id, message_id, user_id, rating, reason)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (message_id, user_id)
                DO UPDATE SET rating = EXCLUDED.rating, reason = EXCLUDED.reason,
                              created_at = now()
                RETURNING message_id::text, rating, reason, created_at
                """,
                message["tenant_id"],
                message_id,
                int(context["user"]["id"]),
                payload.rating,
                payload.reason,
            )
            if row is None:
                raise HTTPException(status_code=500, detail="反馈保存失败")
            return dict(row)
        finally:
            await connection.close()

    @app.post("/api/v1/builds/{build_id}/publish", status_code=201)
    async def publish_build(
        build_id: int,
        payload: ReleasePublishRequest,
        request: Request,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            preview = await _load_release_preview(connection, build_id)
            if preview is None:
                raise HTTPException(status_code=404, detail="构建不存在")
            build = preview["build_record"]
            access = await _require_knowledge_base_role(
                connection,
                context,
                int(build["knowledge_base_id"]),
                {"space_admin", "kb_admin"},
            )
            user_id = int(context["user"]["id"])
            async with connection.transaction():
                knowledge_base = await connection.fetchrow(
                    """
                    SELECT id, tenant_id, active_release_id
                    FROM knowledge_bases
                    WHERE id = $1 AND tenant_id = $2
                    FOR UPDATE
                    """,
                    build["knowledge_base_id"],
                    access["tenant_id"],
                )
                if knowledge_base is None:
                    raise HTTPException(status_code=404, detail="知识库不存在")
                current_active_release_id = (
                    int(knowledge_base["active_release_id"])
                    if knowledge_base["active_release_id"] is not None
                    else None
                )
                if payload.expected_active_release_id != current_active_release_id:
                    raise HTTPException(
                        status_code=409,
                        detail="当前发布版本已变化，请刷新差异后重试",
                    )

                preview = await _load_release_preview(connection, build_id)
                if preview is None:
                    raise HTTPException(status_code=404, detail="构建不存在")
                validation = preview["validation"]
                if not validation["ready"]:
                    first_error = validation["errors"][0]
                    raise HTTPException(status_code=409, detail=first_error["message"])

                existing = await connection.fetchrow(
                    """
                    SELECT id::text, build_id::text, manifest_hash, state, created_at
                    FROM kb_releases
                    WHERE build_id = $1 OR (
                      knowledge_base_id = $2 AND manifest_hash = $3
                    )
                    ORDER BY id DESC LIMIT 1
                    """,
                    build_id,
                    build["knowledge_base_id"],
                    preview["manifest_hash"],
                )
                if existing is not None:
                    if current_active_release_id == int(existing["id"]):
                        return {**dict(existing), "reused": True, "diff": preview["diff"]}
                    raise HTTPException(
                        status_code=409,
                        detail="该构建已经生成过 Release，请使用发布历史进行回退",
                    )

                release = await connection.fetchrow(
                    """
                    INSERT INTO kb_releases(
                      tenant_id, knowledge_base_id, build_id,
                      embedding_profile_id, manifest_hash, state
                    ) VALUES ($1, $2, $3, $4, $5, 'ready')
                    RETURNING id::text, build_id::text, manifest_hash, state, created_at
                    """,
                    build["tenant_id"],
                    build["knowledge_base_id"],
                    build_id,
                    build["embedding_profile_id"],
                    preview["manifest_hash"],
                )
                for item in preview["candidate_records"]:
                    await connection.execute(
                        """
                        INSERT INTO release_items(
                          release_id, tenant_id, knowledge_base_id, document_id,
                          document_version_id, artifact_id
                        ) VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        int(release["id"]),
                        build["tenant_id"],
                        build["knowledge_base_id"],
                        item["document_id"],
                        item["document_version_id"],
                        item["artifact_id"],
                    )
                if current_active_release_id is not None:
                    await connection.execute(
                        "UPDATE kb_releases SET state = 'retired' WHERE id = $1",
                        current_active_release_id,
                    )
                switched = await connection.fetchval(
                    """
                    UPDATE knowledge_bases
                    SET active_release_id = $3, status = 'published', updated_at = now()
                    WHERE id = $1 AND tenant_id = $2
                      AND active_release_id IS NOT DISTINCT FROM $4::bigint
                    RETURNING id
                    """,
                    build["knowledge_base_id"],
                    build["tenant_id"],
                    int(release["id"]),
                    payload.expected_active_release_id,
                )
                if switched is None:
                    raise HTTPException(
                        status_code=409,
                        detail="当前发布版本已变化，请刷新差异后重试",
                    )
                await connection.execute(
                    """
                    INSERT INTO audit_logs(
                      tenant_id, actor_id, action, target_type, target_id, change_summary
                    ) VALUES ($1, $2, 'release.publish', 'knowledge_base', $3, $4::jsonb)
                    """,
                    build["tenant_id"],
                    user_id,
                    str(build["knowledge_base_id"]),
                    json.dumps(
                        {
                            "release_id": release["id"],
                            "build_id": str(build_id),
                            "previous_release_id": (
                                str(current_active_release_id)
                                if current_active_release_id is not None
                                else None
                            ),
                            "manifest_hash": preview["manifest_hash"],
                            "diff": preview["diff"]["counts"],
                        },
                        ensure_ascii=False,
                    ),
                )
            return {**dict(release), "reused": False, "diff": preview["diff"]}
        except asyncpg.UniqueViolationError as error:
            raise HTTPException(status_code=409, detail="该构建已经生成过 Release") from error
        finally:
            await connection.close()

    @app.post("/api/v1/releases/{release_id}/rollback")
    async def rollback_release(
        release_id: int,
        payload: ReleaseRollbackRequest,
        request: Request,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            target = await connection.fetchrow(
                """
                SELECT id, tenant_id, knowledge_base_id, build_id, manifest_hash, state
                FROM kb_releases WHERE id = $1
                """,
                release_id,
            )
            if target is None:
                raise HTTPException(status_code=404, detail="Release 不存在")
            access = await _require_knowledge_base_role(
                connection,
                context,
                int(target["knowledge_base_id"]),
                {"space_admin", "kb_admin"},
            )
            user_id = int(context["user"]["id"])
            async with connection.transaction():
                knowledge_base = await connection.fetchrow(
                    """
                    SELECT id, tenant_id, active_release_id
                    FROM knowledge_bases
                    WHERE id = $1 AND tenant_id = $2
                    FOR UPDATE
                    """,
                    target["knowledge_base_id"],
                    access["tenant_id"],
                )
                if knowledge_base is None:
                    raise HTTPException(status_code=404, detail="知识库不存在")
                current_release_id = (
                    int(knowledge_base["active_release_id"])
                    if knowledge_base["active_release_id"] is not None
                    else None
                )
                if payload.expected_active_release_id != current_release_id:
                    raise HTTPException(
                        status_code=409,
                        detail="当前发布版本已变化，请刷新发布历史后重试",
                    )
                if current_release_id == release_id:
                    raise HTTPException(status_code=409, detail="该 Release 已经是当前版本")
                if target["state"] != "retired":
                    raise HTTPException(status_code=409, detail="该 Release 当前不可回退")

                recent_releases = await connection.fetch(
                    """
                    SELECT id::text, state
                    FROM kb_releases
                    WHERE tenant_id = $1 AND knowledge_base_id = $2
                      AND id <> $3 AND state = 'retired'
                    ORDER BY created_at DESC, id DESC
                    LIMIT 2
                    """,
                    access["tenant_id"],
                    target["knowledge_base_id"],
                    current_release_id,
                )
                candidate_ids = rollback_candidate_ids(
                    [dict(item) for item in recent_releases],
                    current_release_id=current_release_id,
                )
                if release_id not in candidate_ids:
                    raise HTTPException(
                        status_code=409,
                        detail="只允许回退到最近两个历史 Release",
                    )

                invalid_sources = await connection.fetch(
                    """
                    SELECT ri.document_id::text,
                           COALESCE(d.title, '来源 #' || ri.document_id::text) AS title
                    FROM release_items ri
                    LEFT JOIN documents d ON d.id = ri.document_id
                      AND d.tenant_id = ri.tenant_id
                      AND d.knowledge_base_id = ri.knowledge_base_id
                    LEFT JOIN document_versions dv ON dv.id = ri.document_version_id
                      AND dv.tenant_id = ri.tenant_id AND dv.document_id = ri.document_id
                    LEFT JOIN document_artifacts da ON da.id = ri.artifact_id
                      AND da.tenant_id = ri.tenant_id
                      AND da.knowledge_base_id = ri.knowledge_base_id
                      AND da.document_version_id = ri.document_version_id
                    WHERE ri.release_id = $1
                      AND (
                        d.id IS NULL OR d.status <> 'active'
                        OR dv.id IS NULL OR dv.parse_status <> 'complete'
                        OR da.id IS NULL OR da.state <> 'ready'
                      )
                    ORDER BY ri.document_id
                    """,
                    release_id,
                )
                if invalid_sources:
                    titles = "、".join(str(item["title"]) for item in invalid_sources[:3])
                    raise HTTPException(
                        status_code=409,
                        detail=f"Release 包含已删除、停用或失效来源，不能回退：{titles}",
                    )

                await connection.execute(
                    "UPDATE kb_releases SET state = 'retired' WHERE id = $1",
                    current_release_id,
                )
                rolled_back = await connection.fetchrow(
                    """
                    UPDATE kb_releases SET state = 'ready'
                    WHERE id = $1 AND tenant_id = $2 AND knowledge_base_id = $3
                    RETURNING id::text, build_id::text, manifest_hash, state, created_at
                    """,
                    release_id,
                    access["tenant_id"],
                    target["knowledge_base_id"],
                )
                switched = await connection.fetchval(
                    """
                    UPDATE knowledge_bases
                    SET active_release_id = $3, status = 'published', updated_at = now()
                    WHERE id = $1 AND tenant_id = $2 AND active_release_id = $4
                    RETURNING id
                    """,
                    target["knowledge_base_id"],
                    access["tenant_id"],
                    release_id,
                    payload.expected_active_release_id,
                )
                if switched is None or rolled_back is None:
                    raise HTTPException(
                        status_code=409,
                        detail="当前发布版本已变化，请刷新发布历史后重试",
                    )
                await connection.execute(
                    """
                    INSERT INTO audit_logs(
                      tenant_id, actor_id, action, target_type, target_id, change_summary
                    ) VALUES ($1, $2, 'release.rollback', 'knowledge_base', $3, $4::jsonb)
                    """,
                    access["tenant_id"],
                    user_id,
                    str(target["knowledge_base_id"]),
                    json.dumps(
                        {
                            "release_id": str(release_id),
                            "build_id": str(target["build_id"]),
                            "previous_release_id": str(current_release_id),
                            "manifest_hash": target["manifest_hash"],
                        },
                        ensure_ascii=False,
                    ),
                )
            return {
                **dict(rolled_back),
                "previous_release_id": str(current_release_id),
            }
        finally:
            await connection.close()

    @app.post("/api/v1/knowledge-bases/{knowledge_base_id}/builds", status_code=202)
    async def create_build(knowledge_base_id: int, request: Request) -> dict[str, Any]:
        """冻结当前有效文档与 Profile，创建异步构建并记录构建请求审计。"""
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _require_knowledge_base_role(
                connection,
                context,
                knowledge_base_id,
                {"space_admin", "kb_admin"},
            )
            user_id = int(context["user"]["id"])
            async with connection.transaction():
                knowledge_base = await connection.fetchrow(
                    """
                    SELECT id, tenant_id, content_epoch, active_release_id, active_runtime_id
                    FROM knowledge_bases WHERE id = $1 AND tenant_id = $2
                    FOR UPDATE
                    """,
                    knowledge_base_id,
                    access["tenant_id"],
                )
                if knowledge_base is None:
                    raise HTTPException(status_code=404, detail="知识库不存在")
                active_build = await connection.fetchval(
                    """
                    SELECT id FROM index_builds
                    WHERE knowledge_base_id = $1 AND state IN ('queued','running','validating')
                    ORDER BY id DESC LIMIT 1
                    """,
                    knowledge_base_id,
                )
                if active_build is not None:
                    raise HTTPException(status_code=409, detail="该知识库已有正在执行的构建")
                documents = await connection.fetch(
                    """
                    SELECT d.id AS document_id, d.title, d.desired_version_id,
                           dv.parse_status, artifact.id AS artifact_id,
                           artifact.ingestion_profile_id, artifact.state AS artifact_state,
                           count(c.id)::int AS chunk_count
                    FROM documents d
                    LEFT JOIN document_versions dv ON dv.id = d.desired_version_id
                      AND dv.tenant_id = d.tenant_id
                    LEFT JOIN LATERAL (
                      SELECT da.id, da.ingestion_profile_id, da.state
                      FROM document_artifacts da
                      WHERE da.tenant_id = d.tenant_id
                        AND da.document_version_id = d.desired_version_id
                      ORDER BY da.created_at DESC, da.id DESC LIMIT 1
                    ) artifact ON true
                    LEFT JOIN chunks c ON c.tenant_id = d.tenant_id
                      AND c.artifact_id = artifact.id
                    WHERE d.tenant_id = $1 AND d.knowledge_base_id = $2
                      AND d.status = 'active'
                    GROUP BY d.id, dv.id, artifact.id, artifact.ingestion_profile_id,
                             artifact.state
                    ORDER BY d.id
                    """,
                    access["tenant_id"],
                    knowledge_base_id,
                )
                if not documents:
                    raise HTTPException(status_code=409, detail="知识库中没有可构建文档")
                invalid_documents = [
                    str(document["title"])
                    for document in documents
                    if document["desired_version_id"] is None
                    or document["parse_status"] != "complete"
                    or document["artifact_id"] is None
                    or document["artifact_state"] != "ready"
                    or int(document["chunk_count"]) == 0
                ]
                if invalid_documents:
                    raise HTTPException(
                        status_code=409,
                        detail=f"以下文档尚未完整解析：{'、'.join(invalid_documents[:5])}",
                    )
                ingestion_profile_ids = {
                    int(document["ingestion_profile_id"]) for document in documents
                }
                if len(ingestion_profile_ids) != 1:
                    raise HTTPException(
                        status_code=409,
                        detail="文档切片配置不一致，请重新解析后构建",
                    )
                configured_embedding = None
                if knowledge_base["active_runtime_id"] is not None:
                    configured_embedding = await connection.fetchrow(
                        """
                        SELECT ep.id, ep.model_name, ep.model_revision, ep.dimension,
                               me.base_url, me.allowed_models, me.status AS endpoint_status
                        FROM runtime_profiles rp
                        JOIN embedding_profiles ep ON ep.id = rp.embedding_profile_id
                        JOIN model_endpoints me ON me.id = ep.model_endpoint_id
                        WHERE rp.id = $1 AND rp.tenant_id = $2
                          AND rp.knowledge_base_id = $3
                        """,
                        knowledge_base["active_runtime_id"],
                        access["tenant_id"],
                        knowledge_base_id,
                    )
                if configured_embedding is not None:
                    if configured_embedding["endpoint_status"] != "active":
                        raise HTTPException(status_code=409, detail="当前嵌入模型端点已停用")
                    allowed_models = _json_value(configured_embedding["allowed_models"], [])
                    effective_settings = gateway_settings(
                        config,
                        base_url=str(configured_embedding["base_url"]),
                        allowed_models=allowed_models,
                        embedding_model=str(configured_embedding["model_name"]),
                        embedding_dimensions=int(configured_embedding["dimension"]),
                    )
                    try:
                        model_revision = await ModelGatewayClient(
                            effective_settings
                        ).model_revision()
                    except (httpx.HTTPError, ValueError) as error:
                        raise HTTPException(status_code=503, detail="嵌入模型当前不可用") from error
                    if model_revision != configured_embedding["model_revision"]:
                        raise HTTPException(
                            status_code=409,
                            detail="嵌入模型内容已变化，请创建新的 Embedding Profile",
                        )
                    embedding_profile_id = int(configured_embedding["id"])
                    selected_embedding_model = str(configured_embedding["model_name"])
                    selected_embedding_dimension = int(configured_embedding["dimension"])
                else:
                    try:
                        model_revision = await ModelGatewayClient(config).model_revision()
                    except (httpx.HTTPError, ValueError) as error:
                        raise HTTPException(status_code=503, detail="嵌入模型当前不可用") from error
                    embedding_profile_id, _ = await _ensure_embedding_profile(
                        connection,
                        config,
                        model_revision,
                    )
                    selected_embedding_model = config.embedding_model
                    selected_embedding_dimension = config.embedding_dimensions
                ingestion_profile_id = ingestion_profile_ids.pop()
                existing = await connection.fetchrow(
                    """
                    SELECT ib.id::text, ib.task_id::text, ib.state, ib.created_at,
                           ib.updated_at, ib.input_epoch, ep.model_name,
                           ep.model_revision, ep.dimension
                    FROM index_builds ib
                    JOIN embedding_profiles ep ON ep.id = ib.embedding_profile_id
                    WHERE ib.knowledge_base_id = $1 AND ib.input_epoch = $2
                      AND ib.ingestion_profile_id = $3 AND ib.embedding_profile_id = $4
                    """,
                    knowledge_base_id,
                    knowledge_base["content_epoch"],
                    ingestion_profile_id,
                    embedding_profile_id,
                )
                if existing is not None:
                    return {**dict(existing), "reused": True}
                task = await connection.fetchrow(
                    """
                    INSERT INTO tasks(
                      tenant_id, knowledge_base_id, task_type, state,
                      idempotency_key, created_by
                    ) VALUES ($1, $2, 'index_build', 'queued', $3, $4)
                    RETURNING id
                    """,
                    access["tenant_id"],
                    knowledge_base_id,
                    (
                        f"index-build:{knowledge_base_id}:"
                        f"{knowledge_base['content_epoch']}:{embedding_profile_id}"
                    ),
                    user_id,
                )
                build = await connection.fetchrow(
                    """
                    INSERT INTO index_builds(
                      tenant_id, knowledge_base_id, base_release_id, input_epoch,
                      ingestion_profile_id, embedding_profile_id, task_id,
                      state, created_by
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, 'queued', $8)
                    RETURNING id::text, task_id::text, state, input_epoch, created_at, updated_at
                    """,
                    access["tenant_id"],
                    knowledge_base_id,
                    knowledge_base["active_release_id"],
                    knowledge_base["content_epoch"],
                    ingestion_profile_id,
                    embedding_profile_id,
                    task["id"],
                    user_id,
                )
                for document in documents:
                    await connection.execute(
                        """
                        INSERT INTO build_items(
                          build_id, tenant_id, knowledge_base_id, document_id,
                          document_version_id, artifact_id, chunk_count
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                        """,
                        int(build["id"]),
                        access["tenant_id"],
                        knowledge_base_id,
                        document["document_id"],
                        document["desired_version_id"],
                        document["artifact_id"],
                        document["chunk_count"],
                    )
                    await connection.execute(
                        """
                        INSERT INTO task_items(task_id, target_id, stage, state)
                        VALUES ($1, $2, 'embed', 'queued')
                        """,
                        task["id"],
                        document["desired_version_id"],
                    )
                await connection.execute(
                    """
                    INSERT INTO outbox_events(tenant_id, event_type, payload)
                    VALUES ($1, 'index.build.requested', $2::jsonb)
                    """,
                    access["tenant_id"],
                    json.dumps(
                        {"task_id": str(task["id"]), "build_id": build["id"]},
                        ensure_ascii=False,
                    ),
                )
                # 记录快照关键标识与数量，不把文档正文、向量或模型凭据写入审计。
                await write_audit_event(
                    connection,
                    tenant_id=int(access["tenant_id"]),
                    actor_id=user_id,
                    action="build.create",
                    target_type="build",
                    target_id=build["id"],
                    summary={
                        "knowledge_base_id": str(knowledge_base_id),
                        "task_id": str(task["id"]),
                        "input_epoch": int(knowledge_base["content_epoch"]),
                        "document_count": len(documents),
                        "ingestion_profile_id": str(ingestion_profile_id),
                        "embedding_profile_id": str(embedding_profile_id),
                    },
                )
            return {
                **dict(build),
                "knowledge_base_id": str(knowledge_base_id),
                "document_count": len(documents),
                "model_name": selected_embedding_model,
                "model_revision": model_revision,
                "dimension": selected_embedding_dimension,
                "reused": False,
            }
        except asyncpg.UniqueViolationError as error:
            raise HTTPException(status_code=409, detail="相同内容和模型的构建已经存在") from error
        finally:
            await connection.close()

    @app.get("/api/v1/tasks")
    async def list_tasks(
        request: Request,
        tenant_id: int | None = None,
        knowledge_base_id: int | None = None,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            if knowledge_base_id is not None:
                access = await _knowledge_base_access(connection, context, knowledge_base_id)
                if tenant_id is not None and int(access["tenant_id"]) != tenant_id:
                    raise HTTPException(status_code=404, detail="任务不存在")
                tenant_ids = [int(access["tenant_id"])]
                kb_ids = [knowledge_base_id]
            elif tenant_id is not None:
                await _assert_tenant_access(connection, context, tenant_id)
                tenant_ids = [tenant_id]
                kb_ids = None
            else:
                tenant_ids = [int(space["id"]) for space in context["spaces"]]
                kb_ids = None
            if not tenant_ids:
                return {"items": []}
            rows = await connection.fetch(
                """
                SELECT t.id::text, t.tenant_id::text, t.knowledge_base_id::text,
                       t.task_type, t.state, t.attempt, t.error, t.created_at, t.updated_at,
                       count(ti.id)::int AS item_count,
                       count(ti.id) FILTER (WHERE ti.state = 'completed')::int AS completed_items
                FROM tasks t LEFT JOIN task_items ti ON ti.task_id = t.id
                WHERE t.tenant_id = ANY($1::bigint[])
                  AND ($2::bigint[] IS NULL OR t.knowledge_base_id = ANY($2::bigint[]))
                GROUP BY t.id ORDER BY t.created_at DESC LIMIT 100
                """,
                tenant_ids,
                kb_ids,
            )
            return {"items": _rows(rows)}
        finally:
            await connection.close()

    @app.get("/api/v1/tasks/{task_id}")
    async def task_detail(task_id: int, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            task = await connection.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
            if task is None:
                raise HTTPException(status_code=404, detail="任务不存在")
            if task["knowledge_base_id"] is not None:
                await _knowledge_base_access(connection, context, int(task["knowledge_base_id"]))
            elif int(task["tenant_id"]) not in {int(space["id"]) for space in context["spaces"]}:
                raise HTTPException(status_code=404, detail="任务不存在")
            items = await connection.fetch(
                """
                SELECT id::text, target_id::text, stage, state, attempt, error, updated_at
                FROM task_items WHERE task_id = $1 ORDER BY id
                """,
                task_id,
            )
            return {"task": {**dict(task), "id": str(task["id"])}, "items": _rows(items)}
        finally:
            await connection.close()

    @app.post("/api/v1/tasks/{task_id}/retry")
    async def retry_task(task_id: int, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            task = await connection.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
            if task is None or task["knowledge_base_id"] is None:
                raise HTTPException(status_code=404, detail="任务不存在")
            retry_roles = (
                {"space_admin", "kb_admin"}
                if task["task_type"] == "index_build"
                else {"space_admin", "kb_admin", "editor"}
            )
            access = await _require_knowledge_base_role(
                connection,
                context,
                int(task["knowledge_base_id"]),
                retry_roles,
            )
            if task["state"] not in {"failed", "cancelled", "interrupted"}:
                raise HTTPException(status_code=409, detail="当前任务状态不能重试")
            event_type = {
                "document_parse": "document.parse.requested",
                "index_build": "index.build.requested",
            }.get(str(task["task_type"]))
            if event_type is None:
                raise HTTPException(status_code=409, detail="当前任务类型暂不支持重试")
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    UPDATE tasks SET state = 'queued', error = NULL,
                        lease_until = NULL, updated_at = now()
                    WHERE id = $1
                    RETURNING id::text, tenant_id::text, knowledge_base_id::text,
                              task_type, state, attempt, error, created_at, updated_at
                    """,
                    task_id,
                )
                await connection.execute(
                    """
                    UPDATE task_items SET state = 'queued', error = NULL, updated_at = now()
                    WHERE task_id = $1 AND state <> 'completed'
                    """,
                    task_id,
                )
                if task["task_type"] == "index_build":
                    await connection.execute(
                        """
                        UPDATE index_builds SET state = 'queued', error = NULL, updated_at = now()
                        WHERE task_id = $1
                        """,
                        task_id,
                    )
                    await connection.execute(
                        """
                        UPDATE build_items SET state = 'queued', error = NULL, updated_at = now()
                        WHERE build_id = (SELECT id FROM index_builds WHERE task_id = $1)
                          AND state <> 'completed'
                        """,
                        task_id,
                    )
                await connection.execute(
                    """
                    INSERT INTO outbox_events(tenant_id, event_type, payload)
                    VALUES ($1, $2, $3::jsonb)
                    """,
                    task["tenant_id"],
                    event_type,
                    json.dumps({"task_id": str(task_id)}, ensure_ascii=False),
                )
            if row is None:
                raise HTTPException(status_code=404, detail="任务不存在")
            return {**dict(row), "knowledge_base_name": access["name"]}
        finally:
            await connection.close()

    @app.post("/api/v1/tasks/{task_id}/cancel")
    async def cancel_task(task_id: int, request: Request) -> None:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            task = await connection.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
            if task is None or task["knowledge_base_id"] is None:
                raise HTTPException(status_code=404, detail="任务不存在")
            cancel_roles = (
                {"space_admin", "kb_admin"}
                if task["task_type"] == "index_build"
                else {"space_admin", "kb_admin", "editor"}
            )
            await _require_knowledge_base_role(
                connection,
                context,
                int(task["knowledge_base_id"]),
                cancel_roles,
            )
            if task["state"] not in {"queued", "running"}:
                raise HTTPException(status_code=409, detail="当前任务状态不能取消")
            await connection.execute(
                "UPDATE tasks SET state = 'cancelled', updated_at = now() WHERE id = $1",
                task_id,
            )
            if task["task_type"] == "index_build":
                await connection.execute(
                    """
                    UPDATE index_builds SET state = 'cancelled', updated_at = now()
                    WHERE task_id = $1 AND state IN ('queued','running','validating')
                    """,
                    task_id,
                )
                await connection.execute(
                    """
                    UPDATE build_items SET state = 'cancelled', updated_at = now()
                    WHERE build_id = (SELECT id FROM index_builds WHERE task_id = $1)
                      AND state <> 'completed'
                    """,
                    task_id,
                )
            await connection.execute(
                """
                UPDATE task_items SET state = 'cancelled', updated_at = now()
                WHERE task_id = $1 AND state <> 'completed'
                """,
                task_id,
            )
        finally:
            await connection.close()

    @app.post("/api/v1/documents/{document_id}/disable", status_code=204)
    async def disable_document(document_id: int, request: Request) -> None:
        """停用文档并提升内容世代，使后续构建排除该来源且保留审计证据。"""
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _document_access(connection, context, document_id)
            role = _role_for_access(access)
            if role not in {"space_admin", "kb_admin", "editor"}:
                raise HTTPException(status_code=403, detail="当前角色不能停用文档")
            if access["status"] != "active":
                raise HTTPException(status_code=409, detail="当前文档状态不能停用")
            async with connection.transaction():
                await connection.execute(
                    """
                    UPDATE documents
                    SET status = 'disabled', updated_at = now()
                    WHERE id = $1 AND status = 'active'
                    """,
                    document_id,
                )
                await connection.execute(
                    """
                    UPDATE knowledge_bases SET content_epoch = content_epoch + 1,
                        updated_at = now() WHERE id = $1
                    """,
                    access["knowledge_base_id"],
                )
                await write_audit_event(
                    connection,
                    tenant_id=int(access["tenant_id"]),
                    actor_id=int(context["user"]["id"]),
                    action="document.disable",
                    target_type="document",
                    target_id=document_id,
                    summary={
                        "knowledge_base_id": str(access["knowledge_base_id"]),
                        "before": {"status": str(access["status"])},
                        "after": {"status": "disabled"},
                        "active_release_id": (
                            str(access["active_release_id"])
                            if access["active_release_id"] is not None
                            else None
                        ),
                    },
                )
        finally:
            await connection.close()

    @app.delete("/api/v1/documents/{document_id}", status_code=204)
    async def delete_document(document_id: int, request: Request) -> None:
        """软删除文档并提升内容世代，保留历史版本和不可变删除审计。"""
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _document_access(connection, context, document_id)
            role = _role_for_access(access)
            if role not in {"space_admin", "kb_admin"}:
                raise HTTPException(status_code=403, detail="当前角色不能删除文档")
            if access["status"] == "deleted":
                raise HTTPException(status_code=404, detail="文档不存在")
            async with connection.transaction():
                await connection.execute(
                    """
                    UPDATE documents
                    SET status = 'deleted', deleted_at = now(), updated_at = now()
                    WHERE id = $1 AND status <> 'deleted'
                    """,
                    document_id,
                )
                await connection.execute(
                    """
                    UPDATE knowledge_bases SET content_epoch = content_epoch + 1,
                        updated_at = now() WHERE id = $1
                    """,
                    access["knowledge_base_id"],
                )
                await write_audit_event(
                    connection,
                    tenant_id=int(access["tenant_id"]),
                    actor_id=int(context["user"]["id"]),
                    action="document.delete",
                    target_type="document",
                    target_id=document_id,
                    summary={
                        "knowledge_base_id": str(access["knowledge_base_id"]),
                        "before": {"status": str(access["status"])},
                        "after": {"status": "deleted"},
                        "active_release_id": (
                            str(access["active_release_id"])
                            if access["active_release_id"] is not None
                            else None
                        ),
                    },
                )
        finally:
            await connection.close()

    return app


async def _create_knowledge_base(
    connection: asyncpg.Connection, payload: KnowledgeBaseCreate, user_id: int
) -> dict[str, Any]:
    row = await connection.fetchrow(
        """
        INSERT INTO knowledge_bases(tenant_id, name, description, purpose, created_by)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id, tenant_id, name, description, purpose, status, updated_at
        """,
        payload.tenant_id,
        payload.name,
        payload.description,
        payload.purpose,
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


app = create_app()
