"""为知识库增加业务治理元数据，供权限外的检索范围和引用展示使用。"""

from alembic import op

revision = "0027_kb_governance_metadata"
down_revision = "0026_space_creator_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """添加可审计的业务归属、可信度、有效期和标签字段。"""
    op.execute(
        """
        ALTER TABLE knowledge_bases
          ADD COLUMN IF NOT EXISTS business_scenario VARCHAR(240) NOT NULL DEFAULT '',
          ADD COLUMN IF NOT EXISTS target_users VARCHAR(240) NOT NULL DEFAULT '',
          ADD COLUMN IF NOT EXISTS owner_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
          ADD COLUMN IF NOT EXISTS trust_level VARCHAR(20) NOT NULL DEFAULT 'medium'
            CHECK (trust_level IN ('low', 'medium', 'high')),
          ADD COLUMN IF NOT EXISTS valid_from DATE,
          ADD COLUMN IF NOT EXISTS valid_until DATE,
          ADD COLUMN IF NOT EXISTS source_system VARCHAR(160) NOT NULL DEFAULT '',
          ADD COLUMN IF NOT EXISTS business_tags TEXT[] NOT NULL DEFAULT '{}',
          ADD CONSTRAINT knowledge_bases_valid_period_check
            CHECK (valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from)
        """
    )
    for column, comment in {
        "business_scenario": "业务场景；用于治理筛选和引用说明",
        "target_users": "目标用户群体；用于治理筛选和引用说明",
        "owner_user_id": "业务负责人账号",
        "trust_level": "业务可信等级：low/medium/high",
        "valid_from": "资料有效期起始日",
        "valid_until": "资料有效期截止日",
        "source_system": "资料来源系统",
        "business_tags": "业务标签数组",
    }.items():
        op.execute(f"COMMENT ON COLUMN knowledge_bases.{column} IS '{comment}'")


def downgrade() -> None:
    """删除治理字段，恢复到 P0 知识库结构。"""
    op.execute(
        """
        ALTER TABLE knowledge_bases
          DROP CONSTRAINT IF EXISTS knowledge_bases_valid_period_check,
          DROP COLUMN IF EXISTS business_tags,
          DROP COLUMN IF EXISTS source_system,
          DROP COLUMN IF EXISTS valid_until,
          DROP COLUMN IF EXISTS valid_from,
          DROP COLUMN IF EXISTS trust_level,
          DROP COLUMN IF EXISTS owner_user_id,
          DROP COLUMN IF EXISTS target_users,
          DROP COLUMN IF EXISTS business_scenario
        """
    )
