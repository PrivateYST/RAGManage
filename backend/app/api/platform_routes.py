# ruff: noqa
# mypy: ignore-errors
"""平台管理、模型配置和空间管理路由。

路由函数保持薄层，领域规则继续由 app.main 中的兼容辅助函数和 app.rag 服务提供。
"""

from fastapi import FastAPI
from app.main import *  # noqa: F403,F401


def register(app: FastAPI, config: Settings) -> None:
    """将本领域路由挂载到应用；config 是应用级配置快照。"""
    from app import main as main_module

    globals().update(main_module.__dict__)
    # 模型网关密钥替换状态只属于当前 API 进程，不能写入模块全局状态。
    runtime_gateway_key_configured = False

    @app.get("/api/v1/api-keys")
    async def list_api_keys(request: Request) -> dict[str, Any]:
        """列出公司发放的 Key 及输入/输出/总额度，不返回明文 Key。"""
        context = await _authenticated_user(config, request)
        _require_platform_admin(context)
        connection = await _database(config)
        try:
            rows = await connection.fetch(
                """
                SELECT ak.id::text, ak.tenant_id::text, t.name AS tenant_name,
                       ak.name, ak.provider, ak.key_prefix, ak.token_limit, ak.token_used,
                       ak.token_reserved,
                       GREATEST(0, ak.token_limit - ak.token_used - ak.token_reserved)
                         AS token_remaining,
                       CASE WHEN ak.status = 'active' AND ak.expires_at IS NOT NULL
                                  AND ak.expires_at <= now()
                            THEN 'expired' ELSE ak.status END AS status,
                       COALESCE(usage_totals.prompt_tokens, 0)::bigint AS prompt_tokens,
                       COALESCE(usage_totals.completion_tokens, 0)::bigint
                         AS completion_tokens,
                       ak.expires_at, ak.last_used_at, ak.created_at, ak.revoked_at,
                       ak.configured_at
                FROM api_keys ak
                JOIN tenants t ON t.id = ak.tenant_id
                LEFT JOIN LATERAL (
                  SELECT sum(usage.prompt_tokens) AS prompt_tokens,
                         sum(usage.completion_tokens) AS completion_tokens
                  FROM api_key_usage usage WHERE usage.api_key_id = ak.id
                ) usage_totals ON true
                WHERE ak.deleted_at IS NULL
                ORDER BY ak.created_at DESC, ak.id DESC
                """
            )
            return {"items": [dict(row) for row in rows]}
        finally:
            await connection.close()

    @app.post("/api/v1/api-keys", status_code=201)
    async def create_api_key(payload: ApiKeyCreate, request: Request) -> dict[str, Any]:
        """为医院创建一次性展示的 ``sk-`` 网关 Key，并绑定 Token 配额。

        默认模式由 RAGManage 生成 ``sk-`` 格式的客户网关 Key；只有显式开启
        Open WebUI provisioning 时，才会改为从远端账号生成原生 Key。
        """
        context = await _authenticated_user(config, request)
        _require_platform_admin(context)
        connection = await _database(config)
        raw_key: str
        provider = "local"
        provider_user_id: str | None = None
        provider_user_email: str | None = None
        provider_user_password: str | None = None
        existing_service_email: str | None = None
        existing_service_password: str | None = None
        try:
            tenant_name = await connection.fetchval(
                "SELECT name FROM tenants WHERE id = $1 AND status = 'active'",
                payload.tenant_id,
            )
            if tenant_name is None:
                raise HTTPException(status_code=404, detail="客户空间不存在或已停用")
            if config.open_webui_provisioning_enabled:
                # 服务账号由平台级网关 Key 通过管理员接口创建；医院不会接触该 Key。
                await load_persisted_model_gateway_key(config)
                if not config.model_gateway_api_key.get_secret_value().strip():
                    raise OpenWebUIKeyProvisioningError("全局模型网关 Key 未配置")
                existing = await connection.fetchval(
                    """
                    SELECT id FROM api_keys
                    WHERE tenant_id = $1 AND provider = 'open_webui' AND deleted_at IS NULL
                    """,
                    payload.tenant_id,
                )
                if existing is not None:
                    raise HTTPException(
                        status_code=409, detail="该医院已经存在模型网关 Key，请先删除或轮换"
                    )
                previous = await connection.fetchrow(
                    """
                    SELECT provider_user_email, provider_user_password
                    FROM api_keys
                    WHERE tenant_id = $1 AND provider = 'open_webui' AND deleted_at IS NOT NULL
                    ORDER BY deleted_at DESC
                    LIMIT 1
                    """,
                    payload.tenant_id,
                )
                if previous is not None:
                    if not isinstance(previous.get("provider_user_email"), str) or not isinstance(
                        previous.get("provider_user_password"), str
                    ):
                        raise OpenWebUIKeyProvisioningError("历史 Open WebUI 服务账号信息不完整")
                    try:
                        existing_service_password = decrypt_api_key(
                            str(previous["provider_user_password"]),
                            config.api_key_encryption_secret_value,
                        )
                    except ValueError as error:
                        raise HTTPException(
                            status_code=503, detail="API Key 加密配置不可用"
                        ) from error
                    existing_service_email = str(previous["provider_user_email"])
                try:
                    provisioned = await OpenWebUIAdminClient(config).provision_service_key(
                        tenant_id=payload.tenant_id,
                        tenant_name=str(tenant_name),
                        existing_user_email=existing_service_email,
                        existing_user_password=existing_service_password,
                    )
                except (OpenWebUIProvisioningError, httpx.HTTPError) as error:
                    raise OpenWebUIKeyProvisioningError(
                        "Open WebUI 服务账号或 API Key 创建失败"
                    ) from error
                raw_key = provisioned.api_key
                provider = "open_webui"
                provider_user_id = provisioned.user_id
                provider_user_email = provisioned.user_email
                provider_user_password = encrypt_api_key(
                    provisioned.user_password,
                    config.api_key_encryption_secret_value,
                )
            else:
                raw_key, _, _ = generate_api_key()
            key_prefix = f"{raw_key[:12]}…{raw_key[-4:]}"
            key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
            async with connection.transaction():
                if provider == "open_webui":
                    existing = await connection.fetchval(
                        "SELECT id FROM api_keys WHERE tenant_id = $1 AND deleted_at IS NULL",
                        payload.tenant_id,
                    )
                    if existing is not None:
                        raise HTTPException(
                            status_code=409, detail="该医院已经存在模型网关 Key，请先删除或轮换"
                        )
                row = await connection.fetchrow(
                    """
                    INSERT INTO api_keys(
                      tenant_id, name, key_prefix, key_hash, encrypted_key,
                      token_limit, expires_at, created_by, provider,
                      provider_user_id, provider_user_email, provider_user_password
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    RETURNING id::text, tenant_id::text, name, key_prefix, token_limit,
                              token_used, token_reserved, expires_at, created_at, configured_at
                    """,
                    payload.tenant_id,
                    payload.name,
                    key_prefix,
                    key_hash,
                    encrypt_api_key(raw_key, config.api_key_encryption_secret_value),
                    payload.token_limit,
                    payload.expires_at,
                    int(context["user"]["id"]),
                    provider,
                    provider_user_id,
                    provider_user_email,
                    provider_user_password,
                )
                if row is None:
                    raise HTTPException(status_code=500, detail="API Key 创建失败")
                await write_audit_event(
                    connection,
                    tenant_id=payload.tenant_id,
                    actor_id=int(context["user"]["id"]),
                    action="api_key.create",
                    target_type="api_key",
                    target_id=row["id"],
                    summary={"name": payload.name, "token_limit": payload.token_limit},
                )
            return {
                **dict(row),
                "tenant_name": tenant_name,
                "provider": provider,
                "token_remaining": payload.token_limit,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "last_used_at": None,
                "revoked_at": None,
                "status": "active",
                "raw_key": raw_key,
            }
        finally:
            await connection.close()

    @app.get("/api/v1/api-keys/{api_key_id}/key")
    async def reveal_api_key(api_key_id: int, request: Request) -> dict[str, Any]:
        """仅平台管理员通过显式接口复制完整 Key，并记录一次读取审计。"""
        context = await _authenticated_user(config, request)
        _require_platform_admin(context)
        connection = await _database(config)
        try:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    SELECT id::text, tenant_id, name, encrypted_key
                    FROM api_keys WHERE id = $1 AND deleted_at IS NULL
                    FOR SHARE
                    """,
                    api_key_id,
                )
                if row is None:
                    raise HTTPException(status_code=404, detail="API Key 不存在")
                if not row["encrypted_key"]:
                    raise HTTPException(
                        status_code=409,
                        detail="该 Key 创建于复制功能上线前，请重新发放 API Key",
                    )
                try:
                    raw_key = decrypt_api_key(
                        str(row["encrypted_key"]), config.api_key_encryption_secret_value
                    )
                except ValueError as error:
                    raise HTTPException(status_code=503, detail="API Key 加密配置不可用") from error
                await write_audit_event(
                    connection,
                    tenant_id=int(row["tenant_id"]),
                    actor_id=int(context["user"]["id"]),
                    action="api_key.reveal",
                    target_type="api_key",
                    target_id=row["id"],
                    summary={"name": row["name"]},
                )
            return {"id": row["id"], "name": row["name"], "raw_key": raw_key}
        finally:
            await connection.close()

    @app.patch("/api/v1/api-keys/{api_key_id}/status")
    async def update_api_key_status(
        api_key_id: int,
        payload: ApiKeyStatusPatch,
        request: Request,
    ) -> dict[str, Any]:
        """管理员快速启用或停用 Key；停用不会清除历史用量。"""
        context = await _authenticated_user(config, request)
        _require_platform_admin(context)
        connection = await _database(config)
        try:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    UPDATE api_keys
                    SET status = $2::varchar,
                        revoked_at = CASE WHEN $2::varchar = 'active' THEN NULL ELSE revoked_at END
                    WHERE id = $1 AND deleted_at IS NULL AND status IN ('active', 'disabled')
                    RETURNING id::text, tenant_id::text, name, status, revoked_at
                    """,
                    api_key_id,
                    payload.status,
                )
                if row is None:
                    raise HTTPException(
                        status_code=409,
                        detail="只有启用或停用状态的 API Key 可以切换",
                    )
                await write_audit_event(
                    connection,
                    tenant_id=int(row["tenant_id"]),
                    actor_id=int(context["user"]["id"]),
                    action="api_key.status.update",
                    target_type="api_key",
                    target_id=row["id"],
                    summary={"name": row["name"], "status": payload.status},
                )
            return dict(row)
        finally:
            await connection.close()

    @app.patch("/api/v1/api-keys/{api_key_id}/quota")
    async def update_api_key_quota(
        api_key_id: int,
        payload: ApiKeyQuotaPatch,
        request: Request,
    ) -> dict[str, Any]:
        """平台管理员按 Token 数量调整 Key 总额度，并保留用量流水和审计记录。

        先锁定额度行读取最新的已用量和并发预留量；减少总额度时不能低于二者之和，
        这样进行中的请求不会因管理操作而形成负余额或突破现有预留。服务端基于锁定后的
        当前总额度应用增减值，避免两个管理员同时操作时后提交者覆盖前一个人的调整。
        """
        context = await _authenticated_user(config, request)
        _require_platform_admin(context)
        connection = await _database(config)
        try:
            async with connection.transaction():
                current = await connection.fetchrow(
                    """
                    SELECT id::text, tenant_id::text, name, token_limit, token_used,
                           token_reserved
                    FROM api_keys
                    WHERE id = $1 AND deleted_at IS NULL
                    FOR UPDATE
                    """,
                    api_key_id,
                )
                if current is None:
                    raise HTTPException(status_code=404, detail="API Key 不存在或已删除")
                minimum_limit = int(current["token_used"]) + int(current["token_reserved"])
                current_limit = int(current["token_limit"])
                next_limit = current_limit + (
                    payload.amount if payload.direction == "add" else -payload.amount
                )
                if next_limit <= 0:
                    raise HTTPException(status_code=409, detail="API Key 总额度必须大于 0")
                if next_limit > 10_000_000_000:
                    raise HTTPException(
                        status_code=409,
                        detail="调整后的总额度不能超过 10,000,000,000 Token",
                    )
                if next_limit < minimum_limit:
                    raise HTTPException(
                        status_code=409,
                        detail="新总额度不能低于已用 Token 与预留 Token 之和",
                    )
                row = await connection.fetchrow(
                    """
                    UPDATE api_keys
                    SET token_limit = $2
                    WHERE id = $1 AND deleted_at IS NULL
                    RETURNING id::text, tenant_id::text, name, token_limit, token_used,
                              token_reserved,
                              GREATEST(0, token_limit - token_used - token_reserved)
                                AS token_remaining
                    """,
                    api_key_id,
                    next_limit,
                )
                if row is None:
                    raise HTTPException(status_code=404, detail="API Key 不存在或已删除")
                await write_audit_event(
                    connection,
                    tenant_id=int(row["tenant_id"]),
                    actor_id=int(context["user"]["id"]),
                    action="api_key.quota.update",
                    target_type="api_key",
                    target_id=row["id"],
                    summary={
                        "name": row["name"],
                        "previous_token_limit": current_limit,
                        "direction": payload.direction,
                        "amount": payload.amount,
                        "token_limit": next_limit,
                    },
                )
            return dict(row)
        finally:
            await connection.close()

    @app.delete("/api/v1/api-keys/{api_key_id}")
    async def delete_api_key(api_key_id: int, request: Request) -> dict[str, Any]:
        """管理员删除 Key；远端撤销成功后再软删除并保留 Token 历史。"""
        context = await _authenticated_user(config, request)
        _require_platform_admin(context)
        connection = await _database(config)
        try:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    UPDATE api_keys
                    SET deleted_at = now(), status = 'revoked',
                        revoked_at = COALESCE(revoked_at, now())
                    WHERE id = $1 AND deleted_at IS NULL
                    RETURNING id::text, tenant_id::text, name, status, deleted_at,
                              provider, provider_user_email, provider_user_password
                    """,
                    api_key_id,
                )
                if row is None:
                    raise HTTPException(status_code=404, detail="API Key 不存在或已删除")
                if row.get("provider", "local") == "open_webui":
                    email = row.get("provider_user_email")
                    encrypted_password = row.get("provider_user_password")
                    if not isinstance(email, str) or not isinstance(encrypted_password, str):
                        raise HTTPException(status_code=503, detail="Open WebUI 服务账号信息不完整")
                    try:
                        password = decrypt_api_key(
                            encrypted_password,
                            config.api_key_encryption_secret_value,
                        )
                    except ValueError as error:
                        raise HTTPException(
                            status_code=503, detail="API Key 加密配置不可用"
                        ) from error
                    try:
                        await OpenWebUIAdminClient(config).revoke_service_key(
                            user_email=email,
                            user_password=password,
                        )
                    except (OpenWebUIProvisioningError, httpx.HTTPError) as error:
                        raise OpenWebUIKeyProvisioningError(
                            "Open WebUI 原生 API Key 撤销失败，本地 Key 未删除"
                        ) from error
                await write_audit_event(
                    connection,
                    tenant_id=int(row["tenant_id"]),
                    actor_id=int(context["user"]["id"]),
                    action="api_key.delete",
                    target_type="api_key",
                    target_id=row["id"],
                    summary={"name": row["name"]},
                )
            return dict(row)
        finally:
            await connection.close()

    @app.post("/api/v1/api-keys/{api_key_id}/revoke")
    async def revoke_api_key(api_key_id: int, request: Request) -> dict[str, Any]:
        """撤销公司 API Key；撤销后已发放的明文 Key 立即失效。"""
        context = await _authenticated_user(config, request)
        _require_platform_admin(context)
        connection = await _database(config)
        try:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    UPDATE api_keys SET status = 'revoked', revoked_at = now()
                    WHERE id = $1 AND status = 'active'
                    RETURNING id::text, tenant_id::text, name, status, revoked_at
                    """,
                    api_key_id,
                )
                if row is None:
                    raise HTTPException(status_code=404, detail="可撤销的 API Key 不存在")
                await write_audit_event(
                    connection,
                    tenant_id=int(row["tenant_id"]),
                    actor_id=int(context["user"]["id"]),
                    action="api_key.revoke",
                    target_type="api_key",
                    target_id=row["id"],
                    summary={"name": row["name"]},
                )
            return dict(row)
        finally:
            await connection.close()

    @app.get("/api/v1/api-keys/{api_key_id}/usage")
    async def list_api_key_usage(api_key_id: int, request: Request) -> dict[str, Any]:
        """返回某个公司 API Key 的输入、输出、总 Token 用量流水。"""
        context = await _authenticated_user(config, request)
        _require_platform_admin(context)
        connection = await _database(config)
        try:
            summary = await connection.fetchrow(
                """
                SELECT count(usage.id)::int AS request_count,
                       COALESCE(sum(usage.prompt_tokens), 0)::bigint AS prompt_tokens,
                       COALESCE(sum(usage.completion_tokens), 0)::bigint AS completion_tokens,
                       COALESCE(sum(usage.total_tokens), 0)::bigint AS total_tokens
                FROM api_keys key
                LEFT JOIN api_key_usage usage ON usage.api_key_id = key.id
                WHERE key.id = $1
                GROUP BY key.id
                """,
                api_key_id,
            )
            if summary is None:
                raise HTTPException(status_code=404, detail="API Key 不存在")
            rows = await connection.fetch(
                """
                SELECT request_id::text, model_name, prompt_tokens, completion_tokens,
                       total_tokens, usage_source, model_usage, status,
                       created_at, completed_at
                FROM api_key_usage WHERE api_key_id = $1
                ORDER BY created_at DESC LIMIT 200
                """,
                api_key_id,
            )
            daily = await connection.fetch(
                """
                SELECT date_trunc('day', created_at)::date::text AS period,
                       count(*)::int AS request_count,
                       COALESCE(sum(prompt_tokens), 0)::bigint AS prompt_tokens,
                       COALESCE(sum(completion_tokens), 0)::bigint AS completion_tokens,
                       COALESCE(sum(total_tokens), 0)::bigint AS total_tokens
                FROM api_key_usage
                WHERE api_key_id = $1 AND created_at >= now() - interval '30 days'
                GROUP BY 1 ORDER BY 1 DESC
                """,
                api_key_id,
            )
            monthly = await connection.fetch(
                """
                SELECT date_trunc('month', created_at)::date::text AS period,
                       count(*)::int AS request_count,
                       COALESCE(sum(prompt_tokens), 0)::bigint AS prompt_tokens,
                       COALESCE(sum(completion_tokens), 0)::bigint AS completion_tokens,
                       COALESCE(sum(total_tokens), 0)::bigint AS total_tokens
                FROM api_key_usage
                WHERE api_key_id = $1 AND created_at >= now() - interval '12 months'
                GROUP BY 1 ORDER BY 1 DESC
                """,
                api_key_id,
            )
            return {
                "summary": dict(summary),
                "daily": [dict(row) for row in daily],
                "monthly": [dict(row) for row in monthly],
                "recent_limit": API_KEY_USAGE_RECENT_LIMIT,
                "items": [dict(row) for row in rows],
            }
        finally:
            await connection.close()

    @app.get("/api/v1/model-endpoints")
    async def list_model_endpoints(request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        if context["user"]["platform_role"] != "platform_admin":
            raise HTTPException(status_code=403, detail="只有平台管理员可以管理模型端点")
        connection = await _database(config)
        try:
            rows = await connection.fetch(
                """
                SELECT id::text, tenant_id::text, name, provider, endpoint_type, base_url,
                       secret_ref, allowed_models, health_status, status, last_checked_at,
                       last_latency_ms, last_error, observed_dimension, created_at, updated_at
                FROM model_endpoints
                ORDER BY status, endpoint_type, updated_at DESC, id DESC
                """
            )
            items = []
            for row in rows:
                item = dict(row)
                item["allowed_models"] = _json_value(item["allowed_models"], [])
                item["secret_configured"] = bool(item.pop("secret_ref", None))
                items.append(item)
            return {"items": items}
        finally:
            await connection.close()

    @app.get("/api/v1/model-gateway-key")
    async def get_model_gateway_key(request: Request) -> dict[str, Any]:
        """返回模型网关密钥的脱敏状态，供超级管理员确认当前生效来源。"""
        context = await _authenticated_user(config, request)
        _require_platform_admin(context)
        # 页面打开时同步数据库覆盖环境变量，确保重启后的系统状态可见。
        from app.core.runtime_settings import load_persisted_model_gateway_key

        await load_persisted_model_gateway_key(config)
        value = config.model_gateway_api_key.get_secret_value()
        source = "system" if runtime_gateway_key_configured else config.model_gateway_key_source
        return {
            "configured": bool(value),
            "source": source,
            "masked": f"••••••••{value[-4:]}" if len(value) >= 4 else ("••••" if value else ""),
        }

    @app.put("/api/v1/model-gateway-key")
    async def update_model_gateway_key(
        payload: ModelGatewayKeyUpdate,
        request: Request,
    ) -> dict[str, Any]:
        """替换当前 API 进程使用的模型网关密钥，成功后后续请求立即使用新值。"""
        nonlocal runtime_gateway_key_configured
        context = await _authenticated_user(config, request)
        _require_platform_admin(context)
        config.model_gateway_api_key = payload.api_key
        await persist_model_gateway_key(
            config,
            payload.api_key.get_secret_value(),
            int(context["user"]["id"]),
        )
        config.model_gateway_key_refresh_attempted = True
        config.model_gateway_key_source = "system"
        runtime_gateway_key_configured = True
        value = payload.api_key.get_secret_value()
        return {
            "configured": True,
            "source": "system",
            "masked": f"••••••••{value[-4:]}",
        }

    @app.post("/api/v1/model-endpoints", status_code=201)
    async def create_model_endpoint(
        payload: ModelEndpointCreate,
        request: Request,
    ) -> dict[str, Any]:
        """登记平台级模型端点，并记录不包含密钥引用值的配置审计。"""
        context = await _authenticated_user(config, request)
        if context["user"]["platform_role"] != "platform_admin":
            raise HTTPException(status_code=403, detail="只有平台管理员可以登记模型端点")
        unknown_models = set(payload.allowed_models) - config.allowed_model_names
        if unknown_models:
            raise HTTPException(
                status_code=422,
                detail=f"模型不在网关白名单中：{'、'.join(sorted(unknown_models))}",
            )
        connection = await _database(config)
        try:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    INSERT INTO model_endpoints(
                      tenant_id, name, provider, endpoint_type, base_url,
                      secret_ref, allowed_models, status
                    ) VALUES (NULL, $1, $2, $3, $4, $5, $6::jsonb, 'active')
                    RETURNING id::text, tenant_id::text, name, provider, endpoint_type,
                              base_url, allowed_models, health_status, status,
                              last_checked_at, last_latency_ms, last_error,
                              observed_dimension, created_at, updated_at
                    """,
                    payload.name,
                    payload.provider,
                    payload.endpoint_type,
                    payload.base_url,
                    payload.secret_ref,
                    json.dumps(payload.allowed_models, ensure_ascii=False),
                )
                await connection.execute(
                    """
                    INSERT INTO audit_logs(
                      actor_id, action, target_type, target_id, change_summary
                    ) VALUES ($1, 'model_endpoint.create', 'model_endpoint', $2, $3::jsonb)
                    """,
                    int(context["user"]["id"]),
                    row["id"],
                    json.dumps(
                        {
                            "name": payload.name,
                            "endpoint_type": payload.endpoint_type,
                            "allowed_models": payload.allowed_models,
                        },
                        ensure_ascii=False,
                    ),
                )
            result = dict(row)
            result["allowed_models"] = _json_value(result["allowed_models"], [])
            result["secret_configured"] = True
            return result
        except asyncpg.UniqueViolationError as error:
            raise HTTPException(status_code=409, detail="相同用途和地址的端点已经存在") from error
        finally:
            await connection.close()

    @app.patch("/api/v1/model-endpoints/{endpoint_id}")
    async def update_model_endpoint(
        endpoint_id: int,
        payload: ModelEndpointPatch,
        request: Request,
    ) -> dict[str, Any]:
        """更新模型端点安全字段，并在同一事务记录脱敏的配置前后状态。"""
        context = await _authenticated_user(config, request)
        if context["user"]["platform_role"] != "platform_admin":
            raise HTTPException(status_code=403, detail="只有平台管理员可以编辑模型端点")
        values = payload.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=400, detail="没有需要修改的字段")
        models = values.get("allowed_models")
        if models is not None:
            unknown_models = set(models) - config.allowed_model_names
            if unknown_models:
                raise HTTPException(
                    status_code=422,
                    detail=f"模型不在网关白名单中：{'、'.join(sorted(unknown_models))}",
                )
            values["allowed_models"] = json.dumps(models, ensure_ascii=False)
        assignments: list[str] = []
        parameters: list[Any] = [endpoint_id]
        for index, (key, value) in enumerate(values.items(), 2):
            cast_suffix = "::jsonb" if key == "allowed_models" else ""
            assignments.append(f"{key} = ${index}{cast_suffix}")
            parameters.append(value)
        connection = await _database(config)
        try:
            async with connection.transaction():
                # 锁定端点确保审计 before 与本次更新属于同一并发版本；密钥引用值不进入摘要。
                before = await connection.fetchrow(
                    """
                    SELECT id, name, base_url, allowed_models, status, secret_ref
                    FROM model_endpoints WHERE id = $1 FOR UPDATE
                    """,
                    endpoint_id,
                )
                if before is None:
                    raise HTTPException(status_code=404, detail="模型端点不存在")
                row = await connection.fetchrow(
                    f"""
                    UPDATE model_endpoints
                    SET {", ".join(assignments)}, health_status = 'unknown',
                        last_error = NULL, updated_at = now()
                    WHERE id = $1
                    RETURNING id::text, tenant_id::text, name, provider, endpoint_type,
                              base_url, allowed_models, health_status, status,
                              last_checked_at, last_latency_ms, last_error,
                              observed_dimension, created_at, updated_at
                    """,
                    *parameters,
                )
                if row is None:
                    raise HTTPException(status_code=404, detail="模型端点不存在")
                safe_fields = {"name", "base_url", "allowed_models", "status"}
                before_state = {
                    field: (
                        _json_value(before[field], [])
                        if field == "allowed_models"
                        else before[field]
                    )
                    for field in sorted(values)
                    if field in safe_fields
                }
                after_state = {
                    field: (
                        _json_value(row[field], []) if field == "allowed_models" else row[field]
                    )
                    for field in sorted(values)
                    if field in safe_fields
                }
                await connection.execute(
                    """
                    INSERT INTO audit_logs(
                      actor_id, action, target_type, target_id, change_summary
                    ) VALUES ($1, 'model_endpoint.update', 'model_endpoint', $2, $3::jsonb)
                    """,
                    int(context["user"]["id"]),
                    str(endpoint_id),
                    json.dumps(
                        {
                            "fields": sorted(values),
                            "before": before_state,
                            "after": after_state,
                            "secret_ref_changed": "secret_ref" in values,
                        },
                        ensure_ascii=False,
                    ),
                )
            result = dict(row)
            result["allowed_models"] = _json_value(result["allowed_models"], [])
            result["secret_configured"] = True
            return result
        except asyncpg.UniqueViolationError as error:
            raise HTTPException(status_code=409, detail="相同用途和地址的端点已经存在") from error
        finally:
            await connection.close()

    @app.post("/api/v1/model-endpoints/{endpoint_id}/health-check")
    async def check_model_endpoint(
        endpoint_id: int,
        payload: ModelHealthCheckRequest,
        request: Request,
    ) -> dict[str, Any]:
        """真实探测模型端点并保存健康状态；失败只返回统一错误，不泄露网关响应。"""
        context = await _authenticated_user(config, request)
        if context["user"]["platform_role"] != "platform_admin":
            raise HTTPException(status_code=403, detail="只有平台管理员可以检查模型端点")
        connection = await _database(config)
        try:
            endpoint = await connection.fetchrow(
                """
                SELECT id, endpoint_type, base_url, secret_ref, allowed_models, status
                FROM model_endpoints WHERE id = $1
                """,
                endpoint_id,
            )
            if endpoint is None:
                raise HTTPException(status_code=404, detail="模型端点不存在")
            if endpoint["status"] != "active":
                raise HTTPException(status_code=409, detail="已停用端点不能执行健康检查")
            allowed_models = _json_value(endpoint["allowed_models"], [])
            if payload.model_name not in allowed_models:
                raise HTTPException(status_code=422, detail="所选模型不在端点白名单中")
            if endpoint["secret_ref"] not in {
                MODEL_GATEWAY_SECRET_REF,
                LEGACY_MODEL_GATEWAY_SECRET_REF,
            }:
                raise HTTPException(status_code=409, detail="端点密钥引用当前不可用")
            client = ModelGatewayClient(config)
            # 诊断审计只保留耗时、状态和稳定错误码；探测响应与密钥永远不进入日志。
            check_started = time.perf_counter()
            try:
                if endpoint["endpoint_type"] == "generation":
                    probe = await client.probe_generation(endpoint["base_url"], payload.model_name)
                elif endpoint["endpoint_type"] == "embedding":
                    probe = await client.probe_embedding(endpoint["base_url"], payload.model_name)
                else:
                    await connection.execute(
                        """
                        INSERT INTO audit_logs(
                          tenant_id, actor_id, action, target_type, target_id, change_summary
                        ) VALUES (
                          NULL, $1, 'model_endpoint.health_check',
                          'model_endpoint', $2, $3::jsonb
                        )
                        """,
                        int(context["user"]["id"]),
                        str(endpoint_id),
                        json.dumps(
                            {
                                "model": payload.model_name,
                                "status": "unsupported",
                                "error_code": "UNSUPPORTED_ENDPOINT_TYPE",
                                "latency_ms": round(
                                    (time.perf_counter() - check_started) * 1000,
                                    2,
                                ),
                            },
                            ensure_ascii=False,
                        ),
                    )
                    raise HTTPException(status_code=422, detail="重排端点检查将在后续版本提供")
            except (httpx.HTTPError, ValueError) as error:
                error_code = type(error).__name__
                latency_ms = round((time.perf_counter() - check_started) * 1000, 2)
                # 健康状态和对应审计必须原子提交，避免页面状态变化却没有操作证据。
                async with connection.transaction():
                    await connection.execute(
                        """
                        UPDATE model_endpoints
                        SET health_status = 'unhealthy', last_checked_at = now(),
                            last_error = $2, last_latency_ms = NULL,
                            observed_dimension = NULL, updated_at = now()
                        WHERE id = $1
                        """,
                        endpoint_id,
                        error_code,
                    )
                    await connection.execute(
                        """
                        INSERT INTO audit_logs(
                          tenant_id, actor_id, action, target_type, target_id, change_summary
                        ) VALUES (
                          NULL, $1, 'model_endpoint.health_check',
                          'model_endpoint', $2, $3::jsonb
                        )
                        """,
                        int(context["user"]["id"]),
                        str(endpoint_id),
                        json.dumps(
                            {
                                "model": payload.model_name,
                                "status": "unhealthy",
                                "error_code": error_code,
                                "latency_ms": latency_ms,
                            },
                            ensure_ascii=False,
                        ),
                    )
                return {
                    "status": "unhealthy",
                    "model": payload.model_name,
                    "error": "模型调用失败，请检查地址、密钥和模型服务状态",
                }
            observed_dimension = probe.get("dimension")
            # 成功状态与审计使用同一事务，且平台事件显式保持 tenant_id 为空。
            async with connection.transaction():
                await connection.execute(
                    """
                    UPDATE model_endpoints
                    SET health_status = 'healthy', last_checked_at = now(),
                        last_latency_ms = $2, last_error = NULL,
                        observed_dimension = $3, updated_at = now()
                    WHERE id = $1
                    """,
                    endpoint_id,
                    probe["latency_ms"],
                    observed_dimension,
                )
                await connection.execute(
                    """
                    INSERT INTO audit_logs(
                      tenant_id, actor_id, action, target_type, target_id, change_summary
                    ) VALUES (
                      NULL, $1, 'model_endpoint.health_check',
                      'model_endpoint', $2, $3::jsonb
                    )
                    """,
                    int(context["user"]["id"]),
                    str(endpoint_id),
                    json.dumps(
                        {
                            "model": payload.model_name,
                            "status": "healthy",
                            "latency_ms": probe["latency_ms"],
                            "dimension": observed_dimension,
                        },
                        ensure_ascii=False,
                    ),
                )
            return {"status": "healthy", **probe}
        finally:
            await connection.close()

    @app.get("/api/v1/profiles")
    async def list_profiles(knowledge_base_id: int, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        _require_platform_admin(context)
        connection = await _database(config)
        try:
            access = await _require_knowledge_base_role(
                connection,
                context,
                knowledge_base_id,
                {"space_admin", "kb_admin"},
            )
            ingestion_rows = await connection.fetch(
                """
                SELECT id::text, definition, definition_hash, created_by::text, created_at
                FROM ingestion_profiles
                WHERE tenant_id = $1 AND knowledge_base_id = $2
                ORDER BY created_at DESC, id DESC
                """,
                access["tenant_id"],
                knowledge_base_id,
            )
            embedding_rows = await connection.fetch(
                """
                SELECT ep.id::text, ep.model_endpoint_id::text, ep.model_name,
                       ep.model_revision, ep.dimension, ep.dtype, ep.instructions,
                       ep.normalization, ep.definition_hash, ep.created_at,
                       me.name AS endpoint_name, me.status AS endpoint_status
                FROM embedding_profiles ep
                JOIN model_endpoints me ON me.id = ep.model_endpoint_id
                WHERE me.tenant_id IS NULL OR me.tenant_id = $1
                ORDER BY ep.created_at DESC, ep.id DESC
                """,
                access["tenant_id"],
            )
            runtime_rows = await connection.fetch(
                """
                SELECT rp.id::text, rp.embedding_profile_id::text, rp.definition,
                       rp.definition_hash, rp.created_by::text, rp.created_at,
                       (kb.active_runtime_id = rp.id) AS active
                FROM runtime_profiles rp
                JOIN knowledge_bases kb ON kb.id = rp.knowledge_base_id
                  AND kb.tenant_id = rp.tenant_id
                WHERE rp.tenant_id = $1 AND rp.knowledge_base_id = $2
                ORDER BY rp.created_at DESC, rp.id DESC
                """,
                access["tenant_id"],
                knowledge_base_id,
            )
            ingestion = []
            for row in ingestion_rows:
                item = dict(row)
                item["definition"] = _json_value(item["definition"], {})
                item["effect_scope"] = "reparse_required"
                ingestion.append(item)
            embedding = []
            for row in embedding_rows:
                item = dict(row)
                item["instructions"] = _json_value(item["instructions"], {})
                item["effect_scope"] = "rebuild_required"
                embedding.append(item)
            runtime = []
            for row in runtime_rows:
                item = dict(row)
                item["definition"] = _json_value(item["definition"], {})
                item["effect_scope"] = "immediate" if item["active"] else "activate_required"
                runtime.append(item)
            return {
                "knowledge_base_id": str(knowledge_base_id),
                "ingestion_profiles": ingestion,
                "embedding_profiles": embedding,
                "runtime_profiles": runtime,
            }
        finally:
            await connection.close()

    @app.post("/api/v1/ingestion-profiles", status_code=201)
    async def create_ingestion_profile(
        payload: IngestionProfileCreate,
        request: Request,
    ) -> dict[str, Any]:
        """创建知识库不可变解析 Profile；重复定义复用且不重复写审计。"""
        context = await _authenticated_user(config, request)
        _require_platform_admin(context)
        connection = await _database(config)
        try:
            access = await _require_knowledge_base_role(
                connection,
                context,
                payload.knowledge_base_id,
                {"space_admin", "kb_admin"},
            )
            definition = {
                "parser": "markdown-it/docx/pdfplumber:v1",
                "chunking": {
                    "strategy": "source-block",
                    "max_chars": payload.max_chars,
                    "overlap_chars": payload.overlap_chars,
                },
                "preserve_locator": payload.preserve_locator,
            }
            definition_hash = profile_hash(definition)
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    INSERT INTO ingestion_profiles(
                      tenant_id, knowledge_base_id, definition, definition_hash, created_by
                    ) VALUES ($1, $2, $3::jsonb, $4, $5)
                    ON CONFLICT (knowledge_base_id, definition_hash) DO NOTHING
                    RETURNING id::text, definition, definition_hash, created_at
                    """,
                    access["tenant_id"],
                    payload.knowledge_base_id,
                    json.dumps(definition, ensure_ascii=False),
                    definition_hash,
                    int(context["user"]["id"]),
                )
                reused = row is None
                if row is None:
                    row = await connection.fetchrow(
                        """
                        SELECT id::text, definition, definition_hash, created_at
                        FROM ingestion_profiles
                        WHERE knowledge_base_id = $1 AND definition_hash = $2
                        """,
                        payload.knowledge_base_id,
                        definition_hash,
                    )
                if not reused:
                    await connection.execute(
                        """
                        INSERT INTO audit_logs(
                          tenant_id, actor_id, action, target_type, target_id, change_summary
                        ) VALUES ($1, $2, 'ingestion_profile.create',
                                  'ingestion_profile', $3, $4::jsonb)
                        """,
                        access["tenant_id"],
                        int(context["user"]["id"]),
                        row["id"],
                        json.dumps(
                            {
                                "knowledge_base_id": str(payload.knowledge_base_id),
                                "definition_hash": definition_hash,
                                "effect_scope": "reparse_required",
                            },
                            ensure_ascii=False,
                        ),
                    )
            result = dict(row)
            result["definition"] = _json_value(result["definition"], {})
            return {**result, "reused": reused, "effect_scope": "reparse_required"}
        finally:
            await connection.close()

    @app.post("/api/v1/embedding-profiles", status_code=201)
    async def create_embedding_profile(
        payload: EmbeddingProfileCreate,
        request: Request,
    ) -> dict[str, Any]:
        """实测嵌入模型后创建平台级不可变 Profile，并记录重建索引影响。"""
        context = await _authenticated_user(config, request)
        if context["user"]["platform_role"] != "platform_admin":
            raise HTTPException(status_code=403, detail="只有平台管理员可以创建嵌入 Profile")
        connection = await _database(config)
        try:
            endpoint = await connection.fetchrow(
                """
                SELECT id, name, endpoint_type, base_url, secret_ref, allowed_models,
                       status, health_status
                FROM model_endpoints WHERE id = $1
                """,
                payload.model_endpoint_id,
            )
            if endpoint is None or endpoint["endpoint_type"] != "embedding":
                raise HTTPException(status_code=404, detail="嵌入模型端点不存在")
            if endpoint["status"] != "active":
                raise HTTPException(status_code=409, detail="嵌入模型端点已停用")
            if payload.model_name not in _json_value(endpoint["allowed_models"], []):
                raise HTTPException(status_code=422, detail="模型不在端点白名单中")
            client = ModelGatewayClient(config)
            try:
                probe = await client.probe_embedding(endpoint["base_url"], payload.model_name)
                revision = await client.model_revision(payload.model_name, endpoint["base_url"])
            except (httpx.HTTPError, ValueError) as error:
                raise HTTPException(status_code=503, detail="嵌入模型实测失败") from error
            dimension = int(probe["dimension"])
            if payload.expected_dimension is not None and payload.expected_dimension != dimension:
                raise HTTPException(
                    status_code=409,
                    detail=f"实测维度为 {dimension}，与期望维度不一致",
                )
            definition = {
                "provider": "open_webui",
                "base_url": str(endpoint["base_url"]).rstrip("/"),
                "secret_ref": MODEL_GATEWAY_SECRET_REF,
                "model": payload.model_name,
                "model_revision": revision,
                "dimension": dimension,
                "dtype": "float32",
                "normalization": payload.normalization,
                "instructions": {
                    "query": payload.query_instruction,
                    "document": payload.document_instruction,
                },
            }
            definition_hash = profile_hash(definition)
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    INSERT INTO embedding_profiles(
                      model_endpoint_id, model_name, model_revision, dimension, dtype,
                      instructions, normalization, definition_hash
                    ) VALUES ($1, $2, $3, $4, 'float32', $5::jsonb, $6, $7)
                    ON CONFLICT (definition_hash) DO NOTHING
                    RETURNING id::text, model_endpoint_id::text, model_name, model_revision,
                              dimension, dtype, instructions, normalization,
                              definition_hash, created_at
                    """,
                    payload.model_endpoint_id,
                    payload.model_name,
                    revision,
                    dimension,
                    json.dumps(definition["instructions"], ensure_ascii=False),
                    payload.normalization,
                    definition_hash,
                )
                reused = row is None
                if row is None:
                    row = await connection.fetchrow(
                        """
                        SELECT id::text, model_endpoint_id::text, model_name, model_revision,
                               dimension, dtype, instructions, normalization,
                               definition_hash, created_at
                        FROM embedding_profiles WHERE definition_hash = $1
                        """,
                        definition_hash,
                    )
                if not reused:
                    await connection.execute(
                        """
                        INSERT INTO audit_logs(
                          actor_id, action, target_type, target_id, change_summary
                        ) VALUES ($1, 'embedding_profile.create',
                                  'embedding_profile', $2, $3::jsonb)
                        """,
                        int(context["user"]["id"]),
                        row["id"],
                        json.dumps(
                            {
                                "model_endpoint_id": str(payload.model_endpoint_id),
                                "model": payload.model_name,
                                "model_revision": revision,
                                "dimension": dimension,
                                "definition_hash": definition_hash,
                                "effect_scope": "rebuild_required",
                            },
                            ensure_ascii=False,
                        ),
                    )
            result = dict(row)
            result["instructions"] = _json_value(result["instructions"], {})
            return {**result, "reused": reused, "effect_scope": "rebuild_required"}
        finally:
            await connection.close()

    @app.post("/api/v1/runtime-profiles", status_code=201)
    async def create_runtime_profile(
        payload: RuntimeProfileCreate,
        request: Request,
    ) -> dict[str, Any]:
        """创建知识库不可变运行 Profile，审计只记录引用和哈希而不保存回答规则正文。"""
        context = await _authenticated_user(config, request)
        _require_platform_admin(context)
        connection = await _database(config)
        try:
            access = await _require_knowledge_base_role(
                connection,
                context,
                payload.knowledge_base_id,
                {"space_admin", "kb_admin"},
            )
            embedding = await connection.fetchrow(
                """
                SELECT ep.id, ep.model_name, ep.dimension, me.status AS endpoint_status
                FROM embedding_profiles ep
                JOIN model_endpoints me ON me.id = ep.model_endpoint_id
                WHERE ep.id = $1 AND (me.tenant_id IS NULL OR me.tenant_id = $2)
                """,
                payload.embedding_profile_id,
                access["tenant_id"],
            )
            generation = await connection.fetchrow(
                """
                SELECT id, name, allowed_models, status
                FROM model_endpoints
                WHERE id = $1 AND endpoint_type = 'generation'
                  AND (tenant_id IS NULL OR tenant_id = $2)
                """,
                payload.generation_endpoint_id,
                access["tenant_id"],
            )
            if embedding is None or embedding["endpoint_status"] != "active":
                raise HTTPException(status_code=409, detail="嵌入 Profile 或端点不可用")
            if generation is None or generation["status"] != "active":
                raise HTTPException(status_code=409, detail="生成模型端点不可用")
            if payload.generation_model not in _json_value(generation["allowed_models"], []):
                raise HTTPException(status_code=422, detail="生成模型不在端点白名单中")
            definition = {
                "retrieval": {
                    "mode": "vector",
                    "top_k": payload.top_k,
                    "context_max_chars": payload.context_max_chars,
                },
                "generation": {
                    "endpoint_id": payload.generation_endpoint_id,
                    "model": payload.generation_model,
                    "temperature": payload.temperature,
                },
                "answer_rules": payload.answer_rules,
            }
            definition_hash = profile_hash(
                {**definition, "embedding_profile_id": payload.embedding_profile_id}
            )
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    INSERT INTO runtime_profiles(
                      tenant_id, knowledge_base_id, embedding_profile_id,
                      definition, definition_hash, created_by
                    ) VALUES ($1, $2, $3, $4::jsonb, $5, $6)
                    ON CONFLICT (knowledge_base_id, definition_hash) DO NOTHING
                    RETURNING id::text, embedding_profile_id::text, definition,
                              definition_hash, created_at
                    """,
                    access["tenant_id"],
                    payload.knowledge_base_id,
                    payload.embedding_profile_id,
                    json.dumps(definition, ensure_ascii=False),
                    definition_hash,
                    int(context["user"]["id"]),
                )
                reused = row is None
                if row is None:
                    row = await connection.fetchrow(
                        """
                        SELECT id::text, embedding_profile_id::text, definition,
                               definition_hash, created_at
                        FROM runtime_profiles
                        WHERE knowledge_base_id = $1 AND definition_hash = $2
                        """,
                        payload.knowledge_base_id,
                        definition_hash,
                    )
                if not reused:
                    await connection.execute(
                        """
                        INSERT INTO audit_logs(
                          tenant_id, actor_id, action, target_type, target_id, change_summary
                        ) VALUES ($1, $2, 'runtime_profile.create',
                                  'runtime_profile', $3, $4::jsonb)
                        """,
                        access["tenant_id"],
                        int(context["user"]["id"]),
                        row["id"],
                        json.dumps(
                            {
                                "knowledge_base_id": str(payload.knowledge_base_id),
                                "embedding_profile_id": str(payload.embedding_profile_id),
                                "generation_endpoint_id": str(payload.generation_endpoint_id),
                                "generation_model": payload.generation_model,
                                "definition_hash": definition_hash,
                                "effect_scope": "activate_required",
                            },
                            ensure_ascii=False,
                        ),
                    )
            result = dict(row)
            result["definition"] = _json_value(result["definition"], {})
            return {**result, "reused": reused, "effect_scope": "activate_required"}
        finally:
            await connection.close()

    @app.post("/api/v1/runtime-profiles/{profile_id}/activate")
    async def activate_runtime_profile(profile_id: int, request: Request) -> dict[str, Any]:
        """激活知识库 Runtime Profile，并记录旧值、新值及是否需要重新构建。"""
        context = await _authenticated_user(config, request)
        _require_platform_admin(context)
        connection = await _database(config)
        try:
            target = await connection.fetchrow(
                """
                SELECT rp.id, rp.tenant_id, rp.knowledge_base_id,
                       rp.embedding_profile_id, rp.definition_hash,
                       kb.active_runtime_id AS previous_runtime_profile_id,
                       kb.active_release_id, kr.embedding_profile_id AS release_embedding_profile_id
                FROM runtime_profiles rp
                JOIN knowledge_bases kb ON kb.id = rp.knowledge_base_id
                  AND kb.tenant_id = rp.tenant_id
                LEFT JOIN kb_releases kr ON kr.id = kb.active_release_id
                  AND kr.tenant_id = kb.tenant_id
                WHERE rp.id = $1
                """,
                profile_id,
            )
            if target is None:
                raise HTTPException(status_code=404, detail="Runtime Profile 不存在")
            access = await _require_knowledge_base_role(
                connection,
                context,
                int(target["knowledge_base_id"]),
                {"space_admin", "kb_admin"},
            )
            if int(access["tenant_id"]) != int(target["tenant_id"]):
                raise HTTPException(status_code=404, detail="Runtime Profile 不存在")
            effect_scope = (
                "immediate"
                if target["active_release_id"] is None
                or target["release_embedding_profile_id"] == target["embedding_profile_id"]
                else "rebuild_required"
            )
            async with connection.transaction():
                await connection.execute(
                    """
                    UPDATE knowledge_bases SET active_runtime_id = $3, updated_at = now()
                    WHERE id = $1 AND tenant_id = $2
                    """,
                    target["knowledge_base_id"],
                    target["tenant_id"],
                    profile_id,
                )
                await connection.execute(
                    """
                    INSERT INTO audit_logs(
                      tenant_id, actor_id, action, target_type, target_id, change_summary
                    ) VALUES ($1, $2, 'runtime_profile.activate',
                              'knowledge_base', $3, $4::jsonb)
                    """,
                    target["tenant_id"],
                    int(context["user"]["id"]),
                    str(target["knowledge_base_id"]),
                    json.dumps(
                        {
                            "before": {
                                "runtime_profile_id": (
                                    str(target["previous_runtime_profile_id"])
                                    if target["previous_runtime_profile_id"] is not None
                                    else None
                                )
                            },
                            "after": {"runtime_profile_id": str(profile_id)},
                            "effect_scope": effect_scope,
                        },
                        ensure_ascii=False,
                    ),
                )
            return {
                "id": str(profile_id),
                "knowledge_base_id": str(target["knowledge_base_id"]),
                "active": True,
                "effect_scope": effect_scope,
            }
        finally:
            await connection.close()

    @app.get("/api/v1/admin/menus")
    async def admin_menus(request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        if context["user"]["platform_role"] != "platform_admin":
            raise HTTPException(status_code=403, detail="只有平台管理员可以管理菜单")
        connection = await _database(config)
        try:
            rows = await connection.fetch(
                """
                SELECT id::text, code, name, kind, parent_id::text, route, icon,
                       permission_code, sort_order, visible, status
                FROM menus ORDER BY sort_order, id
                """
            )
            return {"items": _rows(rows)}
        finally:
            await connection.close()

    @app.post("/api/v1/admin/menus", status_code=201)
    async def create_menu(payload: MenuCreate, request: Request) -> dict[str, Any]:
        """创建菜单并校验父级存在，避免形成悬挂层级。"""
        context = await _authenticated_user(config, request)
        if context["user"]["platform_role"] != "platform_admin":
            raise HTTPException(status_code=403, detail="只有平台管理员可以管理菜单")
        connection = await _database(config)
        try:
            if payload.parent_id is not None:
                parent_exists = await connection.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM menus WHERE id = $1)", payload.parent_id
                )
                if not parent_exists:
                    raise HTTPException(status_code=400, detail="父级菜单不存在")
            row = await connection.fetchrow(
                """
                INSERT INTO menus(code, name, kind, parent_id, route, icon, permission_code,
                                  sort_order, visible, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'active')
                RETURNING id::text, code, name, kind, parent_id::text, route, icon,
                          permission_code, sort_order, visible, status
                """,
                payload.code,
                payload.name,
                payload.kind,
                payload.parent_id,
                payload.route,
                payload.icon,
                payload.permission_code,
                payload.sort_order,
                payload.visible,
            )
            if row is None:
                raise HTTPException(status_code=500, detail="菜单创建失败")
            return dict(row)
        except asyncpg.UniqueViolationError as error:
            raise HTTPException(status_code=409, detail="菜单编码或权限标识已存在") from error
        finally:
            await connection.close()

    @app.patch("/api/v1/admin/menus/{menu_id}")
    async def update_menu(menu_id: int, payload: MenuPatch, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        if context["user"]["platform_role"] != "platform_admin":
            raise HTTPException(status_code=403, detail="只有平台管理员可以管理菜单")
        values = payload.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=400, detail="没有需要修改的字段")
        connection = await _database(config)
        try:
            if payload.parent_id == menu_id:
                raise HTTPException(status_code=400, detail="菜单不能挂载到自身")
            if payload.parent_id is not None:
                parent_exists = await connection.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM menus WHERE id = $1)", payload.parent_id
                )
                if not parent_exists:
                    raise HTTPException(status_code=400, detail="父级菜单不存在")
            assignments = []
            parameters: list[Any] = [menu_id]
            for index, (key, value) in enumerate(values.items(), 2):
                assignments.append(f"{key} = ${index}")
                parameters.append(value)
            row = await connection.fetchrow(
                f"""
                UPDATE menus SET {", ".join(assignments)}, updated_at = now() WHERE id = $1
                RETURNING id::text, code, name, kind, parent_id::text, route, icon,
                          permission_code, sort_order, visible, status
                """,
                *parameters,
            )
            if row is None:
                raise HTTPException(status_code=404, detail="菜单不存在")
            return dict(row)
        finally:
            await connection.close()

    @app.get("/api/v1/admin/roles")
    async def admin_roles(request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        if context["user"]["platform_role"] != "platform_admin":
            raise HTTPException(status_code=403, detail="只有平台管理员可以查看系统角色")
        connection = await _database(config)
        try:
            rows = await connection.fetch(
                """
                SELECT r.id::text, r.code, r.name, r.scope, r.description, r.is_system,
                       COALESCE(array_agg(rm.menu_id ORDER BY rm.menu_id)
                         FILTER (WHERE rm.menu_id IS NOT NULL), '{}') AS menu_ids
                FROM roles r LEFT JOIN role_menus rm ON rm.role_id = r.id
                GROUP BY r.id ORDER BY r.scope, r.id
                """
            )
            return {"items": _rows(rows)}
        finally:
            await connection.close()

    @app.patch("/api/v1/admin/roles/{role_id}/menus")
    async def update_role_menus(
        role_id: int, payload: RoleMenuPatch, request: Request
    ) -> dict[str, Any]:
        """原子替换角色菜单权限并记录变更前后集合，禁止修改系统角色。"""
        context = await _authenticated_user(config, request)
        _require_platform_admin(context)
        menu_ids = sorted(set(payload.menu_ids))
        connection = await _database(config)
        try:
            async with connection.transaction():
                role = await connection.fetchrow(
                    """
                    SELECT id::text, code, name, scope, is_system
                    FROM roles WHERE id = $1 FOR UPDATE
                    """,
                    role_id,
                )
                if role is None:
                    raise HTTPException(status_code=404, detail="角色不存在")
                if role["is_system"]:
                    raise HTTPException(status_code=409, detail="系统角色不允许直接修改权限")
                valid_ids = await connection.fetchval(
                    "SELECT count(*)::int FROM menus WHERE id = ANY($1::bigint[])", menu_ids
                )
                if int(valid_ids or 0) != len(menu_ids):
                    raise HTTPException(status_code=400, detail="存在无效菜单权限")
                old_ids = await connection.fetchval(
                    """
                    SELECT COALESCE(array_agg(menu_id ORDER BY menu_id), '{}')
                    FROM role_menus WHERE role_id = $1
                    """,
                    role_id,
                )
                await connection.execute("DELETE FROM role_menus WHERE role_id = $1", role_id)
                if menu_ids:
                    await connection.executemany(
                        "INSERT INTO role_menus(role_id, menu_id) VALUES ($1, $2)",
                        [(role_id, menu_id) for menu_id in menu_ids],
                    )
                await write_audit_event(
                    connection,
                    tenant_id=None,  # type: ignore[arg-type]
                    actor_id=int(context["user"]["id"]),
                    action="role.permissions.update",
                    target_type="role",
                    target_id=role_id,
                    summary={
                        "role_code": role["code"],
                        "before_menu_ids": list(old_ids or []),
                        "after_menu_ids": menu_ids,
                    },
                )
            return {**dict(role), "menu_ids": menu_ids}
        finally:
            await connection.close()

    @app.get("/api/v1/admin/users")
    async def admin_users(request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        if context["user"]["platform_role"] != "platform_admin":
            raise HTTPException(status_code=403, detail="只有平台管理员可以管理用户")
        connection = await _database(config)
        try:
            rows = await connection.fetch(
                """
                SELECT u.id::text, u.login, u.display_name, u.status,
                       pr.code AS platform_role, count(DISTINCT tm.tenant_id)::int AS space_count,
                       u.last_login_at, u.created_at
                FROM users u LEFT JOIN roles pr ON pr.id = u.platform_role_id
                LEFT JOIN tenant_members tm ON tm.user_id = u.id AND tm.status = 'active'
                GROUP BY u.id, pr.code ORDER BY u.created_at DESC
                """
            )
            return {"items": _rows(rows)}
        finally:
            await connection.close()

    @app.post("/api/v1/admin/users", status_code=201)
    async def create_user(payload: UserCreate, request: Request) -> dict[str, Any]:
        """创建平台账号，并在同一事务中保存可选空间授权及两级审计事件。"""
        context = await _authenticated_user(config, request)
        if context["user"]["platform_role"] != "platform_admin":
            raise HTTPException(status_code=403, detail="只有平台管理员可以创建用户")
        if payload.tenant_id is not None and payload.tenant_role_code is None:
            raise HTTPException(status_code=400, detail="分配空间时必须指定空间角色")
        connection = await _database(config)
        try:
            # 用户、空间成员关系和对应审计必须原子提交，避免出现已授权但无法追责的状态。
            async with connection.transaction():
                platform_role_id = None
                if payload.platform_role_code:
                    platform_role_id = await connection.fetchval(
                        "SELECT id FROM roles WHERE code = $1 AND scope = 'platform'",
                        payload.platform_role_code,
                    )
                    if platform_role_id is None:
                        raise HTTPException(status_code=400, detail="平台角色不存在")
                tenant_role_id = None
                if payload.tenant_id is not None:
                    tenant_role_id = await connection.fetchval(
                        "SELECT id FROM roles WHERE code = $1 AND scope = 'tenant'",
                        payload.tenant_role_code,
                    )
                    tenant_exists = await connection.fetchval(
                        "SELECT EXISTS (SELECT 1 FROM tenants WHERE id = $1 AND status = 'active')",
                        payload.tenant_id,
                    )
                    if tenant_role_id is None or not tenant_exists:
                        raise HTTPException(status_code=400, detail="空间或空间角色不存在")
                user_row = await connection.fetchrow(
                    """
                    INSERT INTO users(login, display_name, password_hash, platform_role_id)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id, login, display_name, status, created_at
                    """,
                    payload.login,
                    payload.display_name,
                    password_hasher.hash(payload.password),
                    platform_role_id,
                )
                if payload.tenant_id is not None and tenant_role_id is not None:
                    await connection.execute(
                        """
                        INSERT INTO tenant_members(tenant_id, user_id, role_id)
                        VALUES ($1, $2, $3)
                        """,
                        payload.tenant_id,
                        user_row["id"],
                        tenant_role_id,
                    )
                    await _write_membership_audit(
                        connection,
                        tenant_id=payload.tenant_id,
                        actor_id=int(context["user"]["id"]),
                        action="space_member.add",
                        target_type="user",
                        target_id=int(user_row["id"]),
                        summary={
                            "role_code": payload.tenant_role_code,
                            "source": "user.create",
                        },
                    )
                await connection.execute(
                    """
                    INSERT INTO audit_logs(
                      actor_id, action, target_type, target_id, change_summary
                    ) VALUES ($1, 'user.create', 'user', $2, $3::jsonb)
                    """,
                    int(context["user"]["id"]),
                    str(user_row["id"]),
                    json.dumps(
                        {
                            "login": payload.login,
                            "display_name": payload.display_name,
                            "platform_role_code": payload.platform_role_code,
                            "tenant_id": (
                                str(payload.tenant_id) if payload.tenant_id is not None else None
                            ),
                            "tenant_role_code": payload.tenant_role_code,
                        },
                        ensure_ascii=False,
                    ),
                )
                return {**dict(user_row), "id": str(user_row["id"])}
        except asyncpg.UniqueViolationError as error:
            raise HTTPException(status_code=409, detail="登录名已存在") from error
        finally:
            await connection.close()

    @app.patch("/api/v1/admin/users/{user_id}")
    async def update_user(user_id: int, payload: UserPatch, request: Request) -> dict[str, Any]:
        """更新用户资料或状态，并记录安全脱敏的前后状态与会话失效结果。"""
        context = await _authenticated_user(config, request)
        if context["user"]["platform_role"] != "platform_admin":
            raise HTTPException(status_code=403, detail="只有平台管理员可以管理用户")
        values = payload.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=400, detail="没有需要修改的字段")
        if user_id == int(context["user"]["id"]) and values.get("status") == "disabled":
            raise HTTPException(status_code=400, detail="不能停用当前登录账号")
        role_values = {
            key: values.pop(key)
            for key in ("platform_role_code", "tenant_id", "tenant_role_code")
            if key in values
        }
        if (
            "tenant_id" in role_values
            and role_values["tenant_id"] is not None
            and not role_values.get("tenant_role_code")
        ):
            raise HTTPException(status_code=400, detail="分配空间时必须指定空间角色")
        assignments: list[str] = []
        parameters: list[Any] = [user_id]
        for index, (key, value) in enumerate(values.items(), 2):
            column = "password_hash" if key == "password" else key
            value = password_hasher.hash(value) if key == "password" else value
            assignments.append(f"{column} = ${index}")
            parameters.append(value)
        connection = await _database(config)
        try:
            async with connection.transaction():
                # 锁定用户行，保证审计中的 before 与本次更新属于同一并发版本。
                before = await connection.fetchrow(
                    """
                    SELECT id, login, display_name, status
                    FROM users WHERE id = $1 FOR UPDATE
                    """,
                    user_id,
                )
                if before is None:
                    raise HTTPException(status_code=404, detail="用户不存在")
                # 编辑表单提交角色三元组时，在同一事务内校验角色与空间并替换当前有效归属。
                if role_values:
                    platform_role_id = None
                    if role_values.get("platform_role_code"):
                        platform_role_id = await connection.fetchval(
                            "SELECT id FROM roles WHERE code = $1 AND scope = 'platform'",
                            role_values["platform_role_code"],
                        )
                        if platform_role_id is None:
                            raise HTTPException(status_code=400, detail="平台角色不存在")
                    await connection.execute(
                        "UPDATE users SET platform_role_id = $2 WHERE id = $1",
                        user_id,
                        platform_role_id,
                    )
                    await connection.execute(
                        "UPDATE tenant_members SET status = 'disabled' WHERE user_id = $1 AND status = 'active'",
                        user_id,
                    )
                    if role_values.get("tenant_id") is not None:
                        tenant_role_id = await connection.fetchval(
                            "SELECT id FROM roles WHERE code = $1 AND scope = 'tenant'",
                            role_values["tenant_role_code"],
                        )
                        tenant_exists = await connection.fetchval(
                            "SELECT EXISTS (SELECT 1 FROM tenants WHERE id = $1 AND status = 'active')",
                            role_values["tenant_id"],
                        )
                        if tenant_role_id is None or not tenant_exists:
                            raise HTTPException(status_code=400, detail="空间或空间角色不存在")
                        await connection.execute(
                            """
                            INSERT INTO tenant_members(tenant_id, user_id, role_id, status)
                            VALUES ($1, $2, $3, 'active')
                            ON CONFLICT (tenant_id, user_id) DO UPDATE
                            SET role_id = EXCLUDED.role_id, status = 'active'
                            """,
                            role_values["tenant_id"],
                            user_id,
                            tenant_role_id,
                        )
                row = (
                    await connection.fetchrow(
                        f"""
                    UPDATE users SET {", ".join(assignments)}, updated_at = now()
                    WHERE id = $1
                    RETURNING id::text, login, display_name, status, last_login_at, created_at
                    """,
                        *parameters,
                    )
                    if assignments
                    else await connection.fetchrow(
                        "SELECT id::text, login, display_name, status, last_login_at, created_at FROM users WHERE id = $1",
                        user_id,
                    )
                )
                if row is None:
                    raise HTTPException(status_code=404, detail="用户不存在")
                revoked_sessions = 0
                if "password" in values or values.get("status") == "disabled":
                    # 密码重置或账号停用必须立即使现有会话失效，撤销数量用于运维核验。
                    revoked_sessions = int(
                        await connection.fetchval(
                            """
                            WITH revoked AS (
                              UPDATE sessions SET revoked_at = now()
                              WHERE user_id = $1 AND revoked_at IS NULL
                              RETURNING id
                            ) SELECT count(*)::int FROM revoked
                            """,
                            user_id,
                        )
                        or 0
                    )
                changed_fields = sorted(values)
                # 密码只记录“发生过重置”，绝不写入明文或哈希；前后值仅允许非敏感字段。
                summary_fields = {"display_name", "status"}
                await connection.execute(
                    """
                    INSERT INTO audit_logs(
                      actor_id, action, target_type, target_id, change_summary
                    ) VALUES ($1, 'user.update', 'user', $2, $3::jsonb)
                    """,
                    int(context["user"]["id"]),
                    str(user_id),
                    json.dumps(
                        {
                            "fields": changed_fields,
                            "before": {
                                field: before[field]
                                for field in changed_fields
                                if field in summary_fields
                            },
                            "after": {
                                field: row[field]
                                for field in changed_fields
                                if field in summary_fields
                            },
                            "password_reset": "password" in values,
                            "revoked_sessions": revoked_sessions,
                        },
                        ensure_ascii=False,
                    ),
                )
            return dict(row)
        finally:
            await connection.close()

    @app.post("/api/v1/admin/tenants", status_code=201)
    async def create_tenant(payload: TenantCreate, request: Request) -> dict[str, Any]:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            is_platform_admin = await _require_space_management_actor(connection, context)
            try:
                async with connection.transaction():
                    if not is_platform_admin:
                        # 对用户行加锁串行化额度检查，避免两个并发请求同时越过单空间上限。
                        await connection.fetchval(
                            "SELECT id FROM users WHERE id = $1 FOR UPDATE",
                            int(context["user"]["id"]),
                        )
                        created_count = await connection.fetchval(
                            "SELECT count(*) FROM tenants WHERE created_by = $1",
                            int(context["user"]["id"]),
                        )
                        if int(created_count or 0) >= 1:
                            raise HTTPException(
                                status_code=409,
                                detail="空间管理员最多只能额外创建一个空间",
                            )
                        row = await connection.fetchrow(
                            "INSERT INTO tenants(code, name, created_by) VALUES ($1, $2, $3) "
                            "RETURNING id::text, code, name, status, created_at",
                            payload.code,
                            payload.name,
                            int(context["user"]["id"]),
                        )
                    else:
                        row = await connection.fetchrow(
                            "INSERT INTO tenants(code, name) VALUES ($1, $2) "
                            "RETURNING id::text, code, name, status, created_at",
                            payload.code,
                            payload.name,
                        )
                    space_admin_role_id = await connection.fetchval(
                        "SELECT id FROM roles WHERE code = 'space_admin'"
                    )
                    if row is None or space_admin_role_id is None:
                        raise HTTPException(status_code=500, detail="空间管理员角色未初始化")
                    await connection.execute(
                        """
                        INSERT INTO tenant_members(tenant_id, user_id, role_id)
                        VALUES ($1, $2, $3)
                        """,
                        int(row["id"]),
                        int(context["user"]["id"]),
                        space_admin_role_id,
                    )
            except asyncpg.UniqueViolationError as error:
                raise HTTPException(status_code=409, detail="空间编码已存在") from error
            return dict(row)
        finally:
            await connection.close()

    @app.get("/api/v1/admin/tenants")
    async def admin_tenants(request: Request) -> dict[str, Any]:
        """返回可管理空间；平台管理员看全部，空间管理员只看已分配空间及自己的额外空间。"""
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            is_platform_admin = await _require_space_management_actor(connection, context)
            user_id = int(context["user"]["id"])
            scope_clause = (
                ""
                if is_platform_admin
                else (
                    "AND EXISTS (SELECT 1 FROM tenant_members scoped_tm "
                    "WHERE scoped_tm.tenant_id = t.id AND scoped_tm.user_id = $1 "
                    "AND scoped_tm.status = 'active')"
                )
            )
            args: tuple[Any, ...] = () if is_platform_admin else (user_id,)
            rows = await connection.fetch(
                f"""
                SELECT t.id::text, t.code, t.name, t.status, t.created_at,
                       count(DISTINCT tm.user_id)::int AS member_count,
                       count(DISTINCT kb.id)::int AS knowledge_base_count,
                       current_key.id::text AS api_key_id,
                       current_key.status AS api_key_status,
                       current_key.key_prefix AS api_key_prefix,
                       current_key.token_limit AS api_key_token_limit,
                       current_key.token_used AS api_key_token_used,
                       current_key.token_remaining AS api_key_token_remaining,
                       current_key.configured_at AS api_key_configured_at,
                       current_key.expires_at AS api_key_expires_at
                FROM tenants t LEFT JOIN tenant_members tm
                  ON tm.tenant_id = t.id AND tm.status = 'active'
                LEFT JOIN knowledge_bases kb ON kb.tenant_id = t.id AND kb.status <> 'disabled'
                LEFT JOIN LATERAL (
                  SELECT ak.id,
                         CASE WHEN ak.status = 'active' AND ak.expires_at IS NOT NULL
                                   AND ak.expires_at <= now()
                              THEN 'expired' ELSE ak.status END AS status,
                         ak.key_prefix,
                         ak.token_limit,
                         ak.token_used,
                         GREATEST(0, ak.token_limit - ak.token_used - ak.token_reserved)
                           AS token_remaining,
                         ak.configured_at,
                         ak.expires_at
                  FROM api_keys ak
                  WHERE ak.tenant_id = t.id AND ak.deleted_at IS NULL
                  ORDER BY ak.created_at DESC, ak.id DESC
                  LIMIT 1
                ) current_key ON true
                WHERE 1 = 1 {scope_clause}
                GROUP BY t.id, current_key.id, current_key.status, current_key.key_prefix,
                         current_key.token_limit, current_key.token_used,
                         current_key.token_remaining, current_key.configured_at,
                         current_key.expires_at
                ORDER BY t.created_at DESC
                """,
                *args,
            )
            created_count = (
                0
                if is_platform_admin
                else await connection.fetchval(
                    "SELECT count(*) FROM tenants WHERE created_by = $1", user_id
                )
            )
            return {
                "items": _rows(rows),
                "can_create": is_platform_admin or int(created_count or 0) < 1,
                "created_space_count": int(created_count or 0),
            }
        finally:
            await connection.close()

    @app.get("/api/v1/spaces/{tenant_id}/api-key/configuration")
    async def get_tenant_api_key_configuration(
        tenant_id: int,
        request: Request,
    ) -> dict[str, Any]:
        """返回当前医院最新一把 Key 的脱敏状态，确认前不读取任何明文。"""
        context = await _authenticated_user(config, request)
        _require_hospital_account(context)
        connection = await _database(config)
        try:
            await _require_space_admin(connection, context, tenant_id)
            row = await connection.fetchrow(
                """
                SELECT ak.key_prefix, ak.configured_at,
                       CASE WHEN tenant.status <> 'active' THEN 'disabled'
                            WHEN ak.status = 'active' AND ak.expires_at IS NOT NULL
                                 AND ak.expires_at <= now() THEN 'expired'
                            ELSE ak.status END AS status
                FROM api_keys ak
                JOIN tenants tenant ON tenant.id = ak.tenant_id
                WHERE ak.tenant_id = $1 AND ak.deleted_at IS NULL
                ORDER BY ak.created_at DESC, ak.id DESC
                LIMIT 1
                """,
                tenant_id,
            )
            if row is None:
                return {
                    "configured": False,
                    "key_prefix": None,
                    "status": None,
                    "configured_at": None,
                }
            return {
                "configured": row["configured_at"] is not None,
                "key_prefix": row["key_prefix"],
                "status": row["status"],
                "configured_at": row["configured_at"],
            }
        finally:
            await connection.close()

    @app.post("/api/v1/spaces/{tenant_id}/api-key/configuration")
    async def confirm_tenant_api_key_configuration(
        tenant_id: int,
        payload: TenantApiKeyConfiguration,
        request: Request,
    ) -> dict[str, Any]:
        """核验医院管理员粘贴的 Key 属于当前医院，再记录无明文的交接确认。"""
        context = await _authenticated_user(config, request)
        _require_hospital_account(context)
        connection = await _database(config)
        raw_key = payload.api_key.get_secret_value()
        try:
            async with connection.transaction():
                await _require_space_admin(connection, context, tenant_id)
                row = await connection.fetchrow(
                    """
                    SELECT ak.id, ak.key_prefix, ak.status, ak.expires_at,
                           ak.token_limit, ak.token_used, ak.token_reserved,
                           ak.configured_at, tenant.status AS tenant_status
                    FROM api_keys ak
                    JOIN tenants tenant ON tenant.id = ak.tenant_id
                    WHERE ak.tenant_id = $1 AND ak.key_hash = $2
                      AND ak.deleted_at IS NULL
                      AND ak.id = (
                        SELECT current_key.id FROM api_keys current_key
                        WHERE current_key.tenant_id = $1 AND current_key.deleted_at IS NULL
                        ORDER BY current_key.created_at DESC, current_key.id DESC
                        LIMIT 1
                      )
                    FOR UPDATE OF ak
                    """,
                    tenant_id,
                    hash_api_key(raw_key),
                )
                if row is None:
                    raise HTTPException(
                        status_code=400,
                        detail="此 Key 与系统为当前医院分配的最新 Key 不匹配",
                    )
                is_usable = (
                    row["tenant_status"] == "active"
                    and row["status"] == "active"
                    and (row["expires_at"] is None or row["expires_at"] > datetime.now(UTC))
                    and row["token_used"] + row["token_reserved"] < row["token_limit"]
                )
                if not is_usable:
                    raise HTTPException(
                        status_code=409,
                        detail="当前医院 Key 已停用、过期或额度不足，请联系系统管理员",
                    )
                configured_at = row["configured_at"]
                if configured_at is None:
                    configured_at = await connection.fetchval(
                        """
                        UPDATE api_keys SET configured_at = now(), configured_by = $2
                        WHERE id = $1 AND configured_at IS NULL
                        RETURNING configured_at
                        """,
                        row["id"],
                        int(context["user"]["id"]),
                    )
                    await write_audit_event(
                        connection,
                        tenant_id=tenant_id,
                        actor_id=int(context["user"]["id"]),
                        action="api_key.configure",
                        target_type="api_key",
                        target_id=row["id"],
                        summary={"configured": True},
                    )
            return {
                "configured": True,
                "key_prefix": row["key_prefix"],
                "status": "active",
                "configured_at": configured_at,
            }
        finally:
            await connection.close()
