"""验证统一错误码响应头与既有 detail 响应体的兼容边界。"""

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_http_exception_has_stable_error_code_without_breaking_detail() -> None:
    """业务错误返回稳定错误码，同时保留旧客户端读取的 detail 字段。"""
    with TestClient(create_app(Settings())) as client:
        response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json() == {"detail": "未登录或 API Key 无效"}
    assert response.headers["x-error-code"] == "unauthorized"


def test_validation_exception_has_standard_error_code() -> None:
    """参数错误统一标记 validation_error，便于客户端分类处理。"""
    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/search-test",
            json={"knowledge_base_id": 1, "query": "   "},
        )
    assert response.status_code == 422
    assert response.headers["x-error-code"] == "validation_error"
