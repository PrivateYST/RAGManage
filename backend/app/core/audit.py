"""统一写入租户范围审计事件，供 HTTP 接口与后台任务共享。"""

from __future__ import annotations

import json
from typing import Any

import asyncpg


async def write_audit_event(
    connection: asyncpg.Connection,
    *,
    tenant_id: int,
    actor_id: int | None,
    action: str,
    target_type: str,
    target_id: int | str | None,
    summary: dict[str, Any],
) -> None:
    """在调用方事务内保存审计事件；调用方必须先移除正文、凭据等敏感内容。"""
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
        str(target_id) if target_id is not None else None,
        json.dumps(summary, ensure_ascii=False),
    )
