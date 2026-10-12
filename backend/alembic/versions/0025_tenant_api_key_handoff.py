"""记录医院管理员确认接收系统分配 API Key 的时间和账号。"""

from alembic import op

revision = "0025_tenant_api_key_handoff"
down_revision = "0024_environment_check_menu"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """只保存交接元数据，不重复保存医院 API Key 明文。"""
    op.execute("ALTER TABLE api_keys ADD COLUMN configured_at TIMESTAMPTZ")
    op.execute(
        "ALTER TABLE api_keys ADD COLUMN configured_by BIGINT "
        "REFERENCES users(id) ON DELETE SET NULL"
    )
    op.execute(
        "COMMENT ON COLUMN api_keys.configured_at IS "
        "'医院管理员确认粘贴系统分配 Key 的时间；NULL 表示尚未确认'"
    )
    op.execute(
        "COMMENT ON COLUMN api_keys.configured_by IS "
        "'确认 Key 交接的医院管理员；不保存提交的 Key 明文'"
    )


def downgrade() -> None:
    """移除交接状态字段，不影响 API Key、额度和既有审计流水。"""
    op.execute("ALTER TABLE api_keys DROP COLUMN configured_by")
    op.execute("ALTER TABLE api_keys DROP COLUMN configured_at")
