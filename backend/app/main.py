import hashlib
import json
import secrets
from pathlib import Path
from typing import Annotated, Any, cast

import asyncpg
from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.auth import (
    SESSION_COOKIE,
    authenticate,
    load_user_from_token,
    password_hasher,
    revoke_token,
)
from app.core.config import Settings
from app.core.health import check_dependencies

ALLOWED_DOCUMENT_TYPES = {
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
}
MAX_DOCUMENT_SIZE = 50 * 1024 * 1024


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


class KnowledgeBaseCreate(BaseModel):
    tenant_id: int
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=1000)
    purpose: str = Field(default="general", min_length=2, max_length=80)


async def _authenticated_user(settings: Settings, request: Request) -> dict[str, Any]:
    context = await load_user_from_token(settings, request.cookies.get(SESSION_COOKIE))
    if context is None:
        raise HTTPException(status_code=401, detail="未登录")
    return context


async def _database(settings: Settings) -> asyncpg.Connection:
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="数据库未配置")
    try:
        return await asyncpg.connect(settings.database_url, timeout=5)
    except (OSError, asyncpg.PostgresError) as error:
        raise HTTPException(status_code=503, detail="数据库暂不可用") from error


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


async def _knowledge_base_access(
    connection: asyncpg.Connection,
    context: dict[str, Any],
    knowledge_base_id: int,
) -> asyncpg.Record:
    """返回当前用户对知识库的授权信息；未授权统一隐藏资源是否存在。"""
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


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()

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
        context = await _authenticated_user(config, request)
        if context["user"]["platform_role"] != "platform_admin":
            raise HTTPException(status_code=403, detail="只有平台管理员可以创建用户")
        if payload.tenant_id is not None and payload.tenant_role_code is None:
            raise HTTPException(status_code=400, detail="分配空间时必须指定空间角色")
        connection = await _database(config)
        try:
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
                return {**dict(user_row), "id": str(user_row["id"])}
        except asyncpg.UniqueViolationError as error:
            raise HTTPException(status_code=409, detail="登录名已存在") from error
        finally:
            await connection.close()

    @app.patch("/api/v1/admin/users/{user_id}")
    async def update_user(user_id: int, payload: UserPatch, request: Request) -> dict[str, Any]:
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
                row = await connection.fetchrow(
                    f"""
                    UPDATE users SET {", ".join(assignments)}, updated_at = now()
                    WHERE id = $1
                    RETURNING id::text, login, display_name, status, last_login_at, created_at
                    """,
                    *parameters,
                )
                if row is not None and ("password" in values or values.get("status") == "disabled"):
                    await connection.execute(
                        "UPDATE sessions SET revoked_at = now() "
                        "WHERE user_id = $1 AND revoked_at IS NULL",
                        user_id,
                    )
            if row is None:
                raise HTTPException(status_code=404, detail="用户不存在")
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
                row = await connection.fetchrow(
                    "INSERT INTO tenants(code, name) VALUES ($1, $2) "
                    "RETURNING id::text, code, name, status, created_at",
                    payload.code,
                    payload.name,
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
            if tenant_id is None:
                tenant_ids = [int(space["id"]) for space in context["spaces"]]
            else:
                await _assert_tenant_access(connection, context, tenant_id)
                tenant_ids = [tenant_id]
            if not tenant_ids:
                return {"items": []}
            rows = await connection.fetch(
                """
                SELECT kb.id::text, kb.tenant_id::text, kb.name, kb.description, kb.purpose,
                       kb.status, kb.active_release_id::text, kb.updated_at,
                       count(DISTINCT d.id)::int AS document_count
                FROM knowledge_bases kb LEFT JOIN documents d
                  ON d.knowledge_base_id = kb.id AND d.status <> 'deleted'
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

    @app.post("/api/v1/knowledge-bases/{knowledge_base_id}/documents", status_code=202)
    async def upload_document(
        knowledge_base_id: int,
        request: Request,
        file: Annotated[UploadFile, File(...)],
    ) -> dict[str, Any]:
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
            try:
                from app.jobs.worker import celery_app

                celery_app.send_task("app.jobs.tasks.process_document", args=[int(task["id"])])
            except Exception:
                # 任务记录保持 queued，任务中心可重试；上传本身不能因为 broker 短暂不可用而丢失。
                pass
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

    @app.get("/api/v1/tasks")
    async def list_tasks(request: Request, knowledge_base_id: int | None = None) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            if knowledge_base_id is not None:
                access = await _knowledge_base_access(connection, context, knowledge_base_id)
                tenant_ids = [int(access["tenant_id"])]
                kb_ids = [knowledge_base_id]
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
            access = await _require_knowledge_base_role(
                connection,
                context,
                int(task["knowledge_base_id"]),
                {"space_admin", "kb_admin", "editor"},
            )
            if task["state"] not in {"failed", "cancelled", "interrupted"}:
                raise HTTPException(status_code=409, detail="当前任务状态不能重试")
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
            if row is None:
                raise HTTPException(status_code=404, detail="任务不存在")
            try:
                from app.jobs.worker import celery_app

                celery_app.send_task("app.jobs.tasks.process_document", args=[task_id])
            except Exception:
                pass
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
            await _require_knowledge_base_role(
                connection,
                context,
                int(task["knowledge_base_id"]),
                {"space_admin", "kb_admin", "editor"},
            )
            if task["state"] not in {"queued", "running"}:
                raise HTTPException(status_code=409, detail="当前任务状态不能取消")
            await connection.execute(
                "UPDATE tasks SET state = 'cancelled', updated_at = now() WHERE id = $1",
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
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _document_access(connection, context, document_id)
            role = _role_for_access(access)
            if role not in {"space_admin", "kb_admin", "editor"}:
                raise HTTPException(status_code=403, detail="当前角色不能停用文档")
            await connection.execute(
                """
                UPDATE documents
                SET status = 'disabled', updated_at = now()
                WHERE id = $1
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
        finally:
            await connection.close()

    @app.delete("/api/v1/documents/{document_id}", status_code=204)
    async def delete_document(document_id: int, request: Request) -> None:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _document_access(connection, context, document_id)
            role = _role_for_access(access)
            if role not in {"space_admin", "kb_admin"}:
                raise HTTPException(status_code=403, detail="当前角色不能删除文档")
            await connection.execute(
                """
                UPDATE documents
                SET status = 'deleted', deleted_at = now(), updated_at = now()
                WHERE id = $1
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
