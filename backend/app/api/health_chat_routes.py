# ruff: noqa
# mypy: ignore-errors
"""健康检查与 OpenAI 兼容问答路由。

路由函数保持薄层，领域规则继续由 app.main 中的兼容辅助函数和 app.rag 服务提供。
"""

from fastapi import FastAPI
from app.main import *  # noqa: F403,F401


def register(app: FastAPI, config: Settings) -> None:
    """将本领域路由挂载到应用；config 是应用级配置快照。"""
    from app import main as main_module

    globals().update(main_module.__dict__)

    @app.get("/api/v1/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/health/ready")
    async def ready() -> JSONResponse:
        checks = await check_dependencies(config)
        healthy = all(value == "ok" for value in checks.values())
        return JSONResponse(
            status_code=200 if healthy else 503,
            content={"status": "ready" if healthy else "not_ready", "checks": checks},
        )

    @app.get("/api/v1/health/metrics")
    async def metrics(request: Request) -> dict[str, object]:
        """仅向平台管理员返回聚合运行指标，不泄露租户正文或凭据。"""
        context = await _authenticated_user(config, request)
        _require_platform_admin(context)
        return await collect_runtime_metrics(config)

    @app.post("/v1/chat/completions")
    async def openai_chat_completions(
        payload: OpenAIChatCompletionRequest,
        request: Request,
    ) -> Response:
        """提供客户 Key 专用的 OpenAI 兼容 RAG 问答入口和标准 SSE。"""
        request_id_header = request.headers.get("x-request-id")
        try:
            context = await _authenticated_user(config, request)
            if context.get("api_key_id") is None:
                return JSONResponse(
                    status_code=403,
                    content=_openai_error_payload(
                        "api_key_scope_forbidden",
                        "只有客户 API Key 可以调用模型网关",
                    ),
                )
            max_output_tokens = min(
                OPENAI_CHAT_MAX_OUTPUT_TOKENS,
                max(1, config.generation_max_tokens),
            )
            if payload.max_tokens is not None and payload.max_tokens > max_output_tokens:
                return JSONResponse(
                    status_code=400,
                    content=_openai_error_payload(
                        "max_tokens_exceeds_server_limit",
                        "max_tokens 超过服务端单次生成上限",
                    ),
                )
            if payload.request_id is not None and request_id_header:
                try:
                    header_request_id = UUID(request_id_header)
                except ValueError as error:
                    raise HTTPException(
                        status_code=400, detail="X-Request-ID 必须是 UUID"
                    ) from error
                if payload.request_id != header_request_id:
                    return JSONResponse(
                        status_code=400,
                        content=_openai_error_payload(
                            "request_id_mismatch",
                            "request_id 与 X-Request-ID 必须一致",
                        ),
                    )
            if payload.request_id is not None:
                request_id = payload.request_id
            elif request_id_header:
                try:
                    request_id = UUID(request_id_header)
                except ValueError as error:
                    raise HTTPException(
                        status_code=400, detail="X-Request-ID 必须是 UUID"
                    ) from error
            else:
                request_id = uuid4()
            question = _openai_question(payload.messages)
            connection = await _database(config)
            try:
                effective_max_tokens = payload.max_tokens or max_output_tokens
                run_id, run = await _prepare_openai_run(
                    connection,
                    context=context,
                    knowledge_base_id=payload.knowledge_base_id,
                    model=payload.model,
                    question=question,
                    request_id=request_id,
                    max_tokens=effective_max_tokens,
                    default_model=config.generation_model,
                    default_allowed_models=config.allowed_model_names,
                )
            finally:
                await connection.close()

            public_run = _public_run_payload(run)
            public_id = str(public_run.get("id") or uuid4())
            completion_id = f"chatcmpl_{public_id}"
            created = int(time.time())
            source = stream_generation_run(
                config,
                run_id=run_id,
                user_id=int(context["user"]["id"]),
                api_key_id=str(context["api_key_id"]),
                api_key_tenant_id=int(context["api_key_tenant_id"]),
                max_tokens=effective_max_tokens,
            )
            headers = {"Cache-Control": "no-cache", "X-Request-ID": str(request_id)}
            if payload.stream:
                headers["X-Accel-Buffering"] = "no"
                return StreamingResponse(
                    _stream_openai_completion(
                        source,
                        completion_id=completion_id,
                        model=payload.model,
                        created=created,
                    ),
                    media_type="text/event-stream",
                    headers=headers,
                )
            result = await _collect_openai_completion(
                source,
                completion_id=completion_id,
                model=payload.model,
                created=created,
            )
            status_code = 200
            if "error" in result:
                error_code = str(result["error"].get("code", "generation_failed"))
                status_code = 429 if error_code == "TOKEN_QUOTA_EXCEEDED" else 502
                if error_code == "request_cancelled":
                    status_code = 409
            return JSONResponse(status_code=status_code, content=result, headers=headers)
        except HTTPException as error:
            if error.status_code == 401:
                code = "invalid_api_key"
            elif error.status_code == 403:
                code = "api_key_scope_forbidden"
            elif error.status_code == 404:
                code = "knowledge_base_not_found"
            elif error.status_code == 409:
                code = "duplicate_request"
            elif error.status_code == 429:
                code = "rate_limit_exceeded"
            elif error.status_code == 503:
                code = "service_unavailable"
            else:
                code = "invalid_request"
            return JSONResponse(
                status_code=error.status_code,
                content=_openai_error_payload(code, str(error.detail)),
            )
        except asyncpg.PostgresError as error:
            logger.exception("OpenAI 兼容入口数据库操作失败", exc_info=error)
            return JSONResponse(
                status_code=503,
                content=_openai_error_payload(
                    "service_unavailable", "问答服务暂不可用，请稍后重试。"
                ),
            )
        except Exception as error:
            logger.exception("OpenAI 兼容入口发生未预期异常", exc_info=error)
            return JSONResponse(
                status_code=502,
                content=_openai_error_payload("generation_failed", "问答生成失败，可以重试。"),
            )
