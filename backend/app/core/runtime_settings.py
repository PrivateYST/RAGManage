"""持久化平台运行凭据的读取和写入边界。

模型网关 Key 由超级管理员在页面中替换后必须跨 API/Worker 重启生效，因此数据库
只保存服务端加密密文；调用模型前按 Settings 实例最多加载一次，避免每个请求重复建连。
"""

from __future__ import annotations

import asyncpg
from pydantic import SecretStr

from app.core.api_keys import decrypt_api_key, encrypt_api_key
from app.core.config import Settings

MODEL_GATEWAY_SETTING = "model_gateway_api_key"


async def load_persisted_model_gateway_key(settings: Settings) -> bool:
    """从平台设置表加载全局模型 Key；数据库未配置或旧库未迁移时保留环境变量。"""
    if settings.model_gateway_key_refresh_attempted:
        return bool(settings.model_gateway_api_key.get_secret_value())
    settings.model_gateway_key_refresh_attempted = True
    if not settings.database_url:
        return bool(settings.model_gateway_api_key.get_secret_value())
    connection: asyncpg.Connection | None = None
    try:
        connection = await asyncpg.connect(settings.database_url, timeout=1)
        row = await connection.fetchrow(
            "SELECT encrypted_value FROM platform_settings WHERE setting_key = $1",
            MODEL_GATEWAY_SETTING,
        )
        if row is None or not row["encrypted_value"]:
            return bool(settings.model_gateway_api_key.get_secret_value())
        settings.model_gateway_api_key = SecretStr(
            decrypt_api_key(str(row["encrypted_value"]), settings.api_key_encryption_secret_value)
        )
        return True
    except (OSError, asyncpg.PostgresError, ValueError):
        # 本地测试和迁移窗口可能尚未有新表；环境变量仍是可用的回退来源。
        return bool(settings.model_gateway_api_key.get_secret_value())
    finally:
        if connection is not None:
            await connection.close()


async def persist_model_gateway_key(settings: Settings, raw_key: str, actor_id: int) -> None:
    """把全局模型网关 Key 以密文写入平台设置，并记录最后修改人。"""
    if not settings.database_url:
        return
    connection = await asyncpg.connect(settings.database_url, timeout=5)
    try:
        try:
            await connection.execute(
                """
                INSERT INTO platform_settings(setting_key, encrypted_value, updated_by)
                VALUES ($1, $2, $3)
                ON CONFLICT (setting_key) DO UPDATE
                SET encrypted_value = EXCLUDED.encrypted_value,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = now()
                """,
                MODEL_GATEWAY_SETTING,
                encrypt_api_key(raw_key, settings.api_key_encryption_secret_value),
                actor_id,
            )
        except asyncpg.UndefinedTableError:
            # 迁移尚未执行时仍立即切换当前进程；下一次迁移后可再次保存为持久配置。
            return
    finally:
        await connection.close()
