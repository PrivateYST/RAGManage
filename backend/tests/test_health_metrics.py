"""验证运行指标聚合只返回任务、模型和磁盘的安全统计信息。"""

import asyncio
from types import SimpleNamespace
from typing import Any

from app.core.config import Settings
from app.core.health import collect_runtime_metrics


class FakeConnection:
    """提供固定数据库聚合结果，不依赖真实 PostgreSQL。"""

    async def fetch(self, query: str) -> list[dict[str, Any]]:
        """按查询内容返回任务或模型健康统计。"""
        if "FROM tasks" in query:
            return [{"state": "queued", "count": 3}, {"state": "failed", "count": 2}]
        return [{"health_status": "healthy", "count": 1}, {"health_status": None, "count": 2}]

    async def close(self) -> None:
        """模拟释放数据库连接。"""


def test_collect_runtime_metrics_aggregates_safe_counts(monkeypatch: Any) -> None:
    """指标应聚合队列、失败任务、模型状态与磁盘容量，不包含业务明细。"""

    async def connect(*args: Any, **kwargs: Any) -> FakeConnection:
        """返回模拟连接，保持 asyncpg.connect 的异步契约。"""
        return FakeConnection()

    monkeypatch.setattr("app.core.health.asyncpg.connect", connect)
    monkeypatch.setattr(
        "app.core.health.shutil.disk_usage",
        lambda _: SimpleNamespace(used=10, free=90, total=100),
    )
    result = asyncio.run(collect_runtime_metrics(Settings(database_url="postgresql://test")))
    assert result["tasks"] == {"queued": 3, "running": 0, "failed": 2}
    assert result["models"] == {"healthy": 1, "unhealthy": 0, "unknown": 2}
    assert result["storage"] == {"used_bytes": 10, "free_bytes": 90, "total_bytes": 100}
