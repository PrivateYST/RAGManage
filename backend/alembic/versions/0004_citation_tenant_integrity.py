# ruff: noqa: E501
"""为回答引用和证据补充空间字段与复合外键。

Revision ID: 0004_citation_tenant
Revises: 0003_tenant_integrity
"""

from alembic import op

revision = "0004_citation_tenant"
down_revision = "0003_tenant_integrity"
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
        ALTER TABLE message_citations ADD COLUMN tenant_id BIGINT;
        UPDATE message_citations citation SET tenant_id = message.tenant_id
          FROM messages message WHERE message.id = citation.message_id;
        ALTER TABLE message_citations ALTER COLUMN tenant_id SET NOT NULL;
        ALTER TABLE message_citations ADD CONSTRAINT message_citations_tenant_fk
          FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
        ALTER TABLE message_citations ADD CONSTRAINT message_citations_tenant_message_fk
          FOREIGN KEY (tenant_id, message_id) REFERENCES messages(tenant_id, id);
        ALTER TABLE message_citations ADD CONSTRAINT message_citations_tenant_chunk_fk
          FOREIGN KEY (tenant_id, chunk_id) REFERENCES chunks(tenant_id, id);
        ALTER TABLE message_citations ADD CONSTRAINT message_citations_tenant_version_fk
          FOREIGN KEY (tenant_id, document_version_id) REFERENCES document_versions(tenant_id, id);
        COMMENT ON COLUMN message_citations.tenant_id IS '所属客户空间';
        COMMENT ON CONSTRAINT message_citations_tenant_message_fk ON message_citations
          IS '保证回答引用与消息属于同一客户空间';

        ALTER TABLE message_evidence ADD COLUMN tenant_id BIGINT;
        UPDATE message_evidence evidence SET tenant_id = message.tenant_id
          FROM messages message WHERE message.id = evidence.message_id;
        ALTER TABLE message_evidence ALTER COLUMN tenant_id SET NOT NULL;
        ALTER TABLE message_evidence ADD CONSTRAINT message_evidence_tenant_fk
          FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
        ALTER TABLE message_evidence ADD CONSTRAINT message_evidence_tenant_message_fk
          FOREIGN KEY (tenant_id, message_id) REFERENCES messages(tenant_id, id);
        ALTER TABLE message_evidence ADD CONSTRAINT message_evidence_tenant_document_fk
          FOREIGN KEY (tenant_id, document_id) REFERENCES documents(tenant_id, id);
        ALTER TABLE message_evidence ADD CONSTRAINT message_evidence_tenant_version_fk
          FOREIGN KEY (tenant_id, document_version_id) REFERENCES document_versions(tenant_id, id);
        COMMENT ON COLUMN message_evidence.tenant_id IS '所属客户空间';
        COMMENT ON CONSTRAINT message_evidence_tenant_message_fk ON message_evidence
          IS '保证回答证据与消息属于同一客户空间';
        """
    )


def downgrade() -> None:
    _execute_all(
        """
        ALTER TABLE message_evidence DROP CONSTRAINT message_evidence_tenant_version_fk;
        ALTER TABLE message_evidence DROP CONSTRAINT message_evidence_tenant_document_fk;
        ALTER TABLE message_evidence DROP CONSTRAINT message_evidence_tenant_message_fk;
        ALTER TABLE message_evidence DROP CONSTRAINT message_evidence_tenant_fk;
        ALTER TABLE message_evidence DROP COLUMN tenant_id;
        ALTER TABLE message_citations DROP CONSTRAINT message_citations_tenant_version_fk;
        ALTER TABLE message_citations DROP CONSTRAINT message_citations_tenant_chunk_fk;
        ALTER TABLE message_citations DROP CONSTRAINT message_citations_tenant_message_fk;
        ALTER TABLE message_citations DROP CONSTRAINT message_citations_tenant_fk;
        ALTER TABLE message_citations DROP COLUMN tenant_id;
        """
    )
