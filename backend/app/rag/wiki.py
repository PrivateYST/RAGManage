"""LLM Wiki 的验证、版本快照与查询扩展；词条只引导检索，原文仍是回答证据。"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping
from datetime import date
from typing import Any, Literal

import asyncpg
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class WikiSource(BaseModel):
    """关联同库的原文切片；文档、版本和页码由服务端推导，避免手填错配。"""

    chunk_id: int = Field(gt=0)
    note: str = Field(default="", max_length=500)


class WikiContent(BaseModel):
    """完整词条编辑契约；替换内容时必须携带版本号以防覆盖其他人的修改。"""

    model_config = ConfigDict(extra="forbid")
    term: str = Field(min_length=2, max_length=200)
    definition: str = Field(min_length=1, max_length=10000)
    aliases: list[str] = Field(default_factory=list, max_length=30)
    owner_user_id: int | None = Field(default=None, gt=0)
    valid_from: date | None = None
    valid_until: date | None = None
    sources: list[WikiSource] = Field(default_factory=list, max_length=30)
    expected_version: int | None = Field(default=None, gt=0)

    @field_validator("term", "definition")
    @classmethod
    def strip_required(cls, value: str) -> str:
        """空白名称/定义没有业务含义，不能通过长度校验绕过。"""
        if not value.strip():
            raise ValueError("词条名称和定义不能为空白")
        return value.strip()

    @field_validator("aliases")
    @classmethod
    def clean_aliases(cls, values: list[str]) -> list[str]:
        """过滤重复别名并限制单个别名长度，避免检索扩展无限膨胀。"""
        result = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if any(len(value) < 2 or len(value) > 200 for value in result):
            raise ValueError("别名长度须为 2～200 个字符")
        return result

    @model_validator(mode="after")
    def validate_period(self) -> WikiContent:
        """拒绝反向有效期以及重复来源。"""
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("截止日不能早于起始日")
        if len({source.chunk_id for source in self.sources}) != len(self.sources):
            raise ValueError("不能重复关联同一切片")
        return self


class WikiTransition(BaseModel):
    """显式状态迁移；每次操作校验版本，避免旧页面重复发布。"""

    status: Literal["draft", "review", "published", "retired"]
    expected_version: int = Field(gt=0)


def validate_transition(current: str, target: str) -> None:
    """允许草稿直发、审核发布/退回、发布停用和停用后重新启用。"""
    allowed = {
        "draft": {"review", "published"},
        "review": {"published", "draft"},
        "published": {"retired"},
        "retired": {"draft", "published"},
    }
    if target not in allowed.get(current, set()):
        raise HTTPException(409, "当前词条状态不支持该操作，请刷新后重试")


async def validate_content(
    connection: asyncpg.Connection,
    tenant_id: int,
    knowledge_base_id: int,
    payload: WikiContent,
) -> list[dict[str, Any]]:
    """校验有效负责人和同库可用证据，返回服务端推导的来源版本与页码。"""
    if payload.owner_user_id is not None and not await connection.fetchval(
        """SELECT EXISTS(SELECT 1 FROM tenant_members tm JOIN users u ON u.id=tm.user_id
           WHERE tm.tenant_id=$1 AND tm.user_id=$2 AND tm.status='active'
             AND u.status='active')""",
        tenant_id,
        payload.owner_user_id,
    ):
        raise HTTPException(400, "负责人不是当前空间有效成员")
    sources = []
    for source in payload.sources:
        row = await connection.fetchrow(
            """SELECT c.id::text AS chunk_id, d.id::text AS document_id,
                      dv.id::text AS document_version_id, d.title AS document_title,
                      dv.version_no, c.locator, c.content
               FROM chunks c JOIN document_artifacts da ON da.id=c.artifact_id
                 AND da.tenant_id=c.tenant_id AND da.knowledge_base_id=c.knowledge_base_id
               JOIN document_versions dv ON dv.id=da.document_version_id
                 AND dv.tenant_id=c.tenant_id
               JOIN documents d ON d.id=dv.document_id AND d.tenant_id=c.tenant_id
                 AND d.knowledge_base_id=c.knowledge_base_id
               WHERE c.id=$1 AND c.tenant_id=$2 AND c.knowledge_base_id=$3
                 AND d.status='active' AND d.deleted_at IS NULL
                 AND dv.parse_status IN ('complete','partial')
                 AND da.state IN ('ready','partial')""",
            source.chunk_id,
            tenant_id,
            knowledge_base_id,
        )
        if row is None:
            raise HTTPException(400, "来源不存在、已失效或不属于当前知识库")
        sources.append({**dict(row), "note": source.note})
    return sources


async def load_entry(connection: asyncpg.Connection, entry_id: int) -> dict[str, Any]:
    """读取完整词条及关联；调用方必须先完成知识库鉴权。"""
    row = await connection.fetchrow("SELECT * FROM wiki_entries WHERE id=$1", entry_id)
    if row is None:
        raise HTTPException(404, "词条不存在")
    aliases = await connection.fetch(
        "SELECT alias FROM wiki_aliases WHERE entry_id=$1 ORDER BY alias",
        entry_id,
    )
    sources = await connection.fetch(
        """SELECT s.chunk_id::text, s.document_id::text, s.document_version_id::text,
                  s.note, d.title AS document_title, dv.version_no, c.locator,
                  left(c.content, 500) AS content
           FROM wiki_entry_sources s LEFT JOIN documents d ON d.id=s.document_id
           LEFT JOIN document_versions dv ON dv.id=s.document_version_id
           LEFT JOIN chunks c ON c.id=s.chunk_id WHERE s.entry_id=$1 ORDER BY s.id""",
        entry_id,
    )
    result = dict(row)
    for field in ("id", "tenant_id", "knowledge_base_id", "owner_user_id", "created_by"):
        if result.get(field) is not None:
            result[field] = str(result[field])
    result["aliases"] = [alias["alias"] for alias in aliases]
    result["sources"] = [dict(source) for source in sources]
    for source in result["sources"]:
        if isinstance(source["locator"], str):
            source["locator"] = json.loads(source["locator"])
    return result


async def replace_links(
    connection: asyncpg.Connection,
    entry_id: int,
    payload: WikiContent,
    sources: list[dict[str, Any]],
) -> None:
    """在调用方事务内替换别名和来源，保证内容、证据与快照一致。"""
    await connection.execute("DELETE FROM wiki_aliases WHERE entry_id=$1", entry_id)
    for alias in payload.aliases:
        await connection.execute(
            "INSERT INTO wiki_aliases(entry_id, alias) VALUES($1,$2)",
            entry_id,
            alias,
        )
    await connection.execute("DELETE FROM wiki_entry_sources WHERE entry_id=$1", entry_id)
    for source in sources:
        await connection.execute(
            """INSERT INTO wiki_entry_sources(
                 entry_id,document_id,document_version_id,chunk_id,note)
               VALUES($1,$2,$3,$4,$5)""",
            entry_id,
            int(source["document_id"]),
            int(source["document_version_id"]),
            int(source["chunk_id"]),
            source["note"],
        )


async def save_revision(
    connection: asyncpg.Connection,
    entry_id: int,
    actor_id: int,
    action: str,
) -> dict[str, Any]:
    """保存不可变的完整修订快照；状态变更也占用独立版本号。"""
    entry = await load_entry(connection, entry_id)
    await connection.execute(
        """INSERT INTO wiki_entry_revisions(entry_id,version_no,action,snapshot,actor_id)
           VALUES($1,$2,$3,$4::jsonb,$5)""",
        entry_id,
        entry["version_no"],
        action,
        json.dumps(entry, default=str, ensure_ascii=False),
        actor_id,
    )
    return entry


def match_entries(query: str, entries: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """最长名称优先，最多使用三个词条；短英文别名须整词命中避免意外扩展。"""
    normalized = unicodedata.normalize("NFKC", query).casefold()
    matches = []
    for entry in entries:
        names = [str(entry["term"]), *list(entry.get("aliases") or [])]
        hits = []
        for name in names:
            name = unicodedata.normalize("NFKC", name).casefold().strip()
            if len(name) < 2:
                continue
            hit = (
                re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", normalized)
                if name.isascii()
                else name in normalized
            )
            if hit:
                hits.append(len(name))
        if hits:
            matches.append((max(hits), dict(entry)))
    matches.sort(key=lambda item: (-item[0], int(item[1]["id"])))
    return [entry for _, entry in matches[:3]]


async def lookup_entries(
    connection: asyncpg.Connection,
    *,
    tenant_id: int,
    knowledge_base_id: int,
    release_id: int,
    query: str,
) -> list[dict[str, Any]]:
    """只匹配已发布、有效期内且原文仍在当前 Release 的词条，禁止旧来源绕过过滤。"""
    rows = await connection.fetch(
        """SELECT e.id::text, e.term, e.version_no,
                  ARRAY(SELECT alias FROM wiki_aliases WHERE entry_id=e.id) AS aliases,
                  array_agg(DISTINCT s.chunk_id) AS chunk_ids
           FROM wiki_entries e JOIN wiki_entry_sources s ON s.entry_id=e.id
           JOIN chunks c ON c.id=s.chunk_id AND c.tenant_id=e.tenant_id
             AND c.knowledge_base_id=e.knowledge_base_id
           JOIN release_items ri ON ri.artifact_id=c.artifact_id AND ri.release_id=$3
             AND ri.tenant_id=e.tenant_id AND ri.knowledge_base_id=e.knowledge_base_id
             AND ri.document_version_id=s.document_version_id
           JOIN documents d ON d.id=s.document_id AND d.tenant_id=e.tenant_id
             AND d.status='active' AND d.deleted_at IS NULL
           JOIN document_artifacts da ON da.id=c.artifact_id AND da.state IN ('ready','partial')
           JOIN document_versions dv ON dv.id=s.document_version_id
             AND dv.parse_status IN ('complete','partial')
           WHERE e.tenant_id=$1 AND e.knowledge_base_id=$2 AND e.status='published'
             AND (e.valid_from IS NULL OR e.valid_from <= CURRENT_DATE)
             AND (e.valid_until IS NULL OR e.valid_until >= CURRENT_DATE)
           GROUP BY e.id""",
        tenant_id,
        knowledge_base_id,
        release_id,
    )
    return match_entries(query, rows)
