"""把请求幂等范围收紧到单个 API Key，阻止跨会话复用绕过计费。

用量表允许不同 Key 使用相同客户端 UUID，但同一 Key 只能结算一次；运行表使用
相同约束，让模型执行和用量流水共享同一个幂等边界。
"""

from alembic import op

revision = "0011_api_key_request_scope"
down_revision = "0010_api_keys_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """替换全局流水唯一约束，并增加 Key 级运行唯一索引。"""
    op.execute("ALTER TABLE api_key_usage DROP CONSTRAINT api_key_usage_request_id_key")
    op.execute(
        """
        ALTER TABLE api_key_usage
          ADD CONSTRAINT api_key_usage_key_request_unique UNIQUE (api_key_id, request_id)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX generation_runs_api_key_request_unique
          ON generation_runs(api_key_id, request_id) WHERE api_key_id IS NOT NULL
        """
    )


def downgrade() -> None:
    """无跨 Key 重复 UUID 时恢复早期全局唯一规则，否则明确拒绝有损回滚。"""
    op.execute("DROP INDEX generation_runs_api_key_request_unique")
    op.execute(
        "ALTER TABLE api_key_usage DROP CONSTRAINT api_key_usage_key_request_unique"
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT request_id FROM api_key_usage GROUP BY request_id HAVING count(*) > 1
          ) THEN
            RAISE EXCEPTION 'cannot restore global request_id uniqueness with duplicates';
          END IF;
        END
        $$
        """
    )
    op.execute(
        "ALTER TABLE api_key_usage ADD CONSTRAINT api_key_usage_request_id_key UNIQUE (request_id)"
    )
