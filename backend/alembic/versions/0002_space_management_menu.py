"""增加平台客户空间管理菜单。

Revision ID: 0002_space_management_menu
Revises: 0001_identity_knowledge
"""

from alembic import op

revision = "0002_space_management_menu"
down_revision = "0001_identity_knowledge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO menus(
            code, name, kind, parent_id, route, icon, permission_code, sort_order
        )
        SELECT 'spaces', '空间管理', 'menu', parent.id, '/system/spaces',
               'Building2', 'space:manage', 60
        FROM menus parent WHERE parent.code = 'customers'
        ON CONFLICT (code) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO role_menus(role_id, menu_id)
        SELECT role.id, menu.id FROM roles role CROSS JOIN menus menu
        WHERE role.code = 'platform_admin' AND menu.code = 'spaces'
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM menus WHERE code = 'spaces'")
