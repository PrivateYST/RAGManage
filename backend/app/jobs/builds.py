"""知识库索引构建任务。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence

import asyncpg
import httpx

from app.core.audit import write_audit_event
from app.core.config import Settings
from app.jobs.worker import celery_app
from app.rag.models import ModelGatewayClient
from app.rag.profiles import gateway_settings

EMBEDDING_BATCH_SIZE = 16


def _vector_literal(vector: Sequence[float]) -> str:
    """把已校验的浮点向量转换为 pgvector 接受的文本格式。"""
    return "[" + ",".join(format(value, ".9g") for value in vector) + "]"


def _failure_code(error: Exception) -> str:
    """把内部异常收敛为可审计的稳定错误代码，避免泄露响应正文或凭据。"""
    if isinstance(error, ValueError) and str(error):
        return str(error)[:120]
    if isinstance(error, httpx.HTTPError):
        return "EMBEDDING_SERVICE_UNAVAILABLE"
    return "INDEX_BUILD_FAILED"


async def _mark_build_failure(
    connection: asyncpg.Connection,
    task_id: int,
    build_id: int,
    error: Exception,
) -> None:
    """把构建及未完成子项统一标记失败，调用方随后写入一次构建失败审计。"""
    code = _failure_code(error)
    payload = json.dumps({"code": code}, ensure_ascii=False)
    task_state = await connection.fetchval("SELECT state FROM tasks WHERE id = $1", task_id)
    if task_state == "cancelled":
        return
    await connection.execute(
        """
        UPDATE tasks SET state = 'failed', error = $2::jsonb,
            lease_until = NULL, updated_at = now() WHERE id = $1
        """,
        task_id,
        payload,
    )
    await connection.execute(
        """
        UPDATE task_items SET state = 'failed', error = $2::jsonb, updated_at = now()
        WHERE task_id = $1 AND state <> 'completed'
        """,
        task_id,
        payload,
    )
    await connection.execute(
        """
        UPDATE index_builds SET state = 'failed', error = $2::jsonb, updated_at = now()
        WHERE id = $1
        """,
        build_id,
        payload,
    )
    await connection.execute(
        """
        UPDATE build_items SET state = 'failed', error = $2::jsonb, updated_at = now()
        WHERE build_id = $1 AND state <> 'completed'
        """,
        build_id,
        payload,
    )


async def _process_build_item(
    connection: asyncpg.Connection,
    client: ModelGatewayClient,
    task_id: int,
    build_id: int,
    embedding_profile_id: int,
    item: asyncpg.Record,
) -> bool:
    """为单个文档的切片生成向量；任务取消时返回 False 终止剩余批次。"""
    current_state = await connection.fetchval("SELECT state FROM tasks WHERE id = $1", task_id)
    if current_state == "cancelled":
        return False

    async with connection.transaction():
        await connection.execute(
            """
            UPDATE build_items SET state = 'running', error = NULL, updated_at = now()
            WHERE build_id = $1 AND document_id = $2
            """,
            build_id,
            item["document_id"],
        )
        await connection.execute(
            """
            UPDATE task_items SET state = 'running', attempt = attempt + 1,
                error = NULL, updated_at = now()
            WHERE task_id = $1 AND target_id = $2 AND stage = 'embed'
            """,
            task_id,
            item["document_version_id"],
        )

    chunks = await connection.fetch(
        """
        SELECT id, embed_text FROM chunks
        WHERE tenant_id = $1 AND knowledge_base_id = $2 AND artifact_id = $3
        ORDER BY ordinal
        """,
        item["tenant_id"],
        item["knowledge_base_id"],
        item["artifact_id"],
    )
    if not chunks:
        raise ValueError("BUILD_ITEM_HAS_NO_CHUNKS")

    embedded_count = 0
    for offset in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
        task_state = await connection.fetchval("SELECT state FROM tasks WHERE id = $1", task_id)
        if task_state == "cancelled":
            return False
        batch = chunks[offset : offset + EMBEDDING_BATCH_SIZE]
        vectors = await client.embed([str(chunk["embed_text"]) for chunk in batch])
        async with connection.transaction():
            for chunk, vector in zip(batch, vectors, strict=True):
                await connection.execute(
                    """
                    INSERT INTO chunk_embeddings(
                      tenant_id, knowledge_base_id, chunk_id, embedding_profile_id, embedding
                    ) VALUES ($1, $2, $3, $4, $5::vector)
                    ON CONFLICT (chunk_id, embedding_profile_id)
                    DO UPDATE SET embedding = EXCLUDED.embedding, created_at = now()
                    """,
                    item["tenant_id"],
                    item["knowledge_base_id"],
                    chunk["id"],
                    embedding_profile_id,
                    _vector_literal(vector),
                )
            embedded_count += len(batch)
            await connection.execute(
                """
                UPDATE build_items SET chunk_count = $3, embedded_count = $4,
                    updated_at = now() WHERE build_id = $1 AND document_id = $2
                """,
                build_id,
                item["document_id"],
                len(chunks),
                embedded_count,
            )
            await connection.execute(
                """
                UPDATE tasks SET lease_until = now() + interval '5 minutes', updated_at = now()
                WHERE id = $1 AND state = 'running'
                """,
                task_id,
            )

    async with connection.transaction():
        await connection.execute(
            """
            UPDATE build_items SET state = 'completed', chunk_count = $3,
                embedded_count = $3, error = NULL, updated_at = now()
            WHERE build_id = $1 AND document_id = $2
            """,
            build_id,
            item["document_id"],
            len(chunks),
        )
        await connection.execute(
            """
            UPDATE task_items SET state = 'completed', error = NULL, updated_at = now()
            WHERE task_id = $1 AND target_id = $2 AND stage = 'embed'
            """,
            task_id,
            item["document_version_id"],
        )
    return True


async def _process_index_build(task_id: int) -> None:
    """执行索引构建、校验向量完整性，并记录构建成功或失败终态。"""
    settings = Settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_NOT_CONFIGURED")
    connection = await asyncpg.connect(settings.database_url, timeout=10)
    build_id = 0
    try:
        async with connection.transaction():
            build = await connection.fetchrow(
                """
                SELECT ib.id, ib.tenant_id, ib.knowledge_base_id, ib.created_by,
                       ib.embedding_profile_id, ib.state AS build_state,
                       t.state AS task_state, ep.dimension, ep.model_name,
                       me.base_url, me.allowed_models, me.status AS endpoint_status
                FROM index_builds ib
                JOIN tasks t ON t.id = ib.task_id AND t.tenant_id = ib.tenant_id
                JOIN embedding_profiles ep ON ep.id = ib.embedding_profile_id
                JOIN model_endpoints me ON me.id = ep.model_endpoint_id
                WHERE ib.task_id = $1
                FOR UPDATE OF ib, t
                """,
                task_id,
            )
            if build is None:
                raise ValueError("INDEX_BUILD_NOT_FOUND")
            build_id = int(build["id"])
            if build["task_state"] in {"completed", "cancelled"}:
                return
            if build["endpoint_status"] != "active":
                raise ValueError("MODEL_ENDPOINT_DISABLED")
            await connection.execute(
                """
                UPDATE tasks SET state = 'running', attempt = attempt + 1,
                    lease_until = now() + interval '5 minutes', updated_at = now()
                WHERE id = $1
                """,
                task_id,
            )
            await connection.execute(
                """
                UPDATE index_builds SET state = 'running', error = NULL, updated_at = now()
                WHERE id = $1
                """,
                build_id,
            )

        raw_models = build["allowed_models"]
        allowed_models = json.loads(raw_models) if isinstance(raw_models, str) else raw_models
        if build["model_name"] not in allowed_models:
            raise ValueError("MODEL_NOT_ALLOWED")
        effective_settings = gateway_settings(
            settings,
            base_url=str(build["base_url"]),
            allowed_models=list(allowed_models),
            embedding_model=str(build["model_name"]),
            embedding_dimensions=int(build["dimension"]),
        )
        client = ModelGatewayClient(effective_settings)
        items = await connection.fetch(
            """
            SELECT build_id, tenant_id, knowledge_base_id, document_id,
                   document_version_id, artifact_id, state
            FROM build_items WHERE build_id = $1 ORDER BY document_id
            """,
            build_id,
        )
        if not items:
            raise ValueError("INDEX_BUILD_HAS_NO_ITEMS")
        for item in items:
            if item["state"] == "completed":
                continue
            completed = await _process_build_item(
                connection,
                client,
                task_id,
                build_id,
                int(build["embedding_profile_id"]),
                item,
            )
            if not completed:
                return

        async with connection.transaction():
            await connection.execute(
                "UPDATE index_builds SET state = 'validating', updated_at = now() WHERE id = $1",
                build_id,
            )
            counts = await connection.fetchrow(
                """
                SELECT count(c.id)::int AS expected_count,
                       count(ce.id)::int AS embedded_count
                FROM build_items bi
                JOIN chunks c ON c.tenant_id = bi.tenant_id AND c.artifact_id = bi.artifact_id
                LEFT JOIN chunk_embeddings ce ON ce.tenant_id = c.tenant_id
                  AND ce.chunk_id = c.id AND ce.embedding_profile_id = $2
                WHERE bi.build_id = $1
                """,
                build_id,
                build["embedding_profile_id"],
            )
            if counts is None or counts["expected_count"] != counts["embedded_count"]:
                raise ValueError("BUILD_EMBEDDING_COUNT_MISMATCH")
            await connection.execute(
                """
                UPDATE index_builds SET state = 'ready', error = NULL, updated_at = now()
                WHERE id = $1
                """,
                build_id,
            )
            await connection.execute(
                """
                UPDATE tasks SET state = 'completed', error = NULL, lease_until = NULL,
                    updated_at = now() WHERE id = $1 AND state <> 'cancelled'
                """,
                task_id,
            )
            # 成功事件与 ready 状态原子提交，摘要仅保留构建规模和 Profile 标识。
            await write_audit_event(
                connection,
                tenant_id=int(build["tenant_id"]),
                actor_id=int(build["created_by"]) if build["created_by"] is not None else None,
                action="build.completed",
                target_type="build",
                target_id=build_id,
                summary={
                    "knowledge_base_id": str(build["knowledge_base_id"]),
                    "task_id": str(task_id),
                    "embedding_profile_id": str(build["embedding_profile_id"]),
                    "chunk_count": int(counts["embedded_count"]),
                },
            )
    except Exception as error:
        if build_id:
            try:
                async with connection.transaction():
                    await _mark_build_failure(connection, task_id, build_id, error)
                    audit_context = await connection.fetchrow(
                        """
                        SELECT tenant_id, knowledge_base_id, embedding_profile_id, created_by
                        FROM index_builds WHERE id = $1
                        """,
                        build_id,
                    )
                    if audit_context is not None:
                        await write_audit_event(
                            connection,
                            tenant_id=int(audit_context["tenant_id"]),
                            actor_id=(
                                int(audit_context["created_by"])
                                if audit_context["created_by"] is not None
                                else None
                            ),
                            action="build.failed",
                            target_type="build",
                            target_id=build_id,
                            summary={
                                "knowledge_base_id": str(audit_context["knowledge_base_id"]),
                                "task_id": str(task_id),
                                "embedding_profile_id": str(audit_context["embedding_profile_id"]),
                                "error_code": _failure_code(error),
                            },
                        )
            except Exception:
                # 审计或状态回写失败不能替换原始构建异常，租约巡检仍可恢复任务。
                pass
        raise
    finally:
        await connection.close()


@celery_app.task(name="app.jobs.builds.process_index_build")  # type: ignore[untyped-decorator]
def process_index_build(task_id: int) -> None:
    """Celery 同步入口，将任务 ID 交给异步索引构建流程。"""
    asyncio.run(_process_index_build(int(task_id)))
