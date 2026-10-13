"""记录空间创建人，并把空间管理授权给空间管理员。"""

from alembic import op

revision = "0026_space_creator_admin"
down_revision = "0025_tenant_api_key_handoff"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """为管理员额外空间额度提供稳定的创建人依据，并修正菜单权限。"""
    op.execute(
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS "
        "created_by BIGINT REFERENCES users(id)"
    )
    op.execute(
        """
        DELETE FROM role_menus
        WHERE role_id = (SELECT id FROM roles WHERE code = 'space_admin')
          AND menu_id IN (SELECT id FROM menus WHERE permission_code = 'model:list')
        """
    )
    op.execute(
        """
        INSERT INTO role_menus(role_id, menu_id)
        SELECT r.id, m.id FROM roles r CROSS JOIN menus m
        WHERE r.code = 'space_admin' AND m.code = 'spaces'
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    """回退菜单授权和创建人字段。"""
    op.execute(
        """
        DELETE FROM role_menus
        WHERE role_id = (SELECT id FROM roles WHERE code = 'space_admin')
          AND menu_id = (SELECT id FROM menus WHERE code = 'spaces')
        """
    )
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS created_by")
