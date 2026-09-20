# ruff: noqa: E501
"""补齐跨空间复合外键，阻止不同客户空间的数据发生关联。

Revision ID: 0003_tenant_integrity
Revises: 0002_space_management_menu
"""

from alembic import op

revision = "0003_tenant_integrity"
down_revision = "0002_space_management_menu"
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
        ALTER TABLE datasets ADD CONSTRAINT uq_datasets_tenant_id UNIQUE (tenant_id, id);
        ALTER TABLE ingestion_profiles ADD CONSTRAINT uq_ingestion_profiles_tenant_id UNIQUE (tenant_id, id);
        ALTER TABLE runtime_profiles ADD CONSTRAINT uq_runtime_profiles_tenant_id UNIQUE (tenant_id, id);
        ALTER TABLE index_builds ADD CONSTRAINT uq_index_builds_tenant_id UNIQUE (tenant_id, id);
        ALTER TABLE document_artifacts ADD CONSTRAINT uq_document_artifacts_tenant_id UNIQUE (tenant_id, id);
        ALTER TABLE chunks ADD CONSTRAINT uq_chunks_tenant_id UNIQUE (tenant_id, id);
        ALTER TABLE kb_releases ADD CONSTRAINT uq_kb_releases_tenant_id UNIQUE (tenant_id, id);
        ALTER TABLE conversations ADD CONSTRAINT uq_conversations_tenant_id UNIQUE (tenant_id, id);
        ALTER TABLE messages ADD CONSTRAINT uq_messages_tenant_id UNIQUE (tenant_id, id);
        ALTER TABLE retrieval_traces ADD CONSTRAINT uq_retrieval_traces_tenant_id UNIQUE (tenant_id, id);

        ALTER TABLE datasets ADD CONSTRAINT datasets_tenant_kb_fk
          FOREIGN KEY (tenant_id, knowledge_base_id) REFERENCES knowledge_bases(tenant_id, id);
        ALTER TABLE documents ADD CONSTRAINT documents_tenant_kb_fk
          FOREIGN KEY (tenant_id, knowledge_base_id) REFERENCES knowledge_bases(tenant_id, id);
        ALTER TABLE documents ADD CONSTRAINT documents_tenant_dataset_fk
          FOREIGN KEY (tenant_id, dataset_id) REFERENCES datasets(tenant_id, id);
        ALTER TABLE documents ADD CONSTRAINT documents_tenant_desired_version_fk
          FOREIGN KEY (tenant_id, desired_version_id) REFERENCES document_versions(tenant_id, id);
        ALTER TABLE document_versions ADD CONSTRAINT document_versions_tenant_document_fk
          FOREIGN KEY (tenant_id, document_id) REFERENCES documents(tenant_id, id);
        ALTER TABLE ingestion_profiles ADD CONSTRAINT ingestion_profiles_tenant_kb_fk
          FOREIGN KEY (tenant_id, knowledge_base_id) REFERENCES knowledge_bases(tenant_id, id);
        ALTER TABLE runtime_profiles ADD CONSTRAINT runtime_profiles_tenant_kb_fk
          FOREIGN KEY (tenant_id, knowledge_base_id) REFERENCES knowledge_bases(tenant_id, id);
        ALTER TABLE index_builds ADD CONSTRAINT index_builds_tenant_kb_fk
          FOREIGN KEY (tenant_id, knowledge_base_id) REFERENCES knowledge_bases(tenant_id, id);
        ALTER TABLE index_builds ADD CONSTRAINT index_builds_tenant_ingestion_fk
          FOREIGN KEY (tenant_id, ingestion_profile_id) REFERENCES ingestion_profiles(tenant_id, id);
        ALTER TABLE document_artifacts ADD CONSTRAINT document_artifacts_tenant_kb_fk
          FOREIGN KEY (tenant_id, knowledge_base_id) REFERENCES knowledge_bases(tenant_id, id);
        ALTER TABLE document_artifacts ADD CONSTRAINT document_artifacts_tenant_version_fk
          FOREIGN KEY (tenant_id, document_version_id) REFERENCES document_versions(tenant_id, id);
        ALTER TABLE document_artifacts ADD CONSTRAINT document_artifacts_tenant_ingestion_fk
          FOREIGN KEY (tenant_id, ingestion_profile_id) REFERENCES ingestion_profiles(tenant_id, id);
        ALTER TABLE chunks ADD CONSTRAINT chunks_tenant_kb_fk
          FOREIGN KEY (tenant_id, knowledge_base_id) REFERENCES knowledge_bases(tenant_id, id);
        ALTER TABLE chunks ADD CONSTRAINT chunks_tenant_artifact_fk
          FOREIGN KEY (tenant_id, artifact_id) REFERENCES document_artifacts(tenant_id, id);
        ALTER TABLE chunk_embeddings ADD CONSTRAINT chunk_embeddings_tenant_kb_fk
          FOREIGN KEY (tenant_id, knowledge_base_id) REFERENCES knowledge_bases(tenant_id, id);
        ALTER TABLE chunk_embeddings ADD CONSTRAINT chunk_embeddings_tenant_chunk_fk
          FOREIGN KEY (tenant_id, chunk_id) REFERENCES chunks(tenant_id, id);
        ALTER TABLE kb_releases ADD CONSTRAINT kb_releases_tenant_kb_fk
          FOREIGN KEY (tenant_id, knowledge_base_id) REFERENCES knowledge_bases(tenant_id, id);
        ALTER TABLE kb_releases ADD CONSTRAINT kb_releases_tenant_build_fk
          FOREIGN KEY (tenant_id, build_id) REFERENCES index_builds(tenant_id, id);
        ALTER TABLE knowledge_bases ADD CONSTRAINT knowledge_bases_tenant_active_release_fk
          FOREIGN KEY (tenant_id, active_release_id) REFERENCES kb_releases(tenant_id, id);
        ALTER TABLE knowledge_bases ADD CONSTRAINT knowledge_bases_tenant_active_runtime_fk
          FOREIGN KEY (tenant_id, active_runtime_id) REFERENCES runtime_profiles(tenant_id, id);
        ALTER TABLE index_builds ADD CONSTRAINT index_builds_tenant_base_release_fk
          FOREIGN KEY (tenant_id, base_release_id) REFERENCES kb_releases(tenant_id, id);
        ALTER TABLE release_items ADD CONSTRAINT release_items_tenant_release_fk
          FOREIGN KEY (tenant_id, release_id) REFERENCES kb_releases(tenant_id, id);
        ALTER TABLE release_items ADD CONSTRAINT release_items_tenant_kb_fk
          FOREIGN KEY (tenant_id, knowledge_base_id) REFERENCES knowledge_bases(tenant_id, id);
        ALTER TABLE release_items ADD CONSTRAINT release_items_tenant_document_fk
          FOREIGN KEY (tenant_id, document_id) REFERENCES documents(tenant_id, id);
        ALTER TABLE release_items ADD CONSTRAINT release_items_tenant_version_fk
          FOREIGN KEY (tenant_id, document_version_id) REFERENCES document_versions(tenant_id, id);
        ALTER TABLE release_items ADD CONSTRAINT release_items_tenant_artifact_fk
          FOREIGN KEY (tenant_id, artifact_id) REFERENCES document_artifacts(tenant_id, id);
        ALTER TABLE tasks ADD CONSTRAINT tasks_tenant_kb_fk
          FOREIGN KEY (tenant_id, knowledge_base_id) REFERENCES knowledge_bases(tenant_id, id);
        ALTER TABLE conversations ADD CONSTRAINT conversations_tenant_kb_fk
          FOREIGN KEY (tenant_id, knowledge_base_id) REFERENCES knowledge_bases(tenant_id, id);
        ALTER TABLE messages ADD CONSTRAINT messages_tenant_conversation_fk
          FOREIGN KEY (tenant_id, conversation_id) REFERENCES conversations(tenant_id, id);
        ALTER TABLE messages ADD CONSTRAINT messages_tenant_release_fk
          FOREIGN KEY (tenant_id, release_id) REFERENCES kb_releases(tenant_id, id);
        ALTER TABLE messages ADD CONSTRAINT messages_tenant_runtime_fk
          FOREIGN KEY (tenant_id, runtime_id) REFERENCES runtime_profiles(tenant_id, id);
        ALTER TABLE retrieval_traces ADD CONSTRAINT retrieval_traces_tenant_kb_fk
          FOREIGN KEY (tenant_id, knowledge_base_id) REFERENCES knowledge_bases(tenant_id, id);
        ALTER TABLE retrieval_traces ADD CONSTRAINT retrieval_traces_tenant_message_fk
          FOREIGN KEY (tenant_id, message_id) REFERENCES messages(tenant_id, id);
        ALTER TABLE retrieval_trace_items ADD CONSTRAINT retrieval_trace_items_tenant_trace_fk
          FOREIGN KEY (tenant_id, trace_id) REFERENCES retrieval_traces(tenant_id, id);
        ALTER TABLE retrieval_trace_items ADD CONSTRAINT retrieval_trace_items_tenant_chunk_fk
          FOREIGN KEY (tenant_id, chunk_id) REFERENCES chunks(tenant_id, id);
        ALTER TABLE feedback ADD CONSTRAINT feedback_tenant_message_fk
          FOREIGN KEY (tenant_id, message_id) REFERENCES messages(tenant_id, id);

        COMMENT ON CONSTRAINT datasets_tenant_kb_fk ON datasets IS '保证数据集与知识库属于同一客户空间';
        COMMENT ON CONSTRAINT documents_tenant_kb_fk ON documents IS '保证文档与知识库属于同一客户空间';
        COMMENT ON CONSTRAINT documents_tenant_dataset_fk ON documents IS '保证文档与数据集属于同一客户空间';
        COMMENT ON CONSTRAINT document_versions_tenant_document_fk ON document_versions IS '保证文档版本与文档属于同一客户空间';
        COMMENT ON CONSTRAINT document_artifacts_tenant_version_fk ON document_artifacts IS '保证处理产物与文档版本属于同一客户空间';
        COMMENT ON CONSTRAINT chunks_tenant_artifact_fk ON chunks IS '保证切片与处理产物属于同一客户空间';
        COMMENT ON CONSTRAINT tasks_tenant_kb_fk ON tasks IS '保证后台任务与知识库属于同一客户空间';
        COMMENT ON CONSTRAINT conversations_tenant_kb_fk ON conversations IS '保证问答会话与知识库属于同一客户空间';
        COMMENT ON CONSTRAINT messages_tenant_conversation_fk ON messages IS '保证消息与会话属于同一客户空间';
        COMMENT ON CONSTRAINT feedback_tenant_message_fk ON feedback IS '保证反馈与消息属于同一客户空间';
        """
    )


def downgrade() -> None:
    _execute_all(
        """
        ALTER TABLE feedback DROP CONSTRAINT feedback_tenant_message_fk;
        ALTER TABLE retrieval_trace_items DROP CONSTRAINT retrieval_trace_items_tenant_chunk_fk;
        ALTER TABLE retrieval_trace_items DROP CONSTRAINT retrieval_trace_items_tenant_trace_fk;
        ALTER TABLE retrieval_traces DROP CONSTRAINT retrieval_traces_tenant_message_fk;
        ALTER TABLE retrieval_traces DROP CONSTRAINT retrieval_traces_tenant_kb_fk;
        ALTER TABLE messages DROP CONSTRAINT messages_tenant_runtime_fk;
        ALTER TABLE messages DROP CONSTRAINT messages_tenant_release_fk;
        ALTER TABLE messages DROP CONSTRAINT messages_tenant_conversation_fk;
        ALTER TABLE conversations DROP CONSTRAINT conversations_tenant_kb_fk;
        ALTER TABLE tasks DROP CONSTRAINT tasks_tenant_kb_fk;
        ALTER TABLE release_items DROP CONSTRAINT release_items_tenant_artifact_fk;
        ALTER TABLE release_items DROP CONSTRAINT release_items_tenant_version_fk;
        ALTER TABLE release_items DROP CONSTRAINT release_items_tenant_document_fk;
        ALTER TABLE release_items DROP CONSTRAINT release_items_tenant_kb_fk;
        ALTER TABLE release_items DROP CONSTRAINT release_items_tenant_release_fk;
        ALTER TABLE index_builds DROP CONSTRAINT index_builds_tenant_base_release_fk;
        ALTER TABLE knowledge_bases DROP CONSTRAINT knowledge_bases_tenant_active_runtime_fk;
        ALTER TABLE knowledge_bases DROP CONSTRAINT knowledge_bases_tenant_active_release_fk;
        ALTER TABLE kb_releases DROP CONSTRAINT kb_releases_tenant_build_fk;
        ALTER TABLE kb_releases DROP CONSTRAINT kb_releases_tenant_kb_fk;
        ALTER TABLE chunk_embeddings DROP CONSTRAINT chunk_embeddings_tenant_chunk_fk;
        ALTER TABLE chunk_embeddings DROP CONSTRAINT chunk_embeddings_tenant_kb_fk;
        ALTER TABLE chunks DROP CONSTRAINT chunks_tenant_artifact_fk;
        ALTER TABLE chunks DROP CONSTRAINT chunks_tenant_kb_fk;
        ALTER TABLE document_artifacts DROP CONSTRAINT document_artifacts_tenant_ingestion_fk;
        ALTER TABLE document_artifacts DROP CONSTRAINT document_artifacts_tenant_version_fk;
        ALTER TABLE document_artifacts DROP CONSTRAINT document_artifacts_tenant_kb_fk;
        ALTER TABLE index_builds DROP CONSTRAINT index_builds_tenant_ingestion_fk;
        ALTER TABLE index_builds DROP CONSTRAINT index_builds_tenant_kb_fk;
        ALTER TABLE runtime_profiles DROP CONSTRAINT runtime_profiles_tenant_kb_fk;
        ALTER TABLE ingestion_profiles DROP CONSTRAINT ingestion_profiles_tenant_kb_fk;
        ALTER TABLE document_versions DROP CONSTRAINT document_versions_tenant_document_fk;
        ALTER TABLE documents DROP CONSTRAINT documents_tenant_desired_version_fk;
        ALTER TABLE documents DROP CONSTRAINT documents_tenant_dataset_fk;
        ALTER TABLE documents DROP CONSTRAINT documents_tenant_kb_fk;
        ALTER TABLE datasets DROP CONSTRAINT datasets_tenant_kb_fk;

        ALTER TABLE retrieval_traces DROP CONSTRAINT uq_retrieval_traces_tenant_id;
        ALTER TABLE messages DROP CONSTRAINT uq_messages_tenant_id;
        ALTER TABLE conversations DROP CONSTRAINT uq_conversations_tenant_id;
        ALTER TABLE kb_releases DROP CONSTRAINT uq_kb_releases_tenant_id;
        ALTER TABLE chunks DROP CONSTRAINT uq_chunks_tenant_id;
        ALTER TABLE document_artifacts DROP CONSTRAINT uq_document_artifacts_tenant_id;
        ALTER TABLE index_builds DROP CONSTRAINT uq_index_builds_tenant_id;
        ALTER TABLE runtime_profiles DROP CONSTRAINT uq_runtime_profiles_tenant_id;
        ALTER TABLE ingestion_profiles DROP CONSTRAINT uq_ingestion_profiles_tenant_id;
        ALTER TABLE datasets DROP CONSTRAINT uq_datasets_tenant_id;
        """
    )
