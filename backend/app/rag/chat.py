"""问答运行、SSE 事件、引用校验与历史授权。"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from typing import Any

import asyncpg
import httpx

from app.core.api_keys import (
    ApiKeyQuotaExceededError,
    release_api_key_reservation,
    reserve_api_key_tokens,
    settle_api_key_usage,
    update_api_key_reservation_usage,
)
from app.core.config import Settings
from app.rag.models import ModelGatewayClient, estimate_token_count
from app.rag.profiles import gateway_settings
from app.rag.retrieval import RetrievalServiceError, assemble_evidence, execute_vector_search

CITATION_PATTERN = re.compile(r"\[证据\s*(\d+)\]")
MARKDOWN_URL_PATTERN = re.compile(r"\[([^\]]+)]\(https?://[^)]+\)", re.IGNORECASE)
RAW_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
# 只匹配对所问事项的结论性拒答，避免正文中的局部不确定被误当作整题拒答。
SCOPE_REFUSAL_PATTERN = re.compile(
    r"(?:当前已发布知识库中)?没有找到足够依据.{0,80}"
    r"(?:表明|证明|说明).{0,80}(?:规范|文档|资料).{0,40}"
    r"(?:规定|收费标准|接口字段)"
    r"|没有找到.{0,80}(?:规范|文档|资料).{0,30}(?:直接)?规定.{0,80}(?:依据|证据)"
    r"|仅凭.{0,40}(?:不能|无法)(?:判断|确定|回答)"
    r"|不能仅凭.{0,40}(?:判断|确定|回答)"
    r"|无法据此回答|不能据此回答|无法回答这个问题",
    re.IGNORECASE,
)
SOURCE_CONFLICT_MARKER = "[[SOURCE_CONFLICT]]"
NO_ANSWER_TEXT = "当前已发布知识库中没有找到足够依据，暂时无法回答这个问题。"
INVALID_CITATION_TEXT = "生成结果没有提供可验证引用，已拒绝展示。"

logger = logging.getLogger(__name__)


def _json_value(value: Any, fallback: Any) -> Any:
    """兼容 asyncpg 已解码 JSON 与测试替身字符串，并在非法 JSON 时使用回退值。"""
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
    history: Sequence[Mapping[str, str]] = (),
) -> list[dict[str, str]]:
    """构造带最近会话上下文、但事实结论必须引用本轮证据的消息。"""
    system = (
        "你是公司知识库问答助手。只能使用给定证据回答，不得使用外部知识。"
        "每个事实结论都必须使用形如 [证据 1] 的编号引用。"
        "不得输出网址、文件链接或自行编造来源。"
        f"证据不足、证据没有覆盖问题或问题超出资料范围时，只回答：{NO_ANSWER_TEXT}"
        "有充分证据时直接简洁回答，普通问题控制在一至三句；确有多个步骤或类别时再使用列表。"
        "如果证据之间存在无法消解的冲突，请在回答开头输出 [[SOURCE_CONFLICT]]，"
        "说明冲突点，并引用冲突双方。"
    )
    if answer_rules.strip():
        system += f"\n当前知识库补充回答规则：{answer_rules.strip()}"
    user = f"问题：\n{question}\n\n可用证据：\n{context}"
    messages = [{"role": "system", "content": system}]
    messages.extend(
        {"role": item["role"], "content": item["content"]}
        for item in history
        if item.get("role") in {"user", "assistant"} and item.get("content", "").strip()
    )
    messages.append({"role": "user", "content": user})
    return messages


def build_general_assistant_messages(
    question: str,
    history: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    """构造不需要知识库证据的普通助理对话，并明确避免编造租户事实。"""
    messages = [
        {
            "role": "system",
            "content": (
                "你是 RAGManage 的企业 AI 助理。使用最近对话理解追问，直接、清晰地回答一般交流、"
                "上下文管理和系统使用方式。涉及当前客户的制度、业务数据或知识库事实时，"
                "如果没有检索证据，不要猜测；说明需要查询对应资料。不要输出网址或虚构来源。"
            ),
        }
    ]
    messages.extend(
        {"role": item["role"], "content": item["content"]}
        for item in history
        if item.get("role") in {"user", "assistant"} and item.get("content", "").strip()
    )
    messages.append({"role": "user", "content": question})
    return messages


async def classify_assistant_question(
    client: ModelGatewayClient,
    *,
    question: str,
    history: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    """判断本轮是否需要跨知识库检索，并为含糊追问生成独立检索查询。"""
    history_payload = [
        {"role": item["role"], "content": item["content"][-2000:]}
        for item in history[-8:]
        if item.get("role") in {"user", "assistant"} and item.get("content", "").strip()
    ]
    messages = [
        {
            "role": "system",
            "content": (
                "你负责为企业 AI 助理路由每条新消息。判断是否需要查询客户知识库："
                "客户制度、产品操作、业务事实、流程、政策和对话中承接的知识问题需要检索；"
                "问候、感谢、闲聊、对刚才回答的格式或上下文管理要求不需要检索。"
                "如果需要检索，把当前问题结合历史改写为可独立检索的简短问题。"
                '只输出 JSON：{"retrieve":true或false,"query":"检索问题或空字符串"}。'
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {"history": history_payload, "question": question}, ensure_ascii=False
            ),
        },
    ]
    try:
        result = await client.complete_chat(
            messages,
            temperature=0,
            max_tokens=96,
            response_format={"type": "json_object"},
        )
    except (httpx.HTTPError, ValueError, TypeError) as error:
        # 部分旧版兼容客户端不接受 response_format，先用旧形状重试一次。
        if isinstance(error, TypeError):
            try:
                result = await client.complete_chat(messages, temperature=0, max_tokens=96)
            except (httpx.HTTPError, ValueError) as retry_error:
                logger.warning("助手问题路由失败，降级为知识库检索: %s", retry_error)
                return {
                    "retrieve": True,
                    "query": question.strip()[:4000],
                    "usage": {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "usage_source": "unavailable",
                    },
                    "model": client.settings.generation_model,
                }
        else:
            try:
                result = await client.complete_chat(messages, temperature=0, max_tokens=96)
            except (httpx.HTTPError, ValueError) as retry_error:
                logger.warning("助手问题路由失败，降级为知识库检索: %s", retry_error)
                return {
                    "retrieve": True,
                    "query": question.strip()[:4000],
                    "usage": {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "usage_source": "unavailable",
                    },
                    "model": client.settings.generation_model,
                }
    raw = str(result["content"])
    match = re.search(r"\{[\s\S]*\}", raw)
    try:
        decision = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        decision = {}
    retrieve = decision.get("retrieve") if isinstance(decision, dict) else None
    query = decision.get("query") if isinstance(decision, dict) else None
    # 路由输出不完整或格式异常时采用保守检索，避免把应有依据的事实问题当闲聊作答。
    if not isinstance(retrieve, bool):
        retrieve = True
    if not isinstance(query, str) or not query.strip():
        query = question
    return {
        "retrieve": retrieve,
        "query": query.strip()[:4000],
        "usage": result["usage"],
        "model": client.settings.generation_model,
    }


def validate_general_answer(content: str) -> str:
    """清理普通助理输出中的 URL，保留不要求引用知识库的自然回答。"""
    sanitized = MARKDOWN_URL_PATTERN.sub(r"\1", content)
    sanitized = RAW_URL_PATTERN.sub("", sanitized).strip()
    return sanitized or "我暂时没有生成有效回答，请换一种方式提问。"


async def execute_assistant_scope_search(
    connection: asyncpg.Connection,
    settings: Settings,
    *,
    tenant_id: int,
    user_id: int,
    query: str,
    message_id: int,
    on_embedding_usage: Callable[[Mapping[str, Any], str, str], Awaitable[None]] | None,
    top_k: int = 10,
    context_max_chars: int = 8000,
) -> dict[str, Any]:
    """在 API Key 所属空间的全部已发布知识库中检索并统一编号候选证据。"""
    knowledge_bases = await connection.fetch(
        """
        SELECT kb.id, kb.name, kb.active_release_id, rp.definition AS runtime_definition
        FROM knowledge_bases kb
        LEFT JOIN runtime_profiles rp ON rp.id = kb.active_runtime_id
          AND rp.tenant_id = kb.tenant_id AND rp.knowledge_base_id = kb.id
        WHERE kb.tenant_id = $1 AND kb.status <> 'disabled'
          AND kb.active_release_id IS NOT NULL
        ORDER BY kb.updated_at DESC, kb.id
        """,
        tenant_id,
    )
    trace_ids: list[str] = []
    candidate_items: list[dict[str, Any]] = []
    states: list[str] = []
    for knowledge_base in knowledge_bases:
        runtime_definition = _json_value(knowledge_base["runtime_definition"], {})
        retrieval_definition = runtime_definition.get("retrieval", {})

        async def report_usage_for_knowledge_base(
            usage: Mapping[str, Any],
            model_name: str,
            knowledge_base_id: str = str(knowledge_base["id"]),
        ) -> None:
            """让同一嵌入模型在不同知识库的消费可分别更新和结算。"""
            if on_embedding_usage is not None:
                await on_embedding_usage(usage, model_name, knowledge_base_id)

        result = await execute_vector_search(
            connection,
            settings,
            tenant_id=tenant_id,
            knowledge_base_id=int(knowledge_base["id"]),
            user_id=user_id,
            query=query,
            active_release_id=int(knowledge_base["active_release_id"]),
            top_k=int(retrieval_definition.get("top_k", top_k)),
            context_max_chars=context_max_chars,
            message_id=message_id,
            on_embedding_usage=(
                report_usage_for_knowledge_base if on_embedding_usage is not None else None
            ),
        )
        states.append(str(result["state"]))
        trace_id = result.get("trace_id")
        if trace_id:
            trace_ids.append(str(trace_id))
        for item in result["items"]:
            candidate = dict(item)
            candidate["knowledge_base_id"] = str(knowledge_base["id"])
            candidate["knowledge_base_name"] = str(knowledge_base["name"])
            # 单库函数已编号其上下文；全局合并时重新排序并生成唯一证据编号。
            candidate["context_included"] = False
            candidate["evidence_no"] = None
            candidate_items.append(candidate)

    candidate_items.sort(
        key=lambda item: (
            -float(item.get("fused_score", 0)),
            -float(item.get("similarity", 0)),
            str(item.get("knowledge_base_name", "")),
        )
    )
    items, context = assemble_evidence(
        candidate_items,
        context_max_chars=context_max_chars,
    )
    if items:
        state = "completed"
    elif "index_not_ready" in states:
        state = "index_not_ready"
    else:
        state = "no_results"
    return {
        "state": state,
        "trace_id": trace_ids[0] if trace_ids else "",
        "trace_ids": trace_ids,
        "items": items,
        "context": context,
        "knowledge_base_count": len(knowledge_bases),
    }


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
    # 结论性范围拒答优先于引用解析，防止模型用背景证据把拒答伪装成已回答。
    if SCOPE_REFUSAL_PATTERN.search(sanitized):
        return NO_ANSWER_TEXT, [], "no_answer"
    if sanitized == NO_ANSWER_TEXT or not sanitized:
        return NO_ANSWER_TEXT, [], "no_answer"
    if not cited:
        return INVALID_CITATION_TEXT, [], "no_answer"
    return sanitized, cited, "answered"


def aggregate_embedding_usage(
    usage_by_operation: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> dict[str, dict[str, Any]]:
    """合并各知识库最终嵌入用量；每个操作中的 estimate 已由真实值覆盖。"""
    aggregated: dict[str, dict[str, Any]] = {}
    for model_usage in usage_by_operation.values():
        for model_name, usage in model_usage.items():
            combined = aggregated.setdefault(
                model_name,
                {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "usage_source": "gateway",
                },
            )
            for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
                combined[field] += max(0, int(usage.get(field, 0)))
            if usage.get("usage_source") == "estimate":
                combined["usage_source"] = "estimate"
            elif usage.get("usage_source") != "gateway" and combined["usage_source"] != "estimate":
                combined["usage_source"] = "unavailable"
    return aggregated


async def load_run_snapshot(
    connection: asyncpg.Connection,
    *,
    run_id: int,
    user_id: int,
    api_key_tenant_id: int | str | None = None,
    api_key_id: str | None = None,
) -> dict[str, Any] | None:
    """读取运行快照并归一化鉴权 ID。API Key 读取自身运行；网页登录只读取有权访问的单库会话。"""
    row = await connection.fetchrow(
        """
        SELECT gr.id::text, gr.public_id::text AS public_id, gr.tenant_id::text,
               gr.knowledge_base_id::text, conversation.scope AS conversation_scope,
               gr.conversation_id::text, gr.user_message_id::text,
               gr.assistant_message_id::text, gr.release_id::text, gr.api_key_id::text,
               gr.request_id::text, gr.state, gr.outcome, gr.cancel_requested,
               gr.error, gr.created_at, gr.updated_at, gr.completed_at,
               um.content AS question, am.content AS answer, am.state AS message_state,
               am.usage AS usage,
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
        LEFT JOIN tenant_members tm ON tm.tenant_id = gr.tenant_id
          AND tm.user_id = $2 AND tm.status = 'active'
        LEFT JOIN roles tenant_role ON tenant_role.id = tm.role_id
        LEFT JOIN kb_members km ON km.tenant_id = gr.tenant_id
          AND km.knowledge_base_id = gr.knowledge_base_id
          AND km.user_id = $2 AND km.status = 'active'
        WHERE gr.id = $1 AND (
          ($3::bigint IS NOT NULL AND gr.tenant_id = $3 AND gr.api_key_id = $4) OR
          ($3::bigint IS NULL AND conversation.scope = 'knowledge_base' AND (
            tenant_role.code IN ('space_admin', 'customer_reader') OR km.user_id IS NOT NULL
          ))
        )
        """,
        run_id,
        user_id,
        int(api_key_tenant_id) if api_key_tenant_id is not None else None,
        int(api_key_id) if api_key_id is not None else None,
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
                   chunk.knowledge_base_id::text, kb.name AS knowledge_base_name,
                   kb.business_scenario, kb.target_users, kb.trust_level,
                   kb.valid_from, kb.valid_until, kb.source_system, kb.business_tags,
                   COALESCE((SELECT jsonb_agg(jsonb_build_object(
                     'id', we.id::text, 'term', we.term, 'version_no', we.version_no,
                     'status', we.status) ORDER BY we.term)
                     FROM wiki_entry_sources wes JOIN wiki_entries we ON we.id = wes.entry_id
                     WHERE wes.chunk_id = chunk.id AND we.status = 'published'
                       AND we.tenant_id=chunk.tenant_id
                       AND we.knowledge_base_id=chunk.knowledge_base_id
                       AND wes.document_version_id=citation.document_version_id
                       AND (we.valid_from IS NULL OR we.valid_from <= CURRENT_DATE)
                       AND (we.valid_until IS NULL OR we.valid_until >= CURRENT_DATE)
                   ), '[]') AS wiki_entries
            FROM message_citations citation
            JOIN chunks chunk ON chunk.id = citation.chunk_id
              AND chunk.tenant_id = citation.tenant_id
            JOIN document_versions version ON version.id = citation.document_version_id
              AND version.tenant_id = citation.tenant_id
            JOIN documents document ON document.id = version.document_id
              AND document.tenant_id = citation.tenant_id
              AND document.status = 'active' AND document.deleted_at IS NULL
            JOIN knowledge_bases kb ON kb.id = chunk.knowledge_base_id
              AND kb.tenant_id = chunk.tenant_id
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
            item["governance"] = {
                "business_scenario": item.pop("business_scenario", ""),
                "target_users": item.pop("target_users", ""),
                "trust_level": item.pop("trust_level", "medium"),
                "valid_from": (
                    item.pop("valid_from").isoformat()
                    if item.get("valid_from") is not None
                    else None
                ),
                "valid_until": (
                    item.pop("valid_until").isoformat()
                    if item.get("valid_until") is not None
                    else None
                ),
                "source_system": item.pop("source_system", ""),
                "business_tags": list(item.pop("business_tags", []) or []),
            }
            item["wiki_entries"] = _json_value(item.pop("wiki_entries", []), [])
            item["source_path"] = (
                f"/documents?knowledge_base_id={item['knowledge_base_id']}"
                f"&document_id={item['document_id']}"
                f"&version_id={item['document_version_id']}&chunk_id={item['chunk_id']}"
            )
            citations.append(item)
    result = dict(row)
    result["error"] = _json_value(result["error"], None)
    result["answer"] = "" if hidden else result["answer"]
    result["usage"] = _json_value(result.get("usage"), {})
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
    trace_ids: Sequence[str] = (),
    usage: Mapping[str, Any] | None = None,
) -> bool:
    """原子领取完成权并写入无生成回答；取消已先发生时不覆盖终态。"""
    final_usage = dict(usage or {})
    async with connection.transaction():
        completed_run_id = await connection.fetchval(
            """
            UPDATE generation_runs SET state = 'completed', outcome = $3,
                completed_at = now(), updated_at = now(), error = NULL
            WHERE id = $1 AND tenant_id = $2 AND state = 'running'
              AND cancel_requested = false
            RETURNING id
            """,
            run_id,
            tenant_id,
            outcome,
        )
        if completed_run_id is None:
            return False
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
                {
                    "retrieval_trace_id": trace_id,
                    "retrieval_trace_ids": list(trace_ids) or ([trace_id] if trace_id else []),
                    "prompt_tokens": int(final_usage.get("prompt_tokens", 0)),
                    "completion_tokens": int(final_usage.get("completion_tokens", 0)),
                    "total_tokens": int(final_usage.get("total_tokens", 0)),
                    "usage_source": str(final_usage.get("usage_source", "unavailable")),
                    "model_usage": final_usage.get("model_usage", {}),
                },
                ensure_ascii=False,
            ),
        )
    return True


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
    release_id: int | None,
    content: str,
    outcome: str,
    cited_numbers: Sequence[int],
    evidence: Sequence[dict[str, Any]],
    trace_id: str,
    trace_ids: Sequence[str] = (),
    usage: dict[str, Any],
) -> bool:
    """只有仍持有 running 状态的执行者才能提交最终答案和引用。"""
    evidence_by_no = {
        int(item["evidence_no"]): item
        for item in evidence
        if item.get("evidence_no") is not None and item.get("context_included")
    }
    async with connection.transaction():
        completed_run_id = await connection.fetchval(
            """
            UPDATE generation_runs SET state = 'completed', outcome = $3,
                completed_at = now(), updated_at = now(), error = NULL
            WHERE id = $1 AND tenant_id = $2 AND state = 'running'
              AND cancel_requested = false
            RETURNING id
            """,
            run_id,
            tenant_id,
            outcome,
        )
        if completed_run_id is None:
            return False
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
                {
                    "retrieval_trace_id": trace_id,
                    "retrieval_trace_ids": list(trace_ids) or ([trace_id] if trace_id else []),
                    "citation_count": len(cited_numbers),
                    **usage,
                },
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
    return True


async def _mark_failed(
    connection: asyncpg.Connection,
    *,
    run_id: int,
    tenant_id: int,
    assistant_message_id: int,
    code: str,
    usage: Mapping[str, Any] | None = None,
) -> None:
    """持久化失败终态，并在模型已消费时保留可审计的用量。"""
    payload = json.dumps({"code": code, **dict(usage or {})}, ensure_ascii=False)
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


def _combined_usage(
    *,
    embedding_usage: Mapping[str, Any] | None,
    embedding_model: str | None,
    generation_usage: Mapping[str, Any] | None,
    generation_model: str | None,
    embedding_breakdown: Mapping[str, Mapping[str, Any]] | None = None,
    routing_usage: Mapping[str, Any] | None = None,
    routing_model: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """合并意图路由、多个知识库嵌入和回答生成用量，保留按模型拆分的审计明细。"""
    model_usage: dict[str, Any] = {}
    parts: list[Mapping[str, Any]] = []
    model_names: list[str] = []
    if embedding_breakdown:
        embedding_key_prefix = len(embedding_breakdown) == 1
        for model_name, part in embedding_breakdown.items():
            key = "embedding" if embedding_key_prefix else f"embedding:{model_name}"
            model_usage[key] = {"model": model_name, **dict(part)}
            parts.append(part)
            model_names.append(model_name)
    elif embedding_usage is not None and embedding_model:
        model_usage["embedding"] = {"model": embedding_model, **dict(embedding_usage)}
        parts.append(embedding_usage)
        model_names.append(embedding_model)
    if routing_usage is not None and routing_model:
        model_usage["routing"] = {"model": routing_model, **dict(routing_usage)}
        parts.append(routing_usage)
        model_names.append(routing_model)
    if generation_usage is not None and generation_model:
        model_usage["generation"] = {"model": generation_model, **dict(generation_usage)}
        parts.append(generation_usage)
        model_names.append(generation_model)
    sources = {str(part.get("usage_source", "unavailable")) for part in parts}
    if "estimate" in sources:
        source = "estimate"
    elif sources == {"gateway"}:
        source = "gateway"
    else:
        source = "unavailable"
    prompt_tokens = sum(max(0, int(part.get("prompt_tokens", 0))) for part in parts)
    completion_tokens = sum(max(0, int(part.get("completion_tokens", 0))) for part in parts)
    total_tokens = sum(max(0, int(part.get("total_tokens", 0))) for part in parts)
    usage = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": max(total_tokens, prompt_tokens + completion_tokens),
        "usage_source": source,
        "model_usage": model_usage,
    }
    return usage, model_usage, " + ".join(model_names) or "unavailable"


async def _persist_retrieval_trace_timings(
    connection: asyncpg.Connection,
    *,
    tenant_id: int,
    assistant_message_id: int,
    timings: Mapping[str, float],
) -> None:
    """合并问答阶段耗时到本消息的检索 Trace，保留检索服务原有指标。"""
    if not timings:
        return
    await connection.execute(
        """
        UPDATE retrieval_traces
        SET timings = timings || $3::jsonb
        WHERE tenant_id = $1 AND message_id = $2
        """,
        tenant_id,
        assistant_message_id,
        json.dumps(dict(timings), ensure_ascii=False),
    )


async def stream_generation_run(
    settings: Settings,
    *,
    run_id: int,
    user_id: int,
    api_key_id: str | None = None,
    api_key_tenant_id: int | None = None,
    max_tokens: int | None = None,
) -> AsyncIterator[str]:
    """执行检索、生成和引用校验，并以 SSE 返回可恢复的运行事件。

    ``max_tokens`` 由服务端预算或兼容入口的受限请求决定；温度始终来自冻结的 Runtime Profile。
    """
    if not settings.database_url:
        yield sse_event("error", {"code": "DATABASE_NOT_CONFIGURED", "retryable": True})
        return
    connection = await asyncpg.connect(settings.database_url, timeout=10)
    row: asyncpg.Record | None = None
    reserved_tokens = 0
    quota_settled = False
    embedding_usage_by_operation: dict[str, dict[str, dict[str, Any]]] = {}
    routing_usage: dict[str, Any] | None = None
    routing_model: str | None = None
    gateway_usage: dict[str, Any] | None = None
    generation_model: str | None = None
    prompt_tokens_estimate = 0
    generated_parts: list[str] = []
    generation_started = False
    run_started_at: float | None = None
    retrieval_started_at: float | None = None
    generation_request_started_at: float | None = None
    first_token_at: float | None = None
    trace_timings: dict[str, float] = {}

    async def capture_embedding_usage(
        usage: Mapping[str, Any],
        model_name: str,
        operation_id: str = "single",
    ) -> None:
        """按知识库记录嵌入估算或实测消费，供进程中断及失败路径结算。"""
        # execute_vector_search 会先报告估算值，再报告网关实测值；同一模型应以后者覆盖。
        embedding_usage_by_operation.setdefault(operation_id, {})[model_name] = dict(usage)
        await persist_quota_progress()

    def current_usage() -> tuple[dict[str, Any], dict[str, Any], str]:
        """构造当前已消费用量；流式失败时没有网关尾帧则使用明确的估算值。"""
        generation_usage: dict[str, Any] | None = gateway_usage
        if generation_started and generation_usage is None:
            completion_tokens = estimate_token_count("".join(generated_parts))
            generation_usage = {
                "prompt_tokens": prompt_tokens_estimate,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens_estimate + completion_tokens,
                "usage_source": "estimate",
            }
        return _combined_usage(
            embedding_usage=None,
            embedding_model=None,
            generation_usage=generation_usage,
            generation_model=generation_model,
            embedding_breakdown=aggregate_embedding_usage(embedding_usage_by_operation),
            routing_usage=routing_usage,
            routing_model=routing_model,
        )

    async def finalize_quota(status: str) -> dict[str, Any]:
        """幂等结算本次 Key 请求；无模型消费时只释放预扣额度。"""
        nonlocal quota_settled
        usage, model_usage, model_names = current_usage()
        if api_key_id is None or quota_settled:
            return usage
        if usage["total_tokens"] > 0 and row is not None:
            await settle_api_key_usage(
                connection,
                api_key_id=api_key_id,
                run_id=run_id,
                tenant_id=int(row["tenant_id"]),
                request_id=str(row["request_id"]),
                model_name=model_names,
                usage=usage,
                status=status,
                model_usage=model_usage,
            )
        elif reserved_tokens:
            await release_api_key_reservation(
                connection,
                api_key_id=api_key_id,
                run_id=run_id,
            )
        quota_settled = True
        return usage

    async def persist_quota_progress() -> None:
        """定期保存已发生用量，缩小进程中断时无法恢复的计费窗口。"""
        if api_key_id is None or row is None or not reserved_tokens:
            return
        usage = current_usage()[0]
        await update_api_key_reservation_usage(
            connection,
            api_key_id=api_key_id,
            run_id=run_id,
            usage=usage,
        )

    try:
        snapshot = await load_run_snapshot(
            connection,
            run_id=run_id,
            user_id=user_id,
            api_key_tenant_id=api_key_tenant_id,
            api_key_id=api_key_id,
        )
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
            RETURNING id, tenant_id, knowledge_base_id, conversation_id, request_id,
                      user_message_id, assistant_message_id, release_id
            """,
            run_id,
            int(snapshot["tenant_id"]),
        )
        if row is None:
            latest = await load_run_snapshot(
                connection,
                run_id=run_id,
                user_id=user_id,
                api_key_tenant_id=api_key_tenant_id,
                api_key_id=api_key_id,
            )
            if latest is not None and latest["state"] in {"completed", "failed", "cancelled"}:
                yield sse_event("done", {"run": latest})
            else:
                yield sse_event(
                    "error",
                    {"code": "RUN_ALREADY_RUNNING", "retryable": True, "run": latest},
                )
            return
        run_started_at = time.perf_counter()
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
        assistant_scope = snapshot.get("conversation_scope") == "assistant"
        history: list[dict[str, str]] = []
        retrieval_started_at = time.perf_counter()
        if assistant_scope:
            history_rows = await connection.fetch(
                """
                SELECT role, content FROM messages
                WHERE tenant_id = $1 AND conversation_id = $2 AND id < $3
                  AND role IN ('user', 'assistant') AND state = 'complete'
                ORDER BY id DESC LIMIT 8
                """,
                int(row["tenant_id"]),
                int(snapshot["conversation_id"]),
                int(row["user_message_id"]),
            )
            history = [
                {"role": str(item["role"]), "content": str(item["content"])}
                for item in reversed(history_rows)
            ]
            route_messages = [
                {"role": item["role"], "content": item["content"][-2000:]}
                for item in history
            ] + [{"role": "user", "content": str(snapshot["question"])}]
            if api_key_id is not None:
                # 路由模型也计入 Key 额度；用 UTF-8 字节数覆盖短 JSON 分类输出上限。
                reserved_tokens += await reserve_api_key_tokens(
                    connection,
                    api_key_id=api_key_id,
                    run_id=run_id,
                    requested_tokens=sum(
                        len(item["content"].encode("utf-8")) for item in route_messages
                    )
                    # 额外覆盖路由系统提示和结构化 JSON 输出预算。
                    + 1024,
                )
            route = await classify_assistant_question(
                ModelGatewayClient(settings),
                question=str(snapshot["question"]),
                history=history,
            )
            routing_usage = dict(route["usage"])
            routing_model = str(route["model"])
            await persist_quota_progress()
            if route["retrieve"]:
                retrieval = await execute_assistant_scope_search(
                    connection,
                    settings,
                    tenant_id=int(api_key_tenant_id or row["tenant_id"]),
                    user_id=user_id,
                    query=str(route["query"]),
                    message_id=int(row["assistant_message_id"]),
                    on_embedding_usage=capture_embedding_usage,
                    context_max_chars=int(retrieval_definition.get("context_max_chars", 8000)),
                )
                retrieval["mode"] = "knowledge_base"
            else:
                retrieval = {
                    "state": "skipped",
                    "trace_id": "",
                    "trace_ids": [],
                    "items": [],
                    "context": "",
                    "knowledge_base_count": 0,
                    "mode": "general",
                }
        else:
            if api_key_id is not None:
                # UTF-8 字节数是跨中英文分词器的保守上界，确保查询消耗先进入预留额度。
                reserved_tokens += await reserve_api_key_tokens(
                    connection,
                    api_key_id=api_key_id,
                    run_id=run_id,
                    requested_tokens=len(str(snapshot["question"]).encode("utf-8")),
                )
            retrieval = await execute_vector_search(
                connection,
                settings,
                tenant_id=int(row["tenant_id"]),
                knowledge_base_id=int(row["knowledge_base_id"]),
                user_id=user_id,
                query=str(snapshot["question"]),
                active_release_id=(
                    int(row["release_id"]) if row["release_id"] is not None else None
                ),
                top_k=int(retrieval_definition.get("top_k", 10)),
                context_max_chars=int(retrieval_definition.get("context_max_chars", 8000)),
                message_id=int(row["assistant_message_id"]),
                on_embedding_usage=capture_embedding_usage,
            )
            retrieval["trace_ids"] = (
                [str(retrieval["trace_id"])] if retrieval.get("trace_id") else []
            )
            retrieval["knowledge_base_count"] = 1
            retrieval["mode"] = "knowledge_base"
        # 正式检索通过回调上报用量；同时读取返回值，兼容已有服务替身和未启用回调的调用者。
        raw_embedding_usage = retrieval.get("embedding_usage")
        raw_embedding_model = retrieval.get("embedding_model")
        if isinstance(raw_embedding_usage, Mapping) and raw_embedding_model:
            embedding_usage_by_operation.setdefault("single", {})[
                str(raw_embedding_model)
            ] = dict(raw_embedding_usage)
        await persist_quota_progress()
        yield sse_event(
            "retrieval",
            {
                "state": retrieval["state"],
                "trace_id": retrieval["trace_id"],
                "trace_ids": retrieval["trace_ids"],
                "evidence_count": len(retrieval["items"]),
                "knowledge_base_count": retrieval["knowledge_base_count"],
                "mode": retrieval["mode"],
            },
        )
        await _persist_evidence(
            connection,
            tenant_id=int(row["tenant_id"]),
            assistant_message_id=int(row["assistant_message_id"]),
            evidence=retrieval["items"],
        )
        trace_timings["pipeline_retrieval_ms"] = round(
            (time.perf_counter() - retrieval_started_at) * 1000, 2
        )
        await _persist_retrieval_trace_timings(
            connection,
            tenant_id=int(row["tenant_id"]),
            assistant_message_id=int(row["assistant_message_id"]),
            timings=trace_timings,
        )
        cancelled_after_retrieval = await connection.fetchval(
            """
            SELECT state = 'cancelled' OR cancel_requested
            FROM generation_runs WHERE id = $1 AND tenant_id = $2
            """,
            run_id,
            row["tenant_id"],
        )
        if cancelled_after_retrieval:
            await finalize_quota("cancelled")
            latest = await load_run_snapshot(
                connection,
                run_id=run_id,
                user_id=user_id,
                api_key_tenant_id=api_key_tenant_id,
                api_key_id=api_key_id,
            )
            yield sse_event("cancelled", {"run": latest})
            return
        if retrieval["state"] not in {"completed", "skipped"}:
            outcome = "index_not_ready" if retrieval["state"] == "index_not_ready" else "no_answer"
            content = (
                "当前知识库索引尚未就绪，暂时无法回答。"
                if outcome == "index_not_ready"
                else NO_ANSWER_TEXT
            )
            usage = current_usage()[0]
            answer_persist_started_at = time.perf_counter()
            completed = await _finish_without_generation(
                connection,
                run_id=run_id,
                assistant_message_id=int(row["assistant_message_id"]),
                tenant_id=int(row["tenant_id"]),
                content=content,
                outcome=outcome,
                release_id=(int(row["release_id"]) if row["release_id"] is not None else None),
                trace_id=retrieval["trace_id"],
                trace_ids=retrieval["trace_ids"],
                usage=usage,
            )
            await finalize_quota("completed" if completed else "cancelled")
            trace_timings["answer_persist_ms"] = round(
                (time.perf_counter() - answer_persist_started_at) * 1000, 2
            )
            trace_timings["pipeline_total_ms"] = round(
                (time.perf_counter() - run_started_at) * 1000, 2
            )
            await _persist_retrieval_trace_timings(
                connection,
                tenant_id=int(row["tenant_id"]),
                assistant_message_id=int(row["assistant_message_id"]),
                timings=trace_timings,
            )
            latest = await load_run_snapshot(
                connection,
                run_id=run_id,
                user_id=user_id,
                api_key_tenant_id=api_key_tenant_id,
                api_key_id=api_key_id,
            )
            yield sse_event("done" if completed else "cancelled", {"run": latest})
            return

        if retrieval["state"] == "skipped":
            messages = build_general_assistant_messages(str(snapshot["question"]), history)
        else:
            messages = build_grounded_messages(
                str(snapshot["question"]),
                retrieval["context"],
                str(runtime_definition.get("answer_rules", "")),
                history,
            )
        generation_model = client.settings.generation_model
        effective_max_tokens = (
            max_tokens if max_tokens is not None else client.settings.generation_max_tokens
        )
        effective_temperature = float(generation_definition.get("temperature", 0.2))
        prompt_tokens_estimate = sum(
            estimate_token_count(item.get("content", "")) for item in messages
        )
        if api_key_id is not None:
            # 生成输入按 UTF-8 字节预扣，并额外锁定 max_tokens 输出上限。
            reserved_tokens += await reserve_api_key_tokens(
                connection,
                api_key_id=api_key_id,
                run_id=run_id,
                requested_tokens=sum(
                    len(item.get("content", "").encode("utf-8")) for item in messages
                )
                + effective_max_tokens,
            )
        generation_started = True
        await persist_quota_progress()
        generation_request_started_at = time.perf_counter()
        async for event in client.stream_chat_events(
            messages,
            temperature=effective_temperature,
            # 普通网页登录和客户 API Key 都必须遵守服务端输出上限，避免网关默认预算拖长生成。
            max_tokens=effective_max_tokens,
        ):
            if event["usage"] is not None:
                gateway_usage = {**event["usage"], "usage_source": "gateway"}
                await persist_quota_progress()
                continue
            token = event["text"]
            if not token:
                continue
            if first_token_at is None:
                first_token_at = time.perf_counter()
            if len(generated_parts) == 0 or len(generated_parts) % 5 == 0:
                cancelled = await connection.fetchval(
                    """
                    SELECT state = 'cancelled' OR cancel_requested
                    FROM generation_runs WHERE id = $1 AND tenant_id = $2
                    """,
                    run_id,
                    row["tenant_id"],
                )
                if cancelled:
                    usage = current_usage()[0]
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
                        UPDATE messages SET content = $3, state = 'cancelled', usage = $4::jsonb
                        WHERE id = $1 AND tenant_id = $2
                        """,
                        row["assistant_message_id"],
                        row["tenant_id"],
                        "".join(generated_parts),
                        json.dumps(usage, ensure_ascii=False),
                    )
                    await finalize_quota("cancelled")
                    if generation_request_started_at is not None:
                        generation_finished_at = time.perf_counter()
                        trace_timings["generation_stream_ms"] = round(
                            (generation_finished_at - generation_request_started_at) * 1000,
                            2,
                        )
                        if first_token_at is not None:
                            trace_timings["generation_ttft_ms"] = round(
                                (first_token_at - generation_request_started_at) * 1000, 2
                            )
                    trace_timings["pipeline_total_ms"] = round(
                        (time.perf_counter() - run_started_at) * 1000, 2
                    )
                    await _persist_retrieval_trace_timings(
                        connection,
                        tenant_id=int(row["tenant_id"]),
                        assistant_message_id=int(row["assistant_message_id"]),
                        timings=trace_timings,
                    )
                    latest = await load_run_snapshot(
                        connection,
                        run_id=run_id,
                        user_id=user_id,
                        api_key_tenant_id=api_key_tenant_id,
                        api_key_id=api_key_id,
                    )
                    yield sse_event("cancelled", {"run": latest})
                    return
            generated_parts.append(token)
            if len(generated_parts) % 5 == 0:
                await persist_quota_progress()
            # 知识库答案只有完成引用与拒答校验后才能发送，否则流式客户端无法撤回未验证正文。
            if retrieval["state"] == "skipped":
                yield sse_event("token", {"text": token})

        await persist_quota_progress()
        generation_finished_at = time.perf_counter()
        if generation_request_started_at is not None:
            trace_timings["generation_stream_ms"] = round(
                (generation_finished_at - generation_request_started_at) * 1000, 2
            )
            if first_token_at is not None:
                trace_timings["generation_ttft_ms"] = round(
                    (first_token_at - generation_request_started_at) * 1000, 2
                )
        valid_numbers = {
            int(item["evidence_no"])
            for item in retrieval["items"]
            if item.get("context_included") and item.get("evidence_no") is not None
        }
        if retrieval["state"] == "skipped":
            content = validate_general_answer("".join(generated_parts))
            cited_numbers: list[int] = []
            outcome = "answered"
        else:
            content, cited_numbers, outcome = validate_generated_answer(
                "".join(generated_parts),
                valid_numbers,
            )
        usage = current_usage()[0]
        answer_persist_started_at = time.perf_counter()
        completed = await _persist_completed_answer(
            connection,
            run_id=run_id,
            tenant_id=int(row["tenant_id"]),
            assistant_message_id=int(row["assistant_message_id"]),
            release_id=(int(row["release_id"]) if row["release_id"] is not None else None),
            content=content,
            outcome=outcome,
            cited_numbers=cited_numbers,
            evidence=retrieval["items"],
            trace_id=retrieval["trace_id"],
            trace_ids=retrieval["trace_ids"],
            usage=usage,
        )
        await finalize_quota("completed" if completed else "cancelled")
        trace_timings["answer_persist_ms"] = round(
            (time.perf_counter() - answer_persist_started_at) * 1000, 2
        )
        trace_timings["pipeline_total_ms"] = round(
            (time.perf_counter() - run_started_at) * 1000, 2
        )
        await _persist_retrieval_trace_timings(
            connection,
            tenant_id=int(row["tenant_id"]),
            assistant_message_id=int(row["assistant_message_id"]),
            timings=trace_timings,
        )
        latest = await load_run_snapshot(
            connection,
            run_id=run_id,
            user_id=user_id,
            api_key_tenant_id=api_key_tenant_id,
            api_key_id=api_key_id,
        )
        if completed and retrieval["state"] != "skipped" and content:
            yield sse_event("token", {"text": content})
        yield sse_event("done" if completed else "cancelled", {"run": latest})
    except asyncio.CancelledError:
        usage = await finalize_quota("failed")
        if row is not None:
            await _mark_failed(
                connection,
                run_id=run_id,
                tenant_id=int(row["tenant_id"]),
                assistant_message_id=int(row["assistant_message_id"]),
                code="STREAM_DISCONNECTED",
                usage=usage,
            )
        raise
    except ApiKeyQuotaExceededError:
        usage = await finalize_quota("failed")
        if row is not None:
            await _mark_failed(
                connection,
                run_id=run_id,
                tenant_id=int(row["tenant_id"]),
                assistant_message_id=int(row["assistant_message_id"]),
                code="TOKEN_QUOTA_EXCEEDED",
                usage=usage,
            )
        yield sse_event(
            "error",
            {
                "code": "TOKEN_QUOTA_EXCEEDED",
                "message": "API Key Token 额度不足，请联系公司管理员。",
                "retryable": False,
            },
        )
    except (httpx.HTTPError, ValueError, RetrievalServiceError, asyncpg.PostgresError) as error:
        usage = await finalize_quota("failed")
        if row is not None:
            await _mark_failed(
                connection,
                run_id=run_id,
                tenant_id=int(row["tenant_id"]),
                assistant_message_id=int(row["assistant_message_id"]),
                code=type(error).__name__.upper(),
                usage=usage,
            )
        yield sse_event(
            "error",
            {"code": "GENERATION_FAILED", "message": "问答生成失败，可以重试。", "retryable": True},
        )
    except Exception as error:
        logger.exception("问答运行出现未预期异常", exc_info=error)
        usage = await finalize_quota("failed")
        if row is not None:
            await _mark_failed(
                connection,
                run_id=run_id,
                tenant_id=int(row["tenant_id"]),
                assistant_message_id=int(row["assistant_message_id"]),
                code="UNEXPECTED_GENERATION_ERROR",
                usage=usage,
            )
        yield sse_event(
            "error",
            {"code": "GENERATION_FAILED", "message": "问答生成失败，可以重试。", "retryable": True},
        )
    finally:
        await connection.close()
