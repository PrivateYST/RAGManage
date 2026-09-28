"""回归登录 Redis 限速边界，防止失败尝试绕过保护或泄露账号是否存在。"""

from typing import Any
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.security import login_attempt_keys, session_csrf_token
from app.main import create_app


class FakeRedis:
    """记录登录限速所需的原子读写，并允许测试预置失败计数。"""

    def __init__(
        self,
        counts: list[bytes | None] | None = None,
        *,
        fail_reserve: bool = False,
        fail_finish: bool = False,
    ) -> None:
        """预置账号和来源 IP 的 Redis 计数。"""
        self.counts = counts or [None, None]
        self.fail_reserve = fail_reserve
        self.fail_finish = fail_finish
        self.login_attempts = 0
        self.eval_calls: list[tuple[Any, ...]] = []
        self.delete_calls: list[tuple[str, ...]] = []
        self.closed = False

    async def eval(self, *args: Any) -> list[int]:
        """记录 Redis Lua 原子操作并模拟账号/IP 限额结果。"""
        self.eval_calls.append(args)
        if "account_total" in args[0]:
            self.login_attempts += 1
            if self.fail_reserve:
                raise OSError("redis unavailable")
            if self.counts[0] == b"5" or self.counts[1] == b"20":
                return 0
            return 1
        if self.fail_finish:
            raise OSError("redis unavailable")
        return 1

    async def delete(self, *keys: str) -> int:
        """记录成功登录后重置的账号连续失败计数。"""
        self.delete_calls.append(keys)
        return 1

    async def incr(self, key: str) -> int:
        """模拟具有过期时间的账号/IP失败数递增。"""
        return 1

    async def expire(self, key: str, seconds: int) -> bool:
        """接受登录失败计数的有限过期窗口。"""
        assert seconds == 900
        return True

    async def aclose(self) -> None:
        """标记本次请求已关闭 Redis 连接池。"""
        self.closed = True


def test_login_rate_limit_blocks_before_password_authentication(monkeypatch: Any) -> None:
    """同一来源对同一账号连续失败达到门槛后不再触发密码校验。"""
    redis = FakeRedis(counts=[b"5", None])
    monkeypatch.setattr("app.main.Redis.from_url", lambda *args, **kwargs: redis)
    authenticate = AsyncMock(return_value=None)
    monkeypatch.setattr("app.main.authenticate", authenticate)

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"login": "admin", "password": "wrong-password"},
            headers={"origin": "http://testserver"},
        )

    assert response.status_code == 429
    assert response.json() == {"detail": "登录尝试过多，请稍后重试"}
    authenticate.assert_not_awaited()
    assert len(redis.eval_calls) == 1
    assert "account_total" in redis.eval_calls[0][0]
    assert redis.closed


def test_login_failure_budget_is_scoped_to_account_and_source_ip() -> None:
    """单个攻击来源触发账号-IP 门槛时，不会阻断同账号的其他来源登录。"""
    first_source = login_attempt_keys(" Admin ", "203.0.113.10")
    same_source = login_attempt_keys("admin", "203.0.113.10")
    other_source = login_attempt_keys("admin", "203.0.113.11")

    assert first_source.account_failure_key == same_source.account_failure_key
    assert first_source.account_inflight_key == same_source.account_inflight_key
    assert first_source.account_failure_key != other_source.account_failure_key
    assert first_source.ip_failure_key != other_source.ip_failure_key


def test_login_ip_failure_limit_applies_across_distinct_accounts(monkeypatch: Any) -> None:
    """同一来源 IP 达到共享失败上限时，即使换账号也不能继续猜测凭据。"""
    redis = FakeRedis(counts=[None, b"20"])
    monkeypatch.setattr("app.main.Redis.from_url", lambda *args, **kwargs: redis)
    authenticate = AsyncMock(return_value=None)
    monkeypatch.setattr("app.main.authenticate", authenticate)

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"login": "different-account", "password": "wrong-password"},
            headers={"origin": "http://testserver"},
        )

    assert response.status_code == 429
    authenticate.assert_not_awaited()
    assert redis.closed


def test_login_fails_closed_when_redis_rate_limit_store_is_unavailable(
    monkeypatch: Any,
) -> None:
    """限速 Redis 不可用时返回 503，绝不降级为不受保护的密码认证。"""
    redis = FakeRedis(fail_reserve=True)
    monkeypatch.setattr("app.main.Redis.from_url", lambda *args, **kwargs: redis)
    authenticate = AsyncMock(return_value=None)
    monkeypatch.setattr("app.main.authenticate", authenticate)

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"login": "admin", "password": "wrong-password"},
            headers={"origin": "http://testserver"},
        )

    assert response.status_code == 503
    authenticate.assert_not_awaited()
    assert redis.closed


def test_failed_login_increments_atomic_account_and_ip_counters(monkeypatch: Any) -> None:
    """错误凭据同时递增账号与来源 IP 计数，并确保使用有限过期窗口。"""
    redis = FakeRedis()
    monkeypatch.setattr("app.main.Redis.from_url", lambda *args, **kwargs: redis)
    monkeypatch.setattr("app.main.authenticate", AsyncMock(return_value=None))

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"login": "admin", "password": "wrong-password"},
            headers={"origin": "http://testserver"},
        )

    assert response.status_code == 401
    assert len(redis.eval_calls) == 2
    assert redis.eval_calls[0][1] == 4
    assert redis.eval_calls[1][1] == 4
    assert redis.eval_calls[1][-1] == "900"
    assert redis.closed


def test_successful_login_clears_only_account_failure_streak(monkeypatch: Any) -> None:
    """成功认证清除该账号的连续失败数，但保留来源 IP 的聚合异常计数。"""
    redis = FakeRedis()
    monkeypatch.setattr("app.main.Redis.from_url", lambda *args, **kwargs: redis)
    monkeypatch.setattr(
        "app.main.authenticate",
        AsyncMock(return_value={"user": {"id": "11"}, "token": "session-token"}),
    )

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"login": "admin", "password": "correct-password"},
            headers={"origin": "http://testserver"},
        )

    assert response.status_code == 200
    assert response.cookies.get("ragmanage_session") == "session-token"
    assert response.cookies.get("ragmanage_csrf") == session_csrf_token(
        Settings().csrf_secret_value, "session-token"
    )
    assert len(redis.eval_calls) == 2
    assert redis.eval_calls[-1][0].startswith("\nfor index = 2, 4, 2 do")
    assert redis.closed


def test_successful_login_revokes_session_if_rate_limit_settlement_fails(
    monkeypatch: Any,
) -> None:
    """限速状态无法结算时，撤销已经创建但无法安全完成登录的会话。"""
    redis = FakeRedis(fail_finish=True)
    monkeypatch.setattr("app.main.Redis.from_url", lambda *args, **kwargs: redis)
    monkeypatch.setattr(
        "app.main.authenticate",
        AsyncMock(return_value={"user": {"id": "11"}, "token": "orphan-session"}),
    )
    revoke = AsyncMock()
    monkeypatch.setattr("app.main.revoke_token", revoke)

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"login": "admin", "password": "correct-password"},
            headers={"origin": "http://testserver"},
        )

    assert response.status_code == 503
    revoke.assert_awaited_once_with(Settings(), "orphan-session")
    assert response.cookies.get("ragmanage_session") is None
    assert redis.closed


def test_login_does_not_retry_failed_counter_after_redis_finish_timeout(
    monkeypatch: Any,
) -> None:
    """Redis 结算超时不重放失败脚本，避免已处理请求被重复计数。"""
    redis = FakeRedis(fail_finish=True)
    monkeypatch.setattr("app.main.Redis.from_url", lambda *args, **kwargs: redis)
    monkeypatch.setattr("app.main.authenticate", AsyncMock(return_value=None))

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"login": "admin", "password": "wrong-password"},
            headers={"origin": "http://testserver"},
        )

    assert response.status_code == 503
    assert len(redis.eval_calls) == 2
    assert redis.closed
