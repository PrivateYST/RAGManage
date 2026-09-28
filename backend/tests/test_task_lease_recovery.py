"""任务租约回收回归：防止 Worker 崩溃后 running 任务永久卡死。"""

import asyncio
from unittest.mock import AsyncMock

from app.core.config import Settings
from app.jobs import tasks


class _Transaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: object) -> None:
        return None


class _Connection:
    def __init__(self) -> None:
        self.execute_calls: list[tuple[str, object]] = []
        self.closed = False

    def transaction(self) -> _Transaction:
        return _Transaction()

    async def fetch(self, query: str) -> list[dict[str, int]]:
        assert "lease_until < now()" in query
        return [{"id": 11}, {"id": 12}]

    async def execute(self, query: str, value: object) -> None:
        self.execute_calls.append((query, value))

    async def close(self) -> None:
        self.closed = True


def test_expired_task_leases_are_requeued_with_pending_items(monkeypatch) -> None:
    """租约过期后任务和 running 子项都回到 queued，下一次 Worker 可安全重放。"""
    connection = _Connection()
    monkeypatch.setattr(tasks, "Settings", lambda: Settings(database_url="postgresql://test"))
    monkeypatch.setattr(tasks.asyncpg, "connect", AsyncMock(return_value=connection))

    recovered = asyncio.run(tasks._recover_expired_task_leases())

    assert recovered == 2
    assert connection.closed
    assert len(connection.execute_calls) == 1
    assert connection.execute_calls[0][1] == [11, 12]
