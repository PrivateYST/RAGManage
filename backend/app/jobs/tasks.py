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


def _chunk_blocks(document: ParsedDocument) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for ordinal, block in enumerate(document.blocks):
        text = block.text.strip()
        if not text:
            continue
        # 保留解析器的原文块，避免首版切片破坏页码、行号和标题路径。
        chunks.append(
            {
                "ordinal": ordinal,
                "content": text,
                "embed_text": text,
                "token_count": max(1, len(text) // 4),
                "section_path": list(block.section_path),
                "locator": block.locator,
            }
        )
    return chunks


async def _mark_task_failure(connection: asyncpg.Connection, task_id: int, message: str) -> None:
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
    settings = Settings()
    if not settings.database_url:
        return
    connection = await asyncpg.connect(settings.database_url, timeout=10)
    try:
        async with connection.transaction():
            task = await connection.fetchrow(
                "SELECT id, state, knowledge_base_id FROM tasks WHERE id = $1 FOR UPDATE", task_id
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
        definition = _profile_definition()
        definition_json = json.dumps(definition, ensure_ascii=False, sort_keys=True)
        definition_hash = _profile_hash(definition)
        chunks = _chunk_blocks(parsed)

        async with connection.transaction():
            profile_id = await connection.fetchval(
                """
                SELECT id FROM ingestion_profiles
                WHERE tenant_id = $1 AND knowledge_base_id = $2 AND definition_hash = $3
                """,
                version["tenant_id"],
                version["knowledge_base_id"],
                definition_hash,
            )
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
        except Exception:
            # 进程异常时由下一次任务巡检回收租约；不要遮蔽原始 worker 错误。
            pass
    finally:
        await connection.close()


@celery_app.task(name="app.jobs.tasks.process_document")  # type: ignore[untyped-decorator]
def process_document(task_id: int) -> None:
    asyncio.run(_process_document(int(task_id)))
