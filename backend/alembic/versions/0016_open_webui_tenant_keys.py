"""把客户 API Key 标记为 Open WebUI 医院服务账号，并保存可轮换的远端身份。"""

from alembic import op

revision = "0016_open_webui_tenant_keys"
down_revision = "0015_public_chat_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """增加远端用户标识和加密服务账号密码，确保每个租户只有一把未删除 Key。"""
    op.execute(
        "ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS provider VARCHAR(32) NOT NULL "
        "DEFAULT 'local'"
    )
    op.execute("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS provider_user_id VARCHAR(160)")
    op.execute("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS provider_user_email VARCHAR(320)")
    op.execute("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS provider_user_password TEXT")
    op.execute(
        "COMMENT ON COLUMN api_keys.provider_user_password IS "
        "'加密的 Open WebUI 服务账号密码，不保存明文'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS api_keys_provider_user_idx "
        "ON api_keys(provider, provider_user_id)"
    )
    # Open WebUI 原生 Key 按医院唯一；本地兼容 Key 仍允许旧数据迁移期间并存。
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS api_keys_open_webui_tenant_active_idx
        ON api_keys(tenant_id)
        WHERE deleted_at IS NULL AND provider = 'open_webui'
        """
    )


def downgrade() -> None:
    """移除 Open WebUI 远端身份字段，保留原有本地 Key 表结构。"""
    op.execute("DROP INDEX IF EXISTS api_keys_open_webui_tenant_active_idx")
    op.execute("DROP INDEX IF EXISTS api_keys_provider_user_idx")
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS provider_user_password")
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS provider_user_email")
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS provider_user_id")
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS provider")
