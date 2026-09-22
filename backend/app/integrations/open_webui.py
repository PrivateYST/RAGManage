"""Open WebUI 服务账号与原生 API Key 的管理适配器。

该模块只负责和 Open WebUI 的认证及账号管理接口通信，不保存凭据；调用方负责
把返回的服务账号密码和 ``sk-`` Key 加密后写入业务数据库。
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

import httpx

from app.core.config import Settings


class OpenWebUIProvisioningError(RuntimeError):
    """Open WebUI 账号或 API Key 创建失败，调用方应回滚本地事务。"""


@dataclass(frozen=True)
class ProvisionedOpenWebUIKey:
    """一次医院服务账号创建所需持久化的远端身份信息。"""

    user_email: str
    user_password: str
    api_key: str
    user_id: str | None


class OpenWebUIAdminClient:
    """使用平台管理员账号在 Open WebUI 中创建医院级服务账号和原生 Key。"""

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport

    def _base_url(self) -> str:
        return self.settings.model_gateway_base_url.rstrip("/")

    async def provision_service_key(
        self,
        *,
        tenant_id: int,
        tenant_name: str,
        existing_user_email: str | None = None,
        existing_user_password: str | None = None,
    ) -> ProvisionedOpenWebUIKey:
        """创建或复用医院服务账号，再调用用户级 Key 接口生成 ``sk-`` Key。"""
        email = existing_user_email or self._service_email(tenant_id)
        password = existing_user_password or secrets.token_urlsafe(32)
        async with httpx.AsyncClient(timeout=30, transport=self.transport) as client:
            user_id = None
            if existing_user_email is None or existing_user_password is None:
                user_id = await self._create_user(client, email, password, tenant_name)
            user_token = await self._signin(client, email, password)
            response = await client.post(
                f"{self._base_url()}/api/v1/auths/api_key",
                headers={"Authorization": f"Bearer {user_token}"},
            )
            if response.status_code >= 400:
                raise OpenWebUIProvisioningError(
                    f"OPEN_WEBUI_API_KEY_CREATE_FAILED:{response.status_code}"
                )
            payload = response.json()
            api_key = payload.get("api_key") if isinstance(payload, dict) else None
            if not isinstance(api_key, str) or not api_key:
                raise OpenWebUIProvisioningError("OPEN_WEBUI_API_KEY_RESPONSE_INVALID")
            return ProvisionedOpenWebUIKey(email, password, api_key, user_id)

    async def revoke_service_key(self, *, user_email: str, user_password: str) -> None:
        """通过医院服务账号删除当前 Key；删除失败会向上抛出，避免误报已撤销。"""
        async with httpx.AsyncClient(timeout=30, transport=self.transport) as client:
            token = await self._signin(client, user_email, user_password)
            response = await client.delete(
                f"{self._base_url()}/api/v1/auths/api_key",
                headers={"Authorization": f"Bearer {token}"},
            )
            if response.status_code >= 400:
                raise OpenWebUIProvisioningError(
                    f"OPEN_WEBUI_API_KEY_DELETE_FAILED:{response.status_code}"
                )

    async def _signin(self, client: httpx.AsyncClient, email: str, password: str) -> str:
        response = await client.post(
            f"{self._base_url()}/api/v1/auths/signin",
            json={"email": email, "password": password},
        )
        if response.status_code >= 400:
            raise OpenWebUIProvisioningError(f"OPEN_WEBUI_SIGNIN_FAILED:{response.status_code}")
        payload = response.json()
        token = payload.get("token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise OpenWebUIProvisioningError("OPEN_WEBUI_SIGNIN_RESPONSE_INVALID")
        return token

    async def _create_user(
        self,
        client: httpx.AsyncClient,
        email: str,
        password: str,
        tenant_name: str,
    ) -> str | None:
        """用当前全局 Open WebUI 管理 Key 创建医院服务账号。"""
        response = await client.post(
            f"{self._base_url()}/api/v1/auths/add",
            headers=self._admin_headers(),
            json={"email": email, "password": password, "name": tenant_name, "role": "user"},
        )
        if response.status_code >= 400:
            raise OpenWebUIProvisioningError(
                f"OPEN_WEBUI_SERVICE_USER_CREATE_FAILED:{response.status_code}"
            )
        payload = response.json()
        if isinstance(payload, dict):
            for key in ("id", "user_id"):
                value = payload.get(key)
                if value is not None:
                    return str(value)
        return None

    def _admin_headers(self) -> dict[str, str]:
        """返回页面中配置的全局 Key；该 Key 不能作为医院服务账号下发。"""
        api_key = self.settings.model_gateway_api_key.get_secret_value().strip()
        if not api_key:
            raise OpenWebUIProvisioningError("MODEL_GATEWAY_API_KEY_NOT_CONFIGURED")
        return {"Authorization": f"Bearer {api_key}"}

    def _service_email(self, tenant_id: int) -> str:
        """用租户 ID 生成稳定邮箱，避免医院名称中的特殊字符破坏 Open WebUI 校验。"""
        domain = self.settings.open_webui_service_email_domain.strip().lstrip("@").lower()
        return f"ragmanage-tenant-{tenant_id}@{domain}"
