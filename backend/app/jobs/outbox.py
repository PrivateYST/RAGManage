"""可靠派发数据库 Outbox 事件。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import asyncpg

from app.core.config import Settings
from app.jobs.worker import celery_app

EVENT_TASKS = {
    "document.parse.requested": "app.jobs.tasks.process_document",
    "index.build.requested": "app.jobs.builds.process_index_build",
}


def _payload_dict(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    return value if isinstance(value, dict) else {}


async def _dispatch_outbox_events(limit: int = 20) -> int:
    settings = Settings()
    if not settings.database_url:
        return 0
    connection = await asyncpg.connect(settings.database_url, timeout=10)
    dispatched = 0
    try:
        for _ in range(limit):
            async with connection.transaction():
                event = await connection.fetchrow(
                    """
                    SELECT id, event_type, payload, attempt
                    FROM outbox_events
                    WHERE state = 'pending' AND next_attempt_at <= now()
                    ORDER BY id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                    """
                )
                if event is None:
                    break
                event_type = str(event["event_type"])
                payload = _payload_dict(event["payload"])
                task_name = EVENT_TASKS.get(event_type)
                task_id = payload.get("task_id")
                if task_name is None or task_id is None:
                    await connection.execute(
                        """
                        UPDATE outbox_events SET state = 'failed', attempt = attempt + 1
                        WHERE id = $1
                        """,
                        event["id"],
                    )
                    continue
                try:
                    celery_app.send_task(task_name, args=[int(task_id)])
                except Exception:
                    await connection.execute(
                        """
                        UPDATE outbox_events SET attempt = attempt + 1,
                            next_attempt_at = now() + interval '10 seconds',
                            state = CASE WHEN attempt + 1 >= 10 THEN 'failed' ELSE 'pending' END
                        WHERE id = $1
                        """,
                        event["id"],
                    )
                    continue
                await connection.execute(
                    "UPDATE outbox_events SET state = 'sent', attempt = attempt + 1 WHERE id = $1",
                    event["id"],
                )
                dispatched += 1
        return dispatched
    finally:
        await connection.close()


@celery_app.task(name="app.jobs.outbox.dispatch_outbox_events")  # type: ignore[untyped-decorator]
def dispatch_outbox_events() -> int:
    return asyncio.run(_dispatch_outbox_events())
