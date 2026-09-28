"""验证所有 HTTP 响应都带可关联的 request_id，便于定位服务端错误。"""

from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.security import RequestIDMiddleware


def _app() -> FastAPI:
    """构造最小应用，覆盖成功和异常响应两条 ASGI 路径。"""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        """返回成功载荷，验证中间件不改变业务内容。"""
        return {"status": "ok"}

    @app.get("/error")
    async def error() -> None:
        """抛出业务异常，验证请求 ID 仍会被写入响应头。"""
        raise HTTPException(status_code=400, detail="bad request")

    return app


def test_request_id_reuses_valid_header() -> None:
    """合法的上游 request_id 应被原样透传，便于跨代理串联日志。"""
    request_id = "12345678-1234-5678-1234-567812345678"
    with TestClient(_app()) as client:
        response = client.get("/ok", headers={"X-Request-ID": request_id})
    assert response.status_code == 200
    assert response.headers["x-request-id"] == request_id


def test_request_id_is_generated_for_invalid_header_and_error() -> None:
    """非法请求头不得污染追踪链，异常响应仍返回新的 UUID。"""
    with TestClient(_app()) as client:
        response = client.get("/error", headers={"X-Request-ID": "not-a-uuid"})
    assert response.status_code == 400
    generated = response.headers["x-request-id"]
    UUID(generated)
    assert response.json() == {"detail": "bad request"}
