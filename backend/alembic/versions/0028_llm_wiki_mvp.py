"""为知识库增加可审核的 LLM Wiki 词条、别名和来源关联。"""

from alembic import op

revision = "0028_llm_wiki_mvp"
down_revision = "0027_kb_governance_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """建立词条生命周期与文档证据关联，供检索扩展和引用展示使用。"""
    script = """
        CREATE TABLE IF NOT EXISTS wiki_entries (
          id BIGSERIAL PRIMARY KEY,
          tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          knowledge_base_id BIGINT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
          term VARCHAR(200) NOT NULL,
          definition TEXT NOT NULL DEFAULT '',
          status VARCHAR(20) NOT NULL DEFAULT 'draft'
            CHECK (status IN ('draft', 'review', 'published', 'retired')),
          version_no INTEGER NOT NULL DEFAULT 1 CHECK (version_no > 0),
          owner_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
          valid_from DATE,
          valid_until DATE,
          created_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (knowledge_base_id, term),
          CHECK (valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from)
        );
        CREATE INDEX IF NOT EXISTS wiki_entries_kb_status_idx
          ON wiki_entries(knowledge_base_id, status, updated_at DESC);
        CREATE TABLE IF NOT EXISTS wiki_aliases (
          id BIGSERIAL PRIMARY KEY,
          entry_id BIGINT NOT NULL REFERENCES wiki_entries(id) ON DELETE CASCADE,
          alias VARCHAR(200) NOT NULL,
          UNIQUE (entry_id, alias)
        );
        CREATE INDEX IF NOT EXISTS wiki_aliases_alias_idx ON wiki_aliases(lower(alias));
        CREATE TABLE IF NOT EXISTS wiki_entry_sources (
          id BIGSERIAL PRIMARY KEY,
          entry_id BIGINT NOT NULL REFERENCES wiki_entries(id) ON DELETE CASCADE,
          document_id BIGINT REFERENCES documents(id) ON DELETE SET NULL,
          document_version_id BIGINT REFERENCES document_versions(id) ON DELETE SET NULL,
          chunk_id BIGINT REFERENCES chunks(id) ON DELETE SET NULL,
          note VARCHAR(500) NOT NULL DEFAULT '',
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (entry_id, document_version_id, chunk_id)
        );
        CREATE INDEX IF NOT EXISTS wiki_sources_chunk_idx ON wiki_entry_sources(chunk_id);
        CREATE TABLE IF NOT EXISTS wiki_entry_revisions (
          id BIGSERIAL PRIMARY KEY,
          entry_id BIGINT NOT NULL REFERENCES wiki_entries(id) ON DELETE CASCADE,
          version_no INTEGER NOT NULL,
          action VARCHAR(30) NOT NULL,
          snapshot JSONB NOT NULL,
          actor_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE(entry_id, version_no)
        );
        """
    # asyncpg 的 prepared statement 只接受一条语句，逐条执行固定 DDL。
    for statement in script.split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade() -> None:
    """删除 LLM Wiki MVP 表，不影响原有文档和向量数据。"""
    op.execute("DROP TABLE IF EXISTS wiki_entry_revisions")
    op.execute("DROP TABLE IF EXISTS wiki_entry_sources")
    op.execute("DROP TABLE IF EXISTS wiki_aliases")
    op.execute("DROP TABLE IF EXISTS wiki_entries")
