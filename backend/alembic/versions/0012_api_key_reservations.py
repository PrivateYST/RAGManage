"""按问答运行持久化 API Key Token 预留，支持异常退出后的额度回收。

聚合字段 ``api_keys.token_reserved`` 继续提供快速额度判断；本表记录其来源，
让认证流程能够识别已终止或超时运行并恢复额度。
"""

from alembic import op

revision = "0012_api_key_reservations"
down_revision = "0011_api_key_request_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建每个生成运行唯一的持久化预留记录。"""
    op.execute(
        """
        CREATE TABLE api_key_reservations (
            run_id BIGINT PRIMARY KEY REFERENCES generation_runs(id) ON DELETE CASCADE,
            api_key_id BIGINT NOT NULL REFERENCES api_keys(id) ON DELETE CASCADE,
            reserved_tokens BIGINT NOT NULL CHECK (reserved_tokens > 0),
            usage JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX api_key_reservations_key_updated_idx
          ON api_key_reservations(api_key_id, updated_at)
        """
    )
    op.execute(
        """
        COMMENT ON TABLE api_key_reservations
          IS '按生成运行记录尚未结算的 Token 预留，用于异常恢复'
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN api_key_reservations.usage
          IS '运行过程中最近一次可恢复的输入、输出和模型分项用量快照'
        """
    )


def downgrade() -> None:
    """仅在没有未结算预留时移除恢复表，避免静默丢失额度来源。"""
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM api_key_reservations) THEN
            RAISE EXCEPTION 'cannot downgrade with unsettled API key reservations';
          END IF;
        END
        $$
        """
    )
    op.execute("DROP INDEX api_key_reservations_key_updated_idx")
    op.execute("DROP TABLE api_key_reservations")
