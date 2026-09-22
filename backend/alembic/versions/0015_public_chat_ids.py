"""为问答会话和运行增加对外 opaque ID，避免暴露数据库自增主键。"""

from alembic import op

revision = "0015_public_chat_ids"
down_revision = "0014_api_key_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """为历史数据生成稳定 UUID，并为新问答资源建立唯一索引。"""
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS public_id UUID NOT NULL "
        "DEFAULT gen_random_uuid()"
    )
    op.execute(
        "ALTER TABLE generation_runs ADD COLUMN IF NOT EXISTS public_id UUID NOT NULL "
        "DEFAULT gen_random_uuid()"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS conversations_public_id_idx ON conversations(public_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS generation_runs_public_id_idx "
        "ON generation_runs(public_id)"
    )


def downgrade() -> None:
    """回滚对外标识列及其索引；不影响内部 bigint 主键。"""
    op.execute("DROP INDEX IF EXISTS generation_runs_public_id_idx")
    op.execute("DROP INDEX IF EXISTS conversations_public_id_idx")
    op.execute("ALTER TABLE generation_runs DROP COLUMN IF EXISTS public_id")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS public_id")
