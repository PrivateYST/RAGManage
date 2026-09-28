"""允许助理会话不绑定单个知识库，并为自动检索预留运行范围。"""

from alembic import op

revision = "0022_auto_scope_assistant_chat"
down_revision = "0021_build_runtime_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """区分传统单库会话与按 API Key 自动确定范围的助理会话。"""
    op.execute(
        "ALTER TABLE conversations ADD COLUMN scope VARCHAR(24) "
        "NOT NULL DEFAULT 'knowledge_base'"
    )
    op.execute(
        "ALTER TABLE conversations ALTER COLUMN knowledge_base_id DROP NOT NULL"
    )
    op.execute(
        "ALTER TABLE conversations ADD CONSTRAINT conversations_scope_kb_check "
        "CHECK ((scope = 'knowledge_base' AND knowledge_base_id IS NOT NULL) OR "
        "(scope = 'assistant' AND knowledge_base_id IS NULL))"
    )
    # 自动范围运行会在运行时解析零个、一个或多个知识库，不能伪造一个固定库 ID。
    op.execute("ALTER TABLE generation_runs ALTER COLUMN knowledge_base_id DROP NOT NULL")
    op.execute(
        "CREATE INDEX conversations_assistant_owner_idx "
        "ON conversations(tenant_id, owner_user_id, updated_at DESC, id DESC) "
        "WHERE scope = 'assistant' AND status = 'active'"
    )
    op.execute(
        "COMMENT ON COLUMN conversations.scope IS "
        "'knowledge_base 表示固定知识库会话；assistant 表示由 API Key 确定全空间检索范围'"
    )
    op.execute(
        "COMMENT ON COLUMN conversations.knowledge_base_id IS "
        "'固定知识库会话必填；assistant 会话为空，由每次运行自动确定检索范围'"
    )
    op.execute(
        "COMMENT ON COLUMN generation_runs.knowledge_base_id IS "
        "'传统知识问答使用的知识库；自动范围助理运行为空，实际范围由本次检索 Trace 记录'"
    )
    op.execute(
        "COMMENT ON INDEX conversations_assistant_owner_idx IS "
        "'加速当前 API Key 所属用户的活动助理会话列表'"
    )


def downgrade() -> None:
    """仅当没有自动范围会话或运行时回滚，避免悄悄丢弃其语义。"""
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM conversations WHERE scope = 'assistant') "
        "OR EXISTS (SELECT 1 FROM generation_runs WHERE knowledge_base_id IS NULL) "
        "THEN RAISE EXCEPTION '无法回滚：仍存在自动范围助理会话或运行'; END IF; "
        "END $$"
    )
    op.execute("ALTER TABLE generation_runs ALTER COLUMN knowledge_base_id SET NOT NULL")
    op.execute("DROP INDEX conversations_assistant_owner_idx")
    op.execute("ALTER TABLE conversations DROP CONSTRAINT conversations_scope_kb_check")
    op.execute("ALTER TABLE conversations ALTER COLUMN knowledge_base_id SET NOT NULL")
    op.execute("ALTER TABLE conversations DROP COLUMN scope")
