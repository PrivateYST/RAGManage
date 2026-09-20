# ruff: noqa: E501
"""增加可查询、取消和重试的问答运行实体。

Revision ID: 0007_generation_runs
Revises: 0006_release_publish_integrity
"""

from alembic import op

revision = "0007_generation_runs"
down_revision = "0006_release_publish_integrity"
branch_labels = None
depends_on = None


def _execute_all(sql: str) -> None:
    """逐条执行 DDL，兼容 asyncpg prepared statement。"""
    for statement in sql.split(";"):
        if statement.strip():
            op.execute(statement)


def upgrade() -> None:
    _execute_all(
        """
        CREATE TABLE generation_runs (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            knowledge_base_id BIGINT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            conversation_id BIGINT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            user_message_id BIGINT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
            assistant_message_id BIGINT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
            release_id BIGINT REFERENCES kb_releases(id) ON DELETE RESTRICT,
            request_id UUID NOT NULL,
            state VARCHAR(24) NOT NULL DEFAULT 'queued'
              CHECK (state IN ('queued','running','completed','failed','cancelled')),
            outcome VARCHAR(24)
              CHECK (outcome IS NULL OR outcome IN ('answered','no_answer','source_conflict','index_not_ready')),
            cancel_requested BOOLEAN NOT NULL DEFAULT false,
            error JSONB,
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, id),
            UNIQUE (conversation_id, request_id),
            UNIQUE (assistant_message_id),
            CONSTRAINT generation_runs_tenant_kb_fk
              FOREIGN KEY (tenant_id, knowledge_base_id) REFERENCES knowledge_bases(tenant_id, id),
            CONSTRAINT generation_runs_tenant_conversation_fk
              FOREIGN KEY (tenant_id, conversation_id) REFERENCES conversations(tenant_id, id),
            CONSTRAINT generation_runs_tenant_user_message_fk
              FOREIGN KEY (tenant_id, user_message_id) REFERENCES messages(tenant_id, id),
            CONSTRAINT generation_runs_tenant_assistant_message_fk
              FOREIGN KEY (tenant_id, assistant_message_id) REFERENCES messages(tenant_id, id),
            CONSTRAINT generation_runs_tenant_release_fk
              FOREIGN KEY (tenant_id, release_id) REFERENCES kb_releases(tenant_id, id)
        );
        CREATE INDEX generation_runs_conversation_idx
          ON generation_runs(tenant_id, conversation_id, created_at DESC);
        CREATE INDEX generation_runs_active_idx
          ON generation_runs(tenant_id, state, updated_at)
          WHERE state IN ('queued','running');

        COMMENT ON TABLE generation_runs IS '一次可查询、取消和重试的知识问答生成运行';
        COMMENT ON COLUMN generation_runs.id IS '问答运行主键';
        COMMENT ON COLUMN generation_runs.tenant_id IS '所属客户空间';
        COMMENT ON COLUMN generation_runs.knowledge_base_id IS '检索和回答使用的知识库';
        COMMENT ON COLUMN generation_runs.conversation_id IS '所属问答会话';
        COMMENT ON COLUMN generation_runs.user_message_id IS '触发本次运行的用户消息';
        COMMENT ON COLUMN generation_runs.assistant_message_id IS '本次运行写入的助手消息';
        COMMENT ON COLUMN generation_runs.release_id IS '本次运行固定使用的不可变发布版本；未发布时为空';
        COMMENT ON COLUMN generation_runs.request_id IS '客户端生成的幂等请求 UUID';
        COMMENT ON COLUMN generation_runs.state IS '运行状态：queued/running/completed/failed/cancelled';
        COMMENT ON COLUMN generation_runs.outcome IS '业务结果：answered/no_answer/source_conflict/index_not_ready';
        COMMENT ON COLUMN generation_runs.cancel_requested IS '用户是否已经请求停止生成';
        COMMENT ON COLUMN generation_runs.error IS '失败代码与可诊断信息';
        COMMENT ON COLUMN generation_runs.started_at IS '开始执行时间';
        COMMENT ON COLUMN generation_runs.completed_at IS '进入最终状态时间';
        COMMENT ON COLUMN generation_runs.created_at IS '创建时间';
        COMMENT ON COLUMN generation_runs.updated_at IS '最近状态更新时间';
        COMMENT ON CONSTRAINT generation_runs_tenant_kb_fk ON generation_runs
          IS '保证问答运行与知识库属于同一客户空间';
        COMMENT ON CONSTRAINT generation_runs_tenant_conversation_fk ON generation_runs
          IS '保证问答运行与会话属于同一客户空间';
        COMMENT ON CONSTRAINT generation_runs_tenant_user_message_fk ON generation_runs
          IS '保证问答运行与用户消息属于同一客户空间';
        COMMENT ON CONSTRAINT generation_runs_tenant_assistant_message_fk ON generation_runs
          IS '保证问答运行与助手消息属于同一客户空间';
        COMMENT ON CONSTRAINT generation_runs_tenant_release_fk ON generation_runs
          IS '保证问答运行与发布版本属于同一客户空间';
        COMMENT ON INDEX generation_runs_conversation_idx IS '按会话倒序查询问答运行';
        COMMENT ON INDEX generation_runs_active_idx IS '查询需要继续处理或取消的运行';
        """
    )


def downgrade() -> None:
    _execute_all(
        """
        DROP INDEX generation_runs_active_idx;
        DROP INDEX generation_runs_conversation_idx;
        DROP TABLE generation_runs;
        """
    )
