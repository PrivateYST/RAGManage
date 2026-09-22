"""支持 API Key 的可恢复停用和管理员软删除生命周期。"""

from alembic import op

revision = "0014_api_key_lifecycle"
down_revision = "0013_api_key_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """允许 disabled 状态，并为已升级环境补齐软删除列。"""
    op.execute("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ")
    op.execute(
        """COMMENT ON COLUMN api_keys.deleted_at IS
        '管理员删除时间；软删除保留用量、审计和外键历史，且立即禁止鉴权'"""
    )
    op.execute(
        """ALTER TABLE api_keys DROP CONSTRAINT IF EXISTS api_keys_status_check"""
    )
    op.execute(
        """ALTER TABLE api_keys ADD CONSTRAINT api_keys_status_check
        CHECK (status IN ('active', 'disabled', 'revoked', 'expired'))"""
    )


def downgrade() -> None:
    """回滚前把停用状态归入可兼容的 revoked 状态并移除软删除列。"""
    op.execute("UPDATE api_keys SET status = 'revoked' WHERE status = 'disabled'")
    op.execute(
        """ALTER TABLE api_keys DROP CONSTRAINT IF EXISTS api_keys_status_check"""
    )
    op.execute(
        """ALTER TABLE api_keys ADD CONSTRAINT api_keys_status_check
        CHECK (status IN ('active', 'revoked', 'expired'))"""
    )
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS deleted_at")
