# ruff: noqa
# mypy: ignore-errors
"""知识库、成员、文档和内容预览路由。

路由函数保持薄层，领域规则继续由 app.main 中的兼容辅助函数和 app.rag 服务提供。
"""

from fastapi import FastAPI
from app.main import *  # noqa: F403,F401


def register(app: FastAPI, config: Settings) -> None:
    """将本领域路由挂载到应用；config 是应用级配置快照。"""
    from app import main as main_module

    globals().update(main_module.__dict__)

    @app.get("/api/v1/knowledge-bases")
    async def list_knowledge_bases(
        request: Request, tenant_id: int | None = None
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            api_key_tenant_id = context.get("api_key_tenant_id")
            if api_key_tenant_id is not None:
                if tenant_id is not None and tenant_id != int(api_key_tenant_id):
                    raise HTTPException(status_code=404, detail="客户空间不存在")
                tenant_ids = [int(api_key_tenant_id)]
            elif tenant_id is None:
                tenant_ids = [int(space["id"]) for space in context["spaces"]]
            else:
                await _assert_tenant_access(connection, context, tenant_id)
                tenant_ids = [tenant_id]
            if not tenant_ids:
                return {"items": []}
            if api_key_tenant_id is not None:
                rows = await connection.fetch(
                    """
                    SELECT kb.id::text, kb.tenant_id::text, kb.name, kb.description,
                           kb.purpose, kb.status, kb.active_release_id::text, kb.updated_at,
                           kb.business_scenario, kb.target_users, kb.owner_user_id::text,
                           kb.trust_level, kb.valid_from, kb.valid_until, kb.source_system,
                           kb.business_tags,
                           count(DISTINCT d.id)::int AS document_count
                    FROM knowledge_bases kb
                    JOIN tenants tenant ON tenant.id = kb.tenant_id AND tenant.status = 'active'
                    LEFT JOIN documents d
                      ON d.tenant_id = kb.tenant_id AND d.knowledge_base_id = kb.id
                     AND d.status <> 'deleted'
                    WHERE kb.tenant_id = $1 AND kb.status <> 'disabled'
                      AND kb.active_release_id IS NOT NULL
                    GROUP BY kb.id ORDER BY kb.updated_at DESC
                    """,
                    int(api_key_tenant_id),
                )
                return {"items": _rows(rows)}
            rows = await connection.fetch(
                """
                SELECT kb.id::text, kb.tenant_id::text, kb.name, kb.description, kb.purpose,
                       kb.status, kb.active_release_id::text, kb.updated_at,
                       kb.business_scenario, kb.target_users, kb.owner_user_id::text,
                       kb.trust_level, kb.valid_from, kb.valid_until, kb.source_system,
                       kb.business_tags,
                       count(DISTINCT d.id)::int AS document_count
                FROM knowledge_bases kb LEFT JOIN documents d
                  ON d.tenant_id = kb.tenant_id AND d.knowledge_base_id = kb.id
                 AND d.status <> 'deleted'
                WHERE kb.tenant_id = ANY($1::bigint[]) AND kb.status <> 'disabled'
                  AND EXISTS (
                    SELECT 1 FROM tenant_members tm JOIN roles r ON r.id = tm.role_id
                    WHERE tm.tenant_id = kb.tenant_id AND tm.user_id = $2
                       AND tm.status = 'active' AND (
                         r.code IN ('space_admin', 'customer_reader') OR EXISTS (
                           SELECT 1 FROM kb_members km
                          WHERE km.knowledge_base_id = kb.id AND km.tenant_id = kb.tenant_id
                            AND km.user_id = tm.user_id AND km.status = 'active'
                         )
                       ) AND (r.code <> 'customer_reader' OR kb.active_release_id IS NOT NULL)
                  )
                GROUP BY kb.id ORDER BY kb.updated_at DESC
                """,
                tenant_ids,
                int(context["user"]["id"]),
            )
            return {"items": _rows(rows)}
        finally:
            await connection.close()

    @app.post("/api/v1/knowledge-bases", status_code=201)
    async def create_knowledge_base(
        payload: KnowledgeBaseCreate,
        request: Request,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            await _assert_tenant_access(connection, context, payload.tenant_id)
            user_id = int(context["user"]["id"])
            can_create = await connection.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM tenant_members tm JOIN roles r ON r.id = tm.role_id
                    WHERE tm.tenant_id = $1 AND tm.user_id = $2 AND tm.status = 'active'
                      AND r.code = 'space_admin'
                )
                """,
                payload.tenant_id,
                user_id,
            )
            if not can_create:
                raise HTTPException(status_code=403, detail="当前角色不能创建知识库")
            if payload.owner_user_id is not None:
                owner_exists = await connection.fetchval(
                    """
                    SELECT EXISTS (
                      SELECT 1 FROM tenant_members
                      WHERE tenant_id = $1 AND user_id = $2 AND status = 'active'
                    )
                    """,
                    payload.tenant_id,
                    payload.owner_user_id,
                )
                if not owner_exists:
                    raise HTTPException(status_code=400, detail="负责人不是当前空间有效成员")
            async with connection.transaction():
                return await _create_knowledge_base(connection, payload, user_id)
        except asyncpg.UniqueViolationError as error:
            raise HTTPException(status_code=409, detail="该空间已存在同名知识库") from error
        finally:
            await connection.close()

    @app.patch("/api/v1/knowledge-bases/{knowledge_base_id}/governance")
    async def update_knowledge_base_governance(
        knowledge_base_id: int,
        payload: KnowledgeBasePatch,
        request: Request,
    ) -> dict[str, Any]:
        """更新知识库治理元数据；仅空间管理员或知识库管理员可修改。"""
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _require_knowledge_base_role(
                connection, context, knowledge_base_id, {"space_admin", "kb_admin"}
            )
            values = payload.model_dump(exclude_unset=True)
            if not values:
                raise HTTPException(status_code=400, detail="没有需要修改的治理字段")
            if payload.owner_user_id is not None:
                owner_exists = await connection.fetchval(
                    """
                    SELECT EXISTS (
                      SELECT 1 FROM tenant_members
                      WHERE tenant_id = $1 AND user_id = $2 AND status = 'active'
                    )
                    """,
                    int(access["tenant_id"]),
                    payload.owner_user_id,
                )
                if not owner_exists:
                    raise HTTPException(status_code=400, detail="负责人不是当前空间有效成员")
            if "business_tags" in values:
                values["business_tags"] = [str(tag).strip() for tag in values["business_tags"] if str(tag).strip()]
                if len(values["business_tags"]) > 30 or any(len(tag) > 40 for tag in values["business_tags"]):
                    raise HTTPException(status_code=400, detail="业务标签数量或长度超限")
            current = await connection.fetchrow(
                """SELECT business_scenario, target_users, owner_user_id, trust_level,
                          valid_from, valid_until, source_system, business_tags
                   FROM knowledge_bases WHERE id = $1 AND tenant_id = $2""",
                knowledge_base_id,
                int(access["tenant_id"]),
            )
            if current is None:
                raise HTTPException(status_code=404, detail="知识库不存在")
            valid_from = values.get("valid_from", current["valid_from"])
            valid_until = values.get("valid_until", current["valid_until"])
            if valid_from and valid_until and valid_until < valid_from:
                raise HTTPException(status_code=400, detail="有效期截止日不能早于起始日")
            assignments = []
            args: list[Any] = [knowledge_base_id]
            for index, field in enumerate(values, start=2):
                assignments.append(f"{field} = ${index}")
                args.append(values[field])
            args.append(int(access["tenant_id"]))
            async with connection.transaction():
                row = await connection.fetchrow(
                    f"""
                    UPDATE knowledge_bases SET {', '.join(assignments)}, updated_at = now()
                    WHERE id = $1 AND tenant_id = ${len(args)}
                    RETURNING id::text, tenant_id::text, name, description, purpose, status,
                              active_release_id::text, updated_at, business_scenario, target_users,
                              owner_user_id::text, trust_level, valid_from, valid_until,
                              source_system, business_tags
                    """,
                    *args,
                )
                await write_audit_event(
                    connection,
                    tenant_id=int(access["tenant_id"]),
                    actor_id=int(context["user"]["id"]),
                    action="knowledge_base.governance.update",
                    target_type="knowledge_base",
                    target_id=knowledge_base_id,
                    summary={
                        "changed_fields": sorted(values),
                        "before": {
                            field: str(current.get(field)) if current.get(field) is not None else None
                            for field in values
                        },
                        "after": {
                            field: str(row.get(field)) if row and row.get(field) is not None else None
                            for field in values
                        },
                    },
                )
            if row is None:
                raise HTTPException(status_code=404, detail="知识库不存在")
            return dict(row)
        finally:
            await connection.close()

    @app.get("/api/v1/spaces/{tenant_id}/members")
    async def list_space_members(tenant_id: int, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            await _require_space_admin(connection, context, tenant_id)
            rows = await connection.fetch(
                """
                SELECT u.id::text, u.login, u.display_name, u.status AS user_status,
                       tm.status, r.code AS role_code, r.name AS role_name,
                       tm.created_at,
                       count(DISTINCT km.knowledge_base_id) FILTER (
                         WHERE km.status = 'active'
                       )::int AS knowledge_base_count
                FROM tenant_members tm
                JOIN users u ON u.id = tm.user_id
                JOIN roles r ON r.id = tm.role_id
                LEFT JOIN kb_members km ON km.tenant_id = tm.tenant_id
                  AND km.user_id = tm.user_id
                WHERE tm.tenant_id = $1
                GROUP BY u.id, tm.status, r.code, r.name, tm.created_at
                ORDER BY (tm.status = 'active') DESC, tm.created_at, u.id
                """,
                tenant_id,
            )
            return {"items": _rows(rows)}
        finally:
            await connection.close()

    @app.post("/api/v1/spaces/{tenant_id}/members", status_code=201)
    async def add_space_member(
        tenant_id: int,
        payload: SpaceMemberCreate,
        request: Request,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            await _require_space_admin(connection, context, tenant_id)
            async with connection.transaction():
                user = await connection.fetchrow(
                    "SELECT id, login, display_name, status FROM users WHERE login = $1",
                    payload.login,
                )
                if user is None or user["status"] != "active":
                    raise HTTPException(status_code=404, detail="可用账号不存在")
                role_id = await connection.fetchval(
                    "SELECT id FROM roles WHERE code = $1 AND scope = 'tenant'",
                    payload.role_code,
                )
                if role_id is None:
                    raise HTTPException(status_code=400, detail="空间角色不存在")
                exists = await connection.fetchval(
                    """
                    SELECT EXISTS (
                      SELECT 1 FROM tenant_members WHERE tenant_id = $1 AND user_id = $2
                    )
                    """,
                    tenant_id,
                    user["id"],
                )
                if exists:
                    raise HTTPException(status_code=409, detail="该账号已经是空间成员")
                await connection.execute(
                    "INSERT INTO tenant_members(tenant_id, user_id, role_id) VALUES ($1, $2, $3)",
                    tenant_id,
                    user["id"],
                    role_id,
                )
                await connection.execute(
                    """
                    UPDATE knowledge_bases SET auth_epoch = auth_epoch + 1, updated_at = now()
                    WHERE tenant_id = $1
                    """,
                    tenant_id,
                )
                await _write_membership_audit(
                    connection,
                    tenant_id=tenant_id,
                    actor_id=int(context["user"]["id"]),
                    action="space_member.add",
                    target_type="user",
                    target_id=int(user["id"]),
                    summary={"role_code": payload.role_code, "status": "active"},
                )
            return {
                "id": str(user["id"]),
                "login": user["login"],
                "display_name": user["display_name"],
                "user_status": user["status"],
                "status": "active",
                "role_code": payload.role_code,
                "knowledge_base_count": 0,
            }
        finally:
            await connection.close()

    @app.patch("/api/v1/spaces/{tenant_id}/members/{user_id}")
    async def update_space_member(
        tenant_id: int,
        user_id: int,
        payload: SpaceMemberPatch,
        request: Request,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        values = payload.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=400, detail="没有需要修改的字段")
        connection = await _database(config)
        try:
            await _require_space_admin(connection, context, tenant_id)
            async with connection.transaction():
                current = await connection.fetchrow(
                    """
                    SELECT tm.status, r.code AS role_code
                    FROM tenant_members tm JOIN roles r ON r.id = tm.role_id
                    WHERE tm.tenant_id = $1 AND tm.user_id = $2
                    FOR UPDATE OF tm
                    """,
                    tenant_id,
                    user_id,
                )
                if current is None:
                    raise HTTPException(status_code=404, detail="空间成员不存在")
                next_role = payload.role_code or str(current["role_code"])
                next_status = payload.status or str(current["status"])
                await _assert_space_member_role_change(
                    connection,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    current_role=str(current["role_code"]),
                    next_role=next_role,
                    next_status=next_status,
                )
                role_id = await connection.fetchval(
                    "SELECT id FROM roles WHERE code = $1 AND scope = 'tenant'",
                    next_role,
                )
                row = await connection.fetchrow(
                    """
                    UPDATE tenant_members SET role_id = $3, status = $4
                    WHERE tenant_id = $1 AND user_id = $2
                    RETURNING user_id::text AS id, status, created_at
                    """,
                    tenant_id,
                    user_id,
                    role_id,
                    next_status,
                )
                await connection.execute(
                    """
                    UPDATE knowledge_bases SET auth_epoch = auth_epoch + 1, updated_at = now()
                    WHERE tenant_id = $1
                    """,
                    tenant_id,
                )
                await _write_membership_audit(
                    connection,
                    tenant_id=tenant_id,
                    actor_id=int(context["user"]["id"]),
                    action=(
                        "space_member.disable"
                        if next_status == "disabled"
                        else "space_member.update"
                    ),
                    target_type="user",
                    target_id=user_id,
                    summary={
                        "before": {
                            "role_code": current["role_code"],
                            "status": current["status"],
                        },
                        "after": {"role_code": next_role, "status": next_status},
                    },
                )
            if row is None:
                raise HTTPException(status_code=404, detail="空间成员不存在")
            return {**dict(row), "role_code": next_role}
        finally:
            await connection.close()

    @app.get("/api/v1/spaces/{tenant_id}/membership-audit")
    async def list_membership_audit(tenant_id: int, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            await _require_space_admin(connection, context, tenant_id)
            rows = await connection.fetch(
                """
                SELECT al.id::text, al.action, al.target_type, al.target_id,
                       al.change_summary, al.created_at,
                       actor.display_name AS actor_name,
                       target.display_name AS target_name
                FROM audit_logs al
                LEFT JOIN users actor ON actor.id = al.actor_id
                LEFT JOIN users target ON al.target_type = 'user'
                  AND target.id::text = al.target_id
                WHERE al.tenant_id = $1
                  AND al.action IN (
                    'space_member.add', 'space_member.update', 'space_member.disable',
                    'knowledge_base_member.add', 'knowledge_base_member.update',
                    'knowledge_base_member.revoke'
                  )
                ORDER BY al.created_at DESC, al.id DESC LIMIT 100
                """,
                tenant_id,
            )
            items = []
            for row in rows:
                item = dict(row)
                item["change_summary"] = _json_value(item["change_summary"], {})
                items.append(item)
            return {"items": items}
        finally:
            await connection.close()

    @app.get("/api/v1/audit-logs")
    async def list_audit_logs(
        request: Request,
        tenant_id: int | None = None,
        action_prefix: str = Query(default="", max_length=100),
        actor: str = Query(default="", max_length=100),
        target_type: str = Query(default="", max_length=80),
        cursor: int | None = Query(default=None, ge=1),
        limit: int = Query(default=30, ge=1, le=100),
    ) -> dict[str, Any]:
        """按平台或显式授权空间查询不可变审计事件，并使用 ID 游标分页。"""
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            if tenant_id is None:
                if context["user"]["platform_role"] != "platform_admin":
                    raise HTTPException(status_code=403, detail="只有平台管理员可以查看平台日志")
            else:
                await _require_space_admin(connection, context, tenant_id)

            rows = await connection.fetch(
                """
                SELECT al.id::text, al.tenant_id::text, tenant.name AS tenant_name,
                       al.actor_id::text, actor.display_name AS actor_name,
                       actor.login AS actor_login, al.action, al.target_type,
                       al.target_id, al.change_summary, al.request_id::text,
                       al.created_at
                FROM audit_logs al
                LEFT JOIN tenants tenant ON tenant.id = al.tenant_id
                LEFT JOIN users actor ON actor.id = al.actor_id
                WHERE (($1::bigint IS NULL AND al.tenant_id IS NULL) OR al.tenant_id = $1)
                  AND ($2 = '' OR al.action LIKE $2 || '%')
                  AND (
                    $3 = '' OR actor.display_name ILIKE '%' || $3 || '%'
                    OR actor.login ILIKE '%' || $3 || '%'
                  )
                  AND ($4 = '' OR al.target_type = $4)
                  AND ($5::bigint IS NULL OR al.id < $5)
                ORDER BY al.id DESC
                LIMIT $6
                """,
                tenant_id,
                action_prefix.strip(),
                actor.strip(),
                target_type.strip(),
                cursor,
                limit + 1,
            )
            has_more = len(rows) > limit
            visible_rows = rows[:limit]
            items = []
            for row in visible_rows:
                item = dict(row)
                item["change_summary"] = _json_value(item["change_summary"], {})
                items.append(item)
            return {
                "items": items,
                "next_cursor": items[-1]["id"] if has_more and items else None,
            }
        finally:
            await connection.close()

    @app.get("/api/v1/knowledge-bases/{knowledge_base_id}/documents")
    async def list_documents(knowledge_base_id: int, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _knowledge_base_access(connection, context, knowledge_base_id)
            role = _role_for_access(access)
            published_only = role in {"reader", "customer_reader"}
            rows = await connection.fetch(
                """
                SELECT d.id::text, d.title, d.status, d.created_at, d.updated_at,
                       dv.id::text AS version_id, dv.version_no, dv.parse_status,
                       dv.file_size, dv.mime_type, dv.created_at AS version_created_at,
                       CASE WHEN d.status = 'active'
                         AND kb.active_release_id IS NOT NULL AND EXISTS (
                         SELECT 1 FROM release_items ri
                         WHERE ri.release_id = kb.active_release_id AND ri.document_id = d.id
                           AND ri.document_version_id = dv.id
                       ) THEN true ELSE false END AS published
                FROM documents d
                JOIN knowledge_bases kb ON kb.id = d.knowledge_base_id
                LEFT JOIN LATERAL (
                  SELECT id, version_no, parse_status, file_size, mime_type, created_at
                  FROM document_versions
                  WHERE document_id = d.id
                  ORDER BY version_no DESC LIMIT 1
                ) dv ON true
                WHERE d.tenant_id = $1 AND d.knowledge_base_id = $2
                  AND d.status <> 'deleted'
                  AND ($3::boolean = false OR (d.status = 'active' AND EXISTS (
                    SELECT 1 FROM release_items ri
                    WHERE ri.release_id = kb.active_release_id AND ri.document_id = d.id
                      AND ri.document_version_id = dv.id
                  )))
                ORDER BY d.updated_at DESC, d.id DESC
                """,
                access["tenant_id"],
                knowledge_base_id,
                published_only,
            )
            return {
                "items": _rows(rows),
                "knowledge_base": {"id": str(access["id"]), "name": access["name"]},
            }
        finally:
            await connection.close()

    @app.get("/api/v1/knowledge-bases/{knowledge_base_id}/members")
    async def list_knowledge_base_members(
        knowledge_base_id: int,
        request: Request,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _require_knowledge_base_role(
                connection,
                context,
                knowledge_base_id,
                {"space_admin", "kb_admin"},
            )
            rows = await connection.fetch(
                """
                SELECT u.id::text, u.login, u.display_name,
                       tm.status AS space_status, tenant_role.code AS space_role_code,
                       km.status, kb_role.code AS role_code, kb_role.name AS role_name,
                       km.created_at
                FROM kb_members km
                JOIN users u ON u.id = km.user_id
                JOIN tenant_members tm ON tm.tenant_id = km.tenant_id
                  AND tm.user_id = km.user_id
                JOIN roles tenant_role ON tenant_role.id = tm.role_id
                JOIN roles kb_role ON kb_role.id = km.role_id
                WHERE km.tenant_id = $1 AND km.knowledge_base_id = $2
                ORDER BY (km.status = 'active') DESC, km.created_at, u.id
                """,
                access["tenant_id"],
                knowledge_base_id,
            )
            return {"items": _rows(rows)}
        finally:
            await connection.close()

    @app.get("/api/v1/knowledge-bases/{knowledge_base_id}/member-candidates")
    async def list_knowledge_base_member_candidates(
        knowledge_base_id: int,
        request: Request,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _require_knowledge_base_role(
                connection,
                context,
                knowledge_base_id,
                {"space_admin", "kb_admin"},
            )
            rows = await connection.fetch(
                """
                SELECT u.id::text, u.login, u.display_name,
                       km.status AS grant_status, kb_role.code AS grant_role_code
                FROM tenant_members tm
                JOIN users u ON u.id = tm.user_id AND u.status = 'active'
                JOIN roles tenant_role ON tenant_role.id = tm.role_id
                LEFT JOIN kb_members km ON km.tenant_id = tm.tenant_id
                  AND km.knowledge_base_id = $2 AND km.user_id = tm.user_id
                LEFT JOIN roles kb_role ON kb_role.id = km.role_id
                WHERE tm.tenant_id = $1 AND tm.status = 'active'
                  AND tenant_role.code = 'space_member'
                ORDER BY u.display_name, u.id
                """,
                access["tenant_id"],
                knowledge_base_id,
            )
            return {"items": _rows(rows)}
        finally:
            await connection.close()

    @app.post("/api/v1/knowledge-bases/{knowledge_base_id}/members", status_code=201)
    async def add_knowledge_base_member(
        knowledge_base_id: int,
        payload: KnowledgeBaseMemberCreate,
        request: Request,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _require_knowledge_base_role(
                connection,
                context,
                knowledge_base_id,
                {"space_admin", "kb_admin"},
            )
            async with connection.transaction():
                member = await connection.fetchrow(
                    """
                    SELECT tm.user_id, tm.status, r.code AS space_role_code,
                           u.login, u.display_name
                    FROM tenant_members tm
                    JOIN roles r ON r.id = tm.role_id
                    JOIN users u ON u.id = tm.user_id AND u.status = 'active'
                    WHERE tm.tenant_id = $1 AND tm.user_id = $2
                    """,
                    access["tenant_id"],
                    payload.user_id,
                )
                if member is None or member["status"] != "active":
                    raise HTTPException(status_code=400, detail="用户不是当前空间的有效成员")
                if member["space_role_code"] in {"space_admin", "customer_reader"}:
                    raise HTTPException(
                        status_code=409,
                        detail="空间管理员或客户用户无需叠加知识库授权",
                    )
                role_id = await connection.fetchval(
                    "SELECT id FROM roles WHERE code = $1 AND scope = 'knowledge_base'",
                    payload.role_code,
                )
                exists = await connection.fetchval(
                    """
                    SELECT EXISTS (
                      SELECT 1 FROM kb_members
                      WHERE knowledge_base_id = $1 AND user_id = $2
                    )
                    """,
                    knowledge_base_id,
                    payload.user_id,
                )
                if exists:
                    raise HTTPException(status_code=409, detail="该成员已有知识库授权")
                await connection.execute(
                    """
                    INSERT INTO kb_members(
                      tenant_id, knowledge_base_id, user_id, role_id
                    ) VALUES ($1, $2, $3, $4)
                    """,
                    access["tenant_id"],
                    knowledge_base_id,
                    payload.user_id,
                    role_id,
                )
                await connection.execute(
                    """
                    UPDATE knowledge_bases SET auth_epoch = auth_epoch + 1, updated_at = now()
                    WHERE id = $1 AND tenant_id = $2
                    """,
                    knowledge_base_id,
                    access["tenant_id"],
                )
                await _write_membership_audit(
                    connection,
                    tenant_id=int(access["tenant_id"]),
                    actor_id=int(context["user"]["id"]),
                    action="knowledge_base_member.add",
                    target_type="user",
                    target_id=payload.user_id,
                    summary={
                        "knowledge_base_id": str(knowledge_base_id),
                        "role_code": payload.role_code,
                        "status": "active",
                    },
                )
            return {
                "id": str(payload.user_id),
                "login": member["login"],
                "display_name": member["display_name"],
                "status": "active",
                "role_code": payload.role_code,
            }
        finally:
            await connection.close()

    @app.patch("/api/v1/knowledge-bases/{knowledge_base_id}/members/{user_id}")
    async def update_knowledge_base_member(
        knowledge_base_id: int,
        user_id: int,
        payload: KnowledgeBaseMemberPatch,
        request: Request,
    ) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        values = payload.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=400, detail="没有需要修改的字段")
        connection = await _database(config)
        try:
            access = await _require_knowledge_base_role(
                connection,
                context,
                knowledge_base_id,
                {"space_admin", "kb_admin"},
            )
            async with connection.transaction():
                current = await connection.fetchrow(
                    """
                    SELECT km.status, r.code AS role_code
                    FROM kb_members km JOIN roles r ON r.id = km.role_id
                    WHERE km.tenant_id = $1 AND km.knowledge_base_id = $2
                      AND km.user_id = $3
                    FOR UPDATE OF km
                    """,
                    access["tenant_id"],
                    knowledge_base_id,
                    user_id,
                )
                if current is None:
                    raise HTTPException(status_code=404, detail="知识库成员不存在")
                next_role = payload.role_code or str(current["role_code"])
                next_status = payload.status or str(current["status"])
                if next_status == "active":
                    eligible = await connection.fetchval(
                        """
                        SELECT EXISTS (
                          SELECT 1 FROM tenant_members tm
                          JOIN roles r ON r.id = tm.role_id
                          JOIN users u ON u.id = tm.user_id
                          WHERE tm.tenant_id = $1 AND tm.user_id = $2
                            AND tm.status = 'active' AND u.status = 'active'
                            AND r.code IN ('space_admin', 'space_member')
                        )
                        """,
                        access["tenant_id"],
                        user_id,
                    )
                    if not eligible:
                        raise HTTPException(
                            status_code=409,
                            detail="只有有效内部空间成员可以恢复知识库授权",
                        )
                role_id = await connection.fetchval(
                    "SELECT id FROM roles WHERE code = $1 AND scope = 'knowledge_base'",
                    next_role,
                )
                row = await connection.fetchrow(
                    """
                    UPDATE kb_members SET role_id = $4, status = $5
                    WHERE tenant_id = $1 AND knowledge_base_id = $2 AND user_id = $3
                    RETURNING user_id::text AS id, status, created_at
                    """,
                    access["tenant_id"],
                    knowledge_base_id,
                    user_id,
                    role_id,
                    next_status,
                )
                await connection.execute(
                    """
                    UPDATE knowledge_bases SET auth_epoch = auth_epoch + 1, updated_at = now()
                    WHERE id = $1 AND tenant_id = $2
                    """,
                    knowledge_base_id,
                    access["tenant_id"],
                )
                await _write_membership_audit(
                    connection,
                    tenant_id=int(access["tenant_id"]),
                    actor_id=int(context["user"]["id"]),
                    action=(
                        "knowledge_base_member.revoke"
                        if next_status == "disabled"
                        else "knowledge_base_member.update"
                    ),
                    target_type="user",
                    target_id=user_id,
                    summary={
                        "knowledge_base_id": str(knowledge_base_id),
                        "before": {
                            "role_code": current["role_code"],
                            "status": current["status"],
                        },
                        "after": {"role_code": next_role, "status": next_status},
                    },
                )
            if row is None:
                raise HTTPException(status_code=404, detail="知识库成员不存在")
            return {**dict(row), "role_code": next_role}
        finally:
            await connection.close()

    @app.post("/api/v1/knowledge-bases/{knowledge_base_id}/documents", status_code=202)
    async def upload_document(
        knowledge_base_id: int,
        request: Request,
        file: Annotated[UploadFile, File(...)],
    ) -> dict[str, Any]:
        """保存一个不可变文档版本，投递解析任务，并原子记录上传审计。"""
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        storage_path: Path | None = None
        try:
            access = await _require_knowledge_base_role(
                connection,
                context,
                knowledge_base_id,
                {"space_admin", "kb_admin", "editor"},
            )
            filename = _safe_filename(file.filename)
            suffix = _validate_upload_type(filename, file.content_type)
            raw = await _read_upload(file, suffix)
            title = Path(filename).stem[:240] or "未命名文档"
            storage_key = (
                f"tenant/{access['tenant_id']}/knowledge-base/{knowledge_base_id}/"
                f"{secrets.token_hex(16)}{suffix}"
            )
            storage_path = config.storage_root / storage_key
            storage_path.parent.mkdir(parents=True, exist_ok=True)
            storage_path.write_bytes(raw)
            user_id = int(context["user"]["id"])
            async with connection.transaction():
                document = await connection.fetchrow(
                    """
                    SELECT id FROM documents
                    WHERE tenant_id = $1 AND knowledge_base_id = $2 AND title = $3
                      AND status <> 'deleted'
                    ORDER BY id LIMIT 1
                    FOR UPDATE
                    """,
                    access["tenant_id"],
                    knowledge_base_id,
                    title,
                )
                if document is None:
                    document = await connection.fetchrow(
                        """
                        INSERT INTO documents(
                          tenant_id, knowledge_base_id, dataset_id, title, created_by
                        )
                        SELECT kb.tenant_id, kb.id, ds.id, $3, $4
                        FROM knowledge_bases kb JOIN datasets ds
                          ON ds.knowledge_base_id = kb.id AND ds.tenant_id = kb.tenant_id
                          AND ds.is_default = true
                        WHERE kb.id = $1 AND kb.tenant_id = $2
                        RETURNING id
                        """,
                        access["id"],
                        access["tenant_id"],
                        title,
                        user_id,
                    )
                if document is None:
                    raise HTTPException(status_code=409, detail="知识库默认数据集不存在")
                version_no = await connection.fetchval(
                    """
                    SELECT COALESCE(MAX(version_no), 0) + 1
                    FROM document_versions WHERE document_id = $1
                    """,
                    document["id"],
                )
                version = await connection.fetchrow(
                    """
                    INSERT INTO document_versions(
                      tenant_id, document_id, version_no, storage_key, sha256,
                      mime_type, file_size, parse_status, created_by
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, 'queued', $8)
                    RETURNING id, version_no, parse_status, created_at
                    """,
                    access["tenant_id"],
                    document["id"],
                    version_no,
                    storage_key,
                    hashlib.sha256(raw).hexdigest(),
                    ALLOWED_DOCUMENT_TYPES[suffix],
                    len(raw),
                    user_id,
                )
                await connection.execute(
                    """
                    UPDATE documents
                    SET desired_version_id = $1, updated_at = now()
                    WHERE id = $2
                    """,
                    version["id"],
                    document["id"],
                )
                await connection.execute(
                    """
                    UPDATE knowledge_bases SET content_epoch = content_epoch + 1,
                        updated_at = now() WHERE id = $1
                    """,
                    knowledge_base_id,
                )
                task = await connection.fetchrow(
                    """
                    INSERT INTO tasks(
                      tenant_id, knowledge_base_id, task_type, state,
                      idempotency_key, created_by
                    )
                    VALUES ($1, $2, 'document_parse', 'queued', $3, $4)
                    RETURNING id, state, task_type, created_at
                    """,
                    access["tenant_id"],
                    knowledge_base_id,
                    f"document-version:{version['id']}",
                    user_id,
                )
                await connection.execute(
                    """
                    INSERT INTO task_items(task_id, target_id, stage, state)
                    VALUES ($1, $2, 'parse', 'queued')
                    """,
                    task["id"],
                    version["id"],
                )
                await connection.execute(
                    """
                    INSERT INTO outbox_events(tenant_id, event_type, payload)
                    VALUES ($1, 'document.parse.requested', $2::jsonb)
                    """,
                    access["tenant_id"],
                    json.dumps(
                        {"task_id": str(task["id"]), "document_version_id": str(version["id"])}
                    ),
                )
                # 审计与版本、任务和 Outbox 同事务提交，避免出现无法追责的已入库文件。
                await write_audit_event(
                    connection,
                    tenant_id=int(access["tenant_id"]),
                    actor_id=user_id,
                    action="document.upload",
                    target_type="document",
                    target_id=int(document["id"]),
                    summary={
                        "knowledge_base_id": str(knowledge_base_id),
                        "document_version_id": str(version["id"]),
                        "version_no": int(version["version_no"]),
                        "task_id": str(task["id"]),
                        "mime_type": ALLOWED_DOCUMENT_TYPES[suffix],
                        "file_size": len(raw),
                    },
                )
            return {
                "document": {"id": str(document["id"]), "title": title},
                "version": {**dict(version), "id": str(version["id"])},
                "task": {**dict(task), "id": str(task["id"])},
            }
        except HTTPException:
            if storage_path is not None:
                storage_path.unlink(missing_ok=True)
            raise
        except asyncpg.UniqueViolationError as error:
            if storage_path is not None:
                storage_path.unlink(missing_ok=True)
            raise HTTPException(status_code=409, detail="该文档已有相同版本任务") from error
        except Exception:
            if storage_path is not None:
                storage_path.unlink(missing_ok=True)
            raise
        finally:
            await file.close()
            await connection.close()

    @app.get("/api/v1/documents/{document_id}")
    async def document_detail(document_id: int, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _document_access(connection, context, document_id)
            role = _role_for_access(access)
            rows = await connection.fetch(
                """
                SELECT id::text, version_no, sha256, mime_type, file_size, parse_status,
                       warnings, created_at
                FROM document_versions WHERE document_id = $1 ORDER BY version_no DESC
                """,
                document_id,
            )
            if role in {"reader", "customer_reader"}:
                if access["active_release_id"] is None or access["status"] != "active":
                    rows = []
                else:
                    visible_rows: list[asyncpg.Record] = []
                    for row in rows:
                        visible = await connection.fetchval(
                            """
                            SELECT EXISTS (
                              SELECT 1 FROM release_items
                              WHERE release_id = $1 AND document_id = $2
                                AND document_version_id = $3
                            )
                            """,
                            access["active_release_id"],
                            document_id,
                            int(row["id"]),
                        )
                        if visible:
                            visible_rows.append(row)
                    rows = visible_rows
            return {
                "document": {
                    "id": str(access["id"]),
                    "title": access["title"],
                    "status": access["status"],
                    "tenant_id": str(access["tenant_id"]),
                    "knowledge_base_id": str(access["knowledge_base_id"]),
                },
                "versions": [
                    {
                        **dict(row),
                        "warnings": _json_value(row["warnings"], []),
                    }
                    for row in rows
                ],
            }
        finally:
            await connection.close()

    @app.get("/api/v1/document-versions/{version_id}/preview")
    async def document_version_preview(version_id: int, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            version = await connection.fetchrow(
                """
                SELECT dv.id, dv.document_id, dv.version_no, dv.parse_status, dv.warnings,
                       d.title, d.tenant_id, d.knowledge_base_id
                FROM document_versions dv JOIN documents d ON d.id = dv.document_id
                WHERE dv.id = $1
                """,
                version_id,
            )
            if version is None:
                raise HTTPException(status_code=404, detail="文档版本不存在")
            access = await _document_access(connection, context, int(version["document_id"]))
            role = _role_for_access(access)
            if role in {"reader", "customer_reader"}:
                if access["status"] != "active":
                    raise HTTPException(status_code=404, detail="文档版本不存在")
                visible = (
                    await connection.fetchval(
                        """
                        SELECT EXISTS (
                          SELECT 1 FROM release_items
                          WHERE release_id = $1 AND document_id = $2
                            AND document_version_id = $3
                        )
                        """,
                        access["active_release_id"],
                        version["document_id"],
                        version_id,
                    )
                    if access["active_release_id"] is not None
                    else False
                )
                if not visible:
                    raise HTTPException(status_code=404, detail="文档版本不存在")
            chunks = await connection.fetch(
                """
                SELECT c.id::text, c.ordinal, c.content, c.section_path, c.locator,
                       c.token_count, da.state AS artifact_state
                FROM chunks c JOIN document_artifacts da ON da.id = c.artifact_id
                WHERE da.document_version_id = $1 ORDER BY c.ordinal
                """,
                version_id,
            )
            return {
                "document": {"id": str(version["document_id"]), "title": version["title"]},
                "version": {
                    "id": str(version["id"]),
                    "version_no": version["version_no"],
                    "parse_status": version["parse_status"],
                    "warnings": _json_value(version["warnings"], []),
                },
                "chunks": [
                    {
                        **dict(chunk),
                        "section_path": _json_value(chunk["section_path"], []),
                        "locator": _json_value(chunk["locator"], {}),
                    }
                    for chunk in chunks
                ],
            }
        finally:
            await connection.close()

    @app.get("/api/v1/admin/users/{user_id}")
    async def admin_user_detail(user_id: int, request: Request) -> dict[str, Any]:
        """返回平台用户资料、当前空间授权和脱敏授权审计历史。"""
        context = await _authenticated_user(config, request)
        if context["user"]["platform_role"] != "platform_admin":
            raise HTTPException(status_code=403, detail="只有平台管理员可以查看用户详情")
        connection = await _database(config)
        try:
            user = await connection.fetchrow(
                """
                SELECT u.id::text, u.login, u.display_name, u.status, pr.code AS platform_role,
                       u.last_login_at, u.created_at
                FROM users u LEFT JOIN roles pr ON pr.id = u.platform_role_id
                WHERE u.id = $1
                """,
                user_id,
            )
            if user is None:
                raise HTTPException(status_code=404, detail="用户不存在")
            memberships = await connection.fetch(
                """
                SELECT tm.tenant_id::text, t.code AS tenant_code, t.name AS tenant_name,
                       r.code AS role_code, tm.status, tm.created_at
                FROM tenant_members tm
                JOIN tenants t ON t.id = tm.tenant_id
                JOIN roles r ON r.id = tm.role_id
                WHERE tm.user_id = $1 ORDER BY tm.created_at DESC
                """,
                user_id,
            )
            history = await connection.fetch(
                """
                SELECT id::text, action, target_type, target_id, change_summary, created_at
                FROM audit_logs
                WHERE target_type = 'user' AND target_id = $1
                  AND action IN ('user.create', 'user.update', 'space_member.add',
                                 'space_member.update', 'space_member.remove')
                ORDER BY id DESC LIMIT 100
                """,
                str(user_id),
            )
            return {
                "user": dict(user),
                "memberships": _rows(memberships),
                "history": _rows(history),
            }
        finally:
            await connection.close()

    @app.get("/api/v1/document-versions/{version_id}/download")
    async def download_document_version(version_id: int, request: Request) -> Response:
        """按文档可见性提供原文件下载，拒绝跨租户、未发布版本和路径逃逸。"""
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            version = await connection.fetchrow(
                """
                SELECT dv.id, dv.document_id, dv.storage_key, dv.version_no,
                       dv.mime_type, d.title, d.tenant_id, d.knowledge_base_id
                FROM document_versions dv JOIN documents d ON d.id = dv.document_id
                WHERE dv.id = $1
                """,
                version_id,
            )
            if version is None:
                raise HTTPException(status_code=404, detail="文档版本不存在")
            access = await _document_access(connection, context, int(version["document_id"]))
            role = _role_for_access(access)
            if role in {"reader", "customer_reader"}:
                visible = access["status"] == "active" and access["active_release_id"] is not None
                if visible:
                    visible = await connection.fetchval(
                        """
                        SELECT EXISTS (
                          SELECT 1 FROM release_items
                          WHERE release_id = $1 AND document_id = $2
                            AND document_version_id = $3
                        )
                        """,
                        access["active_release_id"],
                        version["document_id"],
                        version_id,
                    )
                if not visible:
                    raise HTTPException(status_code=404, detail="文档版本不存在")
            root = config.storage_root.resolve()
            path = (root / str(version["storage_key"])).resolve()
            if root not in path.parents or not path.is_file():
                raise HTTPException(status_code=404, detail="文件不存在")
            extension = str(version["mime_type"]).split("/")[-1]
            safe_name = f"document-v{int(version['version_no'])}.{extension}"
            return FileResponse(
                path,
                media_type=str(version["mime_type"]),
                filename=safe_name,
                headers={"X-Content-Type-Options": "nosniff"},
            )
        finally:
            await connection.close()

    @app.post("/api/v1/documents/{document_id}/reparse", status_code=202)
    async def reparse_document(document_id: int, request: Request) -> dict[str, Any]:
        """重新排队文档最新版本的解析任务，复用原文件和版本记录。"""
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            document = await connection.fetchrow(
                """
                SELECT d.id, d.tenant_id, d.knowledge_base_id, dv.id AS version_id
                FROM documents d JOIN document_versions dv ON dv.id = d.desired_version_id
                WHERE d.id = $1
                """,
                document_id,
            )
            if document is None:
                raise HTTPException(status_code=404, detail="文档不存在")
            await _require_knowledge_base_role(
                connection,
                context,
                int(document["knowledge_base_id"]),
                {"space_admin", "kb_admin", "editor"},
            )
            task = await connection.fetchrow(
                """
                SELECT t.id, t.state, t.task_type, t.created_at
                FROM tasks t JOIN task_items ti ON ti.task_id = t.id
                WHERE t.task_type = 'document_parse' AND ti.target_id = $1
                ORDER BY t.id DESC LIMIT 1
                """,
                int(document["version_id"]),
            )
            if task is None:
                raise HTTPException(status_code=409, detail="该文档没有可重新解析的任务")
            if task["state"] in {"queued", "running"}:
                raise HTTPException(status_code=409, detail="文档解析任务正在执行")
            async with connection.transaction():
                await connection.execute(
                    """
                    UPDATE tasks SET state = 'queued', error = NULL,
                        lease_until = NULL, updated_at = now()
                    WHERE id = $1
                    """,
                    task["id"],
                )
                await connection.execute(
                    """
                    UPDATE task_items SET state = 'queued', error = NULL, updated_at = now()
                    WHERE task_id = $1
                    """,
                    task["id"],
                )
                await connection.execute(
                    """
                    INSERT INTO outbox_events(tenant_id, event_type, payload)
                    VALUES ($1, 'document.parse.requested', $2::jsonb)
                    """,
                    document["tenant_id"],
                    json.dumps({"task_id": str(task["id"])}, ensure_ascii=False),
                )
            return {**dict(task), "state": "queued", "version_id": str(document["version_id"])}
        finally:
            await connection.close()

    @app.get("/api/v1/documents/{document_id}/compare")
    async def compare_document_versions(
        document_id: int,
        request: Request,
        before_version_id: int,
        after_version_id: int,
    ) -> dict[str, Any]:
        """比较同一文档的两个版本切片，权限沿用文档详情访问边界。"""
        if before_version_id == after_version_id:
            raise HTTPException(status_code=400, detail="待比较的版本必须不同")
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            access = await _document_access(connection, context, document_id)
            versions = await connection.fetch(
                """
                SELECT id, version_no FROM document_versions
                WHERE document_id = $1 AND id = ANY($2::bigint[])
                """,
                document_id,
                [before_version_id, after_version_id],
            )
            if len(versions) != 2:
                raise HTTPException(status_code=404, detail="文档版本不存在")
            chunks = await connection.fetch(
                """
                SELECT da.document_version_id, c.ordinal, c.content
                FROM document_artifacts da JOIN chunks c ON c.artifact_id = da.id
                WHERE da.document_version_id = ANY($1::bigint[])
                ORDER BY da.document_version_id, c.ordinal
                """,
                [before_version_id, after_version_id],
            )
            before = [
                dict(row) for row in chunks if int(row["document_version_id"]) == before_version_id
            ]
            after = [
                dict(row) for row in chunks if int(row["document_version_id"]) == after_version_id
            ]
            version_map = {int(row["id"]): int(row["version_no"]) for row in versions}
            return {
                "document": {"id": str(access["id"]), "title": access["title"]},
                "before": {
                    "id": str(before_version_id),
                    "version_no": version_map[before_version_id],
                },
                "after": {
                    "id": str(after_version_id),
                    "version_no": version_map[after_version_id],
                },
                "diff": _version_diff(before, after),
            }
        finally:
            await connection.close()

    @app.get("/api/v1/artifacts/{artifact_id}/chunks")
    async def artifact_chunks(artifact_id: int, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            artifact = await connection.fetchrow(
                """
                SELECT document_version_id, knowledge_base_id
                FROM document_artifacts WHERE id = $1
                """,
                artifact_id,
            )
            if artifact is None:
                raise HTTPException(status_code=404, detail="处理产物不存在")
            version = await connection.fetchrow(
                "SELECT document_id FROM document_versions WHERE id = $1",
                artifact["document_version_id"],
            )
            if version is None:
                raise HTTPException(status_code=404, detail="处理产物不存在")
            access = await _document_access(connection, context, int(version["document_id"]))
            if _role_for_access(access) in {
                "reader",
                "customer_reader",
            }:
                visible = await connection.fetchval(
                    """
                    SELECT EXISTS (
                      SELECT 1 FROM release_items ri
                      JOIN documents d ON d.id = ri.document_id
                      WHERE ri.release_id = (
                        SELECT active_release_id FROM knowledge_bases WHERE id = $1
                      )
                        AND ri.document_id = $2 AND ri.document_version_id = $3
                        AND d.status = 'active'
                    )
                    """,
                    artifact["knowledge_base_id"],
                    int(version["document_id"]),
                    artifact["document_version_id"],
                )
                if not visible:
                    raise HTTPException(status_code=404, detail="处理产物不存在")
            rows = await connection.fetch(
                """
                SELECT id::text, ordinal, content, section_path, locator, token_count
                FROM chunks WHERE artifact_id = $1 ORDER BY ordinal
                """,
                artifact_id,
            )
            return {"items": _rows(rows)}
        finally:
            await connection.close()
