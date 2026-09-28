"""提供依赖探活与不含业务正文的运行指标采集。"""

import asyncio
import shutil
from tempfile import TemporaryFile
from typing import cast

import asyncpg
from redis.asyncio import Redis

from app.core.config import Settings


async def check_dependencies(settings: Settings) -> dict[str, str]:
    async def database() -> str:
        if not settings.database_url:
            return "unconfigured"
        connection = await asyncpg.connect(settings.database_url, timeout=3)
        try:
            version = await connection.fetchval(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
            )
            supported = version and tuple(map(int, version.split(".")[:2])) >= (0, 8)
            return "ok" if supported else "vector_unavailable"
        finally:
            await connection.close()

    async def redis() -> str:
        async with Redis.from_url(
            settings.redis_url, socket_connect_timeout=3, socket_timeout=3
        ) as client:
            await client.ping()
        return "ok"

    async def storage() -> str:
        def probe() -> None:
            settings.storage_root.mkdir(parents=True, exist_ok=True)
            with TemporaryFile(dir=settings.storage_root) as handle:
                handle.write(b"ragmanage-readiness")
                handle.seek(0)
                if handle.read() != b"ragmanage-readiness":
                    raise OSError("Storage round trip failed")

        await asyncio.to_thread(probe)
        return "ok"

    results = await asyncio.gather(
        *(asyncio.wait_for(probe(), timeout=5) for probe in (database, redis, storage)),
        return_exceptions=True,
    )
    # Do not return exception strings: connection errors can contain credentials.
    return {
        name: "unavailable" if isinstance(result, BaseException) else result
        for name, result in zip(("database", "redis", "storage"), results, strict=True)
    }


async def collect_runtime_metrics(settings: Settings) -> dict[str, object]:
    """聚合任务、模型和磁盘指标；数据库不可用时返回稳定的 unavailable 状态。"""
    metrics: dict[str, object] = {
        "tasks": {"queued": 0, "running": 0, "failed": 0},
        "models": {"healthy": 0, "unhealthy": 0, "unknown": 0},
        "storage": {"used_bytes": 0, "free_bytes": 0, "total_bytes": 0},
    }
    try:
        usage = await asyncio.to_thread(shutil.disk_usage, settings.storage_root)
        metrics["storage"] = {
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "total_bytes": usage.total,
        }
    except OSError:
        metrics["storage"] = {"status": "unavailable"}

    if not settings.database_url:
        metrics["database"] = "unavailable"
        return metrics
    try:
        connection = await asyncpg.connect(settings.database_url, timeout=3)
        try:
            task_rows = await connection.fetch(
                """
                SELECT state, count(*)::int AS count
                FROM tasks
                WHERE state IN ('queued', 'running', 'failed')
                GROUP BY state
                """
            )
            task_metrics = cast(dict[str, int], metrics["tasks"]).copy()
            for row in task_rows:
                task_metrics[str(row["state"])] = int(row["count"])
            metrics["tasks"] = task_metrics
            model_rows = await connection.fetch(
                """
                SELECT health_status, count(*)::int AS count
                FROM model_endpoints
                GROUP BY health_status
                """
            )
            model_metrics = cast(dict[str, int], metrics["models"]).copy()
            for row in model_rows:
                status = str(row["health_status"] or "unknown")
                if status == "healthy":
                    key = "healthy"
                elif status == "unhealthy":
                    key = "unhealthy"
                else:
                    key = "unknown"
                model_metrics[key] = model_metrics.get(key, 0) + int(row["count"])
            metrics["models"] = model_metrics
            metrics["database"] = "ok"
        finally:
            await connection.close()
    except (OSError, asyncpg.PostgresError):
        metrics["database"] = "unavailable"
    return metrics
