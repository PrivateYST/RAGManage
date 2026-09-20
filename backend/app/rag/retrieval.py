"""基于当前 Release 的正式向量检索与证据组装。"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Sequence
from typing import Any

import asyncpg
import httpx

from app.core.config import Settings
from app.rag.models import ModelGatewayClient
from app.rag.profiles import gateway_settings


class RetrievalServiceError(RuntimeError):
    """模型网关暂时无法完成检索，并携带已落库的诊断 Trace 标识。"""

    def __init__(self, message: str, *, trace_id: int | None = None) -> None:
        """保存对外稳定消息和可审计 Trace；不得把网关原始响应传入 message。"""
        super().__init__(message)
        self.trace_id = trace_id


_CJK_RUN_PATTERN = re.compile(r"[\u3400-\u9fff]+")
_LATIN_TERM_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]*")
_LEXICAL_STOP_TERMS = {
    "一个",
    "什么",
    "哪些",
    "如何",
    "当前",
    "怎么",
    "是否",
    "这个",
    "这些",
    "那个",
}
_RRF_K = 60


def _vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(format(value, ".9g") for value in vector) + "]"


def _json_value(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return value


def _elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 2)


def _normalized_content_key(content: str) -> str:
    normalized = " ".join(content.split()).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _lexical_terms(query: str) -> list[str]:
    """提取可用于中英文精确召回的有限关键词，避免把整句中文当成单个词。"""
    terms: list[str] = []
    seen: set[str] = set()

    def append(term: str) -> None:
        normalized = term.casefold().strip()
        if len(normalized) < 2 or normalized in _LEXICAL_STOP_TERMS or normalized in seen:
            return
        seen.add(normalized)
        terms.append(normalized)

    for term in _LATIN_TERM_PATTERN.findall(query):
        append(term)
    for run in _CJK_RUN_PATTERN.findall(query):
        if len(run) <= 4:
            append(run)
        for size in (2, 3, 4):
            for start in range(len(run) - size + 1):
                append(run[start : start + size])
    return terms[:32]


def _locator_label(locator: dict[str, Any]) -> str:
    if "page" in locator:
        return f"第 {locator['page']} 页"
    if "line_start" in locator:
        end = locator.get("line_end", locator["line_start"])
        return f"第 {locator['line_start']}–{end} 行"
    if "char_start" in locator:
        end = locator.get("char_end", locator["char_start"])
        return f"字符 {locator['char_start']}–{end}"
    return "原文片段"


def assemble_evidence(
    candidates: Sequence[dict[str, Any]],
    *,
    context_max_chars: int,
) -> tuple[list[dict[str, Any]], str]:
    """按相关度去重候选，并组装带稳定证据编号的上下文。"""
    unique: list[dict[str, Any]] = []
    seen_chunk_ids: set[str] = set()
    seen_contents: set[str] = set()
    for candidate in candidates:
        chunk_id = str(candidate["chunk_id"])
        content = str(candidate["content"]).strip()
        content_key = _normalized_content_key(content)
        if chunk_id in seen_chunk_ids or content_key in seen_contents:
            continue
        seen_chunk_ids.add(chunk_id)
        seen_contents.add(content_key)
        item = dict(candidate)
        item["rank"] = len(unique) + 1
        item["content"] = content
        item["section_path"] = _json_value(item.get("section_path"), [])
        item["locator"] = _json_value(item.get("locator"), {})
        item["context_included"] = False
        item["evidence_no"] = None
        unique.append(item)

    context_parts: list[str] = []
    used_chars = 0
    evidence_no = 0
    for item in unique:
        section_path = " / ".join(str(part) for part in item["section_path"] if part)
        source = f"{item['document_title']} · v{item['version_no']}"
        if section_path:
            source += f" · {section_path}"
        source += f" · {_locator_label(item['locator'])}"
        next_evidence_no = evidence_no + 1
        prefix = f"[证据 {next_evidence_no}] {source}\n"
        available = context_max_chars - used_chars - len(prefix)
        if available <= 0:
            break
        content = str(item["content"])
        if len(content) > available:
            if evidence_no > 0:
                continue
            content = content[: max(0, available - 1)].rstrip() + "…"
        block = prefix + content
        context_parts.append(block)
        used_chars += len(block) + 2
        evidence_no = next_evidence_no
        item["context_included"] = True
        item["evidence_no"] = evidence_no

    return unique, "\n\n".join(context_parts)


async def _create_trace(
    connection: asyncpg.Connection,
    *,
    tenant_id: int,
    knowledge_base_id: int,
    user_id: int,
    query: str,
    profiles: dict[str, Any],
    message_id: int | None = None,
) -> int:
    trace_id = await connection.fetchval(
        """
        INSERT INTO retrieval_traces(
          tenant_id, knowledge_base_id, user_id, query, profiles, state, message_id
        ) VALUES ($1, $2, $3, $4, $5::jsonb, 'running', $6)
        RETURNING id
        """,
        tenant_id,
        knowledge_base_id,
        user_id,
        query,
        json.dumps(profiles, ensure_ascii=False),
        message_id,
    )
    return int(trace_id)


async def _finish_trace(
    connection: asyncpg.Connection,
    *,
    trace_id: int,
    tenant_id: int,
    state: str,
    timings: dict[str, float],
    candidates: Sequence[dict[str, Any]] = (),
) -> None:
    async with connection.transaction():
        for candidate in candidates:
            await connection.execute(
                """
                INSERT INTO retrieval_trace_items(
                  tenant_id, trace_id, chunk_id, route, rank, score,
                  fused_rank, rerank_score, in_context
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, NULL, $8)
                """,
                tenant_id,
                trace_id,
                int(candidate["chunk_id"]),
                str(candidate.get("route", "vector")),
                int(candidate["raw_rank"]),
                float(candidate["similarity"]),
                int(candidate.get("fused_rank", candidate["raw_rank"])),
                bool(candidate.get("context_included", False)),
            )
        await connection.execute(
            """
            UPDATE retrieval_traces
            SET state = $2, timings = $3::jsonb
            WHERE id = $1 AND tenant_id = $4
            """,
            trace_id,
            state,
            json.dumps(timings, ensure_ascii=False),
            tenant_id,
        )


async def execute_vector_search(
    connection: asyncpg.Connection,
    settings: Settings,
    *,
    tenant_id: int,
    knowledge_base_id: int,
    user_id: int,
    query: str,
    active_release_id: int | None,
    top_k: int,
    context_max_chars: int,
    gateway: ModelGatewayClient | None = None,
    message_id: int | None = None,
) -> dict[str, Any]:
    """只在已授权空间、知识库和当前 Release 内执行向量与词法融合召回。"""
    total_started = time.perf_counter()
    profiles: dict[str, Any] = {
        "release_id": active_release_id,
        "route": "hybrid_rrf",
        "top_k": top_k,
        "context_max_chars": context_max_chars,
    }
    trace_id = await _create_trace(
        connection,
        tenant_id=tenant_id,
        knowledge_base_id=knowledge_base_id,
        user_id=user_id,
        query=query,
        profiles=profiles,
        message_id=message_id,
    )
    timings: dict[str, float] = {}

    async def terminal(
        state: str,
        message: str,
        *,
        release: dict[str, Any] | None = None,
        source_stats: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        timings["total_ms"] = _elapsed_ms(total_started)
        await _finish_trace(
            connection,
            trace_id=trace_id,
            tenant_id=tenant_id,
            state=state,
            timings=timings,
        )
        return {
            "trace_id": str(trace_id),
            "state": state,
            "message": message,
            "release": release,
            "source_stats": source_stats,
            "filters": [],
            "timings": timings,
            "context": "",
            "items": [],
        }

    if active_release_id is None:
        return await terminal("index_not_ready", "当前知识库还没有已发布的 Release。")

    release_started = time.perf_counter()
    release_row = await connection.fetchrow(
        """
        SELECT kr.id, kr.state, kr.embedding_profile_id, kr.manifest_hash,
               ep.model_name, ep.model_revision, ep.dimension,
               ep.definition_hash AS embedding_definition_hash,
               me.provider, me.base_url, me.allowed_models,
               me.status AS endpoint_status, kb.active_runtime_id,
               rp.embedding_profile_id AS expected_embedding_profile_id
        FROM kb_releases kr
        JOIN embedding_profiles ep ON ep.id = kr.embedding_profile_id
        JOIN model_endpoints me ON me.id = ep.model_endpoint_id
        JOIN knowledge_bases kb ON kb.id = kr.knowledge_base_id
          AND kb.tenant_id = kr.tenant_id
        LEFT JOIN runtime_profiles rp ON rp.id = kb.active_runtime_id
          AND rp.tenant_id = kb.tenant_id AND rp.knowledge_base_id = kb.id
        WHERE kr.id = $1 AND kr.tenant_id = $2 AND kr.knowledge_base_id = $3
        """,
        active_release_id,
        tenant_id,
        knowledge_base_id,
    )
    timings["release_check_ms"] = _elapsed_ms(release_started)
    if release_row is None or release_row["state"] != "ready":
        return await terminal("index_not_ready", "当前 Release 不可用于检索。")

    release = {
        "id": str(release_row["id"]),
        "embedding_profile_id": str(release_row["embedding_profile_id"]),
        "model_name": release_row["model_name"],
        "model_revision": release_row["model_revision"],
        "dimension": int(release_row["dimension"]),
        "manifest_hash": release_row["manifest_hash"],
    }
    endpoint_status = release_row.get("endpoint_status", "active")
    active_runtime_id = release_row.get("active_runtime_id")
    expected_embedding_profile_id = release_row.get("expected_embedding_profile_id")
    if endpoint_status != "active":
        return await terminal(
            "index_not_ready",
            "当前 Release 使用的嵌入模型端点已停用。",
            release=release,
        )
    if (
        active_runtime_id is not None
        and expected_embedding_profile_id != release_row["embedding_profile_id"]
    ):
        return await terminal(
            "index_not_ready",
            "当前 Runtime Profile 已更换嵌入模型，请重新构建并发布。",
            release=release,
        )

    stats_started = time.perf_counter()
    stats_row = await connection.fetchrow(
        """
        SELECT count(DISTINCT ri.document_id)::int AS total_documents,
               count(DISTINCT ri.document_id) FILTER (
                 WHERE d.status = 'active' AND d.deleted_at IS NULL
                   AND dv.parse_status IN ('complete', 'partial')
                   AND da.state IN ('ready', 'partial')
               )::int AS valid_documents,
               count(DISTINCT ri.document_id) FILTER (
                 WHERE d.status <> 'active' OR d.deleted_at IS NOT NULL
                   OR dv.parse_status NOT IN ('complete', 'partial')
                   OR da.state NOT IN ('ready', 'partial')
               )::int AS invalid_documents,
               count(c.id) FILTER (
                 WHERE d.status = 'active' AND d.deleted_at IS NULL
                   AND dv.parse_status IN ('complete', 'partial')
                   AND da.state IN ('ready', 'partial')
               )::int AS valid_chunks,
               count(ce.id) FILTER (
                 WHERE d.status = 'active' AND d.deleted_at IS NULL
                   AND dv.parse_status IN ('complete', 'partial')
                   AND da.state IN ('ready', 'partial')
               )::int AS embedded_chunks
        FROM release_items ri
        JOIN documents d ON d.id = ri.document_id AND d.tenant_id = ri.tenant_id
          AND d.knowledge_base_id = ri.knowledge_base_id
        JOIN document_versions dv ON dv.id = ri.document_version_id
          AND dv.tenant_id = ri.tenant_id AND dv.document_id = ri.document_id
        JOIN document_artifacts da ON da.id = ri.artifact_id
          AND da.tenant_id = ri.tenant_id AND da.knowledge_base_id = ri.knowledge_base_id
          AND da.document_version_id = ri.document_version_id
        LEFT JOIN chunks c ON c.artifact_id = ri.artifact_id
          AND c.tenant_id = ri.tenant_id AND c.knowledge_base_id = ri.knowledge_base_id
        LEFT JOIN chunk_embeddings ce ON ce.chunk_id = c.id
          AND ce.tenant_id = ri.tenant_id AND ce.knowledge_base_id = ri.knowledge_base_id
          AND ce.embedding_profile_id = $4
        WHERE ri.release_id = $1 AND ri.tenant_id = $2 AND ri.knowledge_base_id = $3
        """,
        active_release_id,
        tenant_id,
        knowledge_base_id,
        release_row["embedding_profile_id"],
    )
    timings["source_check_ms"] = _elapsed_ms(stats_started)
    source_stats = {
        "total_documents": int(stats_row["total_documents"] if stats_row else 0),
        "valid_documents": int(stats_row["valid_documents"] if stats_row else 0),
        "invalid_documents": int(stats_row["invalid_documents"] if stats_row else 0),
        "valid_chunks": int(stats_row["valid_chunks"] if stats_row else 0),
        "embedded_chunks": int(stats_row["embedded_chunks"] if stats_row else 0),
    }
    if source_stats["valid_documents"] == 0:
        return await terminal(
            "sources_invalid",
            "当前 Release 中没有仍然有效且已授权的来源。",
            release=release,
            source_stats=source_stats,
        )
    if source_stats["valid_chunks"] == 0 or source_stats["embedded_chunks"] == 0:
        return await terminal(
            "index_not_ready",
            "当前 Release 的切片或向量产物尚未就绪。",
            release=release,
            source_stats=source_stats,
        )

    raw_allowed_models = release_row.get("allowed_models", [str(release_row["model_name"])])
    allowed_models = (
        json.loads(raw_allowed_models)
        if isinstance(raw_allowed_models, str)
        else list(raw_allowed_models)
    )
    effective_settings = gateway_settings(
        settings,
        base_url=str(release_row["base_url"]),
        allowed_models=allowed_models,
        embedding_model=str(release_row["model_name"]),
        embedding_dimensions=int(release_row["dimension"]),
    )
    client = gateway or ModelGatewayClient(effective_settings)
    try:
        revision_started = time.perf_counter()
        current_revision = await client.model_revision(str(release_row["model_name"]))
        timings["model_check_ms"] = _elapsed_ms(revision_started)
        if current_revision != release_row["model_revision"]:
            return await terminal(
                "index_not_ready",
                "嵌入模型内容已经变化，请建立新索引后再检索。",
                release=release,
                source_stats=source_stats,
            )

        embedding_started = time.perf_counter()
        query_vector = (await client.embed([query]))[0]
        timings["embedding_ms"] = _elapsed_ms(embedding_started)
    except (httpx.HTTPError, ValueError) as error:
        timings["total_ms"] = _elapsed_ms(total_started)
        await _finish_trace(
            connection,
            trace_id=trace_id,
            tenant_id=tenant_id,
            state="failed",
            timings=timings,
        )
        raise RetrievalServiceError(
            "模型网关暂时无法生成查询向量。",
            trace_id=trace_id,
        ) from error

    search_started = time.perf_counter()
    lexical_terms = _lexical_terms(query)
    rows = await connection.fetch(
        """
        WITH eligible AS (
          SELECT c.id, c.content, c.section_path, c.locator,
                 d.id AS document_id, d.title AS document_title,
                 dv.id AS document_version_id, dv.version_no,
                 (ce.embedding <=> $5::vector)::double precision AS vector_distance,
                 COALESCE((
                   SELECT sum(char_length(term))::int
                   FROM unnest($7::text[]) AS lexical_terms(term)
                   WHERE lower(c.content || ' ' || d.title || ' ' || c.section_path::text)
                     LIKE '%' || lower(term) || '%'
                 ), 0)::int AS keyword_score
          FROM release_items ri
          JOIN kb_releases kr ON kr.id = ri.release_id
            AND kr.tenant_id = ri.tenant_id AND kr.knowledge_base_id = ri.knowledge_base_id
          JOIN documents d ON d.id = ri.document_id AND d.tenant_id = ri.tenant_id
            AND d.knowledge_base_id = ri.knowledge_base_id
            AND d.status = 'active' AND d.deleted_at IS NULL
          JOIN document_versions dv ON dv.id = ri.document_version_id
            AND dv.tenant_id = ri.tenant_id AND dv.document_id = ri.document_id
            AND dv.parse_status IN ('complete', 'partial')
          JOIN document_artifacts da ON da.id = ri.artifact_id
            AND da.tenant_id = ri.tenant_id AND da.knowledge_base_id = ri.knowledge_base_id
            AND da.document_version_id = ri.document_version_id
            AND da.state IN ('ready', 'partial')
          JOIN chunks c ON c.artifact_id = ri.artifact_id
            AND c.tenant_id = ri.tenant_id AND c.knowledge_base_id = ri.knowledge_base_id
          JOIN chunk_embeddings ce ON ce.chunk_id = c.id
            AND ce.tenant_id = ri.tenant_id AND ce.knowledge_base_id = ri.knowledge_base_id
            AND ce.embedding_profile_id = kr.embedding_profile_id
          WHERE ri.release_id = $1 AND ri.tenant_id = $2 AND ri.knowledge_base_id = $3
            AND kr.id = $1 AND kr.state = 'ready' AND kr.embedding_profile_id = $4
        ), ranked AS (
          SELECT eligible.*,
                 row_number() OVER (ORDER BY vector_distance, id) AS vector_rank,
                 CASE WHEN keyword_score > 0 THEN
                   row_number() OVER (
                     ORDER BY (keyword_score > 0) DESC, keyword_score DESC, vector_distance, id
                   )
                 END AS lexical_rank
          FROM eligible
        ), fused AS (
          SELECT ranked.*,
                 (
                   1.0 / ($8 + vector_rank)
                   + CASE WHEN lexical_rank IS NOT NULL THEN 1.0 / ($8 + lexical_rank) ELSE 0 END
                 )::double precision AS fused_score
          FROM ranked
        )
        SELECT id::text AS chunk_id, content, section_path, locator,
               document_id::text AS document_id, document_title,
               document_version_id::text AS document_version_id, version_no,
               (1 - vector_distance)::double precision AS similarity,
               vector_rank::int, lexical_rank::int, keyword_score,
               fused_score,
               CASE WHEN lexical_rank IS NOT NULL THEN 'hybrid' ELSE 'vector' END AS route
        FROM fused
        ORDER BY fused_score DESC, vector_distance, id
        LIMIT $6
        """,
        active_release_id,
        tenant_id,
        knowledge_base_id,
        release_row["embedding_profile_id"],
        _vector_literal(query_vector),
        top_k,
        lexical_terms,
        _RRF_K,
    )
    timings["hybrid_search_ms"] = _elapsed_ms(search_started)
    timings["vector_search_ms"] = timings["hybrid_search_ms"]
    raw_candidates = [
        {
            **dict(row),
            "raw_rank": int(row.get("vector_rank", index)),
            "vector_rank": int(row.get("vector_rank", index)),
            "lexical_rank": (
                int(row["lexical_rank"]) if row.get("lexical_rank") is not None else None
            ),
            "keyword_score": int(row.get("keyword_score", 0)),
            "fused_score": round(float(row.get("fused_score", 0)), 8),
            "fused_rank": index,
            "route": str(row.get("route", "vector")),
            "similarity": round(float(row["similarity"]), 6),
        }
        for index, row in enumerate(rows, start=1)
    ]
    items, context = assemble_evidence(raw_candidates, context_max_chars=context_max_chars)
    state = "completed" if items else "no_results"
    message = (
        f"已从当前 Release 召回 {len(items)} 条去重证据。"
        if items
        else "当前 Release 中没有找到相关证据。"
    )
    timings["total_ms"] = _elapsed_ms(total_started)
    raw_by_chunk = {str(item["chunk_id"]): item for item in items}
    trace_candidates = []
    for candidate in raw_candidates:
        enriched = dict(candidate)
        matched = raw_by_chunk.get(str(candidate["chunk_id"]))
        enriched["context_included"] = bool(matched and matched["context_included"])
        trace_candidates.append(enriched)
    await _finish_trace(
        connection,
        trace_id=trace_id,
        tenant_id=tenant_id,
        state=state,
        timings=timings,
        candidates=trace_candidates,
    )
    filters = [
        {"name": "空间范围", "value": str(tenant_id), "filtered_count": 0},
        {"name": "知识库范围", "value": str(knowledge_base_id), "filtered_count": 0},
        {"name": "当前 Release", "value": str(active_release_id), "filtered_count": 0},
        {
            "name": "有效来源",
            "value": f"{source_stats['valid_documents']}/{source_stats['total_documents']} 份文档",
            "filtered_count": source_stats["invalid_documents"],
        },
    ]
    return {
        "trace_id": str(trace_id),
        "state": state,
        "message": message,
        "release": release,
        "source_stats": source_stats,
        "filters": filters,
        "timings": timings,
        "context": context,
        "items": items,
    }
