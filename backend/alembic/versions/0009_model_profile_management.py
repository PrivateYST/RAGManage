# ruff: noqa: E501
"""补充模型端点生命周期与健康检查结果。

Revision ID: 0009_model_profiles
Revises: 0008_space_member_role
"""

from alembic import op

revision = "0009_model_profiles"
down_revision = "0008_space_member_role"
branch_labels = None
depends_on = None


def _execute_all(sql: str) -> None:
    """逐条执行 DDL，兼容 asyncpg prepared statement。"""
    for statement in sql.split(";"):
        if statement.strip():
            op.execute(statement)


def upgrade() -> None:
    """增加端点停用、最近实测和错误诊断字段。"""
    _execute_all(
        """
        ALTER TABLE model_endpoints
          ADD COLUMN status VARCHAR(24) NOT NULL DEFAULT 'active'
            CHECK (status IN ('active','disabled')),
          ADD COLUMN last_checked_at TIMESTAMPTZ,
          ADD COLUMN last_latency_ms INTEGER CHECK (last_latency_ms IS NULL OR last_latency_ms >= 0),
          ADD COLUMN last_error VARCHAR(500),
          ADD COLUMN observed_dimension INTEGER
            CHECK (observed_dimension IS NULL OR observed_dimension > 0);
        CREATE INDEX model_endpoints_tenant_status_idx
          ON model_endpoints(tenant_id, status, endpoint_type, updated_at DESC);

        COMMENT ON COLUMN model_endpoints.status IS '端点启用状态：active/disabled';
        COMMENT ON COLUMN model_endpoints.last_checked_at IS '最近一次真实模型调用检查时间';
        COMMENT ON COLUMN model_endpoints.last_latency_ms IS '最近一次健康检查总耗时，单位毫秒';
        COMMENT ON COLUMN model_endpoints.last_error IS '最近一次健康检查失败摘要，不包含密钥';
        COMMENT ON COLUMN model_endpoints.observed_dimension IS '嵌入端点最近实测向量维度';
        COMMENT ON INDEX model_endpoints_tenant_status_idx IS '按空间、状态和用途查询模型端点';
        """
    )


def downgrade() -> None:
    """移除模型端点生命周期字段。"""
    _execute_all(
        """
        DROP INDEX model_endpoints_tenant_status_idx;
        ALTER TABLE model_endpoints
          DROP COLUMN observed_dimension,
          DROP COLUMN last_error,
          DROP COLUMN last_latency_ms,
          DROP COLUMN last_checked_at,
          DROP COLUMN status;
        """
    )
