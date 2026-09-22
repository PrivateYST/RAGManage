"""为已加入空间的成员开放知识问答菜单入口。

Revision ID: 0018_space_member_chat_menu
Revises: 0017_platform_settings
"""

from alembic import op

revision = "0018_space_member_chat_menu"
down_revision = "0017_platform_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """让空间成员看到问答入口；实际知识库范围仍由后端内容授权校验决定。"""
    op.execute(
        """
        INSERT INTO role_menus(role_id, menu_id)
        SELECT role.id, menu.id
        FROM roles role
        CROSS JOIN menus menu
        WHERE role.code = 'space_member'
          AND menu.permission_code = 'chat:use'
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    """回退空间成员的问答菜单关联，不影响问答接口或其他角色。"""
    op.execute(
        """
        DELETE FROM role_menus
        WHERE role_id = (SELECT id FROM roles WHERE code = 'space_member')
          AND menu_id = (SELECT id FROM menus WHERE permission_code = 'chat:use')
        """
    )
