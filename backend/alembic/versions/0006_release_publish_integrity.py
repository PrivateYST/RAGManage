"""约束每个构建只能生成一个不可变 Release。"""

from alembic import op

revision = "0006_release_publish_integrity"
down_revision = "0005_build_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE kb_releases ADD CONSTRAINT uq_kb_releases_build_id UNIQUE (build_id)")
    op.execute(
        "CREATE INDEX kb_releases_history_idx "
        "ON kb_releases(tenant_id, knowledge_base_id, created_at DESC)"
    )
    op.execute(
        "COMMENT ON CONSTRAINT uq_kb_releases_build_id ON kb_releases "
        "IS '保证每个索引构建最多生成一个不可变发布版本'"
    )
    op.execute("COMMENT ON INDEX kb_releases_history_idx IS '按客户空间和知识库查询发布历史的索引'")


def downgrade() -> None:
    op.execute("DROP INDEX kb_releases_history_idx")
    op.execute("ALTER TABLE kb_releases DROP CONSTRAINT uq_kb_releases_build_id")
