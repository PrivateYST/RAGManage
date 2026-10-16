"""LLM Wiki 管理接口；复用知识库权限，事务内提交内容、版本快照和审计。"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import asyncpg
from fastapi import FastAPI, HTTPException, Query, Request

from app.core.audit import write_audit_event
from app.core.config import Settings
from app.rag.wiki import (
    WikiContent,
    WikiTransition,
    load_entry,
    replace_links,
    save_revision,
    validate_content,
    validate_transition,
)
from app.rag.wiki_extraction import (
    WikiExtractionImport,
    WikiExtractionRequest,
    preview_extraction,
)


def register(app: FastAPI, config: Settings) -> None:
    """注册词条接口；延迟读取 main 以保持既有鉴权替身与应用工厂兼容。"""
    from app import main

    async def authorize(
        connection: asyncpg.Connection,
        context: dict[str, Any],
        kb_id: int,
        *,
        write: bool = False,
    ) -> dict[str, Any]:
        """客户 API Key 无权编辑；读取和写入分别遵循现有 KB 成员权限。"""
        if write:
            return await main._require_knowledge_base_role(
                connection,
                context,
                kb_id,
                {"space_admin", "kb_admin"},
            )
        return await main._knowledge_base_access(connection, context, kb_id)

    async def authorized_entry(
        connection: asyncpg.Connection,
        context: dict[str, Any],
        entry_id: int,
        *,
        write: bool = False,
    ) -> dict[str, Any]:
        """先鉴权再返回内容；不存在或越权始终由现有 KB 授权机制隐藏。"""
        row = await connection.fetchrow(
            "SELECT id, knowledge_base_id FROM wiki_entries WHERE id=$1",
            entry_id,
        )
        if row is None:
            raise HTTPException(404, "词条不存在")
        await authorize(connection, context, int(row["knowledge_base_id"]), write=write)
        return await load_entry(connection, entry_id)

    @app.get("/api/v1/knowledge-bases/{knowledge_base_id}/wiki-entries")
    async def list_entries(knowledge_base_id: int, request: Request) -> dict[str, Any]:
        """列表同时返回管理权限，使只读用户不会看到可修改按钮。"""
        context = await main._authenticated_user(config, request)
        connection = await main._database(config)
        try:
            access = await authorize(connection, context, knowledge_base_id)
            can_manage = False
            try:
                await authorize(connection, context, knowledge_base_id, write=True)
                can_manage = True
            except HTTPException as error:
                if error.status_code not in {403, 404}:
                    raise
            rows = await connection.fetch(
                """SELECT id FROM wiki_entries WHERE tenant_id=$1 AND knowledge_base_id=$2
                   AND ($3 OR status='published') ORDER BY updated_at DESC,id DESC""",
                int(access["tenant_id"]),
                knowledge_base_id,
                can_manage,
            )
            return {
                "items": [await load_entry(connection, int(row["id"])) for row in rows],
                "can_manage": can_manage,
            }
        finally:
            await connection.close()

    @app.get("/api/v1/knowledge-bases/{knowledge_base_id}/wiki-options")
    async def options(
        knowledge_base_id: int,
        request: Request,
        document_id: int | None = None,
        query: str = Query(default="", max_length=200),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, Any]:
        """提供当前发布原文的可选切片与有效负责人，支持文档和文本筛选。"""
        context = await main._authenticated_user(config, request)
        connection = await main._database(config)
        try:
            access = await authorize(connection, context, knowledge_base_id, write=True)
            tenant_id = int(access["tenant_id"])
            members = await connection.fetch(
                """SELECT u.id::text, u.display_name FROM tenant_members tm
                   JOIN users u ON u.id=tm.user_id WHERE tm.tenant_id=$1
                     AND tm.status='active' AND u.status='active' ORDER BY u.display_name""",
                tenant_id,
            )
            chunks = await connection.fetch(
                """SELECT c.id::text AS chunk_id, d.id::text AS document_id,
                          d.title AS document_title, dv.id::text AS document_version_id,
                          dv.version_no, c.locator, left(c.content,500) AS content
                   FROM knowledge_bases kb JOIN release_items ri
                     ON ri.release_id=kb.active_release_id AND ri.tenant_id=kb.tenant_id
                     AND ri.knowledge_base_id=kb.id
                   JOIN documents d ON d.id=ri.document_id AND d.tenant_id=kb.tenant_id
                     AND d.status='active' AND d.deleted_at IS NULL
                   JOIN document_versions dv ON dv.id=ri.document_version_id
                     AND dv.parse_status IN ('complete','partial')
                   JOIN document_artifacts da ON da.id=ri.artifact_id
                     AND da.state IN ('ready','partial')
                   JOIN chunks c ON c.artifact_id=ri.artifact_id AND c.tenant_id=kb.tenant_id
                     AND c.knowledge_base_id=kb.id
                   WHERE kb.id=$1 AND kb.tenant_id=$2
                     AND ($3::bigint IS NULL OR d.id=$3)
                     AND ($4='' OR c.content ILIKE '%' || $4 || '%')
                   ORDER BY d.id,c.ordinal LIMIT $5""",
                knowledge_base_id,
                tenant_id,
                document_id,
                query,
                limit,
            )
            items = [dict(chunk) for chunk in chunks]
            for item in items:
                if isinstance(item["locator"], str):
                    item["locator"] = json.loads(item["locator"])
            # 文档列表独立于切片上限，避免第一份文档挤掉后续文档选项。
            documents = await connection.fetch(
                """SELECT DISTINCT d.id::text, d.title FROM knowledge_bases kb
                   JOIN release_items ri ON ri.release_id=kb.active_release_id
                     AND ri.tenant_id=kb.tenant_id AND ri.knowledge_base_id=kb.id
                   JOIN documents d ON d.id=ri.document_id AND d.tenant_id=kb.tenant_id
                     AND d.status='active' AND d.deleted_at IS NULL
                   WHERE kb.id=$1 AND kb.tenant_id=$2 ORDER BY d.title""",
                knowledge_base_id,
                tenant_id,
            )
            return {
                "members": [dict(member) for member in members],
                "sources": items,
                "documents": [dict(document) for document in documents],
            }
        finally:
            await connection.close()

    @app.post("/api/v1/knowledge-bases/{knowledge_base_id}/wiki-entries", status_code=201)
    async def create_entry(
        knowledge_base_id: int,
        payload: WikiContent,
        request: Request,
    ) -> dict[str, Any]:
        """创建草稿；来源、负责人、别名、初始快照和审计全部原子保存。"""
        context = await main._authenticated_user(config, request)
        connection = await main._database(config)
        try:
            access = await authorize(connection, context, knowledge_base_id, write=True)
            tenant_id, user_id = int(access["tenant_id"]), int(context["user"]["id"])
            async with connection.transaction():
                sources = await validate_content(connection, tenant_id, knowledge_base_id, payload)
                entry_id = await connection.fetchval(
                    """INSERT INTO wiki_entries(tenant_id,knowledge_base_id,term,definition,
                         owner_user_id,valid_from,valid_until,created_by)
                       VALUES($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id""",
                    tenant_id,
                    knowledge_base_id,
                    payload.term,
                    payload.definition,
                    payload.owner_user_id,
                    payload.valid_from,
                    payload.valid_until,
                    user_id,
                )
                await replace_links(connection, entry_id, payload, sources)
                entry = await save_revision(connection, entry_id, user_id, "create")
                await write_audit_event(
                    connection,
                    tenant_id=tenant_id,
                    actor_id=user_id,
                    action="wiki_entry.create",
                    target_type="wiki_entry",
                    target_id=entry_id,
                    summary={"version_no": 1},
                )
            return entry
        except asyncpg.UniqueViolationError as error:
            raise HTTPException(409, "该知识库已存在同名词条") from error
        finally:
            await connection.close()

    @app.post("/api/v1/knowledge-bases/{knowledge_base_id}/wiki-extraction-preview")
    async def extraction_preview(
        knowledge_base_id: int, payload: WikiExtractionRequest, request: Request
    ) -> dict[str, Any]:
        """管理员预览按章节生成的候选，不写入词条也不调用生成模型。"""
        context = await main._authenticated_user(config, request)
        connection = await main._database(config)
        try:
            access = await authorize(connection, context, knowledge_base_id, write=True)
            return await preview_extraction(
                connection, int(access["tenant_id"]), knowledge_base_id, payload.document_id
            )
        finally:
            await connection.close()

    @app.post("/api/v1/knowledge-bases/{knowledge_base_id}/wiki-extraction-import")
    async def extraction_import(
        knowledge_base_id: int, payload: WikiExtractionImport, request: Request
    ) -> dict[str, Any]:
        """锁定知识库后重新提取并原子导入草稿；旧预览拒绝，重复项跳过，来源不可伪造。"""
        context = await main._authenticated_user(config, request)
        connection = await main._database(config)
        try:
            access = await authorize(connection, context, knowledge_base_id, write=True)
            tenant_id, actor_id = int(access["tenant_id"]), int(context["user"]["id"])
            async with connection.transaction():
                await connection.fetchrow(
                    "SELECT id FROM knowledge_bases WHERE id=$1 AND tenant_id=$2 FOR UPDATE",
                    knowledge_base_id,
                    tenant_id,
                )
                preview = await preview_extraction(
                    connection, tenant_id, knowledge_base_id, payload.document_id
                )
                if (
                    str(payload.release_id) != preview["release_id"]
                    or str(payload.document_version_id) != preview["document_version_id"]
                ):
                    raise HTTPException(409, "文档发布版本已变化，请重新生成预览")
                keys = set(payload.candidate_keys)
                if not keys.issubset({item["key"] for item in preview["items"]}):
                    raise HTTPException(400, "候选已变化或不存在，请重新生成预览")
                created, skipped = [], []
                for item in preview["items"]:
                    if item["key"] not in keys:
                        continue
                    if item["existing"]:
                        skipped.append(item["term"])
                        continue
                    content = WikiContent(
                        term=item["term"],
                        definition=item["definition"],
                        aliases=item["aliases"],
                        owner_user_id=payload.owner_user_id,
                        sources=[
                            {
                                "chunk_id": int(s["chunk_id"]),
                                "note": "按文档章节自动提取，待人工审核",
                            }
                            for s in item["sources"]
                        ],
                    )
                    sources = await validate_content(
                        connection, tenant_id, knowledge_base_id, content
                    )
                    entry_id = await connection.fetchval(
                        """INSERT INTO wiki_entries(tenant_id,knowledge_base_id,term,definition,
                             owner_user_id,created_by) VALUES($1,$2,$3,$4,$5,$6)
                           ON CONFLICT (knowledge_base_id,term) DO NOTHING RETURNING id""",
                        tenant_id,
                        knowledge_base_id,
                        content.term,
                        content.definition,
                        content.owner_user_id,
                        actor_id,
                    )
                    if entry_id is None:
                        skipped.append(item["term"])
                        continue
                    await replace_links(connection, entry_id, content, sources)
                    entry = await save_revision(connection, entry_id, actor_id, "extract")
                    await write_audit_event(
                        connection,
                        tenant_id=tenant_id,
                        actor_id=actor_id,
                        action="wiki_entry.extract",
                        target_type="wiki_entry",
                        target_id=entry_id,
                        summary={"document_id": payload.document_id, "method": preview["method"]},
                    )
                    created.append(entry)
            return {"items": created, "skipped": skipped}
        finally:
            await connection.close()

    @app.patch("/api/v1/wiki-entries/{entry_id}")
    async def update_entry(
        entry_id: int,
        payload: WikiContent,
        request: Request,
    ) -> dict[str, Any]:
        """编辑后回到草稿，未经再次审核不得继续影响线上检索。"""
        context = await main._authenticated_user(config, request)
        connection = await main._database(config)
        try:
            current = await authorized_entry(connection, context, entry_id, write=True)
            tenant_id, user_id = int(current["tenant_id"]), int(context["user"]["id"])
            async with connection.transaction():
                locked = await connection.fetchrow(
                    "SELECT version_no FROM wiki_entries WHERE id=$1 FOR UPDATE",
                    entry_id,
                )
                if payload.expected_version != locked["version_no"]:
                    raise HTTPException(409, "词条已被修改，请刷新后重试")
                sources = await validate_content(
                    connection,
                    tenant_id,
                    int(current["knowledge_base_id"]),
                    payload,
                )
                await connection.execute(
                    """UPDATE wiki_entries SET term=$2,definition=$3,owner_user_id=$4,
                         valid_from=$5,valid_until=$6,status='draft',version_no=version_no+1,
                         updated_at=now() WHERE id=$1""",
                    entry_id,
                    payload.term,
                    payload.definition,
                    payload.owner_user_id,
                    payload.valid_from,
                    payload.valid_until,
                )
                await replace_links(connection, entry_id, payload, sources)
                entry = await save_revision(connection, entry_id, user_id, "update")
                await write_audit_event(
                    connection,
                    tenant_id=tenant_id,
                    actor_id=user_id,
                    action="wiki_entry.update",
                    target_type="wiki_entry",
                    target_id=entry_id,
                    summary={"version_no": entry["version_no"], "status": "draft"},
                )
            return entry
        except asyncpg.UniqueViolationError as error:
            raise HTTPException(409, "该知识库已存在同名词条") from error
        finally:
            await connection.close()

    @app.post("/api/v1/wiki-entries/{entry_id}/status")
    async def transition(
        entry_id: int,
        payload: WikiTransition,
        request: Request,
    ) -> dict[str, Any]:
        """受控送审/发布/退回/停用；发布要求有效负责人和当前 Release 的原文证据。"""
        context = await main._authenticated_user(config, request)
        connection = await main._database(config)
        try:
            current = await authorized_entry(connection, context, entry_id, write=True)
            user_id, tenant_id = int(context["user"]["id"]), int(current["tenant_id"])
            async with connection.transaction():
                locked = await connection.fetchrow(
                    "SELECT * FROM wiki_entries WHERE id=$1 FOR UPDATE",
                    entry_id,
                )
                if locked["version_no"] != payload.expected_version:
                    raise HTTPException(409, "词条已被修改，请刷新后重试")
                validate_transition(locked["status"], payload.status)
                if payload.status in {"review", "published"}:
                    # 重新读取关联，避免与另一个编辑请求并发时使用旧证据。
                    current = await load_entry(connection, entry_id)
                    if not current["owner_user_id"] or not current["sources"]:
                        raise HTTPException(400, "请先指定负责人并关联原文切片")
                    content = WikiContent(
                        term=current["term"],
                        definition=current["definition"],
                        aliases=current["aliases"],
                        owner_user_id=int(current["owner_user_id"]),
                        valid_from=current["valid_from"],
                        valid_until=current["valid_until"],
                        sources=[{"chunk_id": source["chunk_id"]} for source in current["sources"]],
                    )
                    await validate_content(
                        connection,
                        tenant_id,
                        int(current["knowledge_base_id"]),
                        content,
                    )
                    if content.valid_until and content.valid_until < date.today():
                        raise HTTPException(400, "词条已过有效期，不能送审或发布")
                    ready = await connection.fetchval(
                        """SELECT count(DISTINCT s.chunk_id) FROM wiki_entry_sources s
                           JOIN chunks c ON c.id=s.chunk_id JOIN release_items ri
                             ON ri.artifact_id=c.artifact_id
                             AND ri.document_version_id=s.document_version_id
                           JOIN knowledge_bases kb ON kb.active_release_id=ri.release_id
                             AND kb.id=$2 AND ri.knowledge_base_id=kb.id
                           WHERE s.entry_id=$1 AND ri.tenant_id=$3""",
                        entry_id,
                        int(current["knowledge_base_id"]),
                        tenant_id,
                    )
                    if ready != len(content.sources):
                        raise HTTPException(400, "来源不在当前发布版本，请重新关联有效原文")
                await connection.execute(
                    """UPDATE wiki_entries SET status=$2,version_no=version_no+1,updated_at=now()
                       WHERE id=$1""",
                    entry_id,
                    payload.status,
                )
                entry = await save_revision(connection, entry_id, user_id, payload.status)
                await write_audit_event(
                    connection,
                    tenant_id=tenant_id,
                    actor_id=user_id,
                    action=f"wiki_entry.{payload.status}",
                    target_type="wiki_entry",
                    target_id=entry_id,
                    summary={"version_no": entry["version_no"]},
                )
            return entry
        finally:
            await connection.close()

    @app.get("/api/v1/wiki-entries/{entry_id}/revisions")
    async def revisions(entry_id: int, request: Request) -> dict[str, Any]:
        """管理员可查看每次修订的完整快照，普通读者不能读取历史草稿。"""
        context = await main._authenticated_user(config, request)
        connection = await main._database(config)
        try:
            await authorized_entry(connection, context, entry_id, write=True)
            rows = await connection.fetch(
                """SELECT version_no, action, snapshot, actor_id::text, created_at
                   FROM wiki_entry_revisions WHERE entry_id=$1 ORDER BY version_no DESC""",
                entry_id,
            )
            items = [dict(row) for row in rows]
            for item in items:
                if isinstance(item["snapshot"], str):
                    item["snapshot"] = json.loads(item["snapshot"])
            return {"items": items}
        finally:
            await connection.close()
