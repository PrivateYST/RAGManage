"""为公司下发的 API Key 增加额度控制和 Token 用量流水。

API Key 只允许平台管理员创建；数据库保存随机 Key 的哈希而不是明文。
额度通过 ``token_reserved`` 预扣，避免并发请求在结算前重复消费同一份余额。
"""

from alembic import op

revision = "0010_api_keys_usage"
down_revision = "0009_model_profiles"
branch_labels = None
depends_on = None


def _execute_all(sql: str) -> None:
    """逐条执行 DDL，兼容 asyncpg prepared statement。"""
    for statement in sql.split(";"):
        if statement.strip():
            op.execute(statement)


def upgrade() -> None:
    """创建公司 API Key、额度和输入/输出 Token 用量表。"""
    _execute_all(
        """
        CREATE TABLE api_keys (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            name VARCHAR(120) NOT NULL,
            key_prefix VARCHAR(32) NOT NULL,
            key_hash CHAR(64) NOT NULL UNIQUE,
            token_limit BIGINT NOT NULL CHECK (token_limit > 0),
            token_used BIGINT NOT NULL DEFAULT 0 CHECK (token_used >= 0),
            token_reserved BIGINT NOT NULL DEFAULT 0 CHECK (token_reserved >= 0),
            status VARCHAR(24) NOT NULL DEFAULT 'active'
              CHECK (status IN ('active','revoked','expired')),
            expires_at TIMESTAMPTZ,
            created_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            last_used_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            revoked_at TIMESTAMPTZ
        );
        CREATE INDEX api_keys_tenant_status_idx
          ON api_keys(tenant_id, status, created_at DESC);
        COMMENT ON TABLE api_keys IS '公司下发给客户的 RAGManage API Key，不保存明文';
        COMMENT ON COLUMN api_keys.token_reserved IS '并发模型请求已预扣但尚未结算的 Token';

        ALTER TABLE generation_runs
          ADD COLUMN api_key_id BIGINT REFERENCES api_keys(id) ON DELETE RESTRICT;
        CREATE INDEX generation_runs_api_key_idx
          ON generation_runs(api_key_id, created_at DESC) WHERE api_key_id IS NOT NULL;
        COMMENT ON COLUMN generation_runs.api_key_id
          IS '创建本次运行的公司 API Key，防止跨 Key 记账';

        CREATE TABLE api_key_usage (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            api_key_id BIGINT NOT NULL REFERENCES api_keys(id) ON DELETE RESTRICT,
            tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            request_id UUID NOT NULL UNIQUE,
            model_name VARCHAR(160) NOT NULL,
            prompt_tokens BIGINT NOT NULL DEFAULT 0 CHECK (prompt_tokens >= 0),
            completion_tokens BIGINT NOT NULL DEFAULT 0 CHECK (completion_tokens >= 0),
            total_tokens BIGINT NOT NULL DEFAULT 0 CHECK (total_tokens >= 0),
            reserved_tokens BIGINT NOT NULL DEFAULT 0 CHECK (reserved_tokens >= 0),
            usage_source VARCHAR(24) NOT NULL
              CHECK (usage_source IN ('gateway','estimate','unavailable')),
            model_usage JSONB NOT NULL DEFAULT '{}'::jsonb,
            status VARCHAR(24) NOT NULL
              CHECK (status IN ('completed','failed','cancelled')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX api_key_usage_key_created_idx
          ON api_key_usage(api_key_id, created_at DESC);
        CREATE INDEX api_key_usage_tenant_created_idx
          ON api_key_usage(tenant_id, created_at DESC);
        COMMENT ON TABLE api_key_usage IS '按请求记录输入、输出和总 Token，供额度结算与审计';
        COMMENT ON COLUMN api_key_usage.model_usage IS '单次问答内嵌入与生成模型的分项 Token';
        """
    )


def downgrade() -> None:
    """按依赖顺序移除 API Key 用量表和 API Key 表。"""
    _execute_all(
        """
        DROP TABLE api_key_usage;
        DROP INDEX generation_runs_api_key_idx;
        ALTER TABLE generation_runs DROP COLUMN api_key_id;
        DROP INDEX api_keys_tenant_status_idx;
        DROP TABLE api_keys;
        """
    )
