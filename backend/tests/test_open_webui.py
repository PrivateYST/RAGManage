"""Open WebUI 服务账号与原生 API Key 适配器的 HTTP 契约测试。"""

import asyncio
import json
from collections.abc import Awaitable, Callable

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.integrations.open_webui import (
    OpenWebUIAdminClient,
    OpenWebUIProvisioningError,
)


def make_settings() -> Settings:
    """创建只用于测试的网关配置，避免读取开发机环境变量。"""
    return Settings(
        model_gateway_base_url="http://gateway.test",
        model_gateway_api_key=SecretStr("company-admin-key"),
        database_url="",
    )


def make_transport(
    handler: Callable[[httpx.Request], httpx.Response | Awaitable[httpx.Response]],
) -> httpx.MockTransport:
    """把异步请求处理器包装成 AsyncClient 可用的 MockTransport。"""
    return httpx.MockTransport(handler)


def test_provision_service_key_creates_service_user_and_native_key() -> None:
    """创建流程必须先使用平台 Key 建号，再用服务账号登录生成 ``sk-`` Key。"""
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v1/auths/add":
            assert request.headers["authorization"] == "Bearer company-admin-key"
            assert json.loads(request.content)["role"] == "user"
            return httpx.Response(201, json={"id": "remote-user-3"})
        if request.url.path == "/api/v1/auths/signin":
            assert (
                json.loads(request.content)["email"] == "ragmanage-tenant-3@service.ragmanage.local"
            )
            return httpx.Response(200, json={"token": "service-session"})
        if request.url.path == "/api/v1/auths/api_key":
            assert request.headers["authorization"] == "Bearer service-session"
            return httpx.Response(200, json={"api_key": "sk-openwebui-tenant-3"})
        return httpx.Response(404)

    result = asyncio.run(
        OpenWebUIAdminClient(
            make_settings(), transport=make_transport(handler)
        ).provision_service_key(tenant_id=3, tenant_name="客户 A")
    )

    assert result.api_key == "sk-openwebui-tenant-3"
    assert result.user_id == "remote-user-3"
    assert result.user_email == "ragmanage-tenant-3@service.ragmanage.local"
    assert result.user_password
    assert [request.url.path for request in requests] == [
        "/api/v1/auths/add",
        "/api/v1/auths/signin",
        "/api/v1/auths/api_key",
    ]


def test_revoke_service_key_deletes_native_key_after_service_login() -> None:
    """删除远端 Key 必须使用医院服务账号会话，而不是平台管理员 Key。"""
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v1/auths/signin":
            assert json.loads(request.content) == {
                "email": "ragmanage-tenant-3@service.ragmanage.local",
                "password": "service-password",
            }
            return httpx.Response(200, json={"token": "service-session"})
        if request.url.path == "/api/v1/auths/api_key":
            assert request.method == "DELETE"
            assert request.headers["authorization"] == "Bearer service-session"
            return httpx.Response(204)
        return httpx.Response(404)

    asyncio.run(
        OpenWebUIAdminClient(make_settings(), transport=make_transport(handler)).revoke_service_key(
            user_email="ragmanage-tenant-3@service.ragmanage.local",
            user_password="service-password",
        )
    )

    assert [request.method for request in requests] == ["POST", "DELETE"]


def test_provisioning_error_is_explicit_when_open_webui_rejects_request() -> None:
    """Open WebUI 返回错误时必须阻止本地继续写入，便于上层回滚事务。"""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "admin required"})

    with pytest.raises(OpenWebUIProvisioningError, match="SERVICE_USER_CREATE_FAILED:403"):
        asyncio.run(
            OpenWebUIAdminClient(
                make_settings(), transport=make_transport(handler)
            ).provision_service_key(tenant_id=3, tenant_name="客户 A")
        )


def test_revoke_error_is_explicit_when_remote_delete_fails() -> None:
    """远端撤销失败时向上抛出，调用方不能把本地状态误标为已删除。"""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/auths/signin":
            return httpx.Response(200, json={"token": "service-session"})
        return httpx.Response(500)

    with pytest.raises(OpenWebUIProvisioningError, match="API_KEY_DELETE_FAILED:500"):
        asyncio.run(
            OpenWebUIAdminClient(
                make_settings(), transport=make_transport(handler)
            ).revoke_service_key(
                user_email="service@example.test",
                user_password="service-password",
            )
        )
