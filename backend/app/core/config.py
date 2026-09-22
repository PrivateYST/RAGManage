import hashlib
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    database_url: str = ""
    redis_url: str = "redis://127.0.0.1:16379/0"
    storage_root: Path = PROJECT_ROOT / "data/files"
    # 业务 API 和 Worker 只访问带 API Key 的 Open WebUI 模型网关。
    model_gateway_base_url: str = "http://172.2.2.230:8080"
    model_gateway_api_key: SecretStr = SecretStr("")
    # Open WebUI 管理员凭据仅用于自动创建医院服务账号；不作为医院调用凭据下发。
    open_webui_admin_email: str = ""
    open_webui_admin_password: SecretStr = SecretStr("")
    open_webui_service_email_domain: str = "service.ragmanage.local"
    open_webui_provisioning_enabled: bool = False
    # 用于加密保存公司 API Key；生产环境应显式配置，空值时由数据库连接和管理员密码派生。
    api_key_encryption_secret: SecretStr = SecretStr("")
    model_gateway_allowed_models: str = "qwen3-embedding:0.6b,qwen3.8:27b"
    generation_model: str = "qwen3.8:27b"
    # API Key 额度预扣的最大生成预算；真实结算仍以网关 usage 为准。
    generation_max_tokens: int = 1024
    embedding_model: str = "qwen3-embedding:0.6b"
    embedding_dimensions: int = 1024
    bootstrap_admin_login: str = "admin"
    bootstrap_admin_display_name: str = "平台管理员"
    bootstrap_admin_password: str = ""
    session_ttl_hours: int = 12
    cookie_secure: bool = False
    # 避免同一个 Settings 实例在每次模型请求中重复读取平台密钥。
    model_gateway_key_refresh_attempted: bool = False

    @property
    def allowed_model_names(self) -> frozenset[str]:
        """返回模型网关允许代理的模型白名单。"""
        return frozenset(
            name.strip() for name in self.model_gateway_allowed_models.split(",") if name.strip()
        )

    @property
    def api_key_encryption_secret_value(self) -> str:
        """返回跨重启稳定的 API Key 加密材料，避免复制功能依赖进程内存。"""
        configured = self.api_key_encryption_secret.get_secret_value().strip()
        if configured:
            return configured
        return hashlib.sha256(
            f"RAGManage/api-key/{self.database_url}/{self.bootstrap_admin_password}".encode()
        ).hexdigest()
