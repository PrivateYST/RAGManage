import asyncio
from tempfile import TemporaryFile

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
