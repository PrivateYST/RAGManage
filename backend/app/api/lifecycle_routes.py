# ruff: noqa
# mypy: ignore-errors
"""构建发布、回退和任务生命周期路由。

路由函数保持薄层，领域规则继续由 app.main 中的兼容辅助函数和 app.rag 服务提供。
"""

from fastapi import FastAPI
from app.main import *  # noqa: F403,F401


def register(app: FastAPI, config: Settings) -> None:
    """将本领域路由挂载到应用；config 是应用级配置快照。"""
    from app import main as main_module

    globals().update(main_module.__dict__)

    @app.post("/api/v1/builds/{build_id}/publish", status_code=201)
    async def publish_build(
        build_id: int,
        payload: ReleasePublishRequest,
        request: Request,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            preview = await _load_release_preview(connection, build_id)
            if preview is None:
                raise HTTPException(status_code=404, detail="构建不存在")
            build = preview["build_record"]
            access = await _require_knowledge_base_role(
                connection,
                context,
                int(build["knowledge_base_id"]),
                {"space_admin", "kb_admin"},
            )
            user_id = int(context["user"]["id"])
            async with connection.transaction():
                knowledge_base = await connection.fetchrow(
                    """
                    SELECT id, tenant_id, active_release_id
                    FROM knowledge_bases
                    WHERE id = $1 AND tenant_id = $2
                    FOR UPDATE
                    """,
                    build["knowledge_base_id"],
                    access["tenant_id"],
                )
                if knowledge_base is None:
                    raise HTTPException(status_code=404, detail="知识库不存在")
                current_active_release_id = (
                    int(knowledge_base["active_release_id"])
                    if knowledge_base["active_release_id"] is not None
                    else None
                )
                if payload.expected_active_release_id != current_active_release_id:
                    raise HTTPException(
                        status_code=409,
                        detail="当前发布版本已变化，请刷新差异后重试",
                    )

                preview = await _load_release_preview(connection, build_id)
                if preview is None:
                    raise HTTPException(status_code=404, detail="构建不存在")
                validation = preview["validation"]
                if not validation["ready"]:
                    first_error = validation["errors"][0]
                    raise HTTPException(status_code=409, detail=first_error["message"])

                existing = await connection.fetchrow(
                    """
                    SELECT id::text, build_id::text, manifest_hash, state, created_at
                    FROM kb_releases
                    WHERE build_id = $1 OR (
                      knowledge_base_id = $2 AND manifest_hash = $3
                    )
                    ORDER BY id DESC LIMIT 1
                    """,
                    build_id,
                    build["knowledge_base_id"],
                    preview["manifest_hash"],
                )
                if existing is not None:
                    if current_active_release_id == int(existing["id"]):
                        return {**dict(existing), "reused": True, "diff": preview["diff"]}
                    raise HTTPException(
                        status_code=409,
                        detail="该构建已经生成过 Release，请使用发布历史进行回退",
                    )

                release = await connection.fetchrow(
                    """
                    INSERT INTO kb_releases(
                      tenant_id, knowledge_base_id, build_id,
                      embedding_profile_id, manifest_hash, state
                    ) VALUES ($1, $2, $3, $4, $5, 'ready')
                    RETURNING id::text, build_id::text, manifest_hash, state, created_at
                    """,
                    build["tenant_id"],
                    build["knowledge_base_id"],
                    build_id,
                    build["embedding_profile_id"],
                    preview["manifest_hash"],
                )
                for item in preview["candidate_records"]:
                    await connection.execute(
                        """
                        INSERT INTO release_items(
                          release_id, tenant_id, knowledge_base_id, document_id,
                          document_version_id, artifact_id
                        ) VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        int(release["id"]),
                        build["tenant_id"],
                        build["knowledge_base_id"],
                        item["document_id"],
                        item["document_version_id"],
                        item["artifact_id"],
                    )
                if current_active_release_id is not None:
                    await connection.execute(
                        "UPDATE kb_releases SET state = 'retired' WHERE id = $1",
                        current_active_release_id,
                    )
                switched = await connection.fetchval(
                    """
                    UPDATE knowledge_bases
                    SET active_release_id = $3, status = 'published', updated_at = now()
                    WHERE id = $1 AND tenant_id = $2
                      AND active_release_id IS NOT DISTINCT FROM $4::bigint
                    RETURNING id
                    """,
                    build["knowledge_base_id"],
                    build["tenant_id"],
                    int(release["id"]),
                    payload.expected_active_release_id,
                )
                if switched is None:
                    raise HTTPException(
                        status_code=409,
                        detail="当前发布版本已变化，请刷新差异后重试",
                    )
                await connection.execute(
                    """
                    INSERT INTO audit_logs(
                      tenant_id, actor_id, action, target_type, target_id, change_summary
                    ) VALUES ($1, $2, 'release.publish', 'knowledge_base', $3, $4::jsonb)
                    """,
                    build["tenant_id"],
                    user_id,
                    str(build["knowledge_base_id"]),
                    json.dumps(
                        {
                            "release_id": release["id"],
                            "build_id": str(build_id),
                            "previous_release_id": (
                                str(current_active_release_id)
                                if current_active_release_id is not None
                                else None
                            ),
                            "manifest_hash": preview["manifest_hash"],
                            "diff": preview["diff"]["counts"],
                        },
                        ensure_ascii=False,
                    ),
                )
            return {**dict(release), "reused": False, "diff": preview["diff"]}
        except asyncpg.UniqueViolationError as error:
            raise HTTPException(status_code=409, detail="该构建已经生成过 Release") from error
        finally:
            await connection.close()

    @app.post("/api/v1/releases/{release_id}/rollback")
    async def rollback_release(
        release_id: int,
        payload: ReleaseRollbackRequest,
        request: Request,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            target = await connection.fetchrow(
                """
                SELECT id, tenant_id, knowledge_base_id, build_id, manifest_hash, state
                FROM kb_releases WHERE id = $1
                """,
                release_id,
            )
            if target is None:
                raise HTTPException(status_code=404, detail="Release 不存在")
            access = await _require_knowledge_base_role(
                connection,
                context,
                int(target["knowledge_base_id"]),
                {"space_admin", "kb_admin"},
            )
            user_id = int(context["user"]["id"])
            async with connection.transaction():
                knowledge_base = await connection.fetchrow(
                    """
                    SELECT id, tenant_id, active_release_id
                    FROM knowledge_bases
                    WHERE id = $1 AND tenant_id = $2
                    FOR UPDATE
                    """,
                    target["knowledge_base_id"],
                    access["tenant_id"],
                )
                if knowledge_base is None:
                    raise HTTPException(status_code=404, detail="知识库不存在")
                current_release_id = (
                    int(knowledge_base["active_release_id"])
                    if knowledge_base["active_release_id"] is not None
                    else None
                )
                if payload.expected_active_release_id != current_release_id:
                    raise HTTPException(
                        status_code=409,
                        detail="当前发布版本已变化，请刷新发布历史后重试",
                    )
                if current_release_id == release_id:
                    raise HTTPException(status_code=409, detail="该 Release 已经是当前版本")
                if target["state"] != "retired":
                    raise HTTPException(status_code=409, detail="该 Release 当前不可回退")

                recent_releases = await connection.fetch(
                    """
                    SELECT id::text, state
                    FROM kb_releases
                    WHERE tenant_id = $1 AND knowledge_base_id = $2
                      AND id <> $3 AND state = 'retired'
                    ORDER BY created_at DESC, id DESC
                    LIMIT 2
                    """,
                    access["tenant_id"],
                    target["knowledge_base_id"],
                    current_release_id,
                )
                candidate_ids = rollback_candidate_ids(
                    [dict(item) for item in recent_releases],
                    current_release_id=current_release_id,
                )
                if release_id not in candidate_ids:
                    raise HTTPException(
                        status_code=409,
                        detail="只允许回退到最近两个历史 Release",
                    )

                invalid_sources = await connection.fetch(
                    """
                    SELECT ri.document_id::text,
                           COALESCE(d.title, '来源 #' || ri.document_id::text) AS title
                    FROM release_items ri
                    LEFT JOIN documents d ON d.id = ri.document_id
                      AND d.tenant_id = ri.tenant_id
                      AND d.knowledge_base_id = ri.knowledge_base_id
                    LEFT JOIN document_versions dv ON dv.id = ri.document_version_id
                      AND dv.tenant_id = ri.tenant_id AND dv.document_id = ri.document_id
                    LEFT JOIN document_artifacts da ON da.id = ri.artifact_id
                      AND da.tenant_id = ri.tenant_id
                      AND da.knowledge_base_id = ri.knowledge_base_id
                      AND da.document_version_id = ri.document_version_id
                    WHERE ri.release_id = $1
                      AND (
                        d.id IS NULL OR d.status <> 'active'
                        OR dv.id IS NULL OR dv.parse_status <> 'complete'
                        OR da.id IS NULL OR da.state <> 'ready'
                      )
                    ORDER BY ri.document_id
                    """,
                    release_id,
                )
                if invalid_sources:
                    titles = "、".join(str(item["title"]) for item in invalid_sources[:3])
                    raise HTTPException(
                        status_code=409,
                        detail=f"Release 包含已删除、停用或失效来源，不能回退：{titles}",
                    )

                await connection.execute(
                    "UPDATE kb_releases SET state = 'retired' WHERE id = $1",
                    current_release_id,
                )
                rolled_back = await connection.fetchrow(
                    """
                    UPDATE kb_releases SET state = 'ready'
                    WHERE id = $1 AND tenant_id = $2 AND knowledge_base_id = $3
                    RETURNING id::text, build_id::text, manifest_hash, state, created_at
                    """,
                    release_id,
                    access["tenant_id"],
                    target["knowledge_base_id"],
                )
                switched = await connection.fetchval(
                    """
                    UPDATE knowledge_bases
                    SET active_release_id = $3, status = 'published', updated_at = now()
                    WHERE id = $1 AND tenant_id = $2 AND active_release_id = $4
                    RETURNING id
                    """,
                    target["knowledge_base_id"],
                    access["tenant_id"],
                    release_id,
                    payload.expected_active_release_id,
                )
                if switched is None or rolled_back is None:
                    raise HTTPException(
                        status_code=409,
                        detail="当前发布版本已变化，请刷新发布历史后重试",
                    )
                await connection.execute(
                    """
                    INSERT INTO audit_logs(
                      tenant_id, actor_id, action, target_type, target_id, change_summary
                    ) VALUES ($1, $2, 'release.rollback', 'knowledge_base', $3, $4::jsonb)
                    """,
                    access["tenant_id"],
                    user_id,
                    str(target["knowledge_base_id"]),
                    json.dumps(
                        {
                            "release_id": str(release_id),
                            "build_id": str(target["build_id"]),
                            "previous_release_id": str(current_release_id),
                            "manifest_hash": target["manifest_hash"],
                        },
                        ensure_ascii=False,
                    ),
                )
            return {
                **dict(rolled_back),
                "previous_release_id": str(current_release_id),
            }
        finally:
            await connection.close()

    @app.post("/api/v1/knowledge-bases/{knowledge_base_id}/builds", status_code=202)
    async def create_build(knowledge_base_id: int, request: Request) -> dict[str, Any]:
        """冻结当前有效文档与 Profile，创建异步构建并记录构建请求审计。"""
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _require_knowledge_base_role(
                connection,
                context,
                knowledge_base_id,
                {"space_admin", "kb_admin"},
            )
            user_id = int(context["user"]["id"])
            async with connection.transaction():
                knowledge_base = await connection.fetchrow(
                    """
                    SELECT id, tenant_id, content_epoch, active_release_id, active_runtime_id
                    FROM knowledge_bases WHERE id = $1 AND tenant_id = $2
                    FOR UPDATE
                    """,
                    knowledge_base_id,
                    access["tenant_id"],
                )
                if knowledge_base is None:
                    raise HTTPException(status_code=404, detail="知识库不存在")
                active_build = await connection.fetchval(
                    """
                    SELECT id FROM index_builds
                    WHERE knowledge_base_id = $1 AND state IN ('queued','running','validating')
                    ORDER BY id DESC LIMIT 1
                    """,
                    knowledge_base_id,
                )
                if active_build is not None:
                    raise HTTPException(status_code=409, detail="该知识库已有正在执行的构建")
                documents = await connection.fetch(
                    """
                    SELECT d.id AS document_id, d.title, d.desired_version_id,
                           dv.parse_status, artifact.id AS artifact_id,
                           artifact.ingestion_profile_id, artifact.state AS artifact_state,
                           count(c.id)::int AS chunk_count
                    FROM documents d
                    LEFT JOIN document_versions dv ON dv.id = d.desired_version_id
                      AND dv.tenant_id = d.tenant_id
                    LEFT JOIN LATERAL (
                      SELECT da.id, da.ingestion_profile_id, da.state
                      FROM document_artifacts da
                      WHERE da.tenant_id = d.tenant_id
                        AND da.document_version_id = d.desired_version_id
                      ORDER BY da.created_at DESC, da.id DESC LIMIT 1
                    ) artifact ON true
                    LEFT JOIN chunks c ON c.tenant_id = d.tenant_id
                      AND c.artifact_id = artifact.id
                    WHERE d.tenant_id = $1 AND d.knowledge_base_id = $2
                      AND d.status = 'active'
                    GROUP BY d.id, dv.id, artifact.id, artifact.ingestion_profile_id,
                             artifact.state
                    ORDER BY d.id
                    """,
                    access["tenant_id"],
                    knowledge_base_id,
                )
                if not documents:
                    raise HTTPException(status_code=409, detail="知识库中没有可构建文档")
                invalid_documents = [
                    str(document["title"])
                    for document in documents
                    if document["desired_version_id"] is None
                    or document["parse_status"] != "complete"
                    or document["artifact_id"] is None
                    or document["artifact_state"] != "ready"
                    or int(document["chunk_count"]) == 0
                ]
                if invalid_documents:
                    raise HTTPException(
                        status_code=409,
                        detail=f"以下文档尚未完整解析：{'、'.join(invalid_documents[:5])}",
                    )
                ingestion_profile_ids = {
                    int(document["ingestion_profile_id"]) for document in documents
                }
                if len(ingestion_profile_ids) != 1:
                    raise HTTPException(
                        status_code=409,
                        detail="文档切片配置不一致，请重新解析后构建",
                    )
                configured_embedding = None
                if knowledge_base["active_runtime_id"] is not None:
                    configured_embedding = await connection.fetchrow(
                        """
                        SELECT ep.id, ep.model_name, ep.model_revision, ep.dimension,
                               me.base_url, me.allowed_models, me.status AS endpoint_status
                        FROM runtime_profiles rp
                        JOIN embedding_profiles ep ON ep.id = rp.embedding_profile_id
                        JOIN model_endpoints me ON me.id = ep.model_endpoint_id
                        WHERE rp.id = $1 AND rp.tenant_id = $2
                          AND rp.knowledge_base_id = $3
                        """,
                        knowledge_base["active_runtime_id"],
                        access["tenant_id"],
                        knowledge_base_id,
                    )
                if configured_embedding is not None:
                    if configured_embedding["endpoint_status"] != "active":
                        raise HTTPException(status_code=409, detail="当前嵌入模型端点已停用")
                    allowed_models = _json_value(configured_embedding["allowed_models"], [])
                    effective_settings = gateway_settings(
                        config,
                        base_url=str(configured_embedding["base_url"]),
                        allowed_models=allowed_models,
                        embedding_model=str(configured_embedding["model_name"]),
                        embedding_dimensions=int(configured_embedding["dimension"]),
                    )
                    try:
                        model_revision = await ModelGatewayClient(
                            effective_settings
                        ).model_revision()
                    except (httpx.HTTPError, ValueError) as error:
                        raise HTTPException(status_code=503, detail="嵌入模型当前不可用") from error
                    if model_revision != configured_embedding["model_revision"]:
                        raise HTTPException(
                            status_code=409,
                            detail="嵌入模型内容已变化，请创建新的 Embedding Profile",
                        )
                    embedding_profile_id = int(configured_embedding["id"])
                    selected_embedding_model = str(configured_embedding["model_name"])
                    selected_embedding_dimension = int(configured_embedding["dimension"])
                else:
                    try:
                        model_revision = await ModelGatewayClient(config).model_revision()
                    except (httpx.HTTPError, ValueError) as error:
                        raise HTTPException(status_code=503, detail="嵌入模型当前不可用") from error
                    embedding_profile_id, _ = await _ensure_embedding_profile(
                        connection,
                        config,
                        model_revision,
                    )
                    selected_embedding_model = config.embedding_model
                    selected_embedding_dimension = config.embedding_dimensions
                ingestion_profile_id = ingestion_profile_ids.pop()
                existing = await connection.fetchrow(
                    """
                    SELECT ib.id::text, ib.task_id::text, ib.state, ib.created_at,
                           ib.updated_at, ib.input_epoch, ep.model_name,
                           ep.model_revision, ep.dimension
                    FROM index_builds ib
                    JOIN embedding_profiles ep ON ep.id = ib.embedding_profile_id
                    WHERE ib.knowledge_base_id = $1 AND ib.input_epoch = $2
                      AND ib.ingestion_profile_id = $3 AND ib.embedding_profile_id = $4
                    """,
                    knowledge_base_id,
                    knowledge_base["content_epoch"],
                    ingestion_profile_id,
                    embedding_profile_id,
                )
                if existing is not None:
                    return {**dict(existing), "reused": True}
                task = await connection.fetchrow(
                    """
                    INSERT INTO tasks(
                      tenant_id, knowledge_base_id, task_type, state,
                      idempotency_key, created_by
                    ) VALUES ($1, $2, 'index_build', 'queued', $3, $4)
                    RETURNING id
                    """,
                    access["tenant_id"],
                    knowledge_base_id,
                    (
                        f"index-build:{knowledge_base_id}:"
                        f"{knowledge_base['content_epoch']}:{embedding_profile_id}"
                    ),
                    user_id,
                )
                build = await connection.fetchrow(
                    """
                    INSERT INTO index_builds(
                      tenant_id, knowledge_base_id, base_release_id, input_epoch,
                      ingestion_profile_id, embedding_profile_id, runtime_profile_id, task_id,
                      state, created_by
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'queued', $9)
                    RETURNING id::text, task_id::text, state, input_epoch, created_at, updated_at
                    """,
                    access["tenant_id"],
                    knowledge_base_id,
                    knowledge_base["active_release_id"],
                    knowledge_base["content_epoch"],
                    ingestion_profile_id,
                    embedding_profile_id,
                    knowledge_base["active_runtime_id"],
                    task["id"],
                    user_id,
                )
                for document in documents:
                    await connection.execute(
                        """
                        INSERT INTO build_items(
                          build_id, tenant_id, knowledge_base_id, document_id,
                          document_version_id, artifact_id, chunk_count
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                        """,
                        int(build["id"]),
                        access["tenant_id"],
                        knowledge_base_id,
                        document["document_id"],
                        document["desired_version_id"],
                        document["artifact_id"],
                        document["chunk_count"],
                    )
                    await connection.execute(
                        """
                        INSERT INTO task_items(task_id, target_id, stage, state)
                        VALUES ($1, $2, 'embed', 'queued')
                        """,
                        task["id"],
                        document["desired_version_id"],
                    )
                await connection.execute(
                    """
                    INSERT INTO outbox_events(tenant_id, event_type, payload)
                    VALUES ($1, 'index.build.requested', $2::jsonb)
                    """,
                    access["tenant_id"],
                    json.dumps(
                        {"task_id": str(task["id"]), "build_id": build["id"]},
                        ensure_ascii=False,
                    ),
                )
                # 记录快照关键标识与数量，不把文档正文、向量或模型凭据写入审计。
                await write_audit_event(
                    connection,
                    tenant_id=int(access["tenant_id"]),
                    actor_id=user_id,
                    action="build.create",
                    target_type="build",
                    target_id=build["id"],
                    summary={
                        "knowledge_base_id": str(knowledge_base_id),
                        "task_id": str(task["id"]),
                        "input_epoch": int(knowledge_base["content_epoch"]),
                        "document_count": len(documents),
                        "ingestion_profile_id": str(ingestion_profile_id),
                        "embedding_profile_id": str(embedding_profile_id),
                    },
                )
            return {
                **dict(build),
                "knowledge_base_id": str(knowledge_base_id),
                "document_count": len(documents),
                "model_name": selected_embedding_model,
                "model_revision": model_revision,
                "dimension": selected_embedding_dimension,
                "reused": False,
            }
        except asyncpg.UniqueViolationError as error:
            raise HTTPException(status_code=409, detail="相同内容和模型的构建已经存在") from error
        finally:
            await connection.close()

    @app.get("/api/v1/tasks")
    async def list_tasks(
        request: Request,
        tenant_id: int | None = None,
        knowledge_base_id: int | None = None,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            if knowledge_base_id is not None:
                access = await _knowledge_base_access(connection, context, knowledge_base_id)
                if tenant_id is not None and int(access["tenant_id"]) != tenant_id:
                    raise HTTPException(status_code=404, detail="任务不存在")
                tenant_ids = [int(access["tenant_id"])]
                kb_ids = [knowledge_base_id]
            elif tenant_id is not None:
                await _assert_tenant_access(connection, context, tenant_id)
                tenant_ids = [tenant_id]
                kb_ids = None
            else:
                tenant_ids = [int(space["id"]) for space in context["spaces"]]
                kb_ids = None
            if not tenant_ids:
                return {"items": []}
            rows = await connection.fetch(
                """
                SELECT t.id::text, t.tenant_id::text, t.knowledge_base_id::text,
                       t.task_type, t.state, t.attempt, t.error, t.created_at, t.updated_at,
                       count(ti.id)::int AS item_count,
                       count(ti.id) FILTER (WHERE ti.state = 'completed')::int AS completed_items
                FROM tasks t LEFT JOIN task_items ti ON ti.task_id = t.id
                WHERE t.tenant_id = ANY($1::bigint[])
                  AND ($2::bigint[] IS NULL OR t.knowledge_base_id = ANY($2::bigint[]))
                GROUP BY t.id ORDER BY t.created_at DESC LIMIT 100
                """,
                tenant_ids,
                kb_ids,
            )
            return {"items": _rows(rows)}
        finally:
            await connection.close()

    @app.get("/api/v1/tasks/{task_id}")
    async def task_detail(task_id: int, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            task = await connection.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
            if task is None:
                raise HTTPException(status_code=404, detail="任务不存在")
            if task["knowledge_base_id"] is not None:
                await _knowledge_base_access(connection, context, int(task["knowledge_base_id"]))
            elif int(task["tenant_id"]) not in {int(space["id"]) for space in context["spaces"]}:
                raise HTTPException(status_code=404, detail="任务不存在")
            items = await connection.fetch(
                """
                SELECT id::text, target_id::text, stage, state, attempt, error, updated_at
                FROM task_items WHERE task_id = $1 ORDER BY id
                """,
                task_id,
            )
            return {"task": {**dict(task), "id": str(task["id"])}, "items": _rows(items)}
        finally:
            await connection.close()

    @app.post("/api/v1/tasks/{task_id}/retry")
    async def retry_task(task_id: int, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            task = await connection.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
            if task is None or task["knowledge_base_id"] is None:
                raise HTTPException(status_code=404, detail="任务不存在")
            retry_roles = (
                {"space_admin", "kb_admin"}
                if task["task_type"] == "index_build"
                else {"space_admin", "kb_admin", "editor"}
            )
            access = await _require_knowledge_base_role(
                connection,
                context,
                int(task["knowledge_base_id"]),
                retry_roles,
            )
            if task["state"] not in {"failed", "cancelled", "interrupted"}:
                raise HTTPException(status_code=409, detail="当前任务状态不能重试")
            event_type = {
                "document_parse": "document.parse.requested",
                "index_build": "index.build.requested",
            }.get(str(task["task_type"]))
            if event_type is None:
                raise HTTPException(status_code=409, detail="当前任务类型暂不支持重试")
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    UPDATE tasks SET state = 'queued', error = NULL,
                        lease_until = NULL, updated_at = now()
                    WHERE id = $1
                    RETURNING id::text, tenant_id::text, knowledge_base_id::text,
                              task_type, state, attempt, error, created_at, updated_at
                    """,
                    task_id,
                )
                await connection.execute(
                    """
                    UPDATE task_items SET state = 'queued', error = NULL, updated_at = now()
                    WHERE task_id = $1 AND state <> 'completed'
                    """,
                    task_id,
                )
                if task["task_type"] == "index_build":
                    await connection.execute(
                        """
                        UPDATE index_builds SET state = 'queued', error = NULL, updated_at = now()
                        WHERE task_id = $1
                        """,
                        task_id,
                    )
                    await connection.execute(
                        """
                        UPDATE build_items SET state = 'queued', error = NULL, updated_at = now()
                        WHERE build_id = (SELECT id FROM index_builds WHERE task_id = $1)
                          AND state <> 'completed'
                        """,
                        task_id,
                    )
                await connection.execute(
                    """
                    INSERT INTO outbox_events(tenant_id, event_type, payload)
                    VALUES ($1, $2, $3::jsonb)
                    """,
                    task["tenant_id"],
                    event_type,
                    json.dumps({"task_id": str(task_id)}, ensure_ascii=False),
                )
            if row is None:
                raise HTTPException(status_code=404, detail="任务不存在")
            return {**dict(row), "knowledge_base_name": access["name"]}
        finally:
            await connection.close()

    @app.post("/api/v1/tasks/{task_id}/cancel")
    async def cancel_task(task_id: int, request: Request) -> None:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            task = await connection.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
            if task is None or task["knowledge_base_id"] is None:
                raise HTTPException(status_code=404, detail="任务不存在")
            cancel_roles = (
                {"space_admin", "kb_admin"}
                if task["task_type"] == "index_build"
                else {"space_admin", "kb_admin", "editor"}
            )
            await _require_knowledge_base_role(
                connection,
                context,
                int(task["knowledge_base_id"]),
                cancel_roles,
            )
            if task["state"] not in {"queued", "running"}:
                raise HTTPException(status_code=409, detail="当前任务状态不能取消")
            await connection.execute(
                "UPDATE tasks SET state = 'cancelled', updated_at = now() WHERE id = $1",
                task_id,
            )
            if task["task_type"] == "index_build":
                await connection.execute(
                    """
                    UPDATE index_builds SET state = 'cancelled', updated_at = now()
                    WHERE task_id = $1 AND state IN ('queued','running','validating')
                    """,
                    task_id,
                )
                await connection.execute(
                    """
                    UPDATE build_items SET state = 'cancelled', updated_at = now()
                    WHERE build_id = (SELECT id FROM index_builds WHERE task_id = $1)
                      AND state <> 'completed'
                    """,
                    task_id,
                )
            await connection.execute(
                """
                UPDATE task_items SET state = 'cancelled', updated_at = now()
                WHERE task_id = $1 AND state <> 'completed'
                """,
                task_id,
            )
        finally:
            await connection.close()

    @app.post("/api/v1/documents/{document_id}/disable", status_code=204)
    async def disable_document(document_id: int, request: Request) -> None:
        """停用文档并提升内容世代，使后续构建排除该来源且保留审计证据。"""
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _document_access(connection, context, document_id)
            role = _role_for_access(access)
            if role not in {"space_admin", "kb_admin", "editor"}:
                raise HTTPException(status_code=403, detail="当前角色不能停用文档")
            if access["status"] != "active":
                raise HTTPException(status_code=409, detail="当前文档状态不能停用")
            async with connection.transaction():
                await connection.execute(
                    """
                    UPDATE documents
                    SET status = 'disabled', updated_at = now()
                    WHERE id = $1 AND status = 'active'
                    """,
                    document_id,
                )
                await connection.execute(
                    """
                    UPDATE knowledge_bases SET content_epoch = content_epoch + 1,
                        updated_at = now() WHERE id = $1
                    """,
                    access["knowledge_base_id"],
                )
                await write_audit_event(
                    connection,
                    tenant_id=int(access["tenant_id"]),
                    actor_id=int(context["user"]["id"]),
                    action="document.disable",
                    target_type="document",
                    target_id=document_id,
                    summary={
                        "knowledge_base_id": str(access["knowledge_base_id"]),
                        "before": {"status": str(access["status"])},
                        "after": {"status": "disabled"},
                        "active_release_id": (
                            str(access["active_release_id"])
                            if access["active_release_id"] is not None
                            else None
                        ),
                    },
                )
        finally:
            await connection.close()

    @app.delete("/api/v1/documents/{document_id}", status_code=204)
    async def delete_document(document_id: int, request: Request) -> None:
        """软删除文档并提升内容世代，保留历史版本和不可变删除审计。"""
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _document_access(connection, context, document_id)
            role = _role_for_access(access)
            if role not in {"space_admin", "kb_admin"}:
                raise HTTPException(status_code=403, detail="当前角色不能删除文档")
            if access["status"] == "deleted":
                raise HTTPException(status_code=404, detail="文档不存在")
            async with connection.transaction():
                await connection.execute(
                    """
                    UPDATE documents
                    SET status = 'deleted', deleted_at = now(), updated_at = now()
                    WHERE id = $1 AND status <> 'deleted'
                    """,
                    document_id,
                )
                await connection.execute(
                    """
                    UPDATE knowledge_bases SET content_epoch = content_epoch + 1,
                        updated_at = now() WHERE id = $1
                    """,
                    access["knowledge_base_id"],
                )
                await write_audit_event(
                    connection,
                    tenant_id=int(access["tenant_id"]),
                    actor_id=int(context["user"]["id"]),
                    action="document.delete",
                    target_type="document",
                    target_id=document_id,
                    summary={
                        "knowledge_base_id": str(access["knowledge_base_id"]),
                        "before": {"status": str(access["status"])},
                        "after": {"status": "deleted"},
                        "active_release_id": (
                            str(access["active_release_id"])
                            if access["active_release_id"] is not None
                            else None
                        ),
                    },
                )
        finally:
            await connection.close()
