"""为每次 API Key 运行持久化 OpenAI 兼容请求参数指纹。

Revision ID: 0019_openai_request_fingerprint
Revises: 0018_space_member_chat_menu
"""

from alembic import op

revision = "0019_openai_request_fingerprint"
down_revision = "0018_space_member_chat_menu"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """增加稳定摘要，防止幂等重试时改变模型生成参数。"""
    op.execute(
        "ALTER TABLE generation_runs ADD COLUMN request_fingerprint VARCHAR(64) "
        "CHECK (request_fingerprint IS NULL OR length(request_fingerprint) = 64)"
    )
    op.execute(
        "COMMENT ON COLUMN generation_runs.request_fingerprint IS "
        "'OpenAI 兼容请求的知识库、模型、问题和生成参数 SHA-256 指纹'"
    )


def downgrade() -> None:
    """移除可选兼容指纹，不改动历史运行数据。"""
    op.execute("ALTER TABLE generation_runs DROP COLUMN request_fingerprint")
