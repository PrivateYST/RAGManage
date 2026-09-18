from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    database_url: str = ""
    redis_url: str = "redis://127.0.0.1:16379/0"
    storage_root: Path = PROJECT_ROOT / "data/files"
    ollama_base_url: str = "http://192.168.2.59:11434"
    generation_model: str = "qwen3.8:27b"
    embedding_model: str = "qwen3-embedding:0.6b"
    embedding_dimensions: int = 1024
    bootstrap_admin_login: str = "admin"
    bootstrap_admin_display_name: str = "平台管理员"
    bootstrap_admin_password: str = ""
    session_ttl_hours: int = 12
    cookie_secure: bool = False
