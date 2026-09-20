# ruff: noqa: E501
"""增加无默认内容权限的空间成员角色，并修复知识库角色菜单授权。

Revision ID: 0008_space_member_role
Revises: 0007_generation_runs
"""

from alembic import op

revision = "0008_space_member_role"
down_revision = "0007_generation_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """内部成员先加入空间，再通过知识库成员关系获得显式内容权限。"""
    op.execute(
        """
        INSERT INTO roles(code, name, scope, description, is_system)
        VALUES (
          'space_member', '空间成员', 'tenant',
          '已加入空间但仅能访问显式授权的知识库', true
        )
        ON CONFLICT (code) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO role_menus(role_id, menu_id)
        SELECT r.id, m.id FROM roles r JOIN menus m ON m.permission_code = 'dashboard:view'
        WHERE r.code = 'space_member'
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    """仅在没有空间成员使用该角色时允许回退。"""
    op.execute(
        """
        DELETE FROM role_menus
        WHERE role_id = (SELECT id FROM roles WHERE code = 'space_member')
        """
    )
    op.execute("DELETE FROM roles WHERE code = 'space_member'")
