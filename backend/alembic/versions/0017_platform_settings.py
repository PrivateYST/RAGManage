"""保存超级管理员在系统内替换的全局模型网关配置。"""

from alembic import op

revision = "0017_platform_settings"
down_revision = "0016_open_webui_tenant_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建加密平台设置表；明文模型 Key 永远不进入数据库。"""
    op.execute(
        """
        CREATE TABLE platform_settings (
            setting_key VARCHAR(80) PRIMARY KEY,
            encrypted_value TEXT NOT NULL,
            updated_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("COMMENT ON TABLE platform_settings IS '平台级敏感运行配置，仅保存服务端加密密文'")


def downgrade() -> None:
    """移除平台级运行配置表。"""
    op.execute("DROP TABLE platform_settings")
