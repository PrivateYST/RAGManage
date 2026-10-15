# ruff: noqa
# mypy: ignore-errors
"""登录、会话和身份凭据路由。

路由函数保持薄层，领域规则继续由 app.main 中的兼容辅助函数和 app.rag 服务提供。
"""

from fastapi import FastAPI
from app.main import *  # noqa: F403,F401


def register(app: FastAPI, config: Settings) -> None:
    """将本领域路由挂载到应用；config 是应用级配置快照。"""
    from app import main as main_module

    globals().update(main_module.__dict__)

    @app.post("/api/v1/auth/login")
    async def login(
        payload: dict[str, str], request: Request, response: Response
    ) -> dict[str, Any]:
        """跨 Worker 限速管理员登录；Redis 不可用时关闭认证并返回 503。"""
        login_name = payload.get("login", "")
        client_ip = login_client_ip(request)
        try:
            redis = Redis.from_url(
                config.redis_url,
                socket_connect_timeout=2,
                socket_timeout=2,
                decode_responses=False,
            )
        except Exception as error:
            logger.exception("登录限速存储初始化失败")
            raise HTTPException(status_code=503, detail="登录服务暂不可用，请稍后重试") from error
        try:
            reservation = await reserve_login_attempt(redis, login_name, client_ip)
        except Exception as error:
            logger.exception("登录限速存储不可用")
            try:
                await redis.aclose()
            except Exception:
                logger.exception("关闭登录限速连接失败")
            raise HTTPException(status_code=503, detail="登录服务暂不可用，请稍后重试") from error
        if reservation is None:
            try:
                await redis.aclose()
            except Exception:
                logger.exception("关闭登录限速连接失败")
            raise HTTPException(status_code=429, detail="登录尝试过多，请稍后重试")

        try:
            context = await authenticate(config, login_name, payload.get("password", ""))
        except Exception as error:
            try:
                await finish_login_attempt(redis, reservation, succeeded=None)
            except Exception:
                logger.exception("登录失败预占释放异常")
            try:
                await redis.aclose()
            except Exception:
                logger.exception("关闭登录限速连接失败")
            logger.exception("登录认证数据库操作失败")
            raise HTTPException(status_code=503, detail="登录服务暂不可用，请稍后重试") from error

        try:
            await finish_login_attempt(redis, reservation, succeeded=context is not None)
        except Exception as error:
            # 结算响应丢失时不能重放脚本，否则成功认证可能被重复计为失败。
            logger.exception("登录限速状态结算失败")
            if context is not None:
                try:
                    await revoke_token(config, context.get("token"))
                except Exception:
                    logger.exception("登录限速结算失败后撤销孤立会话失败")
            raise HTTPException(status_code=503, detail="登录服务暂不可用，请稍后重试") from error
        finally:
            try:
                await redis.aclose()
            except Exception:
                logger.exception("关闭登录限速连接失败")

        if context is None:
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        token = context.pop("token")
        response.set_cookie(
            SESSION_COOKIE,
            token,
            httponly=True,
            samesite="lax",
            secure=config.cookie_secure,
            max_age=config.session_ttl_hours * 3600,
        )
        response.set_cookie(
            "ragmanage_csrf",
            session_csrf_token(config.csrf_secret_value, token),
            httponly=False,
            samesite="lax",
            secure=config.cookie_secure,
            max_age=config.session_ttl_hours * 3600,
        )
        return context

    @app.get("/api/v1/auth/csrf")
    async def csrf_token(request: Request, response: Response) -> dict[str, str]:
        """为部署升级前已有的有效 Session 补发会话绑定 CSRF Cookie。"""
        context = await _authenticated_user(config, request)
        if context.get("api_key_id") is not None:
            raise HTTPException(status_code=403, detail="CSRF token 仅适用于浏览器会话")
        session_token = request.cookies.get(SESSION_COOKIE, "")
        token = session_csrf_token(config.csrf_secret_value, session_token)
        response.set_cookie(
            "ragmanage_csrf",
            token,
            httponly=False,
            samesite="lax",
            secure=config.cookie_secure,
            max_age=config.session_ttl_hours * 3600,
        )
        response.headers["Cache-Control"] = "no-store"
        return {"csrf_token": token}

    @app.post("/api/v1/auth/logout", status_code=204)
    async def logout(request: Request, response: Response) -> None:
        await revoke_token(config, request.cookies.get(SESSION_COOKIE))
        response.delete_cookie(SESSION_COOKIE)
        response.delete_cookie("ragmanage_csrf")

    @app.get("/api/v1/auth/me")
    async def me(request: Request) -> dict[str, Any]:
        return await _authenticated_user(config, request)

    @app.get("/api/v1/auth/sessions")
    async def list_sessions(request: Request) -> dict[str, Any]:
        """列出当前账号仍有效的浏览器 Session，并标记当前请求对应的会话。"""
        context = await _authenticated_user(config, request)
        if context.get("api_key_id") is not None:
            raise HTTPException(status_code=403, detail="会话管理仅适用于浏览器登录")
        token = request.cookies.get(SESSION_COOKIE, "")
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        connection = await _database(config)
        try:
            rows = await connection.fetch(
                """
                SELECT id::text, created_at, last_seen_at, expires_at,
                       token_hash = $2 AS is_current
                FROM sessions
                WHERE user_id = $1 AND revoked_at IS NULL AND expires_at > now()
                ORDER BY last_seen_at DESC, id DESC
                LIMIT $3
                """,
                int(context["user"]["id"]),
                token_hash,
                SESSION_LIST_LIMIT,
            )
            return {"items": [dict(row) for row in rows]}
        finally:
            await connection.close()

    @app.delete("/api/v1/auth/sessions/{session_id}", status_code=204)
    async def revoke_session(
        session_id: int,
        request: Request,
        response: Response,
    ) -> None:
        """原子撤销本人指定的有效 Session；撤销当前会话时同步清除浏览器 Cookie。"""
        context = await _authenticated_user(config, request)
        if context.get("api_key_id") is not None:
            raise HTTPException(status_code=403, detail="会话管理仅适用于浏览器登录")
        current_token = request.cookies.get(SESSION_COOKIE, "")
        current_hash = hashlib.sha256(current_token.encode("utf-8")).hexdigest()
        connection = await _database(config)
        try:
            async with connection.transaction():
                session = await connection.fetchrow(
                    """
                    UPDATE sessions SET revoked_at = now()
                    WHERE id = $1 AND user_id = $2 AND revoked_at IS NULL
                      AND expires_at > now()
                    RETURNING id, user_id, token_hash
                    """,
                    session_id,
                    int(context["user"]["id"]),
                )
                if session is None:
                    raise HTTPException(status_code=404, detail="有效会话不存在")
                await connection.execute(
                    """
                    INSERT INTO audit_logs(
                      actor_id, action, target_type, target_id, change_summary
                    ) VALUES ($1, 'auth.session.revoked', 'session', $2, $3::jsonb)
                    """,
                    int(context["user"]["id"]),
                    str(session["id"]),
                    json.dumps({"result": "revoked"}, ensure_ascii=False),
                )
                is_current = session["token_hash"] == current_hash
            if is_current:
                response.delete_cookie(SESSION_COOKIE)
                response.delete_cookie("ragmanage_csrf")
        finally:
            await connection.close()

    @app.post("/api/v1/auth/password", status_code=204)
    async def change_password(
        payload: PasswordChange, request: Request, response: Response
    ) -> None:
        context = await _authenticated_user(config, request)
        connection = await _database(config)
        try:
            user_id = int(context["user"]["id"])
            password_hash = await connection.fetchval(
                "SELECT password_hash FROM users WHERE id = $1", user_id
            )
            try:
                password_hasher.verify(password_hash, payload.current_password)
            except (VerifyMismatchError, VerificationError, InvalidHashError) as error:
                raise HTTPException(status_code=400, detail="当前密码不正确") from error
            if payload.current_password == payload.new_password:
                raise HTTPException(status_code=400, detail="新密码不能与当前密码相同")
            async with connection.transaction():
                await connection.execute(
                    "UPDATE users SET password_hash = $2, updated_at = now() WHERE id = $1",
                    user_id,
                    password_hasher.hash(payload.new_password),
                )
                revoked_sessions = await connection.fetchval(
                    """
                    WITH revoked AS (
                      UPDATE sessions SET revoked_at = now()
                      WHERE user_id = $1 AND revoked_at IS NULL
                      RETURNING id
                    ) SELECT count(*)::int FROM revoked
                    """,
                    user_id,
                )
                await connection.execute(
                    """
                    INSERT INTO audit_logs(
                      actor_id, action, target_type, target_id, change_summary
                    ) VALUES ($1, 'auth.password.changed', 'user', $2, $3::jsonb)
                    """,
                    user_id,
                    str(user_id),
                    json.dumps(
                        {"revoked_sessions": int(revoked_sessions or 0)},
                        ensure_ascii=False,
                    ),
                )
            response.delete_cookie(SESSION_COOKIE)
            response.delete_cookie("ragmanage_csrf")
        finally:
            await connection.close()
