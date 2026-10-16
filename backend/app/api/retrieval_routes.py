# ruff: noqa
# mypy: ignore-errors
"""检索调试、会话、回答和引用路由。

路由函数保持薄层，领域规则继续由 app.main 中的兼容辅助函数和 app.rag 服务提供。
"""

from fastapi import FastAPI
from app.main import *  # noqa: F403,F401


def register(app: FastAPI, config: Settings) -> None:
    """将本领域路由挂载到应用；config 是应用级配置快照。"""
    from app import main as main_module

    globals().update(main_module.__dict__)

    @app.get("/api/v1/builds")
    async def list_builds(
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
                    raise HTTPException(status_code=404, detail="构建不存在")
                tenant_ids = [int(access["tenant_id"])]
            elif tenant_id is not None:
                await _assert_tenant_access(connection, context, tenant_id)
                tenant_ids = [tenant_id]
            else:
                tenant_ids = [int(space["id"]) for space in context["spaces"]]
            if not tenant_ids:
                return {"items": []}
            rows = await connection.fetch(
                """
                SELECT ib.id::text, ib.tenant_id::text, ib.knowledge_base_id::text,
                       kb.name AS knowledge_base_name, ib.input_epoch, ib.state, ib.error,
                       ib.created_at, ib.updated_at, ib.task_id::text,
                       ib.embedding_profile_id::text, ib.runtime_profile_id::text,
                       ep.model_name, ep.model_revision,
                       ep.dimension, ep.definition_hash AS embedding_definition_hash,
                       me.provider, me.base_url, kr.id::text AS release_id,
                       CASE WHEN kb.active_release_id = kr.id THEN true ELSE false END
                         AS is_active_release,
                       count(bi.document_id)::int AS document_count,
                       count(bi.document_id) FILTER (WHERE bi.state = 'completed')::int
                         AS completed_documents,
                       COALESCE(sum(bi.chunk_count), 0)::int AS chunk_count,
                       COALESCE(sum(bi.embedded_count), 0)::int AS embedded_count
                FROM index_builds ib
                JOIN knowledge_bases kb ON kb.id = ib.knowledge_base_id
                  AND kb.tenant_id = ib.tenant_id
                JOIN embedding_profiles ep ON ep.id = ib.embedding_profile_id
                JOIN model_endpoints me ON me.id = ep.model_endpoint_id
                LEFT JOIN kb_releases kr ON kr.build_id = ib.id
                LEFT JOIN build_items bi ON bi.build_id = ib.id AND bi.tenant_id = ib.tenant_id
                WHERE ib.tenant_id = ANY($1::bigint[])
                  AND ($2::bigint IS NULL OR ib.knowledge_base_id = $2)
                GROUP BY ib.id, kb.name, kb.active_release_id, ep.id, me.id, kr.id
                ORDER BY ib.created_at DESC, ib.id DESC
                """,
                tenant_ids,
                knowledge_base_id,
            )
            return {
                "items": [{**dict(row), "error": _json_value(row["error"], None)} for row in rows]
            }
        finally:
            await connection.close()

    @app.get("/api/v1/builds/{build_id}")
    async def build_detail(build_id: int, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            build = await connection.fetchrow(
                """
                SELECT ib.id::text, ib.tenant_id::text, ib.knowledge_base_id::text,
                       ib.input_epoch, ib.state, ib.error, ib.created_at, ib.updated_at,
                       ib.task_id::text, ib.embedding_profile_id::text,
                       ib.runtime_profile_id::text,
                       ep.model_name, ep.model_revision, ep.dimension,
                       ep.definition_hash AS embedding_definition_hash,
                       me.provider, me.base_url, kr.id::text AS release_id,
                       CASE WHEN kb.active_release_id = kr.id THEN true ELSE false END
                         AS is_active_release
                FROM index_builds ib
                JOIN knowledge_bases kb ON kb.id = ib.knowledge_base_id
                  AND kb.tenant_id = ib.tenant_id
                JOIN embedding_profiles ep ON ep.id = ib.embedding_profile_id
                JOIN model_endpoints me ON me.id = ep.model_endpoint_id
                LEFT JOIN kb_releases kr ON kr.build_id = ib.id
                WHERE ib.id = $1
                """,
                build_id,
            )
            if build is None:
                raise HTTPException(status_code=404, detail="构建不存在")
            await _knowledge_base_access(connection, context, int(build["knowledge_base_id"]))
            items = await connection.fetch(
                """
                SELECT bi.document_id::text, d.title, bi.document_version_id::text,
                       dv.version_no, bi.artifact_id::text, bi.state, bi.chunk_count,
                       bi.embedded_count, bi.error, bi.updated_at
                FROM build_items bi
                JOIN documents d ON d.id = bi.document_id AND d.tenant_id = bi.tenant_id
                JOIN document_versions dv ON dv.id = bi.document_version_id
                  AND dv.tenant_id = bi.tenant_id
                WHERE bi.build_id = $1 ORDER BY d.title, bi.document_id
                """,
                build_id,
            )
            return {
                "build": {**dict(build), "error": _json_value(build["error"], None)},
                "items": [
                    {**dict(item), "error": _json_value(item["error"], None)} for item in items
                ],
            }
        finally:
            await connection.close()

    @app.get("/api/v1/knowledge-bases/{knowledge_base_id}/releases")
    async def list_releases(knowledge_base_id: int, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _knowledge_base_access(connection, context, knowledge_base_id)
            rows = await connection.fetch(
                """
                SELECT kr.id::text, kr.build_id::text, kr.manifest_hash, kr.state,
                       kr.created_at, kr.embedding_profile_id::text,
                       ep.model_name, ep.model_revision, ep.dimension,
                       ep.definition_hash AS embedding_definition_hash,
                       me.provider, me.base_url,
                       count(ri.document_id)::int AS document_count,
                       CASE WHEN kb.active_release_id = kr.id THEN true ELSE false END
                         AS is_active
                FROM kb_releases kr
                JOIN knowledge_bases kb ON kb.id = kr.knowledge_base_id
                  AND kb.tenant_id = kr.tenant_id
                JOIN embedding_profiles ep ON ep.id = kr.embedding_profile_id
                JOIN model_endpoints me ON me.id = ep.model_endpoint_id
                LEFT JOIN release_items ri ON ri.release_id = kr.id
                  AND ri.tenant_id = kr.tenant_id
                WHERE kr.tenant_id = $1 AND kr.knowledge_base_id = $2
                GROUP BY kr.id, kb.active_release_id, ep.id, me.id
                ORDER BY kr.created_at DESC, kr.id DESC
                """,
                access["tenant_id"],
                knowledge_base_id,
            )
            items = _rows(rows)
            current_release_id = (
                int(access["active_release_id"])
                if access["active_release_id"] is not None
                else None
            )
            rollback_ids = (
                rollback_candidate_ids(items, current_release_id=current_release_id)
                if _role_for_access(access) in {"space_admin", "kb_admin"}
                else set()
            )
            for item in items:
                item["rollback_available"] = int(item["id"]) in rollback_ids
            return {
                "active_release_id": (
                    str(access["active_release_id"])
                    if access["active_release_id"] is not None
                    else None
                ),
                "items": items,
            }
        finally:
            await connection.close()

    @app.get("/api/v1/builds/{build_id}/release-preview")
    async def release_preview(build_id: int, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            preview = await _load_release_preview(connection, build_id)
            if preview is None:
                raise HTTPException(status_code=404, detail="构建不存在")
            build = preview["build_record"]
            await _require_knowledge_base_role(
                connection,
                context,
                int(build["knowledge_base_id"]),
                {"space_admin", "kb_admin"},
            )
            return _release_preview_response(preview)
        finally:
            await connection.close()

    @app.post("/api/v1/search-test")
    async def search_test(payload: SearchTestRequest, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _knowledge_base_access(
                connection,
                context,
                payload.knowledge_base_id,
            )
            diagnostic_started = time.perf_counter()
            try:
                result = await execute_vector_search(
                    connection,
                    config,
                    tenant_id=int(access["tenant_id"]),
                    knowledge_base_id=payload.knowledge_base_id,
                    user_id=int(context["user"]["id"]),
                    query=payload.query,
                    active_release_id=(
                        int(access["active_release_id"])
                        if access["active_release_id"] is not None
                        else None
                    ),
                    top_k=payload.top_k,
                    context_max_chars=payload.context_max_chars,
                    business_scenario=payload.business_scenario,
                    target_users=payload.target_users,
                    source_system=payload.source_system,
                    business_tags=payload.business_tags,
                    trust_levels=payload.trust_levels,
                )
            except RetrievalServiceError as error:
                # 只记录检索状态和 trace 关联信息，不记录问题正文、候选片段或模型响应。
                trace_id = error.trace_id
                await write_audit_event(
                    connection,
                    tenant_id=int(access["tenant_id"]),
                    actor_id=int(context["user"]["id"]),
                    action="search_test.run",
                    target_type="retrieval_trace" if trace_id else "knowledge_base",
                    target_id=trace_id or payload.knowledge_base_id,
                    summary={
                        "knowledge_base_id": str(payload.knowledge_base_id),
                        "trace_id": str(trace_id) if trace_id else None,
                        "state": "failed",
                        "error_code": "RETRIEVAL_SERVICE_ERROR",
                        "total_ms": round((time.perf_counter() - diagnostic_started) * 1000, 2),
                    },
                )
                raise HTTPException(status_code=502, detail=str(error)) from error
            trace_id = result.get("trace_id")
            await write_audit_event(
                connection,
                tenant_id=int(access["tenant_id"]),
                actor_id=int(context["user"]["id"]),
                action="search_test.run",
                target_type="retrieval_trace" if trace_id else "knowledge_base",
                target_id=trace_id or payload.knowledge_base_id,
                summary={
                    "knowledge_base_id": str(payload.knowledge_base_id),
                    "trace_id": trace_id,
                    "state": str(result.get("state", "unknown")),
                    "item_count": len(result.get("items") or []),
                    "total_ms": (result.get("timings") or {}).get(
                        "total_ms",
                        round((time.perf_counter() - diagnostic_started) * 1000, 2),
                    ),
                },
            )
            return result
        finally:
            await connection.close()

    @app.get("/api/v1/assistant/conversations")
    async def list_assistant_conversations(request: Request) -> dict[str, Any]:
        """列出当前 API Key 所属客户空间中的助理会话，不按知识库拆分。"""
        context = await _authenticated_user(config, request)
        tenant_id = context.get("api_key_tenant_id")
        if tenant_id is None or context.get("api_key_id") is None:
            raise HTTPException(status_code=403, detail="自动范围助理仅支持公司 API Key")
        connection = await _database(config)
        try:
            rows = await connection.fetch(
                """
                SELECT conversation.public_id::text AS id, conversation.tenant_id::text,
                       'auto'::text AS scope, conversation.title, conversation.status,
                       conversation.created_at, conversation.updated_at,
                       count(message.id)::int AS message_count
                FROM conversations conversation
                LEFT JOIN messages message ON message.conversation_id = conversation.id
                  AND message.tenant_id = conversation.tenant_id
                WHERE conversation.tenant_id = $1 AND conversation.owner_user_id = $2
                  AND conversation.scope = 'assistant' AND conversation.status = 'active'
                GROUP BY conversation.id
                ORDER BY conversation.updated_at DESC, conversation.id DESC
                LIMIT $3
                """,
                int(tenant_id),
                int(context["user"]["id"]),
                SESSION_LIST_LIMIT,
            )
            return {"items": _rows(rows)}
        finally:
            await connection.close()

    @app.post("/api/v1/assistant/conversations", status_code=201)
    async def create_assistant_conversation(
        payload: AssistantConversationCreate,
        request: Request,
    ) -> dict[str, Any]:
        """创建不绑定知识库的会话；运行时由 API Key 确定全空间检索范围。"""
        context = await _authenticated_user(config, request)
        tenant_id = context.get("api_key_tenant_id")
        if tenant_id is None or context.get("api_key_id") is None:
            raise HTTPException(status_code=403, detail="自动范围助理仅支持公司 API Key")
        connection = await _database(config)
        try:
            row = await connection.fetchrow(
                """
                INSERT INTO conversations(
                  tenant_id, knowledge_base_id, scope, owner_user_id, title
                ) VALUES ($1, NULL, 'assistant', $2, $3)
                RETURNING public_id::text AS id, tenant_id::text, 'auto'::text AS scope,
                          title, status,
                          created_at, updated_at
                """,
                int(tenant_id),
                int(context["user"]["id"]),
                payload.title,
            )
            if row is None:
                raise HTTPException(status_code=500, detail="助理会话创建失败")
            return dict(row)
        finally:
            await connection.close()

    @app.get("/api/v1/assistant/conversations/{conversation_id}")
    async def get_assistant_conversation(
        conversation_id: UUID,
        request: Request,
    ) -> dict[str, Any]:
        """读取助理会话历史及每条回答的引用，权限范围固定为当前 API Key。"""
        context = await _authenticated_user(config, request)
        tenant_id = context.get("api_key_tenant_id")
        api_key_id = context.get("api_key_id")
        if tenant_id is None or api_key_id is None:
            raise HTTPException(status_code=403, detail="自动范围助理仅支持公司 API Key")
        connection = await _database(config)
        try:
            conversation = await connection.fetchrow(
                """
                SELECT id, public_id::text AS public_id, tenant_id::text, scope,
                       title, status, created_at, updated_at
                FROM conversations
                WHERE public_id = $1 AND tenant_id = $2 AND owner_user_id = $3
                  AND scope = 'assistant' AND status = 'active'
                """,
                conversation_id,
                int(tenant_id),
                int(context["user"]["id"]),
            )
            if conversation is None:
                raise HTTPException(status_code=404, detail="助理会话不存在")
            rows = await connection.fetch(
                """
                SELECT message.id::text, message.role, message.content, message.state,
                       message.created_at, run.id::text AS run_id
                FROM messages message
                LEFT JOIN generation_runs run ON run.assistant_message_id = message.id
                  AND run.tenant_id = message.tenant_id
                WHERE message.tenant_id = $1 AND message.conversation_id = $2
                ORDER BY message.created_at, message.id
                """,
                int(tenant_id),
                int(conversation["id"]),
            )
            messages = []
            for row in rows:
                item = dict(row)
                item["citations"] = []
                item["hidden"] = False
                if item["run_id"] is not None:
                    snapshot = await load_run_snapshot(
                        connection,
                        run_id=int(item["run_id"]),
                        user_id=int(context["user"]["id"]),
                        api_key_tenant_id=int(tenant_id),
                        api_key_id=str(api_key_id),
                    )
                    if snapshot is not None:
                        item["content"] = snapshot["answer"]
                        item["state"] = snapshot["message_state"]
                        item["citations"] = snapshot["citations"]
                        item["run_state"] = snapshot["state"]
                        item["outcome"] = snapshot["outcome"]
                        item["hidden"] = snapshot["hidden"]
                    else:
                        # 运行快照会校验 API Key 归属；无权读取时不能回退到原始消息正文。
                        item["content"] = ""
                        item["state"] = "hidden"
                        item["hidden"] = True
                messages.append(item)
            return {
                "conversation": {
                    "id": str(conversation_id),
                    "tenant_id": str(tenant_id),
                    "scope": "auto",
                    "title": conversation["title"],
                    "status": conversation["status"],
                    "created_at": conversation["created_at"],
                    "updated_at": conversation["updated_at"],
                },
                "messages": messages,
            }
        finally:
            await connection.close()

    @app.delete("/api/v1/assistant/conversations/{conversation_id}", status_code=204)
    async def delete_assistant_conversation(
        conversation_id: UUID,
        request: Request,
    ) -> None:
        """软删除当前 API Key 所有者的助理会话并保留可审计历史。"""
        context = await _authenticated_user(config, request)
        tenant_id = context.get("api_key_tenant_id")
        if tenant_id is None or context.get("api_key_id") is None:
            raise HTTPException(status_code=403, detail="自动范围助理仅支持公司 API Key")
        connection = await _database(config)
        try:
            result = await connection.execute(
                """
                UPDATE conversations SET status = 'deleted', updated_at = now()
                WHERE public_id = $1 AND tenant_id = $2 AND owner_user_id = $3
                  AND scope = 'assistant' AND status = 'active'
                """,
                conversation_id,
                int(tenant_id),
                int(context["user"]["id"]),
            )
            if result.endswith(" 0"):
                raise HTTPException(status_code=404, detail="助理会话不存在")
        finally:
            await connection.close()

    @app.post("/api/v1/assistant/conversations/{conversation_id}/runs", status_code=202)
    async def create_assistant_run(
        conversation_id: UUID,
        payload: RunCreate,
        request: Request,
    ) -> dict[str, Any]:
        """提交助理问题；调用方不传知识库，运行器从 API Key 和问题自动分流。"""
        context = await _authenticated_user(config, request)
        tenant_id = context.get("api_key_tenant_id")
        api_key_id = context.get("api_key_id")
        if tenant_id is None or api_key_id is None:
            raise HTTPException(status_code=403, detail="自动范围助理仅支持公司 API Key")
        connection = await _database(config)
        try:
            conversation = await connection.fetchrow(
                """
                SELECT id, tenant_id, knowledge_base_id, owner_user_id, title, status, scope,
                       NULL::text AS knowledge_base_name, NULL::bigint AS active_release_id,
                       NULL::bigint AS active_runtime_id
                FROM conversations
                WHERE public_id = $1 AND tenant_id = $2 AND owner_user_id = $3
                  AND scope = 'assistant' AND status = 'active'
                """,
                conversation_id,
                int(tenant_id),
                int(context["user"]["id"]),
            )
            if conversation is None:
                raise HTTPException(status_code=404, detail="助理会话不存在")
            async with connection.transaction():
                result = await _create_generation_run(
                    connection,
                    conversation=conversation,
                    user_id=int(context["user"]["id"]),
                    request_id=payload.request_id,
                    question=payload.question,
                    api_key_id=str(api_key_id),
                )
                return _public_run_payload(result)
        finally:
            await connection.close()

    @app.get("/api/v1/conversations")
    async def list_conversations(
        request: Request,
        knowledge_base_id: int,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _knowledge_base_access(connection, context, knowledge_base_id)
            rows = await connection.fetch(
                """
                SELECT conversation.public_id::text AS id, conversation.tenant_id::text,
                       conversation.knowledge_base_id::text, conversation.title,
                       conversation.status, conversation.created_at, conversation.updated_at,
                       count(message.id)::int AS message_count
                FROM conversations conversation
                LEFT JOIN messages message ON message.conversation_id = conversation.id
                  AND message.tenant_id = conversation.tenant_id
                WHERE conversation.tenant_id = $1
                  AND conversation.knowledge_base_id = $2
                  AND conversation.owner_user_id = $3
                  AND conversation.status = 'active'
                GROUP BY conversation.id
                ORDER BY conversation.updated_at DESC, conversation.id DESC
                """,
                access["tenant_id"],
                knowledge_base_id,
                int(context["user"]["id"]),
            )
            return {"items": _rows(rows)}
        finally:
            await connection.close()

    @app.post("/api/v1/conversations", status_code=201)
    async def create_conversation(
        payload: ConversationCreate,
        request: Request,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _knowledge_base_access(connection, context, payload.knowledge_base_id)
            row = await connection.fetchrow(
                """
                INSERT INTO conversations(
                  tenant_id, knowledge_base_id, owner_user_id, title
                ) VALUES ($1, $2, $3, $4)
                RETURNING public_id::text AS id, tenant_id::text, knowledge_base_id::text,
                          title, status, created_at, updated_at
                """,
                access["tenant_id"],
                payload.knowledge_base_id,
                int(context["user"]["id"]),
                payload.title,
            )
            if row is None:
                raise HTTPException(status_code=500, detail="会话创建失败")
            return dict(row)
        finally:
            await connection.close()

    @app.delete("/api/v1/conversations/{conversation_id}", status_code=204)
    async def delete_conversation(conversation_id: UUID, request: Request) -> None:
        """软删除当前用户拥有的会话，保留消息历史并写入租户审计日志。"""
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            internal_id = await _conversation_id_from_public(connection, context, conversation_id)
            conversation = await _conversation_access(connection, context, internal_id)
            # 会话只能由其所有者删除；复用访问检查可同时保证知识库权限和租户隔离。
            async with connection.transaction():
                await connection.execute(
                    """
                    UPDATE conversations
                    SET status = 'deleted', updated_at = now()
                    WHERE id = $1 AND tenant_id = $2 AND status = 'active'
                    """,
                    internal_id,
                    conversation["tenant_id"],
                )
                await write_audit_event(
                    connection,
                    tenant_id=int(conversation["tenant_id"]),
                    actor_id=int(context["user"]["id"]),
                    action="conversation.delete",
                    target_type="conversation",
                    target_id=str(conversation_id),
                    summary={
                        "knowledge_base_id": str(conversation["knowledge_base_id"]),
                        "before": {"status": str(conversation["status"])},
                        "after": {"status": "deleted"},
                    },
                )
        finally:
            await connection.close()

    @app.get("/api/v1/conversations/{conversation_id}")
    async def get_conversation(conversation_id: UUID, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            conversation_id_int = await _conversation_id_from_public(
                connection, context, conversation_id
            )
            conversation = await _conversation_access(
                connection,
                context,
                conversation_id_int,
            )
            rows = await connection.fetch(
                """
                SELECT message.id::text, message.role, message.content, message.state,
                       message.release_id::text, message.created_at,
                       run.id::text AS run_id, feedback.rating AS feedback_rating,
                       feedback.reason AS feedback_reason
                FROM messages message
                LEFT JOIN generation_runs run ON run.assistant_message_id = message.id
                  AND run.tenant_id = message.tenant_id
                LEFT JOIN feedback ON feedback.message_id = message.id
                  AND feedback.tenant_id = message.tenant_id AND feedback.user_id = $3
                WHERE message.tenant_id = $1 AND message.conversation_id = $2
                ORDER BY message.created_at, message.id
                """,
                conversation["tenant_id"],
                conversation_id_int,
                int(context["user"]["id"]),
            )
            messages = []
            for row in rows:
                item = dict(row)
                item["citations"] = []
                item["hidden"] = False
                if item["run_id"] is not None:
                    snapshot = await load_run_snapshot(
                        connection,
                        run_id=int(item["run_id"]),
                        user_id=int(context["user"]["id"]),
                        api_key_tenant_id=context.get("api_key_tenant_id"),
                        api_key_id=context.get("api_key_id"),
                    )
                    if snapshot is not None:
                        item["content"] = snapshot["answer"]
                        item["state"] = snapshot["message_state"]
                        item["citations"] = snapshot["citations"]
                        item["hidden"] = snapshot["hidden"]
                        item["run_state"] = snapshot["state"]
                        item["outcome"] = snapshot["outcome"]
                messages.append(item)
            return {
                "conversation": {
                    "id": str(conversation_id),
                    "tenant_id": str(conversation["tenant_id"]),
                    "knowledge_base_id": str(conversation["knowledge_base_id"]),
                    "knowledge_base_name": conversation["knowledge_base_name"],
                    "title": conversation["title"],
                    "status": conversation["status"],
                    "active_release_id": (
                        str(conversation["active_release_id"])
                        if conversation["active_release_id"] is not None
                        else None
                    ),
                },
                "messages": messages,
            }
        finally:
            await connection.close()

    @app.post("/api/v1/conversations/{conversation_id}/runs", status_code=202)
    async def create_run(
        conversation_id: UUID,
        payload: RunCreate,
        request: Request,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            conversation_id_int = await _conversation_id_from_public(
                connection, context, conversation_id
            )
            conversation = await _conversation_access(connection, context, conversation_id_int)
            async with connection.transaction():
                result = await _create_generation_run(
                    connection,
                    conversation=conversation,
                    user_id=int(context["user"]["id"]),
                    request_id=payload.request_id,
                    question=payload.question,
                    api_key_id=context.get("api_key_id"),
                )
                return _public_run_payload(result)
        finally:
            await connection.close()

    @app.get("/api/v1/runs/{run_id}")
    async def get_run(run_id: UUID, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            run_id_int = await _run_id_from_public(connection, str(run_id))
            snapshot = await load_run_snapshot(
                connection,
                run_id=run_id_int,
                user_id=int(context["user"]["id"]),
                api_key_tenant_id=context.get("api_key_tenant_id"),
                api_key_id=context.get("api_key_id"),
            )
            if snapshot is None:
                raise HTTPException(status_code=404, detail="问答运行不存在")
            return _public_run_payload(snapshot)
        finally:
            await connection.close()

    @app.get("/api/v1/runs/{run_id}/events")
    async def stream_run_events(run_id: UUID, request: Request) -> StreamingResponse:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            run_id_int = await _run_id_from_public(connection, str(run_id))
        finally:
            await connection.close()
        return StreamingResponse(
            stream_generation_run(
                config,
                run_id=run_id_int,
                user_id=int(context["user"]["id"]),
                api_key_id=context.get("api_key_id"),
                api_key_tenant_id=context.get("api_key_tenant_id"),
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/api/v1/runs/{run_id}/cancel")
    async def cancel_run(run_id: UUID, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            run_id_int = await _run_id_from_public(connection, str(run_id))
            snapshot = await load_run_snapshot(
                connection,
                run_id=run_id_int,
                user_id=int(context["user"]["id"]),
                api_key_tenant_id=context.get("api_key_tenant_id"),
                api_key_id=context.get("api_key_id"),
            )
            if snapshot is None:
                raise HTTPException(status_code=404, detail="问答运行不存在")
            if snapshot["state"] in {"completed", "failed", "cancelled"}:
                return _public_run_payload(snapshot)
            async with connection.transaction():
                cancelled_run_id = await connection.fetchval(
                    """
                    UPDATE generation_runs SET cancel_requested = true,
                        state = 'cancelled', completed_at = now(),
                        updated_at = now()
                    WHERE id = $1 AND tenant_id = $2 AND state IN ('queued','running')
                    RETURNING id
                    """,
                    run_id_int,
                    int(snapshot["tenant_id"]),
                )
                if cancelled_run_id is not None:
                    await connection.execute(
                        """
                        UPDATE retrieval_traces SET state = 'cancelled'
                        WHERE tenant_id = $1 AND message_id = $2 AND state = 'running'
                        """,
                        int(snapshot["tenant_id"]),
                        int(snapshot["assistant_message_id"]),
                    )
                    await connection.execute(
                        """
                        UPDATE messages SET state = 'cancelled'
                        WHERE id = $1 AND tenant_id = $2
                        """,
                        int(snapshot["assistant_message_id"]),
                        int(snapshot["tenant_id"]),
                    )
            latest = await load_run_snapshot(
                connection,
                run_id=run_id_int,
                user_id=int(context["user"]["id"]),
                api_key_tenant_id=context.get("api_key_tenant_id"),
                api_key_id=context.get("api_key_id"),
            )
            if latest is None:
                raise HTTPException(status_code=404, detail="问答运行不存在")
            return _public_run_payload(latest)
        finally:
            await connection.close()

    @app.post("/api/v1/runs/{run_id}/retry", status_code=202)
    async def retry_run(
        run_id: UUID,
        payload: RunRetryRequest,
        request: Request,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            run_id_int = await _run_id_from_public(connection, str(run_id))
            snapshot = await load_run_snapshot(
                connection,
                run_id=run_id_int,
                user_id=int(context["user"]["id"]),
                api_key_tenant_id=context.get("api_key_tenant_id"),
                api_key_id=context.get("api_key_id"),
            )
            if snapshot is None:
                raise HTTPException(status_code=404, detail="问答运行不存在")
            if snapshot["state"] not in {"failed", "cancelled"}:
                raise HTTPException(status_code=409, detail="只有失败或已取消的运行可以重试")
            conversation = await _conversation_access(
                connection,
                context,
                int(snapshot["conversation_id"]),
            )
            async with connection.transaction():
                result = await _create_generation_run(
                    connection,
                    conversation=conversation,
                    user_id=int(context["user"]["id"]),
                    request_id=payload.request_id,
                    question=str(snapshot["question"]),
                    user_message_id=int(snapshot["user_message_id"]),
                    api_key_id=context.get("api_key_id"),
                )
                return _public_run_payload(result)
        finally:
            await connection.close()

    @app.post("/api/v1/messages/{message_id}/feedback")
    async def save_feedback(
        message_id: int,
        payload: FeedbackCreate,
        request: Request,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            message = await connection.fetchrow(
                """
                SELECT message.id, message.tenant_id, message.conversation_id
                FROM messages message
                WHERE message.id = $1 AND message.role = 'assistant'
                """,
                message_id,
            )
            if message is None:
                raise HTTPException(status_code=404, detail="回答不存在")
            await _conversation_access(connection, context, int(message["conversation_id"]))
            row = await connection.fetchrow(
                """
                INSERT INTO feedback(tenant_id, message_id, user_id, rating, reason)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (message_id, user_id)
                DO UPDATE SET rating = EXCLUDED.rating, reason = EXCLUDED.reason,
                              created_at = now()
                RETURNING message_id::text, rating, reason, created_at
                """,
                message["tenant_id"],
                message_id,
                int(context["user"]["id"]),
                payload.rating,
                payload.reason,
            )
            if row is None:
                raise HTTPException(status_code=500, detail="反馈保存失败")
            return dict(row)
        finally:
            await connection.close()
