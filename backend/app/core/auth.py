"""浏览器会话与公司 API Key 身份认证、密码校验和认证审计。"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.api_keys import authenticate_api_key
from app.core.config import Settings

password_hasher = PasswordHasher()
SESSION_COOKIE = "ragmanage_session"


def _token_hash(token: str) -> str:
    """将高熵会话令牌转换为不可逆数据库索引值，避免保存可用明文。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def _write_auth_audit(
    connection: asyncpg.Connection,
    *,
    actor_id: int | None,
    action: str,
    target_type: str,
    target_id: int | None,
    summary: dict[str, Any],
) -> None:
    """记录认证事件；摘要禁止包含密码、令牌或 Cookie。"""
    await connection.execute(
        """
        INSERT INTO audit_logs(
          actor_id, action, target_type, target_id, change_summary
        ) VALUES ($1, $2, $3, $4, $5::jsonb)
        """,
        actor_id,
        action,
        target_type,
        str(target_id) if target_id is not None else None,
        json.dumps(summary, ensure_ascii=False),
    )


async def ensure_bootstrap_admin(settings: Settings) -> None:
    """使用一次性环境配置创建平台管理员，不覆盖已存在账号。"""
    if not settings.database_url or not settings.bootstrap_admin_password:
        return
    connection = await asyncpg.connect(settings.database_url, timeout=5)
    try:
        role_id = await connection.fetchval("SELECT id FROM roles WHERE code = 'platform_admin'")
        if role_id is None:
            raise RuntimeError("数据库尚未完成权限迁移，请先执行 alembic upgrade head")
        user_id = await connection.fetchval(
            "SELECT id FROM users WHERE login = $1", settings.bootstrap_admin_login
        )
        if user_id is None:
            user_id = await connection.fetchval(
                """
                INSERT INTO users(login, display_name, password_hash, platform_role_id)
                VALUES ($1, $2, $3, $4)
                RETURNING id
                """,
                settings.bootstrap_admin_login,
                settings.bootstrap_admin_display_name,
                password_hasher.hash(settings.bootstrap_admin_password),
                role_id,
            )
        tenant_id = await connection.fetchval("SELECT id FROM tenants WHERE code = 'internal'")
        if tenant_id is None:
            tenant_id = await connection.fetchval(
                """
                INSERT INTO tenants(code, name) VALUES ('internal', '内部工作空间') RETURNING id
                """
            )
        await connection.execute(
            """
            INSERT INTO tenant_members(tenant_id, user_id, role_id)
            SELECT $1, $2, id FROM roles WHERE code = 'space_admin'
            ON CONFLICT (tenant_id, user_id) DO NOTHING
            """,
            tenant_id,
            user_id,
        )
    finally:
        await connection.close()


async def authenticate(settings: Settings, login: str, password: str) -> dict[str, Any] | None:
    """校验启用用户的密码并创建带过期时间、可审计的浏览器会话。"""
    if not settings.database_url:
        return None
    connection = await asyncpg.connect(settings.database_url, timeout=5)
    try:
        login_name = login.strip()[:120]
        user = await connection.fetchrow(
            """
            SELECT u.id, u.login, u.display_name, u.password_hash, u.platform_role_id,
                   r.code AS platform_role
            FROM users u LEFT JOIN roles r ON r.id = u.platform_role_id
            WHERE u.login = $1 AND u.status = 'active'
            """,
            login_name,
        )
        if user is None:
            await _write_auth_audit(
                connection,
                actor_id=None,
                action="auth.login.failed",
                target_type="user",
                target_id=None,
                summary={"login": login_name, "reason": "invalid_credentials"},
            )
            return None
        try:
            password_hasher.verify(user["password_hash"], password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            await _write_auth_audit(
                connection,
                actor_id=None,
                action="auth.login.failed",
                target_type="user",
                target_id=int(user["id"]),
                summary={"login": login_name, "reason": "invalid_credentials"},
            )
            return None
        async with connection.transaction():
            await connection.execute(
                "UPDATE users SET last_login_at = now(), updated_at = now() WHERE id = $1",
                user["id"],
            )
            token = secrets.token_urlsafe(32)
            session_id = await connection.fetchval(
                """
                INSERT INTO sessions(user_id, token_hash, expires_at)
                VALUES ($1, $2, $3)
                RETURNING id
                """,
                user["id"],
                _token_hash(token),
                datetime.now(UTC) + timedelta(hours=settings.session_ttl_hours),
            )
            await _write_auth_audit(
                connection,
                actor_id=int(user["id"]),
                action="auth.login.success",
                target_type="session",
                target_id=int(session_id),
                summary={"login": login_name, "result": "success"},
            )
            context = await load_user_context(connection, user, token)
        return context
    finally:
        await connection.close()


async def load_user_from_token(settings: Settings, token: str | None) -> dict[str, Any] | None:
    """加载未撤销且未过期的会话身份，并刷新最近访问时间。"""
    if not settings.database_url or not token:
        return None
    connection = await asyncpg.connect(settings.database_url, timeout=5)
    try:
        user = await connection.fetchrow(
            """
            SELECT u.id, u.login, u.display_name, u.platform_role_id,
                   r.code AS platform_role
            FROM sessions s JOIN users u ON u.id = s.user_id
            LEFT JOIN roles r ON r.id = u.platform_role_id
            WHERE s.token_hash = $1 AND s.revoked_at IS NULL AND s.expires_at > now()
              AND u.status = 'active'
            """,
            _token_hash(token),
        )
        if user is None:
            return None
        await connection.execute(
            "UPDATE sessions SET last_seen_at = now() WHERE token_hash = $1", _token_hash(token)
        )
        return await load_user_context(connection, user, token)
    finally:
        await connection.close()


async def load_user_from_api_key(settings: Settings, raw_key: str | None) -> dict[str, Any] | None:
    """通过公司下发的 Bearer API Key 加载客户调用身份，不创建浏览器会话。"""
    if not settings.database_url or not raw_key:
        return None
    connection = await asyncpg.connect(settings.database_url, timeout=5)
    try:
        identity = await authenticate_api_key(connection, raw_key)
        if identity is None:
            return None
        user = {
            "id": identity["id"],
            "login": identity["login"],
            "display_name": identity["display_name"],
            "platform_role": identity["platform_role"],
        }
        context = await load_user_context(connection, user)
        # API Key 只能代表客户空间调用，不能继承创建者的平台管理员权限。
        context["user"]["platform_role"] = None
        context["api_key_id"] = identity["api_key_id"]
        context["api_key_tenant_id"] = identity["api_key_tenant_id"]
        context["api_key_name"] = identity["api_key_name"]
        return context
    finally:
        await connection.close()


async def revoke_token(settings: Settings, token: str | None) -> None:
    """幂等撤销浏览器会话，并在实际状态变化时记录退出审计。"""
    if not settings.database_url or not token:
        return
    connection = await asyncpg.connect(settings.database_url, timeout=5)
    try:
        async with connection.transaction():
            session = await connection.fetchrow(
                """
                UPDATE sessions SET revoked_at = now()
                WHERE token_hash = $1 AND revoked_at IS NULL
                RETURNING id, user_id
                """,
                _token_hash(token),
            )
            if session is not None:
                await _write_auth_audit(
                    connection,
                    actor_id=int(session["user_id"]),
                    action="auth.logout",
                    target_type="session",
                    target_id=int(session["id"]),
                    summary={"result": "revoked"},
                )
    finally:
        await connection.close()


async def load_user_context(
    connection: asyncpg.Connection,
    user: asyncpg.Record,
    token: str | None = None,
) -> dict[str, Any]:
    """汇总用户的启用空间与菜单权限；API Key 调用方会在上层收窄平台角色。"""
    memberships = await connection.fetch(
        """
        SELECT t.id::text, t.code, t.name, r.code AS role
        FROM tenant_members tm JOIN tenants t ON t.id = tm.tenant_id
        JOIN roles r ON r.id = tm.role_id
        WHERE tm.user_id = $1 AND tm.status = 'active' AND t.status = 'active'
        ORDER BY t.name
        """,
        user["id"],
    )
    if user["platform_role"] == "platform_admin":
        menu_rows = await connection.fetch(
            """
            SELECT id::text, code, name, kind, parent_id::text, route, icon,
                   permission_code, sort_order, visible
            FROM menus WHERE status = 'active' AND visible = true
            ORDER BY sort_order, id
            """
        )
    else:
        menu_rows = await connection.fetch(
            """
            SELECT DISTINCT m.id::text, m.code, m.name, m.kind, m.parent_id::text,
                   m.route, m.icon, m.permission_code, m.sort_order, m.visible
            FROM menus m JOIN role_menus rm ON rm.menu_id = m.id
            JOIN roles r ON r.id = rm.role_id
            WHERE m.status = 'active'
              AND m.visible = true
              AND (
                EXISTS (
                  SELECT 1 FROM tenant_members tm
                  JOIN tenants t ON t.id = tm.tenant_id AND t.status = 'active'
                  WHERE tm.user_id = $1 AND tm.status = 'active' AND tm.role_id = r.id
                ) OR EXISTS (
                  SELECT 1 FROM kb_members km
                  JOIN tenant_members tm ON tm.tenant_id = km.tenant_id
                    AND tm.user_id = km.user_id AND tm.status = 'active'
                  JOIN tenants t ON t.id = km.tenant_id AND t.status = 'active'
                  WHERE km.user_id = $1 AND km.status = 'active' AND km.role_id = r.id
                )
              )
            ORDER BY m.sort_order, m.id::text
            """,
            user["id"],
        )
    return {
        "user": {
            "id": str(user["id"]),
            "login": user["login"],
            "display_name": user["display_name"],
            "platform_role": user["platform_role"],
        },
        "spaces": [dict(row) for row in memberships],
        "menus": [dict(row) for row in menu_rows],
        **({"token": token} if token else {}),
    }
