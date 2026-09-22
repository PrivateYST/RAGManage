"""公司 API Key 的生成、哈希、额度预扣和用量结算。

本模块只处理凭据和额度边界，不负责模型请求；模型调用完成后由问答流程
把网关返回的输入/输出 Token 传入结算函数，确保 Key 额度与请求流水一致。
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from collections.abc import Mapping
from typing import Any

import asyncpg
from cryptography.fernet import Fernet, InvalidToken

# 客户网关 Key 采用通用的 OpenAI 兼容格式；鉴权仍以完整 Key 的哈希为准。
API_KEY_PREFIX = "sk-"
# 模型与检索超时总计低于该值；超过后视为进程中断并释放持久化预留。
RESERVATION_STALE_AFTER_MINUTES = 10


class ApiKeyQuotaExceededError(ValueError):
    """API Key 不存在、已停用、已过期或剩余额度不足。"""


def generate_api_key() -> tuple[str, str, str]:
    """生成一次性展示的 ``sk-`` 网关 Key，并返回明文、展示前缀和哈希。"""
    raw_key = f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"
    prefix = f"{raw_key[:12]}…{raw_key[-4:]}"
    return raw_key, prefix, hash_api_key(raw_key)


def hash_api_key(raw_key: str) -> str:
    """使用 SHA-256 哈希高熵随机 Key，数据库泄露时不暴露可用凭据。"""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def encrypt_api_key(raw_key: str, encryption_secret: str) -> str:
    """用服务端密钥加密明文 Key，支持管理员复制但不把明文写入数据库。"""
    cipher = _cipher(encryption_secret)
    return cipher.encrypt(raw_key.encode("utf-8")).decode("ascii")


def decrypt_api_key(ciphertext: str, encryption_secret: str) -> str:
    """解密数据库中的 Key；密文损坏或密钥变化时返回稳定错误。"""
    try:
        return _cipher(encryption_secret).decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeError, InvalidToken) as error:
        raise ValueError("API_KEY_CIPHERTEXT_INVALID") from error


def _cipher(encryption_secret: str) -> Fernet:
    """从配置密钥派生固定 Fernet 密钥，避免把可逆密钥存入业务表。"""
    material = hashlib.sha256(encryption_secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(material))


async def authenticate_api_key(
    connection: asyncpg.Connection,
    raw_key: str,
) -> dict[str, Any] | None:
    """校验公司下发的 Key，仅为命中的 Key 回收超时预留并返回身份上下文。"""
    candidate_id = await connection.fetchval(
        """
        SELECT id FROM api_keys WHERE key_hash = $1 AND deleted_at IS NULL
        """,
        hash_api_key(raw_key),
    )
    if candidate_id is None:
        return None
    await recover_stale_api_key_reservations(connection, api_key_id=int(candidate_id))
    row = await connection.fetchrow(
        """
        SELECT ak.id::text AS api_key_id, ak.tenant_id::text AS api_key_tenant_id,
               ak.name AS api_key_name, ak.status, ak.expires_at,
               u.id, u.login, u.display_name, r.code AS platform_role
        FROM api_keys ak
        JOIN tenants tenant ON tenant.id = ak.tenant_id AND tenant.status = 'active'
        JOIN users u ON u.id = ak.created_by
        LEFT JOIN roles r ON r.id = u.platform_role_id
        WHERE ak.key_hash = $1
          AND ak.id = $2
          AND ak.status = 'active'
          AND ak.deleted_at IS NULL
          AND (ak.expires_at IS NULL OR ak.expires_at > now())
          AND ak.token_used + ak.token_reserved < ak.token_limit
        """,
        hash_api_key(raw_key),
        int(candidate_id),
    )
    if row is None:
        return None
    await connection.execute(
        "UPDATE api_keys SET last_used_at = now() WHERE id = $1",
        int(row["api_key_id"]),
    )
    return dict(row)


async def reserve_api_key_tokens(
    connection: asyncpg.Connection,
    *,
    api_key_id: str,
    run_id: int,
    requested_tokens: int,
) -> int:
    """原子预扣额度并按运行持久化，供崩溃恢复和最终结算使用。"""
    reserve = max(1, int(requested_tokens))
    async with connection.transaction():
        row = await connection.fetchrow(
            """
            UPDATE api_keys
            SET token_reserved = token_reserved + $2
            WHERE id = $1
              AND status = 'active'
              AND deleted_at IS NULL
              AND (expires_at IS NULL OR expires_at > now())
              AND token_used + token_reserved + $2 <= token_limit
            RETURNING token_reserved
            """,
            int(api_key_id),
            reserve,
        )
        if row is None:
            raise ApiKeyQuotaExceededError("TOKEN_QUOTA_EXCEEDED")
        await connection.execute(
            """
            INSERT INTO api_key_reservations(run_id, api_key_id, reserved_tokens)
            VALUES ($1, $2, $3)
            ON CONFLICT (run_id) DO UPDATE
            SET reserved_tokens = api_key_reservations.reserved_tokens + EXCLUDED.reserved_tokens,
                updated_at = now()
            WHERE api_key_reservations.api_key_id = EXCLUDED.api_key_id
            """,
            run_id,
            int(api_key_id),
            reserve,
        )
    return reserve


async def release_api_key_reservation(
    connection: asyncpg.Connection,
    *,
    api_key_id: str,
    run_id: int,
) -> None:
    """按运行删除持久化预留，并从 Key 聚合预留中释放同一数值。"""
    async with connection.transaction():
        reserved_tokens = await connection.fetchval(
            """
            DELETE FROM api_key_reservations
            WHERE run_id = $1 AND api_key_id = $2
            RETURNING reserved_tokens
            """,
            run_id,
            int(api_key_id),
        )
        if reserved_tokens is not None:
            await connection.execute(
                """
                UPDATE api_keys
                SET token_reserved = GREATEST(0, token_reserved - $2)
                WHERE id = $1
                """,
                int(api_key_id),
                int(reserved_tokens),
            )


async def update_api_key_reservation_usage(
    connection: asyncpg.Connection,
    *,
    api_key_id: str,
    run_id: int,
    usage: Mapping[str, Any],
) -> None:
    """持久化运行中的最新用量快照，使进程中断后仍能按已发生消费结算。"""
    await connection.execute(
        """
        UPDATE api_key_reservations SET usage = $3::jsonb, updated_at = now()
        WHERE run_id = $1 AND api_key_id = $2
        """,
        run_id,
        int(api_key_id),
        json.dumps(dict(usage), ensure_ascii=False),
    )


async def settle_api_key_usage(
    connection: asyncpg.Connection,
    *,
    api_key_id: str,
    run_id: int,
    tenant_id: int,
    request_id: str,
    model_name: str,
    usage: Mapping[str, Any],
    status: str = "completed",
    model_usage: Mapping[str, Any] | None = None,
) -> bool:
    """写入幂等用量流水，并把实际总 Token 结算到 API Key。"""
    prompt_tokens = max(0, int(usage.get("prompt_tokens", 0)))
    completion_tokens = max(0, int(usage.get("completion_tokens", 0)))
    total_tokens = max(prompt_tokens + completion_tokens, int(usage.get("total_tokens", 0)))
    source = str(usage.get("usage_source", "unavailable"))
    if source not in {"gateway", "estimate", "unavailable"}:
        source = "unavailable"
    async with connection.transaction():
        persisted_reservation = await connection.fetchval(
            """
            DELETE FROM api_key_reservations
            WHERE run_id = $1 AND api_key_id = $2
            RETURNING reserved_tokens
            """,
            run_id,
            int(api_key_id),
        )
        # 聚合预留只能按成功删除的持久化记录释放，避免恢复与迟到结算双重扣减。
        reservation_to_release = max(0, int(persisted_reservation or 0))
        inserted = await connection.fetchval(
            """
            INSERT INTO api_key_usage(
              api_key_id, tenant_id, request_id, model_name,
              prompt_tokens, completion_tokens, total_tokens,
              reserved_tokens, usage_source, model_usage, status
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11)
            ON CONFLICT (api_key_id, request_id) DO NOTHING
            RETURNING id
            """,
            int(api_key_id),
            tenant_id,
            request_id,
            model_name,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            reservation_to_release,
            source,
            json.dumps(dict(model_usage or {}), ensure_ascii=False),
            status,
        )
        if inserted is None:
            # 重连或并发消费同一 request_id 时不重复计费，但必须归还本执行者的预扣。
            await connection.execute(
                """
                UPDATE api_keys
                SET token_reserved = GREATEST(0, token_reserved - $2)
                WHERE id = $1
                """,
                int(api_key_id),
                reservation_to_release,
            )
            return False
        await connection.execute(
            """
            UPDATE api_keys
            SET token_used = token_used + $2,
                token_reserved = GREATEST(0, token_reserved - $3)
            WHERE id = $1
            """,
            int(api_key_id),
            total_tokens,
            reservation_to_release,
        )
    return True


async def recover_stale_api_key_reservations(
    connection: asyncpg.Connection,
    *,
    api_key_id: int,
) -> int:
    """结算当前 Key 的超时预留，并把中断运行转换为可审计失败终态。"""
    async with connection.transaction():
        rows = await connection.fetch(
            """
            SELECT reservation.run_id, reservation.api_key_id,
                   reservation.reserved_tokens, reservation.usage AS reservation_usage,
                   run.tenant_id, run.assistant_message_id, run.request_id::text,
                   run.state, message.usage AS message_usage
            FROM api_key_reservations reservation
            JOIN generation_runs run ON run.id = reservation.run_id
            JOIN messages message ON message.id = run.assistant_message_id
              AND message.tenant_id = run.tenant_id
            WHERE reservation.updated_at < now() - make_interval(mins => $1)
              AND reservation.api_key_id = $2
              AND run.state IN ('running', 'completed', 'failed', 'cancelled')
            FOR UPDATE OF reservation, run
            """,
            RESERVATION_STALE_AFTER_MINUTES,
            api_key_id,
        )
        for row in rows:
            original_state = str(row["state"])
            recovered_status = "failed" if original_state == "running" else original_state
            reservation_usage = _json_mapping(row["reservation_usage"])
            message_usage = _json_mapping(row["message_usage"])
            usage = (
                message_usage
                if _usage_total(message_usage) >= _usage_total(reservation_usage)
                else reservation_usage
            )
            prompt_tokens = max(0, int(usage.get("prompt_tokens", 0)))
            completion_tokens = max(0, int(usage.get("completion_tokens", 0)))
            total_tokens = max(
                prompt_tokens + completion_tokens,
                int(usage.get("total_tokens", 0)),
            )
            usage_source = str(usage.get("usage_source", "unavailable"))
            if usage_source not in {"gateway", "estimate", "unavailable"}:
                usage_source = "unavailable"
            model_usage = _json_mapping(usage.get("model_usage"))
            model_names = [
                str(value["model"])
                for value in model_usage.values()
                if isinstance(value, Mapping) and value.get("model")
            ]
            await connection.execute(
                "DELETE FROM api_key_reservations WHERE run_id = $1",
                int(row["run_id"]),
            )
            if original_state == "running":
                failure_usage = {
                    "code": "PROCESS_INTERRUPTED",
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "usage_source": usage_source,
                    "model_usage": model_usage,
                }
                failure = json.dumps(failure_usage, ensure_ascii=False)
                await connection.execute(
                    """
                    UPDATE generation_runs SET state = 'failed', error = $2::jsonb,
                        completed_at = now(), updated_at = now()
                    WHERE id = $1 AND state = 'running'
                    """,
                    int(row["run_id"]),
                    failure,
                )
                await connection.execute(
                    """
                    UPDATE messages SET state = 'failed', usage = $3::jsonb
                    WHERE id = $1 AND tenant_id = $2
                    """,
                    int(row["assistant_message_id"]),
                    int(row["tenant_id"]),
                    failure,
                )
                await connection.execute(
                    """
                    UPDATE retrieval_traces SET state = 'failed'
                    WHERE tenant_id = $1 AND message_id = $2 AND state = 'running'
                    """,
                    int(row["tenant_id"]),
                    int(row["assistant_message_id"]),
                )
            inserted = None
            if total_tokens > 0:
                inserted = await connection.fetchval(
                    """
                    INSERT INTO api_key_usage(
                      api_key_id, tenant_id, request_id, model_name,
                      prompt_tokens, completion_tokens, total_tokens,
                      reserved_tokens, usage_source, model_usage, status
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11)
                    ON CONFLICT (api_key_id, request_id) DO NOTHING
                    RETURNING id
                    """,
                    int(row["api_key_id"]),
                    int(row["tenant_id"]),
                    str(row["request_id"]),
                    " + ".join(model_names) or "unavailable",
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    int(row["reserved_tokens"]),
                    usage_source,
                    json.dumps(model_usage, ensure_ascii=False),
                    recovered_status,
                )
            await connection.execute(
                """
                UPDATE api_keys
                SET token_used = token_used + $2,
                    token_reserved = GREATEST(0, token_reserved - $3)
                WHERE id = $1
                """,
                int(row["api_key_id"]),
                total_tokens if inserted is not None else 0,
                int(row["reserved_tokens"]),
            )
    return len(rows)


def _json_mapping(value: object) -> dict[str, Any]:
    """把 asyncpg JSONB 或序列化 JSON 统一转换为可校验的字典。"""
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(decoded) if isinstance(decoded, Mapping) else {}
    return {}


def _usage_total(usage: Mapping[str, Any]) -> int:
    """返回用量快照的非负总量，用于选择信息最完整的崩溃恢复来源。"""
    return max(
        0,
        int(usage.get("total_tokens", 0)),
        int(usage.get("prompt_tokens", 0)) + int(usage.get("completion_tokens", 0)),
    )
