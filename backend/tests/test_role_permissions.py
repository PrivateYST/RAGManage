"""验证角色权限编辑的系统角色保护和输入边界。"""

import asyncio
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


class FakeTransaction:
    """提供异步事务上下文，验证异常时不会执行替换操作。"""

    async def __aenter__(self) -> "FakeTransaction":
        """进入模拟事务。"""
        return self

    async def __aexit__(self, *args: object) -> None:
        """退出模拟事务。"""


class FakeConnection:
    """返回系统角色记录并记录连接释放。"""

    def __init__(self) -> None:
        """初始化调用记录。"""
        self.closed = False

    def transaction(self) -> FakeTransaction:
        """返回异步事务上下文。"""
        return FakeTransaction()

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any]:
        """返回受保护的系统角色。"""
        return {
            "id": "1",
            "code": "platform_admin",
            "name": "平台管理员",
            "scope": "platform",
            "is_system": True,
        }

    async def close(self) -> None:
        """标记连接关闭。"""
        self.closed = True


def test_system_role_permission_edit_is_rejected(monkeypatch: Any) -> None:
    """系统角色不能通过管理接口直接修改，防止误删基础权限。"""
    connection = FakeConnection()
    monkeypatch.setattr(
        "app.main._authenticated_user",
        lambda *args, **kwargs: asyncio.sleep(
            0, result={"user": {"id": "1", "platform_role": "platform_admin"}}
        ),
    )

    async def database(*args: object, **kwargs: object) -> FakeConnection:
        """返回模拟连接，保持数据库工厂异步契约。"""
        return connection

    monkeypatch.setattr("app.main._database", database)
    with TestClient(create_app(Settings())) as client:
        response = client.patch("/api/v1/admin/roles/1/menus", json={"menu_ids": [1]})
    assert response.status_code == 409
    assert response.json() == {"detail": "系统角色不允许直接修改权限"}
    assert connection.closed
