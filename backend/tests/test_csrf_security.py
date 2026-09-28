"""验证浏览器会话写请求必须携带绑定会话的 CSRF 凭据。"""

from typing import Any
from unittest.mock import AsyncMock

from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.security import (
    SessionCsrfMiddleware,
    login_client_ip,
    request_has_same_origin,
    session_csrf_token,
)
from app.main import create_app


def test_browser_session_write_requires_matching_csrf_cookie_and_header() -> None:
    """缺少 token 或 token 不匹配时拒绝注销，正确绑定值才允许写请求。"""
    settings = Settings()
    token = session_csrf_token(settings.csrf_secret_value, "session-token")

    with TestClient(create_app(settings)) as client:
        missing = client.post(
            "/api/v1/auth/logout",
            headers={"cookie": "ragmanage_session=session-token"},
        )

    with TestClient(create_app(settings)) as client:
        client.cookies.set("ragmanage_session", "session-token")
        client.cookies.set("ragmanage_csrf", "wrong-token")
        mismatched = client.post(
            "/api/v1/auth/logout",
            headers={"x-csrf-token": token},
        )

    with TestClient(create_app(settings)) as client:
        client.cookies.set("ragmanage_session", "session-token")
        client.cookies.set("ragmanage_csrf", token)
        accepted = client.post(
            "/api/v1/auth/logout",
            headers={"x-csrf-token": token},
        )

    assert missing.status_code == 403
    assert mismatched.status_code == 403
    assert accepted.status_code == 204
    assert "ragmanage_session" in accepted.headers.get("set-cookie", "")
    assert "ragmanage_csrf" in accepted.headers.get("set-cookie", "")


def test_token_from_another_session_cannot_authorize_write() -> None:
    """有效格式的 token 也不能跨 Session 重放，防止跨账号 CSRF 凭据复用。"""
    settings = Settings()
    foreign_token = session_csrf_token(settings.csrf_secret_value, "other-session")
    app = create_app(settings)

    with TestClient(app) as client:
        client.cookies.set("ragmanage_session", "current-session")
        client.cookies.set("ragmanage_csrf", foreign_token)
        response = client.post(
            "/api/v1/auth/logout",
            headers={"x-csrf-token": foreign_token},
        )

    assert response.status_code == 403


def test_explicit_csrf_secret_is_used_verbatim_across_settings_instances() -> None:
    """显式配置的 CSRF 密钥不随数据库连接凭据变化，支持稳定多 Worker 验证。"""
    settings = Settings(csrf_secret="stable-random-deployment-secret")

    assert settings.csrf_secret_value == "stable-random-deployment-secret"


def test_legacy_session_can_bootstrap_bound_token(monkeypatch: Any) -> None:
    """升级前仍有效的 HttpOnly Session 可经同源只读接口补发 CSRF Cookie。"""
    settings = Settings()
    monkeypatch.setattr(
        "app.main._authenticated_user",
        AsyncMock(return_value={"user": {"id": "11"}}),
    )

    with TestClient(create_app(settings)) as client:
        client.cookies.set("ragmanage_session", "legacy-session")
        response = client.get("/api/v1/auth/csrf")

    expected = session_csrf_token(settings.csrf_secret_value, "legacy-session")
    assert response.status_code == 200
    assert response.json() == {"csrf_token": expected}
    assert response.cookies.get("ragmanage_csrf") == expected
    assert response.headers["cache-control"] == "no-store"


def test_login_rejects_cross_origin_request_before_authentication(monkeypatch: Any) -> None:
    """跨站登录请求在触达 Redis 限流和密码认证前被拒绝。"""

    def redis_factory(*args: object, **kwargs: object) -> None:
        raise AssertionError("跨站登录不得访问认证依赖")

    monkeypatch.setattr("app.main.Redis.from_url", redis_factory)

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"login": "admin", "password": "password"},
            headers={"origin": "https://attacker.example"},
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "请求来源校验失败"}


def test_login_accepts_matching_public_origin_and_forwarded_scheme(monkeypatch: Any) -> None:
    """TLS 代理后的公网 Origin、Host 与可信协议头匹配时允许登录处理继续。"""
    settings = Settings()

    def fail_redis_initialization(*args: object, **kwargs: object) -> None:
        raise OSError("expected test stop")

    monkeypatch.setattr(
        "app.main.Redis.from_url",
        fail_redis_initialization,
    )

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/auth/login",
            headers={
                "origin": "https://ragmanage.example:8443",
                "host": "ragmanage.example:8443",
                "x-forwarded-proto": "https",
            },
            json={"login": "admin", "password": "password"},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "登录服务暂不可用，请稍后重试"}


def test_login_rejects_matching_but_malformed_authorities() -> None:
    """非法端口不能因 Origin 和 Host 同时规范化为空值而绕过同源校验。"""
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "server": ("example.test", 80),
            "path": "/api/v1/auth/login",
            "query_string": b"",
            "headers": [
                (b"host", b"example.test:invalid"),
                (b"origin", b"http://example.test:invalid"),
            ],
        }
    )

    assert not request_has_same_origin(request)


def test_login_rate_limit_uses_validated_client_ip_from_edge_proxy() -> None:
    """真实入口代理的 IP 覆盖值用于跨账号限额，伪造/非法值不会进入 Redis 键。"""
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "server": ("api", 8000),
            "client": ("172.20.0.5", 41000),
            "path": "/api/v1/auth/login",
            "query_string": b"",
            "headers": [(b"x-real-ip", b"2001:db8::1")],
        }
    )
    invalid_request = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "server": ("api", 8000),
            "client": ("172.20.0.5", 41000),
            "path": "/api/v1/auth/login",
            "query_string": b"",
            "headers": [(b"x-real-ip", b"forged-address")],
        }
    )

    assert login_client_ip(request) == "2001:db8::1"
    assert login_client_ip(invalid_request) == "172.20.0.5"


def test_bearer_api_key_request_is_not_subject_to_browser_csrf() -> None:
    """显式 Bearer 身份优先于 Cookie，不要求浏览器 CSRF token。"""
    app = FastAPI()
    app.add_middleware(SessionCsrfMiddleware, secret="test-secret")

    @app.post("/api/v1/customer/write")
    async def customer_write() -> Response:
        """模拟一个必须由 Bearer 认证的客户写操作。"""
        return Response(status_code=204)

    with TestClient(app) as client:
        client.cookies.set("ragmanage_session", "browser-session")
        response = client.post(
            "/api/v1/customer/write", headers={"authorization": "Bearer customer-key"}
        )

    assert response.status_code == 204
