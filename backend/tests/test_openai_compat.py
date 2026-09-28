"""OpenAI 兼容客户网关接口的行为测试。

测试通过 FastAPI HTTP 边界验证客户 Key 范围、非流式响应、SSE usage 和幂等请求头；
模型执行与数据库连接使用替身，避免测试依赖外部网关或真实租户数据。
"""

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import asyncpg
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.rag.chat import sse_event


class FakeTransaction:
    """模拟连接事务上下文，允许验证幂等拒绝发生于事务内。"""

    async def __aenter__(self) -> None:
        """开始无副作用的接口测试事务。"""
        return None

    async def __aexit__(self, *args: object) -> None:
        """结束测试事务且不吞掉业务异常。"""
        return None


class FakeConnection:
    """提供兼容入口所需的最小连接生命周期。"""

    def __init__(self) -> None:
        """记录连接是否在请求完成后正确释放。"""
        self.closed = False

    async def close(self) -> None:
        """模拟 asyncpg 连接关闭。"""
        self.closed = True


def _context() -> dict[str, Any]:
    """返回绑定到客户空间的 API Key 身份，作为接口测试前置条件。"""
    return {
        "user": {"id": "3", "platform_role": "platform_admin"},
        "api_key_id": "8",
        "api_key_tenant_id": "7",
    }


def _run_payload() -> dict[str, Any]:
    """返回已创建运行的公开字段，模拟幂等创建接口结果。"""
    return {"id": "11111111-1111-4111-8111-111111111111", "state": "queued"}


async def _completed_events(*_: Any, **__: Any) -> AsyncIterator[str]:
    """模拟问答流，包含文本、服务端答案和真实 usage。"""
    yield sse_event("meta", {"run": _run_payload()})
    yield sse_event("token", {"text": "根据资料回答 [证据 1]"})
    yield sse_event(
        "done",
        {
            "run": {
                **_run_payload(),
                "state": "completed",
                "outcome": "answered",
                "answer": "根据资料回答 [证据 1]",
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 7,
                    "total_tokens": 19,
                    "usage_source": "gateway",
                },
            }
        },
    )


async def _failed_events(*_: Any, **__: Any) -> AsyncIterator[str]:
    """模拟幂等命中已持久化失败运行的终态事件。"""
    yield sse_event(
        "done",
        {
            "run": {
                **_run_payload(),
                "state": "failed",
                "error": {"code": "GENERATION_FAILED"},
                "usage": {},
            }
        },
    )


def _patch_gateway(monkeypatch: Any) -> tuple[AsyncMock, FakeConnection]:
    """替换认证、数据库、运行创建和生成流，保持测试只观察公开 HTTP 行为。"""
    create_run = AsyncMock(return_value=(42, _run_payload()))
    connection = FakeConnection()
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=_context()))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr("app.main._prepare_openai_run", create_run)
    monkeypatch.setattr("app.main.stream_generation_run", _completed_events)
    return create_run, connection


def test_openai_non_stream_returns_openai_completion(monkeypatch: Any) -> None:
    """有效客户 Key 的非流式请求返回 OpenAI completion 和真实 Token usage。"""
    create_run, connection = _patch_gateway(monkeypatch)

    with TestClient(create_app(Settings(generation_model="qwen3.8:27b"))) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": "Bearer sk-customer",
                "X-Request-ID": "22222222-2222-4222-8222-222222222222",
            },
            json={
                "model": "qwen3.8:27b",
                "knowledge_base_id": 9,
                "messages": [{"role": "user", "content": "如何办理？"}],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "chat.completion"
    assert payload["choices"][0]["message"]["content"] == "根据资料回答 [证据 1]"
    assert payload["usage"] == {
        "prompt_tokens": 12,
        "completion_tokens": 7,
        "total_tokens": 19,
        "usage_source": "gateway",
    }
    create_run.assert_awaited_once()
    assert create_run.await_args.kwargs["request_id"] == UUID(
        "22222222-2222-4222-8222-222222222222"
    )
    assert connection.closed


def test_openai_model_is_resolved_from_knowledge_base_runtime(monkeypatch: Any) -> None:
    """知识库 Runtime Profile 可指定不同于全局默认值的模型。"""
    connection = NewRunConnection()
    generation_options: dict[str, Any] = {}

    def start_generation(*_: Any, **kwargs: Any) -> AsyncIterator[str]:
        """捕获交给 RAG 的可选温度，确保由 Runtime Profile 提供默认值。"""
        generation_options.update(kwargs)
        return _completed_events()

    create_run = AsyncMock(
        return_value={
            "id": "42",
            "public_id": "11111111-1111-4111-8111-111111111111",
            "state": "queued",
        }
    )
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=_context()))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr(
        "app.main._knowledge_base_access",
        AsyncMock(
            return_value={
                "tenant_id": 7,
                "active_release_id": 5,
                "active_runtime_id": 6,
                "runtime_definition": {"generation": {"model": "qwen3.8:27b"}},
                "generation_allowed_models": ["qwen3.8:27b"],
                "generation_endpoint_status": "active",
            }
        ),
    )
    monkeypatch.setattr("app.main._create_generation_run", create_run)
    monkeypatch.setattr("app.main.stream_generation_run", start_generation)

    with TestClient(create_app(Settings(generation_model="global-default"))) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer sk-customer"},
            json={
                "model": "qwen3.8:27b",
                "knowledge_base_id": 9,
                "messages": [{"role": "user", "content": "如何办理？"}],
            },
        )

    assert response.status_code == 200
    assert response.json()["model"] == "qwen3.8:27b"
    assert create_run.await_args.kwargs["conversation"]["active_runtime_id"] == 6
    assert create_run.await_args.kwargs["conversation"]["active_release_id"] == 5
    assert create_run.await_args.kwargs["request_fingerprint"]
    assert "temperature" not in generation_options
    assert connection.closed


def test_openai_rejects_temperature_that_differs_from_runtime_profile(
    monkeypatch: Any,
) -> None:
    """接受 SDK 常带的温度字段，但始终由激活的 Runtime Profile 决定实际温度。"""
    connection = NewRunConnection()
    create_run = AsyncMock(
        return_value={
            "id": "42",
            "public_id": "11111111-1111-4111-8111-111111111111",
            "state": "queued",
        }
    )
    generation_options: dict[str, Any] = {}

    def start_generation(*_: Any, **kwargs: Any) -> AsyncIterator[str]:
        """捕获兼容入口交给 RAG 的覆盖项，确保客户端温度不会传入。"""
        generation_options.update(kwargs)
        return _completed_events()

    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=_context()))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr(
        "app.main._knowledge_base_access",
        AsyncMock(
            return_value={
                "tenant_id": 7,
                "active_release_id": 5,
                "active_runtime_id": 6,
                "runtime_definition": {"generation": {"model": "qwen3.8:27b", "temperature": 0.2}},
                "generation_allowed_models": ["qwen3.8:27b"],
                "generation_endpoint_status": "active",
            }
        ),
    )
    monkeypatch.setattr("app.main._create_generation_run", create_run)
    monkeypatch.setattr("app.main.stream_generation_run", start_generation)

    with TestClient(create_app(Settings(generation_model="global-default"))) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer sk-customer"},
            json={
                "model": "qwen3.8:27b",
                "knowledge_base_id": 9,
                "temperature": 0.8,
                "messages": [{"role": "user", "content": "如何办理？"}],
            },
        )

    assert response.status_code == 200
    assert "temperature" not in generation_options
    assert create_run.await_args.kwargs["request_fingerprint"]
    assert connection.closed


def test_openai_rejects_max_tokens_above_server_budget(monkeypatch: Any) -> None:
    """客户不能通过单次请求突破服务端用于上游调用和额度预留的预算。"""
    create_run, _ = _patch_gateway(monkeypatch)

    with TestClient(
        create_app(Settings(generation_model="qwen3.8:27b", generation_max_tokens=512))
    ) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer sk-customer"},
            json={
                "model": "qwen3.8:27b",
                "knowledge_base_id": 9,
                "max_tokens": 513,
                "messages": [{"role": "user", "content": "如何办理？"}],
            },
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "max_tokens_exceeds_server_limit"
    create_run.assert_not_awaited()


def test_openai_rejects_conflicting_request_ids(monkeypatch: Any) -> None:
    """请求头和请求体的幂等 ID 不一致时拒绝含糊身份，避免重试串单。"""
    create_run, _ = _patch_gateway(monkeypatch)

    with TestClient(create_app(Settings(generation_model="qwen3.8:27b"))) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": "Bearer sk-customer",
                "X-Request-ID": "22222222-2222-4222-8222-222222222222",
            },
            json={
                "model": "qwen3.8:27b",
                "knowledge_base_id": 9,
                "request_id": "33333333-3333-4333-8333-333333333333",
                "messages": [{"role": "user", "content": "如何办理？"}],
            },
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "request_id_mismatch"
    create_run.assert_not_awaited()


def test_openai_rejects_model_not_matching_active_runtime(monkeypatch: Any) -> None:
    """请求模型必须匹配所选知识库当前激活 Profile 中的生成模型。"""
    connection = NewRunConnection()
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=_context()))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    access = AsyncMock(
        return_value={
            "tenant_id": 7,
            "active_release_id": 5,
            "active_runtime_id": 6,
            "runtime_definition": {"generation": {"model": "profile-model"}},
            "generation_allowed_models": ["profile-model"],
            "generation_endpoint_status": "active",
        }
    )
    monkeypatch.setattr("app.main._knowledge_base_access", access)

    with TestClient(create_app(Settings(generation_model="qwen3.8:27b"))) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer sk-customer"},
            json={
                "model": "qwen3.8:27b",
                "knowledge_base_id": 9,
                "messages": [{"role": "user", "content": "如何办理？"}],
            },
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    access.assert_awaited_once()
    assert connection.closed


def test_openai_rejects_model_outside_default_server_allowlist(monkeypatch: Any) -> None:
    """无 Runtime Profile 时仍必须校验服务端全局模型白名单。"""
    connection = NewRunConnection()
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=_context()))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr(
        "app.main._knowledge_base_access",
        AsyncMock(
            return_value={
                "tenant_id": 7,
                "active_release_id": 5,
                "active_runtime_id": None,
            }
        ),
    )

    with TestClient(
        create_app(
            Settings(
                generation_model="qwen3.8:27b",
                model_gateway_allowed_models="qwen3-embedding:0.6b",
            )
        )
    ) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer sk-customer"},
            json={
                "model": "qwen3.8:27b",
                "knowledge_base_id": 9,
                "messages": [{"role": "user", "content": "如何办理？"}],
            },
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert connection.closed


def test_openai_rejects_knowledge_base_from_another_tenant(monkeypatch: Any) -> None:
    """即使资源可见，API Key 也不得跨出其绑定的客户空间。"""
    connection = NewRunConnection()
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=_context()))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr(
        "app.main._knowledge_base_access",
        AsyncMock(return_value={"tenant_id": 99, "active_release_id": 5}),
    )

    with TestClient(create_app(Settings(generation_model="qwen3.8:27b"))) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer sk-customer"},
            json={
                "model": "qwen3.8:27b",
                "knowledge_base_id": 9,
                "messages": [{"role": "user", "content": "如何办理？"}],
            },
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "knowledge_base_not_found"
    assert connection.closed


def test_openai_enforces_per_key_concurrency_limit(monkeypatch: Any) -> None:
    """达到每 Key 并发上限后在创建会话前返回 429。"""
    connection = NewRunConnection(active_runs=5)
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=_context()))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    access = AsyncMock(
        return_value={
            "tenant_id": 7,
            "active_release_id": 5,
            "active_runtime_id": None,
        }
    )
    monkeypatch.setattr("app.main._knowledge_base_access", access)

    with TestClient(create_app(Settings(generation_model="qwen3.8:27b"))) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer sk-customer"},
            json={
                "model": "qwen3.8:27b",
                "knowledge_base_id": 9,
                "messages": [{"role": "user", "content": "如何办理？"}],
            },
        )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limit_exceeded"
    access.assert_awaited_once()
    assert connection.closed


def test_openai_invalid_api_key_uses_openai_error_envelope(monkeypatch: Any) -> None:
    """失效、停用或过期 Key 由统一认证拒绝并转换为 OpenAI 错误结构。"""
    from fastapi import HTTPException

    monkeypatch.setattr(
        "app.main._authenticated_user",
        AsyncMock(side_effect=HTTPException(status_code=401, detail="未登录或 API Key 无效")),
    )

    with TestClient(create_app(Settings(generation_model="qwen3.8:27b"))) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer sk-revoked"},
            json={
                "model": "qwen3.8:27b",
                "knowledge_base_id": 9,
                "messages": [{"role": "user", "content": "如何办理？"}],
            },
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_api_key"


async def _quota_events(*_: Any, **__: Any) -> AsyncIterator[str]:
    """模拟既有预扣逻辑发现额度不足后的内部终态事件。"""
    yield sse_event(
        "error",
        {"code": "TOKEN_QUOTA_EXCEEDED", "message": "API Key Token 额度不足"},
    )


async def _internal_generation_error_events(*_: Any, **__: Any) -> AsyncIterator[str]:
    """模拟生成器发出内部大写错误码的 SSE 失败事件。"""
    yield sse_event(
        "error",
        {"code": "GENERATION_FAILED", "message": "上游错误细节不应直出"},
    )


def test_openai_token_quota_exhaustion_returns_too_many_requests(monkeypatch: Any) -> None:
    """RAG 预扣额度失败映射为 429，并保持标准错误包结构。"""
    _patch_gateway(monkeypatch)
    monkeypatch.setattr("app.main.stream_generation_run", _quota_events)

    with TestClient(create_app(Settings(generation_model="qwen3.8:27b"))) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer sk-customer"},
            json={
                "model": "qwen3.8:27b",
                "knowledge_base_id": 9,
                "messages": [{"role": "user", "content": "如何办理？"}],
            },
        )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "TOKEN_QUOTA_EXCEEDED"


def test_openai_quota_stream_emits_one_error_frame(monkeypatch: Any) -> None:
    """流式额度拒绝只发单个错误帧，然后以 DONE 正常结束协议。"""
    _patch_gateway(monkeypatch)
    monkeypatch.setattr("app.main.stream_generation_run", _quota_events)

    with TestClient(create_app(Settings(generation_model="qwen3.8:27b"))) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer sk-customer"},
            json={
                "model": "qwen3.8:27b",
                "knowledge_base_id": 9,
                "stream": True,
                "messages": [{"role": "user", "content": "如何办理？"}],
            },
        )

    assert response.status_code == 200
    assert response.text.count('"code": "TOKEN_QUOTA_EXCEEDED"') == 1
    assert '"code": "generation_incomplete"' not in response.text
    assert response.text.endswith("data: [DONE]\n\n")


def test_openai_database_failure_uses_stable_error_envelope(monkeypatch: Any) -> None:
    """数据库异常不得泄漏 SQL 或 FastAPI 默认错误结构给 OpenAI 客户端。"""
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=_context()))
    monkeypatch.setattr(
        "app.main._database", AsyncMock(side_effect=asyncpg.PostgresError("secret SQL detail"))
    )

    with TestClient(create_app(Settings(generation_model="qwen3.8:27b"))) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer sk-customer"},
            json={
                "model": "qwen3.8:27b",
                "knowledge_base_id": 9,
                "messages": [{"role": "user", "content": "如何办理？"}],
            },
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
    assert "secret SQL detail" not in response.text


def test_openai_stream_emits_sse_usage_and_done(monkeypatch: Any) -> None:
    """流式请求返回增量内容、最终 usage 帧和标准 DONE 哨兵。"""
    _patch_gateway(monkeypatch)

    with TestClient(create_app(Settings(generation_model="qwen3.8:27b"))) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer sk-customer"},
            json={
                "model": "qwen3.8:27b",
                "knowledge_base_id": 9,
                "stream": True,
                "messages": [{"role": "user", "content": "如何办理？"}],
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"content": "根据资料回答 [证据 1]"' in response.text
    usage_fragment = '"usage": {"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19'
    assert usage_fragment in response.text
    assert "data: [DONE]" in response.text


def test_openai_does_not_replay_failed_run_as_success(monkeypatch: Any) -> None:
    """已失败的幂等运行必须返回生成错误，不得合成空的成功 completion。"""
    _patch_gateway(monkeypatch)
    monkeypatch.setattr("app.main.stream_generation_run", _failed_events)

    with TestClient(create_app(Settings(generation_model="qwen3.8:27b"))) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer sk-customer"},
            json={
                "model": "qwen3.8:27b",
                "knowledge_base_id": 9,
                "messages": [{"role": "user", "content": "如何办理？"}],
            },
        )

    assert response.status_code == 502
    assert response.json()["error"]["type"] == "server_error"
    assert response.json()["error"]["code"] == "generation_failed"


def test_openai_normalizes_internal_uppercase_failure_code(monkeypatch: Any) -> None:
    """内部大写终态码仍应映射为 OpenAI server_error，而不是参数错误。"""
    _patch_gateway(monkeypatch)
    monkeypatch.setattr("app.main.stream_generation_run", _internal_generation_error_events)

    with TestClient(create_app(Settings(generation_model="qwen3.8:27b"))) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer sk-customer"},
            json={
                "model": "qwen3.8:27b",
                "knowledge_base_id": 9,
                "stream": True,
                "messages": [{"role": "user", "content": "如何办理？"}],
            },
        )

    assert response.status_code == 200
    assert '"type": "server_error"' in response.text
    assert '"code": "GENERATION_FAILED"' in response.text
    assert "上游错误细节不应直出" not in response.text


def test_openai_endpoint_rejects_browser_session(monkeypatch: Any) -> None:
    """浏览器 Session 不能伪装成客户 Key 调用对外模型网关。"""
    monkeypatch.setattr(
        "app.main._authenticated_user",
        AsyncMock(return_value={"user": {"id": "3", "platform_role": "platform_admin"}}),
    )

    with TestClient(create_app(Settings(generation_model="qwen3.8:27b"))) as client:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "qwen3.8:27b",
                "knowledge_base_id": 9,
                "messages": [{"role": "user", "content": "如何办理？"}],
            },
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "api_key_scope_forbidden"


def test_openai_endpoint_rejects_payload_above_request_limit(monkeypatch: Any) -> None:
    """对外入口在 JSON 解析前限制请求体，避免未知字段消耗过量内存。"""
    _patch_gateway(monkeypatch)

    with TestClient(create_app(Settings(generation_model="qwen3.8:27b"))) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer sk-customer"},
            content=b" " * (1024 * 1024 + 1),
        )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"


def test_openai_validation_errors_use_openai_error_envelope(monkeypatch: Any) -> None:
    """無效角色通过标准 OpenAI error 结构返回，不泄露 FastAPI 验证细节。"""
    _patch_gateway(monkeypatch)

    with TestClient(create_app(Settings(generation_model="qwen3.8:27b"))) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer sk-customer"},
            json={
                "model": "qwen3.8:27b",
                "knowledge_base_id": 9,
                "messages": [{"role": "assistant", "content": "旧轮次"}],
            },
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


class ExistingRunConnection(FakeConnection):
    """返回既有运行，验证 HTTP 幂等拒绝发生在会话创建之前。"""

    def transaction(self) -> FakeTransaction:
        """提供事务边界，运行命中应在创建会话前结束。"""
        return FakeTransaction()

    async def execute(self, query: str, *args: object) -> None:
        """接受每 Key 及每 request 事务锁，供锁定顺序测试使用。"""
        assert "pg_advisory_xact_lock" in query
        assert args in {
            ("openai-concurrency:8",),
            ("api-key-run:8:22222222-2222-4222-8222-222222222222",),
        }

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any]:
        """返回旧运行快照，防止幂等 ID 重放不同问题或生成参数。"""
        assert "FROM generation_runs" in query
        assert args[0] == 8
        return {
            "id": "42",
            "knowledge_base_id": "9",
            "public_id": "run",
            "question": "相同问题",
            "request_fingerprint": "stored-fingerprint",
            "runtime_model": "qwen3.8:27b",
            "api_key_id": "8",
        }


class NewRunConnection(FakeConnection):
    """模拟新兼容请求的事务序列，并返回已授权的 Profile 查询结果。"""

    def __init__(self, active_runs: int = 0) -> None:
        """配置当前并发数，以覆盖是否允许创建新运行的边界。"""
        super().__init__()
        self.active_runs = active_runs

    def transaction(self) -> FakeTransaction:
        """以无副作用事务验证新运行只在单一事务中创建。"""
        return FakeTransaction()

    async def execute(self, query: str, *args: object) -> None:
        """限制测试只执行共享 Key 锁和单请求幂等锁。"""
        assert "pg_advisory_xact_lock" in query
        assert args and str(args[0]).startswith(("openai-concurrency:8", "api-key-run:8:"))

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        """区分幂等查询和会话插入，避免依赖数据库实现细节。"""
        if "FROM generation_runs" in query:
            return None
        if "INSERT INTO conversations" in query:
            return {
                "id": 13,
                "tenant_id": 7,
                "knowledge_base_id": 9,
                "title": "如何办理？",
                "status": "active",
            }
        if "INSERT INTO generation_runs" in query:
            return {
                "id": "42",
                "public_id": "11111111-1111-4111-8111-111111111111",
                "tenant_id": "7",
                "knowledge_base_id": "9",
                "conversation_id": "13",
                "user_message_id": "21",
                "assistant_message_id": "22",
                "release_id": "5",
                "api_key_id": "8",
                "request_id": str(args[6]),
                "state": "queued",
                "outcome": None,
                "cancel_requested": False,
                "error": None,
                "created_at": "2026-09-18T00:00:00Z",
                "updated_at": "2026-09-18T00:00:00Z",
            }
        raise AssertionError(f"未处理的兼容运行查询：{query}")

    async def fetchval(self, query: str, *args: object) -> int:
        """返回 Key 活跃数或用户/助手消息主键，覆盖共享创建边界。"""
        if "count(*)" in query:
            assert args == (8,)
            return self.active_runs
        if "INSERT INTO messages" in query:
            return 21 if "'user'" in query else 22
        raise AssertionError(f"未处理的兼容运行 fetchval 查询：{query}")


def test_openai_rejects_request_id_reuse_with_different_question(monkeypatch: Any) -> None:
    """同一客户 Key 的幂等 ID 携带不同问题时经 HTTP 返回冲突。"""
    connection = ExistingRunConnection()
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=_context()))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))

    with TestClient(create_app(Settings(generation_model="qwen3.8:27b"))) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": "Bearer sk-customer",
                "X-Request-ID": "22222222-2222-4222-8222-222222222222",
            },
            json={
                "model": "qwen3.8:27b",
                "knowledge_base_id": 9,
                "messages": [{"role": "user", "content": "新问题"}],
            },
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "duplicate_request"
    assert connection.closed


def test_openai_rejects_request_id_reuse_with_different_generation_parameters(
    monkeypatch: Any,
) -> None:
    """相同幂等 ID 改变输出预算时返回冲突，不复用旧回答。"""
    connection = ExistingRunConnection()
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=_context()))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))

    with TestClient(create_app(Settings(generation_model="qwen3.8:27b"))) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": "Bearer sk-customer",
                "X-Request-ID": "22222222-2222-4222-8222-222222222222",
            },
            json={
                "model": "qwen3.8:27b",
                "knowledge_base_id": 9,
                "max_tokens": 128,
                "messages": [{"role": "user", "content": "相同问题"}],
            },
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "duplicate_request"
