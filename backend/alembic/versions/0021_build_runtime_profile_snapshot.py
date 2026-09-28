"""为索引构建保存创建时的 Runtime Profile 快照引用。"""

from alembic import op

revision = "0021_build_runtime_snapshot"
down_revision = "0020_runtime_status_menu"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """新增可空快照字段，兼容历史构建并保留配置追溯能力。"""
    op.execute(
        "ALTER TABLE index_builds ADD COLUMN runtime_profile_id BIGINT "
        "REFERENCES runtime_profiles(id) ON DELETE RESTRICT"
    )
    op.execute(
        "COMMENT ON COLUMN index_builds.runtime_profile_id IS "
        "'创建构建时冻结的 Runtime Profile；为空表示历史构建未记录该快照'"
    )


def downgrade() -> None:
    """移除构建 Runtime Profile 快照字段。"""
    op.execute("ALTER TABLE index_builds DROP COLUMN runtime_profile_id")
