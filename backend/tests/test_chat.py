"""问答运行、恢复、取消、引用和 API Key 归属的回归测试。"""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.core.config import Settings
from app.main import _api_key_route_allowed, _create_generation_run, create_app
from app.rag.chat import (
    NO_ANSWER_TEXT,
    _combined_usage,
    _persist_completed_answer,
    aggregate_embedding_usage,
    classify_assistant_question,
    execute_assistant_scope_search,
    load_run_snapshot,
    sse_event,
    stream_generation_run,
    validate_generated_answer,
)
from app.rag.retrieval import RetrievalServiceError


class FakeTransaction:
    """为问答持久化测试提供无副作用的异步事务边界。"""

    async def __aenter__(self) -> None:
        """进入无副作用事务。"""
        return None

    async def __aexit__(self, *args: object) -> None:
        """退出事务且不屏蔽测试异常。"""
        return None


class FakeRunConnection:
    """模拟运行幂等查询、消息创建和运行创建结果。"""

    def __init__(self, *, existing: dict[str, object] | None = None) -> None:
        """配置可选的既有运行，用于幂等和冲突分支。"""
        self.existing = existing
        self.fetchval_calls: list[tuple[Any, ...]] = []
        self.execute_calls: list[tuple[Any, ...]] = []

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        """按运行查询或创建 SQL 返回预设快照。"""
        if "FROM generation_runs" in query:
            if (
                "WHERE api_key_id = $1" in query
                and self.existing is not None
                and str(self.existing.get("api_key_id")) != str(args[0])
            ):
                return None
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
        """按消息角色返回稳定的用户/助手消息 ID。"""
        self.fetchval_calls.append((query, *args))
        return 21 if "'user'" in query else 22

    async def execute(self, query: str, *args: object) -> None:
        """记录 advisory lock 和会话标题更新。"""
        self.execute_calls.append((query, *args))


class FakeEndpointConnection:
    """记录接口级数据库写入，并支持取消操作的原子状态领取。"""

    def __init__(self) -> None:
        """初始化接口写入、关闭和原子领取记录。"""
        self.closed = False
        self.execute_calls: list[tuple[Any, ...]] = []
        self.fetchval_calls: list[tuple[Any, ...]] = []

    def transaction(self) -> FakeTransaction:
        """返回取消接口使用的异步事务边界。"""
        return FakeTransaction()

    async def execute(self, query: str, *args: object) -> None:
        """记录消息、trace 等接口副作用。"""
        self.execute_calls.append((query, *args))

    async def fetchval(self, query: str, *args: object) -> int:
        """模拟取消接口原子领取状态更新。"""
        self.fetchval_calls.append((query, *args))
        return 41

    async def close(self) -> None:
        """标记接口 finally 已关闭连接。"""
        self.closed = True


class FakeSnapshotConnection:
    """返回固定运行快照，并记录 bigint 归一化后的查询参数。"""

    def __init__(self, row: dict[str, object]) -> None:
        """保存固定运行快照及查询观测字段。"""
        self.row = row
        self.fetch_calls = 0
        self.fetchrow_args: tuple[object, ...] = ()

    async def fetchrow(self, query: str, *args: object) -> dict[str, object]:
        """记录归一化后的查询参数并返回快照。"""
        self.fetchrow_args = args
        return self.row

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        """模拟没有可展示引用的运行。"""
        self.fetch_calls += 1
        return []


class FakeStreamConnection:
    """提供流式问答成功领取运行所需的最小数据库行为。"""

    def __init__(self) -> None:
        """初始化流式连接关闭状态与写入记录。"""
        self.closed = False
        self.execute_calls: list[tuple[Any, ...]] = []

    async def fetchrow(self, query: str, *args: object) -> dict[str, object]:
        """返回原子领取后的运行执行字段。"""
        return {
            "id": 41,
            "tenant_id": 7,
            "knowledge_base_id": 9,
            "conversation_id": 13,
            "user_message_id": 21,
            "assistant_message_id": 22,
            "release_id": 5,
            "request_id": "11111111-1111-4111-8111-111111111111",
        }

    async def execute(self, query: str, *args: object) -> None:
        """记录流式状态和用量快照写入。"""
        self.execute_calls.append((query, *args))

    async def close(self) -> None:
        """标记流结束后连接已释放。"""
        self.closed = True


class FakeAlreadyRunningConnection(FakeStreamConnection):
    """模拟另一个 SSE 连接已经原子领取运行执行权。"""

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        """让 queued 原子领取失败，并允许读取 running 快照。"""
        if "state = 'queued'" in query:
            return None
        if "state = 'running'" in query:
            return await super().fetchrow(query, *args)
        return None


class FakeCancelledAfterRetrievalConnection(FakeStreamConnection):
    """模拟检索结束时取消已提交，生成模型不应再被调用。"""

    async def fetchval(self, query: str, *args: object) -> bool:
        """在检索后取消检查中返回已取消。"""
        assert "cancel_requested" in query
        return True


class FakeAssistantStreamConnection(FakeStreamConnection):
    """为助理普通对话流提供独立范围所需的最小数据库响应。"""

    def transaction(self) -> FakeTransaction:
        """提供最终回答持久化使用的无副作用事务。"""
        return FakeTransaction()

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        """只领取运行快照；助理会话没有固定知识库 Runtime Profile。"""
        if "UPDATE generation_runs SET state = 'running'" in query:
            return await super().fetchrow(query, *args)
        if "SELECT rp.definition" in query:
            return None
        raise AssertionError(f"未处理的 fetchrow 查询：{query}")

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        """该测试的新会话没有历史消息。"""
        assert "FROM messages" in query
        return []

    async def fetchval(self, query: str, *args: object) -> int | bool:
        """依次模拟未取消的运行和最终成功领取。"""
        if "cancel_requested = false" in query:
            return 41
        if "cancel_requested" in query:
            return False
        raise AssertionError(f"未处理的 fetchval 查询：{query}")


class FakeCompletionConnection:
    """控制最终状态领取结果，用于验证取消与完成并发时不覆盖数据。"""

    def __init__(self, completed_run_id: int | None) -> None:
        """配置最终完成权是否已被取消路径抢占。"""
        self.completed_run_id = completed_run_id
        self.execute_calls: list[tuple[Any, ...]] = []

    def transaction(self) -> FakeTransaction:
        """返回最终答案持久化使用的事务边界。"""
        return FakeTransaction()

    async def fetchval(self, query: str, *args: object) -> int | None:
        """返回原子完成权领取结果。"""
        assert "cancel_requested = false" in query
        return self.completed_run_id

    async def execute(self, query: str, *args: object) -> None:
        """记录仅在领取完成权后允许发生的消息与引用写入。"""
        self.execute_calls.append((query, *args))


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


def test_generated_scope_refusal_with_citations_is_refused() -> None:
    """模型明确说明资料未覆盖问题时，不能因附带引用而伪装成已回答。"""
    content, citations, outcome = validate_generated_answer(
        "规范没有直接规定 2026 年某省平台的接口字段，无法据此回答。[证据 1]",
        {1},
    )

    assert outcome == "no_answer"
    assert citations == []
    assert content == NO_ANSWER_TEXT


def test_generated_scope_refusal_without_direct_phrase_is_refused() -> None:
    """模型以“没有找到该规范的依据”解释范围边界时，也必须进入拒答终态。"""
    content, citations, outcome = validate_generated_answer(
        "没有找到该规范直接规定 2026 年某省平台接口字段的依据。[证据 1]",
        {1},
    )

    assert outcome == "no_answer"
    assert citations == []
    assert content == NO_ANSWER_TEXT


def test_partial_uncertainty_with_supported_conclusion_remains_answered() -> None:
    """回答包含局部否定但仍给出证据支持的结论时，不能被范围拒答规则吞掉。"""
    content, citations, outcome = validate_generated_answer(
        "规范没有规定地方收费标准，但明确要求每年开展 9 次咨询活动。[证据 1]",
        {1},
    )

    assert outcome == "answered"
    assert citations == [1]
    assert "9 次" in content


def test_grounded_generation_streams_only_validated_final_answer(monkeypatch: Any) -> None:
    """拒答归一后不能让流式客户端先收到模型原文和已删除的引用。"""
    connection = FakeAssistantStreamConnection()
    queued = {
        "id": "41",
        "tenant_id": "7",
        "knowledge_base_id": "9",
        "conversation_id": "13",
        "active_release_id": "5",
        "state": "queued",
        "question": "某项规定是否适用？",
    }
    completed = {**queued, "state": "completed", "answer": NO_ANSWER_TEXT}
    retrieval = {
        "state": "completed",
        "trace_id": "trace-1",
        "trace_ids": ["trace-1"],
        "items": [
            {
                "evidence_no": 1,
                "context_included": True,
                "document_id": 7,
                "document_version_id": 8,
                "chunk_id": 9,
                "locator": {"page": 1},
            }
        ],
        "context": "无关背景证据",
        "knowledge_base_count": 1,
        "mode": "knowledge_base",
    }

    class GroundedClient:
        """生成包含带引用拒答原文的测试模型。"""

        class ClientSettings:
            generation_model = "test-model"
            generation_max_tokens = 64

        def __init__(self, settings: Settings) -> None:
            """提供与正式网关一致的设置属性。"""
            self.settings = self.ClientSettings()

        async def stream_chat_events(
            self,
            messages: list[dict[str, str]],
            *,
            temperature: float,
            max_tokens: int | None = None,
        ) -> Any:
            """先产生未校验的拒答正文，再给出网关用量尾帧。"""
            yield {
                "text": "规范没有直接规定某项规则，无法据此回答。[证据 1]",
                "usage": None,
            }
            yield {
                "text": "",
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 8,
                    "total_tokens": 18,
                },
            }

    monkeypatch.setattr("app.rag.chat.asyncpg.connect", AsyncMock(return_value=connection))
    monkeypatch.setattr(
        "app.rag.chat.load_run_snapshot", AsyncMock(side_effect=[queued, completed])
    )
    monkeypatch.setattr("app.rag.chat.ModelGatewayClient", GroundedClient)
    monkeypatch.setattr("app.rag.chat.execute_vector_search", AsyncMock(return_value=retrieval))
    monkeypatch.setattr("app.rag.chat._persist_completed_answer", AsyncMock(return_value=True))

    async def collect() -> list[str]:
        return [
            event
            async for event in stream_generation_run(
                Settings(database_url="postgresql://test"), run_id=41, user_id=3
            )
        ]

    events = asyncio.run(collect())
    tokens = [
        json.loads(event.split("data: ", 1)[1])["text"]
        for event in events
        if event.startswith("event: token")
    ]

    assert tokens == [NO_ANSWER_TEXT]


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


def test_assistant_scope_search_merges_evidence_with_knowledge_base_names(
    monkeypatch: Any,
) -> None:
    """跨库助理必须合并证据并在来源中保留知识库归属。"""
    connection = AsyncMock()
    connection.fetch = AsyncMock(
        return_value=[
            {
                "id": 9,
                "name": "制度库",
                "active_release_id": 19,
                "runtime_definition": {"retrieval": {"top_k": 5}},
            },
            {
                "id": 10,
                "name": "产品库",
                "active_release_id": 20,
                "runtime_definition": None,
            },
        ]
    )
    search_results = [
        {
            "state": "completed",
            "trace_id": "31",
            "items": [
                {
                    "chunk_id": "101",
                    "content": "制度证据内容",
                    "document_title": "员工手册.md",
                    "version_no": 2,
                    "section_path": ["请假"],
                    "locator": {"page": 2},
                    "fused_score": 0.04,
                }
            ],
        },
        {
            "state": "completed",
            "trace_id": "32",
            "items": [
                {
                    "chunk_id": "102",
                    "content": "产品证据内容",
                    "document_title": "功能说明.md",
                    "version_no": 1,
                    "section_path": ["账号"],
                    "locator": {"page": 4},
                    "fused_score": 0.03,
                }
            ],
        },
    ]
    usage_operations: list[tuple[str, str]] = []

    async def fake_search(*args: Any, **kwargs: Any) -> dict[str, Any]:
        """为每个知识库报告估算和实测用量，并返回对应检索结果。"""
        callback = kwargs["on_embedding_usage"]
        if callback is not None:
            await callback(
                {"prompt_tokens": 20, "completion_tokens": 0, "total_tokens": 20},
                "shared-embedding",
            )
            await callback(
                {
                    "prompt_tokens": 5,
                    "completion_tokens": 0,
                    "total_tokens": 5,
                    "usage_source": "gateway",
                },
                "shared-embedding",
            )
            usage_operations.append((str(kwargs["knowledge_base_id"]), "gateway"))
        return search_results.pop(0)

    searches = AsyncMock(side_effect=fake_search)

    async def record_usage(
        usage: Any,
        model_name: str,
        operation_id: str,
    ) -> None:
        """记录跨库回调传来的用量归属。"""
        usage_operations.append(
            (operation_id, str(usage.get("usage_source", "estimate")))
        )
    monkeypatch.setattr("app.rag.chat.execute_vector_search", searches)

    result = asyncio.run(
        execute_assistant_scope_search(
            connection,  # type: ignore[arg-type]
            Settings(),
            tenant_id=7,
            user_id=3,
            query="如何申请请假？",
            message_id=22,
            on_embedding_usage=record_usage,
        )
    )

    assert result["state"] == "completed"
    assert result["knowledge_base_count"] == 2
    assert result["trace_ids"] == ["31", "32"]
    assert [item["evidence_no"] for item in result["items"]] == [1, 2]
    assert "制度库 · 员工手册.md" in result["context"]
    assert "产品库 · 功能说明.md" in result["context"]
    assert [call.kwargs["knowledge_base_id"] for call in searches.await_args_list] == [9, 10]
    assert usage_operations == [
        ("9", "estimate"),
        ("9", "gateway"),
        ("9", "gateway"),
        ("10", "estimate"),
        ("10", "gateway"),
        ("10", "gateway"),
    ]


def test_embedding_usage_sums_each_knowledge_base_and_keeps_legacy_shape() -> None:
    """跨库运行按实际调用合计嵌入 Token，单模型审计字段兼容旧格式。"""
    breakdown = aggregate_embedding_usage(
        {
            "9": {
                "shared-embedding": {
                    "prompt_tokens": 6,
                    "completion_tokens": 0,
                    "total_tokens": 6,
                    "usage_source": "gateway",
                }
            },
            "10": {
                "shared-embedding": {
                    "prompt_tokens": 4,
                    "completion_tokens": 0,
                    "total_tokens": 4,
                    "usage_source": "gateway",
                }
            },
        }
    )
    usage, model_usage, model_names = _combined_usage(
        embedding_usage=None,
        embedding_model=None,
        embedding_breakdown=breakdown,
        generation_usage=None,
        generation_model=None,
    )

    assert usage["prompt_tokens"] == 10
    assert usage["total_tokens"] == 10
    assert model_usage["embedding"]["model"] == "shared-embedding"
    assert model_names == "shared-embedding"


def test_assistant_question_classifier_falls_back_to_search_on_invalid_json() -> None:
    """分类模型输出异常时仍检索知识库，避免事实问题被普通回答绕过。"""

    class InvalidRouterClient:
        """为路由降级测试返回不可解析结果。"""

        class SettingsValue:
            generation_model = "router-model"

        settings = SettingsValue()

        async def complete_chat(
            self,
            messages: list[dict[str, str]],
            *,
            temperature: float,
            max_tokens: int,
        ) -> dict[str, Any]:
            """返回无效 JSON，模拟网关模型未遵守路由协议。"""
            assert temperature == 0
            assert max_tokens == 96
            return {
                "content": "无法判断",
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                    "usage_source": "gateway",
                },
            }

    result = asyncio.run(
        classify_assistant_question(
            InvalidRouterClient(),  # type: ignore[arg-type]
            question="我们的年假规定是什么？",
            history=[],
        )
    )

    assert result["retrieve"] is True
    assert result["query"] == "我们的年假规定是什么？"


def test_assistant_general_question_skips_knowledge_base_retrieval(monkeypatch: Any) -> None:
    """路由判定为一般交流时直接回答，并且不触发单库或跨库检索。"""
    connection = FakeAssistantStreamConnection()
    queued = {
        "id": "41",
        "tenant_id": "7",
        "conversation_id": "13",
        "conversation_scope": "assistant",
        "state": "queued",
        "question": "你好",
    }
    completed = {**queued, "state": "completed", "answer": "你好，有什么可以帮你？"}
    build_messages: list[list[dict[str, str]]] = []

    class GeneralAssistantClient:
        """返回闲聊分类，并提供最终流式回答。"""

        class ClientSettings:
            generation_model = "assistant-model"
            generation_max_tokens = 64

        def __init__(self, settings: Settings) -> None:
            """保留与真实网关客户端一致的构造签名。"""
            self.settings = self.ClientSettings()

        async def complete_chat(
            self,
            messages: list[dict[str, str]],
            *,
            temperature: float,
            max_tokens: int,
        ) -> dict[str, Any]:
            """把问候分类为无需检索，并返回路由调用用量。"""
            return {
                "content": '{"retrieve": false, "query": ""}',
                "usage": {
                    "prompt_tokens": 2,
                    "completion_tokens": 2,
                    "total_tokens": 4,
                    "usage_source": "gateway",
                },
            }

        async def stream_chat_events(
            self,
            messages: list[dict[str, str]],
            *,
            temperature: float,
            max_tokens: int | None = None,
        ) -> Any:
            """记录最终生成上下文，并返回一段可结算的流。"""
            assert max_tokens == 64
            build_messages.append(messages)
            yield {"text": "你好，有什么可以帮你？", "usage": None}
            yield {
                "text": "",
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 9,
                    "total_tokens": 21,
                },
            }

    no_retrieval = AsyncMock(side_effect=AssertionError("闲聊不应检索知识库"))
    settlement = AsyncMock(return_value=True)
    monkeypatch.setattr("app.rag.chat.asyncpg.connect", AsyncMock(return_value=connection))
    monkeypatch.setattr(
        "app.rag.chat.load_run_snapshot", AsyncMock(side_effect=[queued, completed])
    )
    monkeypatch.setattr("app.rag.chat.ModelGatewayClient", GeneralAssistantClient)
    monkeypatch.setattr("app.rag.chat.execute_vector_search", no_retrieval)
    monkeypatch.setattr("app.rag.chat.execute_assistant_scope_search", no_retrieval)
    monkeypatch.setattr("app.rag.chat.reserve_api_key_tokens", AsyncMock(return_value=64))
    monkeypatch.setattr("app.rag.chat.update_api_key_reservation_usage", AsyncMock())
    monkeypatch.setattr("app.rag.chat.settle_api_key_usage", settlement)

    async def collect() -> list[str]:
        return [
            event
            async for event in stream_generation_run(
                Settings(database_url="postgresql://test"),
                run_id=41,
                user_id=3,
                api_key_id="8",
                api_key_tenant_id=7,
            )
        ]

    events = asyncio.run(collect())

    no_retrieval.assert_not_awaited()
    assert any('"mode": "general"' in event for event in events)
    assert any(event.startswith("event: token") for event in events)
    assert build_messages[0][-1] == {"role": "user", "content": "你好"}
    settlement.assert_awaited_once()
    assert settlement.await_args.kwargs["usage"]["total_tokens"] == 25
    assert connection.closed


def test_assistant_conversation_creation_is_separate_from_knowledge_base_route(
    monkeypatch: Any,
) -> None:
    """助理创建使用独立路由且写入空知识库 ID，旧路由契约仍要求单库 ID。"""
    connection = AsyncMock()
    connection.fetchrow = AsyncMock(
        return_value={
            "id": "11111111-1111-4111-8111-111111111111",
            "tenant_id": "7",
            "scope": "auto",
            "title": "制度咨询",
            "status": "active",
        }
    )
    connection.close = AsyncMock()
    monkeypatch.setattr(
        "app.main._authenticated_user",
        AsyncMock(
            return_value={
                "user": {"id": "3"},
                "api_key_id": "8",
                "api_key_tenant_id": "7",
            }
        ),
    )
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))

    with TestClient(create_app(Settings())) as client:
        assistant_response = client.post(
            "/api/v1/assistant/conversations",
            json={"title": "制度咨询"},
        )
        legacy_response = client.post(
            "/api/v1/conversations",
            json={"title": "传统会话"},
        )

    assert assistant_response.status_code == 201
    assert assistant_response.json()["scope"] == "auto"
    insert_query, *insert_args = connection.fetchrow.await_args.args
    assert "knowledge_base_id, scope" in insert_query
    assert "VALUES ($1, NULL, 'assistant', $2, $3)" in insert_query
    assert insert_args == [7, 3, "制度咨询"]
    assert legacy_response.status_code == 422
    assert connection.close.await_count == 1


def test_api_key_allowlist_keeps_legacy_chat_and_allows_assistant_routes() -> None:
    """公司 API Key 同时保留旧单库问答并可调用新自动范围助理接口。"""

    def make_request(path: str, method: str) -> Request:
        """构造仅含路由判断所需字段的 ASGI 请求。"""
        return Request(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "method": method,
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "headers": [],
                "server": ("test", 80),
                "client": ("test", 1),
            }
        )

    assert _api_key_route_allowed(make_request("/api/v1/conversations", "POST"))
    assert _api_key_route_allowed(make_request("/api/v1/assistant/conversations", "GET"))
    assert _api_key_route_allowed(
        make_request("/api/v1/assistant/conversations/abc/runs", "POST")
    )
    assert _api_key_route_allowed(
        make_request("/api/v1/assistant/conversations/abc", "DELETE")
    )
    assert not _api_key_route_allowed(
        make_request("/api/v1/assistant/conversations/abc", "PATCH")
    )


def test_assistant_run_submission_uses_key_scope_without_knowledge_base_id(
    monkeypatch: Any,
) -> None:
    """助理提问只传问题和幂等 ID，运行会话范围来自新接口及当前 API Key。"""
    connection = AsyncMock()
    connection.fetchrow = AsyncMock(
        return_value={
            "id": 13,
            "tenant_id": 7,
            "knowledge_base_id": None,
            "owner_user_id": 3,
            "title": "制度咨询",
            "status": "active",
            "scope": "assistant",
            "knowledge_base_name": None,
            "active_release_id": None,
            "active_runtime_id": None,
        }
    )
    connection.transaction = lambda: FakeTransaction()
    connection.close = AsyncMock()
    run = AsyncMock(return_value={"id": "41", "state": "queued"})
    monkeypatch.setattr(
        "app.main._authenticated_user",
        AsyncMock(
            return_value={
                "user": {"id": "3"},
                "api_key_id": "8",
                "api_key_tenant_id": "7",
            }
        ),
    )
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr("app.main._create_generation_run", run)

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/assistant/conversations/11111111-1111-4111-8111-111111111111/runs",
            json={
                "question": "公司的年假政策是什么？",
                "request_id": "22222222-2222-4222-8222-222222222222",
            },
        )

    assert response.status_code == 202
    assert response.json()["state"] == "queued"
    assert run.await_args.kwargs["conversation"]["scope"] == "assistant"
    assert run.await_args.kwargs["conversation"]["knowledge_base_id"] is None
    assert run.await_args.kwargs["api_key_id"] == "8"
    assert run.await_args.kwargs["question"] == "公司的年假政策是什么？"
    assert connection.close.await_count == 1


def test_assistant_history_hides_run_content_owned_by_another_api_key(
    monkeypatch: Any,
) -> None:
    """运行快照拒绝当前 Key 时，历史接口不得退回读取数据库中的答案正文。"""
    connection = AsyncMock()
    connection.fetchrow = AsyncMock(
        return_value={
            "id": 13,
            "tenant_id": "7",
            "scope": "assistant",
            "title": "制度咨询",
            "status": "active",
            "created_at": "2026-10-01T00:00:00Z",
            "updated_at": "2026-10-01T00:00:00Z",
        }
    )
    connection.fetch = AsyncMock(
        return_value=[
            {
                "id": "22",
                "role": "assistant",
                "content": "不得透出的旧答案",
                "state": "complete",
                "created_at": "2026-10-01T00:00:00Z",
                "run_id": "41",
            }
        ]
    )
    connection.close = AsyncMock()
    monkeypatch.setattr(
        "app.main._authenticated_user",
        AsyncMock(
            return_value={
                "user": {"id": "3"},
                "api_key_id": "9",
                "api_key_tenant_id": "7",
            }
        ),
    )
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr("app.main.load_run_snapshot", AsyncMock(return_value=None))

    with TestClient(create_app(Settings())) as client:
        response = client.get(
            "/api/v1/assistant/conversations/11111111-1111-4111-8111-111111111111"
        )

    assert response.status_code == 200
    message = response.json()["messages"][0]
    assert message["content"] == ""
    assert message["hidden"] is True
    assert message["state"] == "hidden"
    assert connection.close.await_count == 1


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


def test_idempotent_run_cannot_be_reused_by_another_api_key() -> None:
    """同一 request_id 已绑定其他 Key 时必须拒绝，避免把后续用量记到错误账户。"""
    existing = {
        "id": "41",
        "tenant_id": "7",
        "conversation_id": "13",
        "api_key_id": "8",
    }
    connection = FakeRunConnection(existing=existing)

    with pytest.raises(HTTPException) as raised:
        asyncio.run(
            _create_generation_run(
                connection,  # type: ignore[arg-type]
                conversation={"id": 13, "tenant_id": 7},  # type: ignore[arg-type]
                user_id=3,
                request_id=UUID("11111111-1111-4111-8111-111111111111"),
                question="如何办理出院？",
                api_key_id="9",
            )
        )

    assert raised.value.status_code == 409


def test_api_key_request_id_cannot_be_reused_in_another_conversation() -> None:
    """同一 Key 的 request_id 跨会话仍是同一次计费请求，必须返回冲突。"""
    existing = {
        "id": "41",
        "tenant_id": "7",
        "conversation_id": "12",
        "api_key_id": "9",
    }
    connection = FakeRunConnection(existing=existing)

    with pytest.raises(HTTPException) as raised:
        asyncio.run(
            _create_generation_run(
                connection,  # type: ignore[arg-type]
                conversation={"id": 13, "tenant_id": 7},  # type: ignore[arg-type]
                user_id=3,
                request_id=UUID("11111111-1111-4111-8111-111111111111"),
                question="如何办理出院？",
                api_key_id="9",
            )
        )

    assert raised.value.status_code == 409
    assert "其他会话" in str(raised.value.detail)


def test_native_api_key_run_obeys_shared_concurrency_limit() -> None:
    """原生问答入口与兼容入口共用 Key 并发限制，防止客户通过其他路由绕过上限。"""
    connection = FakeRunConnection()
    active_count = AsyncMock(return_value=5)
    connection.fetchval = active_count  # type: ignore[method-assign]
    connection.fetchrow = AsyncMock(return_value=None)  # type: ignore[method-assign]
    conversation = {
        "id": 13,
        "tenant_id": 7,
        "knowledge_base_id": 9,
        "active_release_id": 5,
        "title": "已有会话",
    }

    with pytest.raises(HTTPException) as raised:
        asyncio.run(
            _create_generation_run(
                connection,  # type: ignore[arg-type]
                conversation=conversation,  # type: ignore[arg-type]
                user_id=3,
                request_id=UUID("11111111-1111-4111-8111-111111111111"),
                question="如何办理出院？",
                api_key_id="8",
            )
        )

    assert raised.value.status_code == 429
    assert "并发问答数" in str(raised.value.detail)
    active_count.assert_awaited_once()


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


def test_api_key_snapshot_converts_identity_ids_to_database_integers() -> None:
    """HTTP 鉴权上下文使用字符串 ID 时，运行查询仍必须绑定 PostgreSQL bigint。"""
    connection = FakeSnapshotConnection(
        {
            "id": "41",
            "tenant_id": "7",
            "knowledge_base_id": "9",
            "conversation_id": "13",
            "user_message_id": "21",
            "assistant_message_id": "22",
            "release_id": "5",
            "api_key_id": "8",
            "request_id": "11111111-1111-4111-8111-111111111111",
            "state": "failed",
            "outcome": None,
            "cancel_requested": False,
            "error": '{"code":"FAIL"}',
            "created_at": "2026-09-18T00:00:00Z",
            "updated_at": "2026-09-18T00:00:01Z",
            "completed_at": "2026-09-18T00:00:01Z",
            "question": "问题",
            "answer": "",
            "message_state": "failed",
            "usage": "{}",
            "has_invalid_evidence": False,
        }
    )

    snapshot = asyncio.run(
        load_run_snapshot(
            connection,  # type: ignore[arg-type]
            run_id=41,
            user_id=3,
            api_key_tenant_id="7",
            api_key_id="8",
        )
    )

    assert snapshot is not None
    assert connection.fetchrow_args == (41, 3, 7, 8)


def test_create_run_endpoint_checks_conversation_access_and_is_idempotent(monkeypatch: Any) -> None:
    """使用公开 UUID 访问会话，并确认授权后创建逻辑运行。"""
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
    monkeypatch.setattr("app.main._conversation_id_from_public", AsyncMock(return_value=13))
    monkeypatch.setattr("app.main._conversation_access", access)
    monkeypatch.setattr("app.main._create_generation_run", create_run)

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/conversations/11111111-1111-4111-8111-111111111111/runs",
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
    """公开运行 UUID 解析后，取消操作应关闭消息和活动检索 Trace。"""
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
    monkeypatch.setattr("app.main._run_id_from_public", AsyncMock(return_value=41))
    monkeypatch.setattr("app.main.load_run_snapshot", snapshot_loader)

    with TestClient(create_app(Settings())) as client:
        response = client.post("/api/v1/runs/11111111-1111-4111-8111-111111111111/cancel")

    assert response.status_code == 200
    assert response.json()["state"] == "cancelled"
    assert any("RETURNING id" in call[0] for call in connection.fetchval_calls)
    assert any("UPDATE retrieval_traces" in call[0] for call in connection.execute_calls)
    assert any("UPDATE messages" in call[0] for call in connection.execute_calls)


def test_retry_run_reuses_original_question_and_user_message(monkeypatch: Any) -> None:
    """公开运行 UUID 解析后，重试应复用原问题与用户消息记录。"""
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
    monkeypatch.setattr("app.main._run_id_from_public", AsyncMock(return_value=41))
    monkeypatch.setattr("app.main.load_run_snapshot", AsyncMock(return_value=cancelled))
    monkeypatch.setattr("app.main._conversation_access", AsyncMock(return_value=conversation))
    monkeypatch.setattr("app.main._create_generation_run", create_run)

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/runs/11111111-1111-4111-8111-111111111111/retry",
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


def test_second_event_stream_does_not_execute_running_job(monkeypatch: Any) -> None:
    """未抢到 queued 状态的并发 SSE 连接只能查看快照，不能再次调用模型。"""
    connection = FakeAlreadyRunningConnection()
    queued = {"id": "41", "tenant_id": "7", "state": "queued", "question": "问题"}
    running = {**queued, "state": "running"}
    search = AsyncMock(side_effect=AssertionError("不应重复执行检索"))
    monkeypatch.setattr("app.rag.chat.asyncpg.connect", AsyncMock(return_value=connection))
    monkeypatch.setattr("app.rag.chat.load_run_snapshot", AsyncMock(side_effect=[queued, running]))
    monkeypatch.setattr("app.rag.chat.execute_vector_search", search)

    async def collect() -> list[str]:
        return [
            event
            async for event in stream_generation_run(
                Settings(database_url="postgresql://test"), run_id=41, user_id=3
            )
        ]

    events = asyncio.run(collect())

    assert any("RUN_ALREADY_RUNNING" in event for event in events)
    search.assert_not_awaited()
    assert connection.closed


def test_cancelled_run_cannot_persist_completed_answer() -> None:
    """取消先取得终态后，迟到的生成结果不得覆盖消息正文或写入引用。"""
    connection = FakeCompletionConnection(completed_run_id=None)

    completed = asyncio.run(
        _persist_completed_answer(
            connection,  # type: ignore[arg-type]
            run_id=41,
            tenant_id=7,
            assistant_message_id=22,
            release_id=5,
            content="迟到答案 [证据 1]",
            outcome="answered",
            cited_numbers=[1],
            evidence=[
                {
                    "evidence_no": 1,
                    "context_included": True,
                    "chunk_id": 10,
                    "document_version_id": 11,
                }
            ],
            trace_id="trace-1",
            usage={"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        )
    )

    assert completed is False
    assert connection.execute_calls == []


def test_cancel_after_retrieval_skips_generation_and_settles_embedding(monkeypatch: Any) -> None:
    """检索期间收到取消时不启动生成，并把已发生的嵌入用量按取消状态结算。"""
    connection = FakeCancelledAfterRetrievalConnection()
    queued = {
        "id": "41",
        "tenant_id": "7",
        "state": "queued",
        "question": "如何办理出院？",
    }
    cancelled = {**queued, "state": "cancelled", "cancel_requested": True}
    retrieval = {
        "state": "completed",
        "trace_id": "trace-1",
        "items": [],
        "context": "证据内容",
        "embedding_usage": {
            "prompt_tokens": 6,
            "completion_tokens": 0,
            "total_tokens": 6,
            "usage_source": "gateway",
        },
        "embedding_model": "embed",
    }
    settlement = AsyncMock(return_value=True)
    build_messages = AsyncMock(side_effect=AssertionError("取消后不应构造生成提示词"))
    monkeypatch.setattr("app.rag.chat.asyncpg.connect", AsyncMock(return_value=connection))
    monkeypatch.setattr(
        "app.rag.chat.load_run_snapshot", AsyncMock(side_effect=[queued, cancelled])
    )
    monkeypatch.setattr("app.rag.chat.execute_vector_search", AsyncMock(return_value=retrieval))
    monkeypatch.setattr("app.rag.chat.reserve_api_key_tokens", AsyncMock(return_value=32))
    monkeypatch.setattr("app.rag.chat.settle_api_key_usage", settlement)
    monkeypatch.setattr("app.rag.chat.build_grounded_messages", build_messages)

    async def collect() -> list[str]:
        return [
            event
            async for event in stream_generation_run(
                Settings(database_url="postgresql://test"),
                run_id=41,
                user_id=3,
                api_key_id="9",
                api_key_tenant_id=7,
            )
        ]

    events = asyncio.run(collect())

    assert any(event.startswith("event: cancelled") for event in events)
    build_messages.assert_not_awaited()
    settlement.assert_awaited_once()
    assert settlement.await_args.kwargs["status"] == "cancelled"
    assert settlement.await_args.kwargs["usage"]["prompt_tokens"] == 6


def test_embedding_usage_is_settled_when_vector_search_fails(monkeypatch: Any) -> None:
    """嵌入已成功计费后，即使向量 SQL 失败也必须保留其输入 Token。"""
    connection = FakeStreamConnection()
    snapshot = {
        "id": "41",
        "tenant_id": "7",
        "state": "queued",
        "question": "如何办理出院？",
    }
    settlement = AsyncMock(return_value=True)

    async def fail_after_embedding(*args: object, **kwargs: object) -> dict[str, object]:
        observer = kwargs["on_embedding_usage"]
        await observer(
            {
                "prompt_tokens": 6,
                "completion_tokens": 0,
                "total_tokens": 6,
                "usage_source": "gateway",
            },
            "embed",
        )
        raise RetrievalServiceError("向量查询失败")

    monkeypatch.setattr("app.rag.chat.asyncpg.connect", AsyncMock(return_value=connection))
    monkeypatch.setattr("app.rag.chat.load_run_snapshot", AsyncMock(return_value=snapshot))
    monkeypatch.setattr("app.rag.chat.execute_vector_search", fail_after_embedding)
    monkeypatch.setattr("app.rag.chat.reserve_api_key_tokens", AsyncMock(return_value=32))
    monkeypatch.setattr("app.rag.chat.settle_api_key_usage", settlement)
    monkeypatch.setattr("app.rag.chat._mark_failed", AsyncMock())

    async def collect() -> list[str]:
        return [
            event
            async for event in stream_generation_run(
                Settings(database_url="postgresql://test"),
                run_id=41,
                user_id=3,
                api_key_id="9",
                api_key_tenant_id=7,
            )
        ]

    events = asyncio.run(collect())

    assert any("GENERATION_FAILED" in event for event in events)
    settlement.assert_awaited_once()
    assert settlement.await_args.kwargs["usage"]["prompt_tokens"] == 6
    assert settlement.await_args.kwargs["model_name"] == "embed"
