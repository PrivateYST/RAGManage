"""文档解析后台任务。

首版先把解析结果和带定位信息的切片落库，嵌入与发布沿用同一任务状态模型，
后续可在不改上传契约的情况下接入向量化阶段。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

import asyncpg

from app.core.audit import write_audit_event
from app.core.config import Settings
from app.jobs.worker import celery_app
from app.rag.parsing import ParsedDocument, parse_document


def _profile_definition() -> dict[str, Any]:
    return {
        "parser": "markdown-it/docx/pdfplumber:v1",
        "chunking": {"strategy": "source-block", "max_chars": 1800},
        "preserve_locator": True,
    }


def _profile_hash(definition: dict[str, Any]) -> str:
    encoded = json.dumps(definition, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _safe_storage_path(root: Path, storage_key: str) -> Path:
    candidate = (root / storage_key).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise ValueError("INVALID_STORAGE_KEY")
    return candidate


def _chunk_blocks(
    document: ParsedDocument,
    definition: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    chunking = (definition or {}).get("chunking", {})
    max_chars = int(chunking.get("max_chars", 1800))
    overlap_chars = int(chunking.get("overlap_chars", 0))
    step = max(1, max_chars - overlap_chars)
    for block in document.blocks:
        text = block.text.strip()
        if not text:
            continue
        for start in range(0, len(text), step):
            part = text[start : start + max_chars]
            if not part:
                continue
            locator = {
                **block.locator,
                "chunk_char_start": start,
                "chunk_char_end": start + len(part),
            }
            chunks.append(
                {
                    "ordinal": len(chunks),
                    "content": part,
                    "embed_text": part,
                    "token_count": max(1, len(part) // 4),
                    "section_path": list(block.section_path),
                    "locator": locator,
                }
            )
            if start + max_chars >= len(text):
                break
    return chunks


async def _mark_task_failure(connection: asyncpg.Connection, task_id: int, message: str) -> None:
    """把解析任务及未完成子项标记为失败；审计由掌握业务目标的调用方写入。"""
    await connection.execute(
        """
        UPDATE tasks SET state = 'failed', error = $2::jsonb, updated_at = now()
        WHERE id = $1
        """,
        task_id,
        json.dumps({"code": message}, ensure_ascii=False),
    )
    await connection.execute(
        """
        UPDATE task_items SET state = 'failed', error = $2::jsonb, updated_at = now()
        WHERE task_id = $1 AND state <> 'completed'
        """,
        task_id,
        json.dumps({"code": message}, ensure_ascii=False),
    )


async def _process_document(task_id: int) -> None:
    """解析一个文档版本并落库切片，同时记录成功、部分成功或失败终态。"""
    settings = Settings()
    if not settings.database_url:
        return
    connection = await asyncpg.connect(settings.database_url, timeout=10)
    try:
        async with connection.transaction():
            task = await connection.fetchrow(
                """
                SELECT id, tenant_id, state, knowledge_base_id, created_by
                FROM tasks WHERE id = $1 FOR UPDATE
                """,
                task_id,
            )
            if task is None or task["state"] in {"completed", "cancelled"}:
                return
            version = await connection.fetchrow(
                """
                SELECT dv.id, dv.document_id, dv.tenant_id, dv.storage_key,
                       d.knowledge_base_id
                FROM document_versions dv JOIN documents d ON d.id = dv.document_id
                WHERE dv.id = (
                  SELECT target_id FROM task_items
                  WHERE task_id = $1 ORDER BY id LIMIT 1
                )
                """,
                task_id,
            )
            if version is None:
                await _mark_task_failure(connection, task_id, "DOCUMENT_VERSION_NOT_FOUND")
                await write_audit_event(
                    connection,
                    tenant_id=int(task["tenant_id"]),
                    actor_id=int(task["created_by"]) if task["created_by"] is not None else None,
                    action="document.parse.failed",
                    target_type="task",
                    target_id=task_id,
                    summary={
                        "knowledge_base_id": str(task["knowledge_base_id"]),
                        "task_id": str(task_id),
                        "error_code": "DOCUMENT_VERSION_NOT_FOUND",
                    },
                )
                return
            await connection.execute(
                """
                UPDATE tasks SET state = 'running', attempt = attempt + 1,
                    updated_at = now() WHERE id = $1
                """,
                task_id,
            )
            await connection.execute(
                "UPDATE document_versions SET parse_status = 'processing' WHERE id = $1",
                version["id"],
            )
            await connection.execute(
                """
                UPDATE task_items SET state = 'running', attempt = attempt + 1,
                    updated_at = now() WHERE task_id = $1
                """,
                task_id,
            )

        path = _safe_storage_path(settings.storage_root, version["storage_key"])
        parsed = parse_document(path)
        configured_profile = await connection.fetchrow(
            """
            SELECT id, definition, definition_hash
            FROM ingestion_profiles
            WHERE tenant_id = $1 AND knowledge_base_id = $2
            ORDER BY created_at DESC, id DESC LIMIT 1
            """,
            version["tenant_id"],
            version["knowledge_base_id"],
        )
        if configured_profile is None:
            definition = _profile_definition()
            definition_hash = _profile_hash(definition)
            profile_id = None
        else:
            raw_definition = configured_profile["definition"]
            definition = (
                json.loads(raw_definition) if isinstance(raw_definition, str) else raw_definition
            )
            definition_hash = str(configured_profile["definition_hash"])
            profile_id = int(configured_profile["id"])
        definition_json = json.dumps(definition, ensure_ascii=False, sort_keys=True)
        chunks = _chunk_blocks(parsed, definition)

        async with connection.transaction():
            if profile_id is None:
                profile_id = await connection.fetchval(
                    """
                    INSERT INTO ingestion_profiles(
                      tenant_id, knowledge_base_id, definition, definition_hash, created_by
                    )
                    SELECT $1, $2, $3::jsonb, $4, created_by
                    FROM documents WHERE id = $5
                    RETURNING id
                    """,
                    version["tenant_id"],
                    version["knowledge_base_id"],
                    definition_json,
                    definition_hash,
                    version["document_id"],
                )
            artifact_id = await connection.fetchval(
                """
                INSERT INTO document_artifacts(
                  tenant_id, knowledge_base_id, document_version_id,
                  ingestion_profile_id, state, manifest
                ) VALUES ($1, $2, $3, $4, 'processing', '{}'::jsonb)
                ON CONFLICT (document_version_id, ingestion_profile_id)
                DO UPDATE SET state = 'processing', manifest = '{}'::jsonb
                RETURNING id
                """,
                version["tenant_id"],
                version["knowledge_base_id"],
                version["id"],
                profile_id,
            )
            await connection.execute("DELETE FROM chunks WHERE artifact_id = $1", artifact_id)
            for chunk in chunks:
                await connection.execute(
                    """
                    INSERT INTO chunks(
                      tenant_id, knowledge_base_id, artifact_id, ordinal,
                      content, embed_text, token_count, section_path, locator, lexical_tsv
                    ) VALUES ($1, $2, $3, $4, $5, $5, $6, $7::jsonb, $8::jsonb,
                              to_tsvector('simple', $5))
                    """,
                    version["tenant_id"],
                    version["knowledge_base_id"],
                    artifact_id,
                    chunk["ordinal"],
                    chunk["content"],
                    chunk["token_count"],
                    json.dumps(chunk["section_path"], ensure_ascii=False),
                    json.dumps(chunk["locator"], ensure_ascii=False),
                )
            final_state = (
                "partial"
                if parsed.status == "partial"
                else "ready"
                if parsed.status == "complete"
                else "failed"
            )
            await connection.execute(
                "UPDATE document_artifacts SET state = $2, manifest = $3::jsonb WHERE id = $1",
                artifact_id,
                final_state,
                json.dumps(
                    {
                        "parser": parsed.parser,
                        "status": parsed.status,
                        "block_count": len(chunks),
                        "warnings": parsed.warnings,
                    },
                    ensure_ascii=False,
                ),
            )
            await connection.execute(
                """
                UPDATE document_versions SET parse_status = $2,
                    warnings = $3::jsonb WHERE id = $1
                """,
                version["id"],
                parsed.status,
                json.dumps(parsed.warnings, ensure_ascii=False),
            )
            if parsed.status == "failed":
                await connection.execute(
                    """
                    UPDATE tasks SET state = 'failed', error = $2::jsonb,
                        updated_at = now() WHERE id = $1
                    """,
                    task_id,
                    json.dumps(
                        {"code": "DOCUMENT_PARSE_FAILED", "warnings": parsed.warnings},
                        ensure_ascii=False,
                    ),
                )
                await connection.execute(
                    """
                    UPDATE task_items SET state = 'failed', error = $2::jsonb,
                        updated_at = now() WHERE task_id = $1
                    """,
                    task_id,
                    json.dumps({"code": "DOCUMENT_PARSE_FAILED"}, ensure_ascii=False),
                )
            else:
                await connection.execute(
                    """
                    UPDATE tasks SET state = 'completed', error = NULL,
                        updated_at = now()
                    WHERE id = $1 AND state <> 'cancelled'
                    """,
                    task_id,
                )
                await connection.execute(
                    """
                    UPDATE task_items SET state = 'completed', error = NULL,
                        updated_at = now()
                    WHERE task_id = $1 AND state <> 'cancelled'
                    """,
                    task_id,
                )
            # 后台任务沿用任务创建人作为操作人；摘要只保留定位 ID、状态和数量。
            await write_audit_event(
                connection,
                tenant_id=int(version["tenant_id"]),
                actor_id=int(task["created_by"]) if task["created_by"] is not None else None,
                action=(
                    "document.parse.failed"
                    if parsed.status == "failed"
                    else "document.parse.completed"
                ),
                target_type="document",
                target_id=int(version["document_id"]),
                summary={
                    "knowledge_base_id": str(version["knowledge_base_id"]),
                    "document_version_id": str(version["id"]),
                    "artifact_id": str(artifact_id),
                    "task_id": str(task_id),
                    "parse_status": parsed.status,
                    "chunk_count": len(chunks),
                    "warning_count": len(parsed.warnings),
                    **(
                        {"error_code": "DOCUMENT_PARSE_FAILED"} if parsed.status == "failed" else {}
                    ),
                },
            )
    except Exception:
        try:
            async with connection.transaction():
                await _mark_task_failure(connection, task_id, "DOCUMENT_PROCESSING_FAILED")
                await connection.execute(
                    """
                    UPDATE document_versions SET parse_status = 'failed',
                        warnings = $2::jsonb WHERE id = (
                          SELECT target_id FROM task_items
                          WHERE task_id = $1 ORDER BY id LIMIT 1
                        )
                    """,
                    task_id,
                    json.dumps(["DOCUMENT_PROCESSING_FAILED"], ensure_ascii=False),
                )
                audit_target = await connection.fetchrow(
                    """
                    SELECT t.tenant_id, t.knowledge_base_id, t.created_by,
                           ti.target_id AS document_version_id, dv.document_id
                    FROM tasks t
                    LEFT JOIN task_items ti ON ti.task_id = t.id AND ti.stage = 'parse'
                    LEFT JOIN document_versions dv ON dv.id = ti.target_id
                    WHERE t.id = $1
                    ORDER BY ti.id LIMIT 1
                    """,
                    task_id,
                )
                if audit_target is not None:
                    await write_audit_event(
                        connection,
                        tenant_id=int(audit_target["tenant_id"]),
                        actor_id=(
                            int(audit_target["created_by"])
                            if audit_target["created_by"] is not None
                            else None
                        ),
                        action="document.parse.failed",
                        target_type=(
                            "document" if audit_target["document_id"] is not None else "task"
                        ),
                        target_id=audit_target["document_id"] or task_id,
                        summary={
                            "knowledge_base_id": str(audit_target["knowledge_base_id"]),
                            "document_version_id": (
                                str(audit_target["document_version_id"])
                                if audit_target["document_version_id"] is not None
                                else None
                            ),
                            "task_id": str(task_id),
                            "error_code": "DOCUMENT_PROCESSING_FAILED",
                        },
                    )
        except Exception:
            # 进程异常时由下一次任务巡检回收租约；不要遮蔽原始 worker 错误。
            pass
    finally:
        await connection.close()


@celery_app.task(name="app.jobs.tasks.process_document")  # type: ignore[untyped-decorator]
def process_document(task_id: int) -> None:
    """Celery 同步入口，将任务 ID 交给异步解析流程。"""
    asyncio.run(_process_document(int(task_id)))
