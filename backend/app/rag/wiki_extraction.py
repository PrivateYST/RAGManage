"""从当前发布原文的明确章节提取可审核草稿，不推测实体或补写企业事实。"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

import asyncpg
from fastapi import HTTPException
from pydantic import BaseModel, Field


class WikiExtractionRequest(BaseModel):
    """预览只针对一份当前发布文档，限制范围以保证来源与版本可追溯。"""

    document_id: int = Field(gt=0)


class WikiExtractionImport(WikiExtractionRequest):
    """导入携带预览版本和稳定候选键，服务端重新抽取，禁止客户端伪造来源。"""

    release_id: int = Field(gt=0)
    document_version_id: int = Field(gt=0)
    candidate_keys: list[str] = Field(min_length=1, max_length=40)
    owner_user_id: int | None = Field(default=None, gt=0)


def normalized_term(term: str) -> str:
    """全半角和空格不构成新概念，用于批量导入的幂等去重。"""
    compact = re.sub(r"\s+", "", unicodedata.normalize("NFKC", term)).casefold()
    return re.sub(r"规范$", "", compact)


def extract_candidates(chunks: list[dict[str, Any]], document_title: str) -> list[dict[str, Any]]:
    """使用明确 Markdown 标题或 PDF 规范章节分组；每条证据最多30片段并提示截断。"""
    if not chunks:
        return []
    headings: list[tuple[int, str]] = []
    for index, chunk in enumerate(chunks):
        lines = str(chunk["content"]).strip().splitlines()
        first = lines[0].strip() if lines else ""
        markdown = re.match(r"^#{1,4}\s+(.+)$", first)
        # 只识别页首的正式章节，目录中的点线/页号和正文提及不当作新词条。
        formal = re.fullmatch(r".{2,100}(?:服务规范|健康管理服务)", first)
        if markdown or (formal and not re.search(r"[.。…]{2,}", first)):
            term = markdown.group(1).strip() if markdown else first
            if 2 <= len(term) <= 200:
                headings.append((index, term))
    if not headings:
        headings = [(0, document_title[:200])]
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for offset, (start, term) in enumerate(headings):
        normalized = normalized_term(term)
        if normalized in seen:
            continue
        seen.add(normalized)
        end = headings[offset + 1][0] if offset + 1 < len(headings) else len(chunks)
        section = chunks[start:end]
        sources = section[:30]
        text = "\n".join(str(chunk["content"]).strip() for chunk in sources)
        key = hashlib.sha256(
            f"{sources[0]['document_version_id']}:{sources[0]['chunk_id']}:{term}".encode()
        ).hexdigest()[:24]
        short = re.sub(r"(?:服务)?规范$", "", term).strip()
        result.append(
            {
                "key": key,
                "term": term,
                "definition": text[:1200],
                "aliases": [short] if short != term and len(short) >= 2 else [],
                "sources": sources,
                "warning": "本章节超过30个片段，已截取前30个；请审核来源覆盖范围。"
                if len(section) > 30
                else "",
            }
        )
    return result[:40]


async def preview_extraction(
    connection: asyncpg.Connection, tenant_id: int, kb_id: int, document_id: int
) -> dict[str, Any]:
    """只读取本空间、本库、当前发布且可用的原文；不读取上传后尚未发布的新版本。"""
    document = await connection.fetchrow(
        """SELECT kb.active_release_id, d.title, dv.id AS document_version_id
           FROM knowledge_bases kb JOIN release_items ri
             ON ri.release_id=kb.active_release_id AND ri.tenant_id=kb.tenant_id
             AND ri.knowledge_base_id=kb.id
           JOIN documents d ON d.id=ri.document_id AND d.tenant_id=kb.tenant_id
             AND d.knowledge_base_id=kb.id AND d.status='active' AND d.deleted_at IS NULL
           JOIN document_versions dv ON dv.id=ri.document_version_id
             AND dv.parse_status IN ('complete','partial')
           JOIN document_artifacts da ON da.id=ri.artifact_id AND da.state IN ('ready','partial')
           WHERE kb.id=$1 AND kb.tenant_id=$2 AND d.id=$3""",
        kb_id,
        tenant_id,
        document_id,
    )
    if not document:
        raise HTTPException(404, "文档不在当前知识库发布版本中或来源已失效")
    rows = await connection.fetch(
        """SELECT c.id::text AS chunk_id, c.content, c.locator,
                  d.id::text AS document_id, d.title AS document_title,
                  dv.id::text AS document_version_id, dv.version_no
           FROM release_items ri JOIN chunks c ON c.artifact_id=ri.artifact_id
             AND c.tenant_id=ri.tenant_id AND c.knowledge_base_id=ri.knowledge_base_id
           JOIN documents d ON d.id=ri.document_id
           JOIN document_versions dv ON dv.id=ri.document_version_id
           WHERE ri.release_id=$1 AND ri.tenant_id=$2 AND ri.knowledge_base_id=$3
             AND ri.document_id=$4 ORDER BY c.ordinal LIMIT 601""",
        document["active_release_id"],
        tenant_id,
        kb_id,
        document_id,
    )
    # 限制单次文档规模，避免请求耗尽内存；禁止静默声称整份超大文档已处理。
    if len(rows) > 600:
        raise HTTPException(400, "该文档超过600个片段，请拆分文档后再生成词条")
    chunks = [dict(row) for row in rows]
    for chunk in chunks:
        if isinstance(chunk["locator"], str):
            chunk["locator"] = json.loads(chunk["locator"])
    existing = await connection.fetch(
        "SELECT term FROM wiki_entries WHERE tenant_id=$1 AND knowledge_base_id=$2",
        tenant_id,
        kb_id,
    )
    known = {normalized_term(row["term"]) for row in existing}
    candidates = extract_candidates(chunks, document["title"])
    for item in candidates:
        item["existing"] = normalized_term(item["term"]) in known
        # 原文只返回可预览摘要，内部片段 ID 在导入时由服务端重新验证。
        for source in item["sources"]:
            source["content"] = source["content"][:500]
    return {
        "release_id": str(document["active_release_id"]),
        "document_version_id": str(document["document_version_id"]),
        "document_title": document["title"],
        "method": "document_sections",
        "items": candidates,
        "notice": "按明确章节抽取原文，最多40条候选；内容与别名须人工审核后发布。",
    }
