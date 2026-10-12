"""为平台管理员增加环境检查页入口。"""

from alembic import op

revision = "0024_environment_check_menu"
down_revision = "0023_platform_gateway_secret"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """将环境检查挂入系统管理目录，且只向平台管理员授予菜单权限。"""
    op.execute(
        """
        INSERT INTO menus(code, name, kind, parent_id, route, icon, permission_code, sort_order)
        SELECT 'environment-check', '环境检查', 'menu', parent.id, '/system/environment',
               'Activity', 'environment:check', 80
        FROM menus parent
        WHERE parent.code = 'system'
          AND NOT EXISTS (SELECT 1 FROM menus WHERE code = 'environment-check')
        """
    )
    op.execute(
        """
        INSERT INTO role_menus(role_id, menu_id)
        SELECT role.id, menu.id
        FROM roles role CROSS JOIN menus menu
        WHERE role.code = 'platform_admin' AND menu.code = 'environment-check'
          AND NOT EXISTS (
            SELECT 1 FROM role_menus existing
            WHERE existing.role_id = role.id AND existing.menu_id = menu.id
          )
        """
    )


def downgrade() -> None:
    """删除环境检查入口和关联授权，不影响健康检查接口本身。"""
    op.execute(
        "DELETE FROM role_menus "
        "WHERE menu_id = (SELECT id FROM menus WHERE code = 'environment-check')"
    )
    op.execute("DELETE FROM menus WHERE code = 'environment-check'")
