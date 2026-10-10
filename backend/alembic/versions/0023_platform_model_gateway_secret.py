"""将模型端点密钥引用迁移为数据库中的平台网关密钥。"""

from alembic import op

revision = "0023_platform_gateway_secret"
down_revision = "0022_auto_scope_assistant_chat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """统一已有端点引用，实际密钥仍由平台设置表加密保存。"""
    op.execute(
        "UPDATE model_endpoints SET secret_ref = 'platform:model_gateway' "
        "WHERE secret_ref = 'env:MODEL_GATEWAY_API_KEY'"
    )


def downgrade() -> None:
    """恢复旧引用格式，供回滚到旧版本代码时继续读取环境变量。"""
    op.execute(
        "UPDATE model_endpoints SET secret_ref = 'env:MODEL_GATEWAY_API_KEY' "
        "WHERE secret_ref = 'platform:model_gateway'"
    )
