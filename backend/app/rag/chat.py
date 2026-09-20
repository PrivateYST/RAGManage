"""问答运行、SSE 事件、引用校验与历史授权。"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator, Sequence
from typing import Any

import asyncpg
import httpx

from app.core.config import Settings
from app.rag.models import ModelGatewayClient
from app.rag.profiles import gateway_settings
from app.rag.retrieval import RetrievalServiceError, execute_vector_search

CITATION_PATTERN = re.compile(r"\[证据\s*(\d+)\]")
MARKDOWN_URL_PATTERN = re.compile(r"\[([^\]]+)]\(https?://[^)]+\)", re.IGNORECASE)
RAW_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
SOURCE_CONFLICT_MARKER = "[[SOURCE_CONFLICT]]"
NO_ANSWER_TEXT = "当前已发布知识库中没有找到足够依据，暂时无法回答这个问题。"
INVALID_CITATION_TEXT = "生成结果没有提供可验证引用，已拒绝展示。"

logger = logging.getLogger(__name__)


def _json_value(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return value


def sse_event(event: str, payload: dict[str, Any]) -> str:
    """输出可被任意网络分片安全解析的标准 SSE 事件。"""
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


def build_grounded_messages(
    question: str,
    context: str,
    answer_rules: str = "",
) -> list[dict[str, str]]:
    system = (
        "你是公司知识库问答助手。只能使用给定证据回答，不得使用外部知识。"
        "每个事实结论都必须使用形如 [证据 1] 的编号引用。"
        "不得输出网址、文件链接或自行编造来源。"
        f"证据不足时只回答：{NO_ANSWER_TEXT}"
        "如果证据之间存在无法消解的冲突，请在回答开头输出 [[SOURCE_CONFLICT]]，"
        "说明冲突点，并引用冲突双方。"
    )
    if answer_rules.strip():
        system += f"\n当前知识库补充回答规则：{answer_rules.strip()}"
    user = f"问题：\n{question}\n\n可用证据：\n{context}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def validate_generated_answer(
    content: str,
    valid_evidence_numbers: set[int],
) -> tuple[str, list[int], str]:
    """删除模型来源 URL 和非法引用，并给出服务端可信的业务终态。"""
    conflict = SOURCE_CONFLICT_MARKER in content
    sanitized = content.replace(SOURCE_CONFLICT_MARKER, "").strip()
    sanitized = MARKDOWN_URL_PATTERN.sub(r"\1", sanitized)
    sanitized = RAW_URL_PATTERN.sub("", sanitized)
    cited: list[int] = []

    def replace_citation(match: re.Match[str]) -> str:
        evidence_no = int(match.group(1))
        if evidence_no not in valid_evidence_numbers:
            return ""
        if evidence_no not in cited:
            cited.append(evidence_no)
        return f"[证据 {evidence_no}]"

    sanitized = CITATION_PATTERN.sub(replace_citation, sanitized)
    sanitized = re.sub(r"[ \t]+\n", "\n", sanitized).strip()
    if conflict and len(cited) >= 2:
        if not sanitized:
            sanitized = "检索到的来源存在冲突，暂时无法给出唯一结论。"
        return sanitized, cited, "source_conflict"
    if conflict:
        return "来源冲突未同时引用冲突双方，已拒绝展示。", [], "no_answer"
    if sanitized == NO_ANSWER_TEXT or not sanitized:
        return NO_ANSWER_TEXT, [], "no_answer"
    if not cited:
        return INVALID_CITATION_TEXT, [], "no_answer"
    return sanitized, cited, "answered"


async def load_run_snapshot(
    connection: asyncpg.Connection,
    *,
    run_id: int,
    user_id: int,
) -> dict[str, Any] | None:
    row = await connection.fetchrow(
        """
        SELECT gr.id::text, gr.tenant_id::text, gr.knowledge_base_id::text,
               gr.conversation_id::text, gr.user_message_id::text,
               gr.assistant_message_id::text, gr.release_id::text,
               gr.request_id::text, gr.state, gr.outcome, gr.cancel_requested,
               gr.error, gr.created_at, gr.updated_at, gr.completed_at,
               um.content AS question, am.content AS answer, am.state AS message_state,
               EXISTS (
                 SELECT 1 FROM message_evidence evidence
                 JOIN documents document ON document.id = evidence.document_id
                   AND document.tenant_id = evidence.tenant_id
                 WHERE evidence.tenant_id = gr.tenant_id
                   AND evidence.message_id = gr.assistant_message_id
                   AND (document.status <> 'active' OR document.deleted_at IS NOT NULL)
               ) AS has_invalid_evidence
        FROM generation_runs gr
        JOIN conversations conversation ON conversation.id = gr.conversation_id
          AND conversation.tenant_id = gr.tenant_id AND conversation.owner_user_id = $2
        JOIN messages um ON um.id = gr.user_message_id AND um.tenant_id = gr.tenant_id
        JOIN messages am ON am.id = gr.assistant_message_id AND am.tenant_id = gr.tenant_id
        JOIN tenants tenant ON tenant.id = gr.tenant_id AND tenant.status = 'active'
        JOIN tenant_members tm ON tm.tenant_id = gr.tenant_id
          AND tm.user_id = $2 AND tm.status = 'active'
        JOIN roles tenant_role ON tenant_role.id = tm.role_id
        LEFT JOIN kb_members km ON km.tenant_id = gr.tenant_id
          AND km.knowledge_base_id = gr.knowledge_base_id
          AND km.user_id = $2 AND km.status = 'active'
        WHERE gr.id = $1 AND (
          tenant_role.code IN ('space_admin', 'customer_reader') OR km.user_id IS NOT NULL
        )
        """,
        run_id,
        user_id,
    )
    if row is None:
        return None
    hidden = bool(row["has_invalid_evidence"])
    citations: list[dict[str, Any]] = []
    if not hidden:
        citation_rows = await connection.fetch(
            """
            SELECT citation.evidence_no, citation.chunk_id::text,
                   citation.document_version_id::text, citation.locator,
                   document.id::text AS document_id, document.title AS document_title,
                   version.version_no, chunk.section_path, chunk.content,
                   chunk.knowledge_base_id::text
            FROM message_citations citation
            JOIN chunks chunk ON chunk.id = citation.chunk_id
              AND chunk.tenant_id = citation.tenant_id
            JOIN document_versions version ON version.id = citation.document_version_id
              AND version.tenant_id = citation.tenant_id
            JOIN documents document ON document.id = version.document_id
              AND document.tenant_id = citation.tenant_id
              AND document.status = 'active' AND document.deleted_at IS NULL
            WHERE citation.tenant_id = $1 AND citation.message_id = $2
            ORDER BY citation.evidence_no
            """,
            int(row["tenant_id"]),
            int(row["assistant_message_id"]),
        )
        for citation in citation_rows:
            item = dict(citation)
            item["locator"] = _json_value(item["locator"], {})
            item["section_path"] = _json_value(item["section_path"], [])
            item["source_path"] = (
                f"/documents?knowledge_base_id={item['knowledge_base_id']}"
                f"&document_id={item['document_id']}"
                f"&version_id={item['document_version_id']}&chunk_id={item['chunk_id']}"
            )
            citations.append(item)
    result = dict(row)
    result["error"] = _json_value(result["error"], None)
    result["answer"] = "" if hidden else result["answer"]
    result["message_state"] = "hidden" if hidden else result["message_state"]
    result["hidden"] = hidden
    result["citations"] = citations
    result.pop("has_invalid_evidence", None)
    return result


async def _finish_without_generation(
    connection: asyncpg.Connection,
    *,
    run_id: int,
    assistant_message_id: int,
    tenant_id: int,
    content: str,
    outcome: str,
    release_id: int | None,
    trace_id: str,
) -> None:
    async with connection.transaction():
        await connection.execute(
            """
            UPDATE messages SET content = $3, state = 'complete', release_id = $4,
                usage = $5::jsonb
            WHERE id = $1 AND tenant_id = $2
            """,
            assistant_message_id,
            tenant_id,
            content,
            release_id,
            json.dumps({"retrieval_trace_id": trace_id}, ensure_ascii=False),
        )
        await connection.execute(
            """
            UPDATE generation_runs SET state = 'completed', outcome = $3,
                completed_at = now(), updated_at = now(), error = NULL
            WHERE id = $1 AND tenant_id = $2
            """,
            run_id,
            tenant_id,
            outcome,
        )


async def _persist_evidence(
    connection: asyncpg.Connection,
    *,
    tenant_id: int,
    assistant_message_id: int,
    evidence: Sequence[dict[str, Any]],
) -> None:
    for item in evidence:
        if not item.get("context_included"):
            continue
        await connection.execute(
            """
            INSERT INTO message_evidence(
              tenant_id, message_id, document_id, document_version_id
            ) VALUES ($1, $2, $3, $4)
            ON CONFLICT (message_id, document_id, document_version_id) DO NOTHING
            """,
            tenant_id,
            assistant_message_id,
            int(item["document_id"]),
            int(item["document_version_id"]),
        )


async def _persist_completed_answer(
    connection: asyncpg.Connection,
    *,
    run_id: int,
    tenant_id: int,
    assistant_message_id: int,
    release_id: int,
    content: str,
    outcome: str,
    cited_numbers: Sequence[int],
    evidence: Sequence[dict[str, Any]],
    trace_id: str,
) -> None:
    evidence_by_no = {
        int(item["evidence_no"]): item
        for item in evidence
        if item.get("evidence_no") is not None and item.get("context_included")
    }
    async with connection.transaction():
        await connection.execute(
            """
            UPDATE messages SET content = $3, state = 'complete', release_id = $4,
                usage = $5::jsonb
            WHERE id = $1 AND tenant_id = $2
            """,
            assistant_message_id,
            tenant_id,
            content,
            release_id,
            json.dumps(
                {"retrieval_trace_id": trace_id, "citation_count": len(cited_numbers)},
                ensure_ascii=False,
            ),
        )
        for evidence_no in cited_numbers:
            item = evidence_by_no.get(evidence_no)
            if item is None:
                continue
            await connection.execute(
                """
                INSERT INTO message_citations(
                  tenant_id, message_id, chunk_id, document_version_id,
                  evidence_no, locator
                ) VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                """,
                tenant_id,
                assistant_message_id,
                int(item["chunk_id"]),
                int(item["document_version_id"]),
                evidence_no,
                json.dumps(item["locator"], ensure_ascii=False),
            )
        await connection.execute(
            """
            UPDATE generation_runs SET state = 'completed', outcome = $3,
                completed_at = now(), updated_at = now(), error = NULL
            WHERE id = $1 AND tenant_id = $2
            """,
            run_id,
            tenant_id,
            outcome,
        )


async def _mark_failed(
    connection: asyncpg.Connection,
    *,
    run_id: int,
    tenant_id: int,
    assistant_message_id: int,
    code: str,
) -> None:
    payload = json.dumps({"code": code}, ensure_ascii=False)
    async with connection.transaction():
        await connection.execute(
            """
            UPDATE retrieval_traces SET state = 'failed'
            WHERE tenant_id = $1 AND message_id = $2 AND state = 'running'
            """,
            tenant_id,
            assistant_message_id,
        )
        await connection.execute(
            """
            UPDATE messages SET state = 'failed', usage = $3::jsonb
            WHERE id = $1 AND tenant_id = $2
              AND EXISTS (
                SELECT 1 FROM generation_runs run
                WHERE run.id = $4 AND run.tenant_id = messages.tenant_id
                  AND run.state <> 'cancelled'
              )
            """,
            assistant_message_id,
            tenant_id,
            payload,
            run_id,
        )
        await connection.execute(
            """
            UPDATE generation_runs SET state = 'failed', error = $3::jsonb,
                completed_at = now(), updated_at = now()
            WHERE id = $1 AND tenant_id = $2 AND state <> 'cancelled'
            """,
            run_id,
            tenant_id,
            payload,
        )


async def stream_generation_run(
    settings: Settings,
    *,
    run_id: int,
    user_id: int,
) -> AsyncIterator[str]:
    """执行检索、生成和引用校验，并以 SSE 返回可恢复的运行事件。"""
    if not settings.database_url:
        yield sse_event("error", {"code": "DATABASE_NOT_CONFIGURED", "retryable": True})
        return
    connection = await asyncpg.connect(settings.database_url, timeout=10)
    row: asyncpg.Record | None = None
    try:
        snapshot = await load_run_snapshot(connection, run_id=run_id, user_id=user_id)
        if snapshot is None:
            yield sse_event("error", {"code": "RUN_NOT_FOUND", "retryable": False})
            return
        yield sse_event("meta", {"run": snapshot})
        if snapshot["state"] in {"completed", "failed", "cancelled"}:
            yield sse_event("done", {"run": snapshot})
            return

        row = await connection.fetchrow(
            """
            UPDATE generation_runs SET state = 'running', started_at = COALESCE(started_at, now()),
                updated_at = now(), error = NULL
            WHERE id = $1 AND tenant_id = $2 AND state = 'queued'
            RETURNING id, tenant_id, knowledge_base_id, conversation_id,
                      user_message_id, assistant_message_id, release_id
            """,
            run_id,
            int(snapshot["tenant_id"]),
        )
        if row is None:
            row = await connection.fetchrow(
                """
                SELECT id, tenant_id, knowledge_base_id, conversation_id,
                       user_message_id, assistant_message_id, release_id
                FROM generation_runs WHERE id = $1 AND tenant_id = $2 AND state = 'running'
                """,
                run_id,
                int(snapshot["tenant_id"]),
            )
        if row is None:
            latest = await load_run_snapshot(connection, run_id=run_id, user_id=user_id)
            yield sse_event("done", {"run": latest})
            return
        await connection.execute(
            "UPDATE messages SET state = 'generating' WHERE id = $1 AND tenant_id = $2",
            row["assistant_message_id"],
            row["tenant_id"],
        )

        runtime_row = await connection.fetchrow(
            """
            SELECT rp.definition, ge.base_url, ge.allowed_models,
                   ge.status AS generation_endpoint_status
            FROM messages message
            JOIN runtime_profiles rp ON rp.id = message.runtime_id
              AND rp.tenant_id = message.tenant_id
            JOIN model_endpoints ge
              ON ge.id = (rp.definition->'generation'->>'endpoint_id')::bigint
            WHERE message.id = $1 AND message.tenant_id = $2
            """,
            row["assistant_message_id"],
            row["tenant_id"],
        )
        has_runtime_profile = runtime_row is not None and "definition" in runtime_row
        runtime_definition = (
            _json_value(runtime_row["definition"], {}) if has_runtime_profile else {}
        )
        retrieval_definition = runtime_definition.get("retrieval", {})
        generation_definition = runtime_definition.get("generation", {})
        if has_runtime_profile and runtime_row is not None:
            if runtime_row["generation_endpoint_status"] != "active":
                raise ValueError("GENERATION_ENDPOINT_DISABLED")
            raw_allowed_models = runtime_row["allowed_models"]
            allowed_models = (
                json.loads(raw_allowed_models)
                if isinstance(raw_allowed_models, str)
                else list(raw_allowed_models)
            )
            generation_model = str(generation_definition.get("model", ""))
            generation_settings = gateway_settings(
                settings,
                base_url=str(runtime_row["base_url"]),
                allowed_models=allowed_models,
                generation_model=generation_model,
            )
            client = ModelGatewayClient(generation_settings)
        else:
            client = ModelGatewayClient(settings)
        retrieval = await execute_vector_search(
            connection,
            settings,
            tenant_id=int(row["tenant_id"]),
            knowledge_base_id=int(row["knowledge_base_id"]),
            user_id=user_id,
            query=str(snapshot["question"]),
            active_release_id=(int(row["release_id"]) if row["release_id"] is not None else None),
            top_k=int(retrieval_definition.get("top_k", 10)),
            context_max_chars=int(retrieval_definition.get("context_max_chars", 8000)),
            message_id=int(row["assistant_message_id"]),
        )
        yield sse_event(
            "retrieval",
            {
                "state": retrieval["state"],
                "trace_id": retrieval["trace_id"],
                "evidence_count": len(retrieval["items"]),
            },
        )
        await _persist_evidence(
            connection,
            tenant_id=int(row["tenant_id"]),
            assistant_message_id=int(row["assistant_message_id"]),
            evidence=retrieval["items"],
        )
        if retrieval["state"] != "completed":
            outcome = "index_not_ready" if retrieval["state"] == "index_not_ready" else "no_answer"
            content = (
                "当前知识库索引尚未就绪，暂时无法回答。"
                if outcome == "index_not_ready"
                else NO_ANSWER_TEXT
            )
            await _finish_without_generation(
                connection,
                run_id=run_id,
                assistant_message_id=int(row["assistant_message_id"]),
                tenant_id=int(row["tenant_id"]),
                content=content,
                outcome=outcome,
                release_id=(int(row["release_id"]) if row["release_id"] is not None else None),
                trace_id=retrieval["trace_id"],
            )
            latest = await load_run_snapshot(connection, run_id=run_id, user_id=user_id)
            yield sse_event("done", {"run": latest})
            return

        messages = build_grounded_messages(
            str(snapshot["question"]),
            retrieval["context"],
            str(runtime_definition.get("answer_rules", "")),
        )
        generated_parts: list[str] = []
        token_count = 0
        async for token in client.stream_chat(
            messages,
            temperature=float(generation_definition.get("temperature", 0.2)),
        ):
            token_count += 1
            if token_count == 1 or token_count % 5 == 0:
                cancelled = await connection.fetchval(
                    "SELECT cancel_requested FROM generation_runs WHERE id = $1 AND tenant_id = $2",
                    run_id,
                    row["tenant_id"],
                )
                if cancelled:
                    await connection.execute(
                        """
                        UPDATE retrieval_traces SET state = 'cancelled'
                        WHERE tenant_id = $1 AND message_id = $2 AND state = 'running'
                        """,
                        row["tenant_id"],
                        row["assistant_message_id"],
                    )
                    await connection.execute(
                        """
                        UPDATE generation_runs SET state = 'cancelled', completed_at = now(),
                            updated_at = now() WHERE id = $1 AND tenant_id = $2
                        """,
                        run_id,
                        row["tenant_id"],
                    )
                    await connection.execute(
                        """
                        UPDATE messages SET content = $3, state = 'cancelled'
                        WHERE id = $1 AND tenant_id = $2
                        """,
                        row["assistant_message_id"],
                        row["tenant_id"],
                        "".join(generated_parts),
                    )
                    latest = await load_run_snapshot(connection, run_id=run_id, user_id=user_id)
                    yield sse_event("cancelled", {"run": latest})
                    return
            generated_parts.append(token)
            yield sse_event("token", {"text": token})

        valid_numbers = {
            int(item["evidence_no"])
            for item in retrieval["items"]
            if item.get("context_included") and item.get("evidence_no") is not None
        }
        content, cited_numbers, outcome = validate_generated_answer(
            "".join(generated_parts),
            valid_numbers,
        )
        await _persist_completed_answer(
            connection,
            run_id=run_id,
            tenant_id=int(row["tenant_id"]),
            assistant_message_id=int(row["assistant_message_id"]),
            release_id=int(row["release_id"]),
            content=content,
            outcome=outcome,
            cited_numbers=cited_numbers,
            evidence=retrieval["items"],
            trace_id=retrieval["trace_id"],
        )
        latest = await load_run_snapshot(connection, run_id=run_id, user_id=user_id)
        yield sse_event("done", {"run": latest})
    except asyncio.CancelledError:
        if row is not None:
            await _mark_failed(
                connection,
                run_id=run_id,
                tenant_id=int(row["tenant_id"]),
                assistant_message_id=int(row["assistant_message_id"]),
                code="STREAM_DISCONNECTED",
            )
        raise
    except (httpx.HTTPError, ValueError, RetrievalServiceError, asyncpg.PostgresError) as error:
        if row is not None:
            await _mark_failed(
                connection,
                run_id=run_id,
                tenant_id=int(row["tenant_id"]),
                assistant_message_id=int(row["assistant_message_id"]),
                code=type(error).__name__.upper(),
            )
        yield sse_event(
            "error",
            {"code": "GENERATION_FAILED", "message": "问答生成失败，可以重试。", "retryable": True},
        )
    except Exception as error:
        logger.exception("问答运行出现未预期异常", exc_info=error)
        if row is not None:
            await _mark_failed(
                connection,
                run_id=run_id,
                tenant_id=int(row["tenant_id"]),
                assistant_message_id=int(row["assistant_message_id"]),
                code="UNEXPECTED_GENERATION_ERROR",
            )
        yield sse_event(
            "error",
            {"code": "GENERATION_FAILED", "message": "问答生成失败，可以重试。", "retryable": True},
        )
    finally:
        await connection.close()
