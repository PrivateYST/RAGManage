# ruff: noqa: E501
"""增加索引构建快照明细和任务关联。

Revision ID: 0005_build_snapshot
Revises: 0004_citation_tenant
"""

from alembic import op

revision = "0005_build_snapshot"
down_revision = "0004_citation_tenant"
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
        ALTER TABLE tasks ADD CONSTRAINT uq_tasks_tenant_id UNIQUE (tenant_id, id);
        ALTER TABLE index_builds ADD COLUMN task_id BIGINT;
        ALTER TABLE index_builds ADD CONSTRAINT uq_index_builds_task UNIQUE (task_id);
        ALTER TABLE index_builds ADD CONSTRAINT index_builds_tenant_task_fk
          FOREIGN KEY (tenant_id, task_id) REFERENCES tasks(tenant_id, id);
        ALTER TABLE index_builds ADD CONSTRAINT uq_index_builds_snapshot
          UNIQUE (knowledge_base_id, input_epoch, ingestion_profile_id, embedding_profile_id);

        CREATE TABLE build_items (
            build_id BIGINT NOT NULL REFERENCES index_builds(id) ON DELETE CASCADE,
            tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            knowledge_base_id BIGINT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE RESTRICT,
            document_version_id BIGINT NOT NULL REFERENCES document_versions(id) ON DELETE RESTRICT,
            artifact_id BIGINT NOT NULL REFERENCES document_artifacts(id) ON DELETE RESTRICT,
            state VARCHAR(24) NOT NULL DEFAULT 'queued'
              CHECK (state IN ('queued','running','completed','failed','cancelled')),
            chunk_count INTEGER NOT NULL DEFAULT 0 CHECK (chunk_count >= 0),
            embedded_count INTEGER NOT NULL DEFAULT 0 CHECK (embedded_count >= 0),
            error JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (build_id, document_id),
            UNIQUE (build_id, document_version_id),
            CONSTRAINT build_items_tenant_build_fk
              FOREIGN KEY (tenant_id, build_id) REFERENCES index_builds(tenant_id, id),
            CONSTRAINT build_items_tenant_kb_fk
              FOREIGN KEY (tenant_id, knowledge_base_id) REFERENCES knowledge_bases(tenant_id, id),
            CONSTRAINT build_items_tenant_document_fk
              FOREIGN KEY (tenant_id, document_id) REFERENCES documents(tenant_id, id),
            CONSTRAINT build_items_tenant_version_fk
              FOREIGN KEY (tenant_id, document_version_id) REFERENCES document_versions(tenant_id, id),
            CONSTRAINT build_items_tenant_artifact_fk
              FOREIGN KEY (tenant_id, artifact_id) REFERENCES document_artifacts(tenant_id, id)
        );
        CREATE INDEX build_items_build_state_idx ON build_items(build_id, state);
        CREATE UNIQUE INDEX uq_global_model_endpoint_identity
          ON model_endpoints(provider, endpoint_type, base_url)
          WHERE tenant_id IS NULL;

        COMMENT ON TABLE build_items IS '索引构建冻结的文档版本与解析产物清单。';
        COMMENT ON COLUMN index_builds.task_id IS '执行该构建的后台任务 ID';
        COMMENT ON COLUMN build_items.build_id IS '所属索引构建';
        COMMENT ON COLUMN build_items.tenant_id IS '所属客户空间';
        COMMENT ON COLUMN build_items.knowledge_base_id IS '所属知识库';
        COMMENT ON COLUMN build_items.document_id IS '构建包含的文档';
        COMMENT ON COLUMN build_items.document_version_id IS '构建冻结的不可变文档版本';
        COMMENT ON COLUMN build_items.artifact_id IS '构建使用的解析切片产物';
        COMMENT ON COLUMN build_items.state IS '处理状态：queued/running/completed/failed/cancelled';
        COMMENT ON COLUMN build_items.chunk_count IS '该文档需要嵌入的切片总数';
        COMMENT ON COLUMN build_items.embedded_count IS '已经成功写入向量的切片数';
        COMMENT ON COLUMN build_items.error IS '失败代码与诊断信息';
        COMMENT ON COLUMN build_items.created_at IS '快照创建时间';
        COMMENT ON COLUMN build_items.updated_at IS '处理状态更新时间';
        COMMENT ON CONSTRAINT index_builds_tenant_task_fk ON index_builds
          IS '保证构建与后台任务属于同一客户空间';
        COMMENT ON CONSTRAINT build_items_tenant_build_fk ON build_items
          IS '保证构建明细与索引构建属于同一客户空间';
        COMMENT ON CONSTRAINT build_items_tenant_kb_fk ON build_items
          IS '保证构建明细与知识库属于同一客户空间';
        COMMENT ON CONSTRAINT build_items_tenant_document_fk ON build_items
          IS '保证构建明细与文档属于同一客户空间';
        COMMENT ON CONSTRAINT build_items_tenant_version_fk ON build_items
          IS '保证构建明细与文档版本属于同一客户空间';
        COMMENT ON CONSTRAINT build_items_tenant_artifact_fk ON build_items
          IS '保证构建明细与解析产物属于同一客户空间';
        """
    )


def downgrade() -> None:
    _execute_all(
        """
        DROP INDEX uq_global_model_endpoint_identity;
        DROP TABLE build_items;
        ALTER TABLE index_builds DROP CONSTRAINT uq_index_builds_snapshot;
        ALTER TABLE index_builds DROP CONSTRAINT index_builds_tenant_task_fk;
        ALTER TABLE index_builds DROP CONSTRAINT uq_index_builds_task;
        ALTER TABLE index_builds DROP COLUMN task_id;
        ALTER TABLE tasks DROP CONSTRAINT uq_tasks_tenant_id;
        """
    )
