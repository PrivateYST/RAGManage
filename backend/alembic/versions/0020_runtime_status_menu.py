"""新增平台运行状态菜单，并仅授予平台管理员访问。"""

from alembic import op

revision = "0020_runtime_status_menu"
down_revision = "0019_openai_request_fingerprint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """把聚合运行指标挂到系统菜单，权限仍由后端接口二次校验。"""
    op.execute(
        """
        INSERT INTO menus(code, name, kind, parent_id, route, icon, permission_code, sort_order)
        SELECT 'runtime-status', '运行状态', 'menu', parent.id, '/system/status',
               'Activity', 'runtime:status', 79
        FROM menus parent
        WHERE parent.code = 'system'
          AND NOT EXISTS (SELECT 1 FROM menus WHERE code = 'runtime-status')
        """
    )
    op.execute(
        """
        INSERT INTO role_menus(role_id, menu_id)
        SELECT role.id, menu.id
        FROM roles role CROSS JOIN menus menu
        WHERE role.code = 'platform_admin' AND menu.code = 'runtime-status'
          AND NOT EXISTS (
            SELECT 1 FROM role_menus existing
            WHERE existing.role_id = role.id AND existing.menu_id = menu.id
          )
        """
    )


def downgrade() -> None:
    """移除菜单及其角色关联，不影响运行指标接口本身。"""
    op.execute(
        "DELETE FROM role_menus "
        "WHERE menu_id = (SELECT id FROM menus WHERE code = 'runtime-status')"
    )
    op.execute("DELETE FROM menus WHERE code = 'runtime-status'")
