"""验证后台 API 的 Redis 固定窗口限流与豁免边界。"""

from typing import Any

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from app.core.security import ManagementRateLimitMiddleware


class FakeRedis:
    """模拟 Redis Lua 返回值，记录每次限流请求使用的键和窗口参数。"""

    def __init__(self, result: list[int]) -> None:
        """设置固定的计数结果，避免测试依赖真实 Redis。"""
        self.result = result
        self.eval_calls: list[tuple[Any, ...]] = []
        self.closed = False

    async def eval(self, *args: Any) -> list[int]:
        """记录原子计数脚本调用并返回计数与剩余秒数。"""
        self.eval_calls.append(args)
        return self.result

    async def aclose(self) -> None:
        """记录中间件是否释放了短连接。"""
        self.closed = True


def _app() -> FastAPI:
    """构造只包含管理接口和健康接口的最小测试应用。"""
    app = FastAPI()
    app.add_middleware(
        ManagementRateLimitMiddleware,
        redis_url="redis://test",
        limit=2,
        window_seconds=60,
    )

    @app.get("/api/v1/admin/resource")
    async def resource() -> Response:
        """返回成功响应，供限流中间件验证放行路径。"""
        return Response(status_code=204)

    @app.get("/api/v1/health/live")
    async def live() -> dict[str, str]:
        """健康检查不占用管理 API 配额。"""
        return {"status": "ok"}

    return app


def test_management_rate_limit_returns_429_with_retry_after(monkeypatch: Any) -> None:
    """超过固定窗口预算时拒绝请求，并返回客户端可执行的等待秒数。"""
    redis = FakeRedis([3, 47])
    monkeypatch.setattr("app.core.security.Redis.from_url", lambda *args, **kwargs: redis)

    with TestClient(_app()) as client:
        response = client.get(
            "/api/v1/admin/resource",
            headers={"cookie": "ragmanage_session=session-a"},
        )

    assert response.status_code == 429
    assert response.json() == {"detail": "管理接口请求过于频繁，请稍后重试"}
    assert response.headers["retry-after"] == "47"
    assert response.headers["x-ratelimit-limit"] == "2"
    assert response.headers["x-ratelimit-remaining"] == "0"
    assert redis.eval_calls[0][1] == 1
    assert redis.eval_calls[0][-2:] == ("2", "60")
    assert redis.closed


def test_management_rate_limit_allows_within_budget_and_scopes_session_key(
    monkeypatch: Any,
) -> None:
    """预算内请求正常放行，并以不可逆 Session 摘要作为 Redis 隔离键。"""
    redis = FakeRedis([1, 59])
    monkeypatch.setattr("app.core.security.Redis.from_url", lambda *args, **kwargs: redis)

    with TestClient(_app()) as client:
        response = client.get(
            "/api/v1/admin/resource",
            headers={"cookie": "ragmanage_session=session-a"},
        )

    assert response.status_code == 204
    key = str(redis.eval_calls[0][2])
    assert key.startswith("ragmanage:management-rate:")
    assert "session-a" not in key
    assert redis.closed


def test_health_check_is_exempt_from_management_rate_limit(monkeypatch: Any) -> None:
    """健康检查必须在 Redis 限流异常时仍可用于探活。"""
    redis = FakeRedis([99, 1])
    monkeypatch.setattr("app.core.security.Redis.from_url", lambda *args, **kwargs: redis)

    with TestClient(_app()) as client:
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert redis.eval_calls == []
    assert not redis.closed
