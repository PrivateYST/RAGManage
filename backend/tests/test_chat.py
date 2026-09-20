import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import _create_generation_run, create_app
from app.rag.chat import (
    load_run_snapshot,
    sse_event,
    stream_generation_run,
    validate_generated_answer,
)


class FakeTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeRunConnection:
    def __init__(self, *, existing: dict[str, object] | None = None) -> None:
        self.existing = existing
        self.fetchval_calls: list[tuple[Any, ...]] = []
        self.execute_calls: list[tuple[Any, ...]] = []

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "FROM generation_runs" in query:
            return self.existing
        if "INSERT INTO generation_runs" in query:
            return {
                "id": "41",
                "tenant_id": "7",
                "knowledge_base_id": "9",
                "conversation_id": "13",
                "user_message_id": "21",
                "assistant_message_id": "22",
                "release_id": "5",
                "request_id": str(args[-1]),
                "state": "queued",
                "outcome": None,
                "cancel_requested": False,
                "error": None,
                "created_at": "2026-09-18T00:00:00Z",
                "updated_at": "2026-09-18T00:00:00Z",
            }
        raise AssertionError(f"未处理的 fetchrow 查询：{query}")

    async def fetchval(self, query: str, *args: object) -> int:
        self.fetchval_calls.append((query, *args))
        return 21 if "'user'" in query else 22

    async def execute(self, query: str, *args: object) -> None:
        self.execute_calls.append((query, *args))


class FakeEndpointConnection:
    def __init__(self) -> None:
        self.closed = False
        self.execute_calls: list[tuple[Any, ...]] = []

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()

    async def execute(self, query: str, *args: object) -> None:
        self.execute_calls.append((query, *args))

    async def close(self) -> None:
        self.closed = True


class FakeSnapshotConnection:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = row
        self.fetch_calls = 0

    async def fetchrow(self, query: str, *args: object) -> dict[str, object]:
        return self.row

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        self.fetch_calls += 1
        return []


class FakeStreamConnection:
    def __init__(self) -> None:
        self.closed = False
        self.execute_calls: list[tuple[Any, ...]] = []

    async def fetchrow(self, query: str, *args: object) -> dict[str, object]:
        return {
            "id": 41,
            "tenant_id": 7,
            "knowledge_base_id": 9,
            "conversation_id": 13,
            "user_message_id": 21,
            "assistant_message_id": 22,
            "release_id": 5,
        }

    async def execute(self, query: str, *args: object) -> None:
        self.execute_calls.append((query, *args))

    async def close(self) -> None:
        self.closed = True


def test_generated_answer_only_keeps_server_known_citations_and_removes_urls() -> None:
    content, citations, outcome = validate_generated_answer(
        "办理步骤见 [证据 1]，详情 https://untrusted.test/x 和 [外部来源](http://bad.test)。"
        "错误引用 [证据 9]。",
        {1, 2},
    )

    assert outcome == "answered"
    assert citations == [1]
    assert "[证据 1]" in content
    assert "证据 9" not in content
    assert "http" not in content
    assert "外部来源" in content


def test_generated_answer_without_valid_citation_is_refused() -> None:
    content, citations, outcome = validate_generated_answer("模型自行回答。", {1})

    assert outcome == "no_answer"
    assert citations == []
    assert content == "生成结果没有提供可验证引用，已拒绝展示。"


def test_source_conflict_requires_citations_from_both_sides() -> None:
    content, citations, outcome = validate_generated_answer(
        "[[SOURCE_CONFLICT]]规则 A 要求办理。[证据 1]规则 B 不允许办理。[证据 2]",
        {1, 2},
    )

    assert outcome == "source_conflict"
    assert citations == [1, 2]
    assert "SOURCE_CONFLICT" not in content

    rejected, rejected_citations, rejected_outcome = validate_generated_answer(
        "[[SOURCE_CONFLICT]]只引用了一方。[证据 1]",
        {1, 2},
    )
    assert rejected_outcome == "no_answer"
    assert rejected_citations == []
    assert rejected == "来源冲突未同时引用冲突双方，已拒绝展示。"


def test_sse_event_uses_complete_json_frame() -> None:
    frame = sse_event(
        "token",
        {"text": "分片\n内容", "created_at": datetime(2026, 9, 18, tzinfo=UTC)},
    )

    assert frame.startswith("event: token\ndata: ")
    assert frame.endswith("\n\n")
    payload = json.loads(frame.split("data: ", 1)[1])
    assert payload == {"text": "分片\n内容", "created_at": "2026-09-18 00:00:00+00:00"}


def test_create_generation_run_persists_user_assistant_and_release_snapshot() -> None:
    connection = FakeRunConnection()
    request_id = UUID("11111111-1111-4111-8111-111111111111")
    conversation = {
        "id": 13,
        "tenant_id": 7,
        "knowledge_base_id": 9,
        "active_release_id": 5,
        "title": "新会话",
    }

    result = asyncio.run(
        _create_generation_run(
            connection,  # type: ignore[arg-type]
            conversation=conversation,  # type: ignore[arg-type]
            user_id=3,
            request_id=request_id,
            question="如何办理出院？",
        )
    )

    assert result["id"] == "41"
    assert len(connection.fetchval_calls) == 2
    assert not any("INSERT INTO generation_runs" in call[0] for call in connection.execute_calls)
    assert any("UPDATE conversations" in call[0] for call in connection.execute_calls)


def test_create_generation_run_reuses_same_request_without_duplicate_messages() -> None:
    existing = {
        "id": "41",
        "tenant_id": "7",
        "knowledge_base_id": "9",
        "conversation_id": "13",
        "user_message_id": "21",
        "assistant_message_id": "22",
        "release_id": "5",
        "request_id": "11111111-1111-4111-8111-111111111111",
        "state": "queued",
        "outcome": None,
        "cancel_requested": False,
        "error": None,
        "created_at": "2026-09-18T00:00:00Z",
        "updated_at": "2026-09-18T00:00:00Z",
    }
    connection = FakeRunConnection(existing=existing)

    result = asyncio.run(
        _create_generation_run(
            connection,  # type: ignore[arg-type]
            conversation={
                "id": 13,
                "tenant_id": 7,
                "knowledge_base_id": 9,
                "active_release_id": 5,
                "title": "新会话",
            },  # type: ignore[arg-type]
            user_id=3,
            request_id=UUID("11111111-1111-4111-8111-111111111111"),
            question="如何办理出院？",
        )
    )

    assert result == existing
    assert connection.fetchval_calls == []
    assert connection.execute_calls == []


def test_history_answer_is_hidden_when_evidence_source_is_disabled() -> None:
    connection = FakeSnapshotConnection(
        {
            "id": "41",
            "tenant_id": "7",
            "knowledge_base_id": "9",
            "conversation_id": "13",
            "user_message_id": "21",
            "assistant_message_id": "22",
            "release_id": "5",
            "request_id": "11111111-1111-4111-8111-111111111111",
            "state": "completed",
            "outcome": "answered",
            "cancel_requested": False,
            "error": None,
            "created_at": "2026-09-18T00:00:00Z",
            "updated_at": "2026-09-18T00:00:01Z",
            "completed_at": "2026-09-18T00:00:01Z",
            "question": "如何办理出院？",
            "answer": "持通知单办理。[证据 1]",
            "message_state": "complete",
            "has_invalid_evidence": True,
        }
    )

    snapshot = asyncio.run(
        load_run_snapshot(connection, run_id=41, user_id=3)  # type: ignore[arg-type]
    )

    assert snapshot is not None
    assert snapshot["hidden"] is True
    assert snapshot["answer"] == ""
    assert snapshot["message_state"] == "hidden"
    assert snapshot["citations"] == []
    assert connection.fetch_calls == 0


def test_create_run_endpoint_checks_conversation_access_and_is_idempotent(monkeypatch: Any) -> None:
    connection = FakeEndpointConnection()
    context = {"user": {"id": "3"}}
    conversation = {
        "id": 13,
        "tenant_id": 7,
        "knowledge_base_id": 9,
        "active_release_id": 5,
        "title": "新会话",
    }
    expected = {"id": "41", "state": "queued", "request_id": "request"}
    access = AsyncMock(return_value=conversation)
    create_run = AsyncMock(return_value=expected)
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=context))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr("app.main._conversation_access", access)
    monkeypatch.setattr("app.main._create_generation_run", create_run)

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/conversations/13/runs",
            json={
                "question": "如何办理出院？",
                "request_id": "11111111-1111-4111-8111-111111111111",
            },
        )

    assert response.status_code == 202
    assert response.json()["id"] == "41"
    access.assert_awaited_once()
    create_run.assert_awaited_once()
    assert connection.closed


def test_cancel_run_closes_message_and_active_retrieval_trace(monkeypatch: Any) -> None:
    connection = FakeEndpointConnection()
    running = {
        "id": "41",
        "tenant_id": "7",
        "assistant_message_id": "22",
        "state": "running",
    }
    cancelled = {**running, "state": "cancelled", "cancel_requested": True}
    snapshot_loader = AsyncMock(side_effect=[running, cancelled])
    monkeypatch.setattr(
        "app.main._authenticated_user", AsyncMock(return_value={"user": {"id": "3"}})
    )
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr("app.main.load_run_snapshot", snapshot_loader)

    with TestClient(create_app(Settings())) as client:
        response = client.post("/api/v1/runs/41/cancel")

    assert response.status_code == 200
    assert response.json()["state"] == "cancelled"
    assert any("UPDATE retrieval_traces" in call[0] for call in connection.execute_calls)
    assert any("UPDATE generation_runs" in call[0] for call in connection.execute_calls)
    assert any("UPDATE messages" in call[0] for call in connection.execute_calls)


def test_retry_run_reuses_original_question_and_user_message(monkeypatch: Any) -> None:
    connection = FakeEndpointConnection()
    cancelled = {
        "id": "41",
        "tenant_id": "7",
        "conversation_id": "13",
        "user_message_id": "21",
        "assistant_message_id": "22",
        "state": "cancelled",
        "question": "如何办理出院？",
    }
    conversation = {
        "id": 13,
        "tenant_id": 7,
        "knowledge_base_id": 9,
        "active_release_id": 5,
        "title": "出院办理",
    }
    create_run = AsyncMock(return_value={**cancelled, "id": "42", "state": "queued"})
    monkeypatch.setattr(
        "app.main._authenticated_user", AsyncMock(return_value={"user": {"id": "3"}})
    )
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr("app.main.load_run_snapshot", AsyncMock(return_value=cancelled))
    monkeypatch.setattr("app.main._conversation_access", AsyncMock(return_value=conversation))
    monkeypatch.setattr("app.main._create_generation_run", create_run)

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/runs/41/retry",
            json={"request_id": "22222222-2222-4222-8222-222222222222"},
        )

    assert response.status_code == 202
    assert response.json()["id"] == "42"
    create_run.assert_awaited_once()
    assert create_run.await_args.kwargs["question"] == "如何办理出院？"
    assert create_run.await_args.kwargs["user_message_id"] == 21


def test_stream_disconnect_marks_run_and_trace_failed(monkeypatch: Any) -> None:
    connection = FakeStreamConnection()
    snapshot = {
        "id": "41",
        "tenant_id": "7",
        "state": "queued",
        "question": "如何办理出院？",
    }
    mark_failed = AsyncMock()
    monkeypatch.setattr("app.rag.chat.asyncpg.connect", AsyncMock(return_value=connection))
    monkeypatch.setattr("app.rag.chat.load_run_snapshot", AsyncMock(return_value=snapshot))
    monkeypatch.setattr(
        "app.rag.chat.execute_vector_search",
        AsyncMock(side_effect=asyncio.CancelledError()),
    )
    monkeypatch.setattr("app.rag.chat._mark_failed", mark_failed)

    async def consume() -> str:
        events = stream_generation_run(
            Settings(database_url="postgresql://test"),
            run_id=41,
            user_id=3,
        )
        first = await anext(events)
        with pytest.raises(asyncio.CancelledError):
            await anext(events)
        return first

    first = asyncio.run(consume())

    assert first.startswith("event: meta")
    mark_failed.assert_awaited_once()
    assert mark_failed.await_args.kwargs["code"] == "STREAM_DISCONNECTED"
    assert connection.closed
