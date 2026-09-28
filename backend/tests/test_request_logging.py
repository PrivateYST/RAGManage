"""验证结构化请求日志只记录可关联元数据，不泄露认证凭据或正文。"""

import json
import logging
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.security import RequestIDMiddleware, StructuredRequestLoggingMiddleware


def test_structured_request_log_contains_safe_metadata(caplog: Any) -> None:
    """成功请求应记录状态和耗时，并避免把 Cookie、Authorization 或正文写入日志。"""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(StructuredRequestLoggingMiddleware)

    @app.post("/items")
    async def create_item() -> dict[str, str]:
        """返回固定响应，测试无需读取请求正文即可完成日志记录。"""
        return {"status": "ok"}

    with caplog.at_level(logging.INFO, logger="app.core.security"):
        with TestClient(app) as client:
            response = client.post(
                "/items",
                headers={
                    "Authorization": "Bearer secret-key",
                    "Cookie": "ragmanage_session=secret",
                },
                json={"password": "secret-body"},
            )

    assert response.status_code == 200
    records = [
        json.loads(record.message) for record in caplog.records if record.message.startswith("{")
    ]
    event = next(record for record in records if record["event"] == "http.request")
    assert event["method"] == "POST"
    assert event["path"] == "/items"
    assert event["status_code"] == 200
    assert isinstance(event["duration_ms"], float)
    assert event["request_id"] == response.headers["x-request-id"]
    assert "secret-key" not in caplog.text
    assert "secret-body" not in caplog.text
    assert "ragmanage_session" not in caplog.text
