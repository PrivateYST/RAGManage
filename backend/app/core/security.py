"""实现登录限速、管理 API 限流、同源校验和浏览器 Session 的 CSRF 防护。"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import time
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from redis.asyncio import Redis
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

LOGIN_ACCOUNT_IP_FAILURE_LIMIT = 5
LOGIN_IP_FAILURE_LIMIT = 20
LOGIN_FAILURE_WINDOW_SECONDS = 15 * 60
LOGIN_RESERVATION_TTL_SECONDS = 60
MANAGEMENT_RATE_LIMIT = 120
MANAGEMENT_RATE_WINDOW_SECONDS = 60

_RESERVE_LOGIN_SCRIPT = """
local account_total = tonumber(redis.call('GET', KEYS[1]) or '0')
  + tonumber(redis.call('GET', KEYS[2]) or '0')
local ip_total = tonumber(redis.call('GET', KEYS[3]) or '0')
  + tonumber(redis.call('GET', KEYS[4]) or '0')
if account_total >= tonumber(ARGV[1]) or ip_total >= tonumber(ARGV[2]) then
  return 0
end
for index = 2, 4, 2 do
  local count = redis.call('INCR', KEYS[index])
  if count == 1 then
    redis.call('EXPIRE', KEYS[index], tonumber(ARGV[3]))
  end
end
return 1
"""

_FINISH_LOGIN_SCRIPT = """
for index = 2, 4, 2 do
  local count = redis.call('DECR', KEYS[index])
  if count <= 0 then
    redis.call('DEL', KEYS[index])
  end
end
if ARGV[1] == 'failure' then
  redis.call('INCR', KEYS[1])
  redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
  redis.call('INCR', KEYS[3])
  redis.call('EXPIRE', KEYS[3], tonumber(ARGV[2]))
elseif ARGV[1] == 'success' then
  redis.call('DEL', KEYS[1])
end
return 1
"""

_MANAGEMENT_RATE_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
end
local ttl = redis.call('TTL', KEYS[1])
return {count, ttl}
"""

# 只有不会改变服务端状态的方法可以不提交 CSRF 证明。
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_RATE_LIMIT_EXCLUDED_PATHS = frozenset(
    {
        "/api/v1/health/live",
        "/api/v1/health/ready",
        "/api/v1/auth/login",
        "/api/v1/auth/csrf",
    }
)
logger = logging.getLogger(__name__)


class StructuredRequestLoggingMiddleware:
    """输出不含敏感数据的 JSON 请求摘要与耗时，供日志系统检索和告警。"""

    def __init__(self, app: ASGIApp) -> None:
        """初始化无状态访问日志中间件，不读取请求正文或认证凭据。"""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """记录方法、路径、状态、request_id 和毫秒耗时，异常按 500 记录后继续抛出。"""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status_code = 500

        async def capture_status(message: Message) -> None:
            """捕获响应状态而不修改响应头或响应体。"""
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, capture_status)
        finally:
            state = scope.get("state", {})
            request_id = state.get("request_id")
            record = {
                "event": "http.request",
                "request_id": str(request_id) if request_id else None,
                "method": scope.get("method", ""),
                "path": scope.get("path", ""),
                "status_code": status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            }
            logger.info(json.dumps(record, ensure_ascii=False, separators=(",", ":")))


class RequestIDMiddleware:
    """为每个 HTTP 请求分配可追踪 UUID，并在响应头中回传给调用方。"""

    def __init__(self, app: ASGIApp) -> None:
        """初始化无状态中间件；仅复用调用方提供的合法 UUID。"""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """将 request_id 写入请求状态，并确保异常响应也带 X-Request-ID。"""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        raw_request_id = headers.get(b"x-request-id", b"").decode("ascii", errors="ignore")
        try:
            request_id = UUID(raw_request_id) if raw_request_id else uuid4()
        except ValueError:
            request_id = uuid4()
        scope["state"] = {**scope.get("state", {}), "request_id": request_id}

        async def send_with_request_id(message: Message) -> None:
            """只给 HTTP 响应追加追踪头，避免影响 websocket 或 lifespan。"""
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers", []))
                response_headers.append((b"x-request-id", str(request_id).encode("ascii")))
                message = {**message, "headers": response_headers}
            await send(message)

        await self.app(scope, receive, send_with_request_id)


@dataclass(frozen=True)
class LoginAttemptReservation:
    """一次正在进行的密码认证预占，用于完成时提交失败或释放成功请求。"""

    account_failure_key: str
    account_inflight_key: str
    ip_failure_key: str
    ip_inflight_key: str


@dataclass(frozen=True)
class ManagementRateLimitResult:
    """管理 API 固定窗口计数结果，包含超限响应所需的等待秒数。"""

    allowed: bool
    retry_after: int
    count: int


def _rate_limit_digest(value: str) -> str:
    """不可逆压缩登录名和客户端地址，避免 Redis 键暴露账号或网络标识。"""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def login_attempt_keys(login: str, client_ip: str) -> LoginAttemptReservation:
    """生成账号-IP 组合及 IP 聚合键，单一攻击来源不能锁定账号的其他用户。"""
    normalized_login = login.strip().casefold()
    normalized_ip = client_ip.strip() or "unknown"
    account_ip_digest = _rate_limit_digest(f"{normalized_login}\0{normalized_ip}")
    ip_digest = _rate_limit_digest(normalized_ip)
    prefix = "ragmanage:login-failure"
    return LoginAttemptReservation(
        account_failure_key=f"{prefix}:account-ip:{account_ip_digest}",
        account_inflight_key=f"{prefix}:account-ip-inflight:{account_ip_digest}",
        ip_failure_key=f"{prefix}:ip:{ip_digest}",
        ip_inflight_key=f"{prefix}:ip-inflight:{ip_digest}",
    )


async def reserve_login_attempt(
    redis: Redis, login: str, client_ip: str
) -> LoginAttemptReservation | None:
    """原子检查失败数并占用两个额度；限额已满返回 None，不调用密码验证。"""
    keys = login_attempt_keys(login, client_ip)
    result = redis.eval(
        _RESERVE_LOGIN_SCRIPT,
        4,
        keys.account_failure_key,
        keys.account_inflight_key,
        keys.ip_failure_key,
        keys.ip_inflight_key,
        str(LOGIN_ACCOUNT_IP_FAILURE_LIMIT),
        str(LOGIN_IP_FAILURE_LIMIT),
        str(LOGIN_RESERVATION_TTL_SECONDS),
    )
    allowed = await cast(Awaitable[Any], result)
    return keys if int(allowed) == 1 else None


async def finish_login_attempt(
    redis: Redis,
    reservation: LoginAttemptReservation,
    *,
    succeeded: bool | None,
) -> None:
    """原子释放在途占用；明确密码失败会计数，成功清除账号连续失败数。"""
    result = redis.eval(
        _FINISH_LOGIN_SCRIPT,
        4,
        reservation.account_failure_key,
        reservation.account_inflight_key,
        reservation.ip_failure_key,
        reservation.ip_inflight_key,
        "neutral" if succeeded is None else ("success" if succeeded else "failure"),
        str(LOGIN_FAILURE_WINDOW_SECONDS),
    )
    await cast(Awaitable[Any], result)


def management_rate_limit_key(request: Request) -> str:
    """生成不暴露 Session 或 IP 原文的管理 API 限流键。"""
    session_token = request.cookies.get("ragmanage_session", "").strip()
    if session_token:
        identity = f"session:{session_token}"
    else:
        identity = f"ip:{login_client_ip(request)}"
    digest = _rate_limit_digest(identity)
    return f"ragmanage:management-rate:{digest}"


async def reserve_management_request(
    redis: Redis,
    request: Request,
    *,
    limit: int = MANAGEMENT_RATE_LIMIT,
    window_seconds: int = MANAGEMENT_RATE_WINDOW_SECONDS,
) -> ManagementRateLimitResult:
    """原子增加管理请求计数，并返回当前窗口是否仍有预算。"""
    result = redis.eval(
        _MANAGEMENT_RATE_LIMIT_SCRIPT,
        1,
        management_rate_limit_key(request),
        str(limit),
        str(window_seconds),
    )
    raw = await cast(Awaitable[Any], result)
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise RuntimeError("管理 API 限流 Redis 返回值无效")
    count = int(raw[0])
    retry_after = max(1, int(raw[1]))
    return ManagementRateLimitResult(count <= limit, retry_after, count)


def session_csrf_token(secret: str, session_token: str) -> str:
    """用部署间共享密钥将 CSRF 凭据绑定到单个高熵 Session。"""
    return hmac.new(
        secret.encode("utf-8"),
        session_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_session_csrf_token(secret: str, session_token: str, candidate: str) -> bool:
    """常量时间比较浏览器提交的凭据，避免错误反馈泄露有效 token 前缀。"""
    expected = session_csrf_token(secret, session_token)
    return hmac.compare_digest(expected, candidate)


def _normalized_authority(authority: str, scheme: str) -> str:
    """规范化 Host 和 Origin authority，处理大小写及默认端口差异。"""
    parsed = urlsplit(f"//{authority}")
    if (
        parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        return ""
    hostname = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError:
        return ""
    if not hostname:
        return ""
    host = f"[{hostname}]" if ":" in hostname else hostname
    default_port = 443 if scheme == "https" else 80
    return f"{host}:{port}" if port is not None and port != default_port else host


def request_has_same_origin(request: Request) -> bool:
    """拒绝登录 CSRF；无 Origin 的旧客户端必须至少带浏览器 same-origin 元数据。"""
    origin_header = request.headers.get("origin")
    if not origin_header:
        return request.headers.get("sec-fetch-site", "").lower() == "same-origin"
    try:
        origin = urlsplit(origin_header)
        if (
            origin.scheme.lower() not in {"http", "https"}
            or origin.username is not None
            or origin.password is not None
            or origin.path not in {"", "/"}
            or origin.query
            or origin.fragment
        ):
            return False
        forwarded_scheme = request.headers.get("x-forwarded-proto", "").split(",", 1)[0]
        request_scheme = (forwarded_scheme.strip() or request.url.scheme).lower()
        origin_authority = _normalized_authority(origin.netloc, origin.scheme.lower())
        request_authority = _normalized_authority(request.headers.get("host", ""), request_scheme)
        return (
            bool(origin_authority)
            and bool(request_authority)
            and origin.scheme.lower() == request_scheme
            and origin_authority == request_authority
        )
    except ValueError:
        return False


def login_client_ip(request: Request) -> str:
    """读取入口代理覆盖写入的真实客户端 IP；非法或缺失时回退 ASGI peer。"""
    forwarded_address = request.headers.get("x-real-ip", "").strip()
    try:
        if forwarded_address:
            return str(ipaddress.ip_address(forwarded_address))
    except ValueError:
        pass
    return request.client.host if request.client else "unknown"


class SessionCsrfMiddleware:
    """校验 Cookie Session 写请求；Bearer API Key 和登录入口走各自认证边界。"""

    def __init__(self, app: ASGIApp, *, secret: str) -> None:
        """初始化跨 Worker 稳定的 CSRF 密钥，不能使用进程随机状态。"""
        self.app = app
        self.secret = secret

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """在路由执行前拒绝跨站登录及缺少有效 token 的 Session 写操作。"""
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/v1/"):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        if scope.get("path") == "/api/v1/auth/login" and scope.get("method") == "POST":
            if not request_has_same_origin(request):
                await JSONResponse({"detail": "请求来源校验失败"}, status_code=403)(
                    scope, receive, send
                )
                return
            await self.app(scope, receive, send)
            return

        if scope.get("method", "GET").upper() in _SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        authorization = request.headers.get("authorization", "")
        scheme, _, _ = authorization.partition(" ")
        session_token = request.cookies.get("ragmanage_session")
        if scheme.lower() == "bearer" or not session_token:
            await self.app(scope, receive, send)
            return

        cookie_token = request.cookies.get("ragmanage_csrf", "")
        header_token = request.headers.get("x-csrf-token", "")
        if (
            not cookie_token
            or not header_token
            or not hmac.compare_digest(cookie_token, header_token)
            or not verify_session_csrf_token(self.secret, session_token, header_token)
        ):
            await JSONResponse({"detail": "CSRF 校验失败"}, status_code=403)(scope, receive, send)
            return

        await self.app(scope, receive, send)


class ManagementRateLimitMiddleware:
    """为后台 API 施加跨 Worker 的 Redis 固定窗口限流。"""

    def __init__(
        self,
        app: ASGIApp,
        *,
        redis_url: str,
        limit: int = MANAGEMENT_RATE_LIMIT,
        window_seconds: int = MANAGEMENT_RATE_WINDOW_SECONDS,
    ) -> None:
        """保存 Redis 连接配置和窗口参数；每次请求短连接执行原子计数。"""
        self.app = app
        self.redis_url = redis_url
        self.limit = limit
        self.window_seconds = window_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """只限制管理 API，健康检查与认证引导接口沿用各自的保护策略。"""
        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()
        if (
            scope["type"] != "http"
            or not path.startswith("/api/v1/")
            or path in _RATE_LIMIT_EXCLUDED_PATHS
            or method == "OPTIONS"
        ):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        redis: Redis | None = None
        try:
            redis = Redis.from_url(
                self.redis_url,
                socket_connect_timeout=1,
                socket_timeout=1,
                decode_responses=False,
            )
            decision = await reserve_management_request(
                redis,
                request,
                limit=self.limit,
                window_seconds=self.window_seconds,
            )
        except Exception:
            # 限流存储故障不应把已认证后台完全锁死；登录入口仍由独立逻辑 fail closed。
            logger.exception("管理 API 限流存储不可用，暂时放行请求")
            decision = None
        finally:
            if redis is not None:
                try:
                    await redis.aclose()
                except Exception:
                    logger.exception("关闭管理 API 限流连接失败")

        if decision is not None and not decision.allowed:
            response = JSONResponse(
                {"detail": "管理接口请求过于频繁，请稍后重试"},
                status_code=429,
                headers={
                    "Retry-After": str(decision.retry_after),
                    "X-RateLimit-Limit": str(self.limit),
                    "X-RateLimit-Remaining": "0",
                },
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
