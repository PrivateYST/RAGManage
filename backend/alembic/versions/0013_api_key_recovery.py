"""为公司 API Key 增加可控复制所需的加密密文。"""

from alembic import op

revision = "0013_api_key_recovery"
down_revision = "0012_api_key_reservations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """保存 Fernet 密文；既有只保存哈希的 Key 保持可鉴权但不能回显明文。"""
    op.execute("ALTER TABLE api_keys ADD COLUMN encrypted_key TEXT")
    op.execute(
        """COMMENT ON COLUMN api_keys.encrypted_key IS
        '服务端加密的 API Key 明文，仅平台管理员复制接口临时解密；旧 Key 可为空'"""
    )


def downgrade() -> None:
    """移除可复制密文，恢复为仅哈希存储。"""
    op.execute("ALTER TABLE api_keys DROP COLUMN encrypted_key")
