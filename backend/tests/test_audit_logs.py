from typing import Any
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def audit_row(item_id: int) -> dict[str, Any]:
    return {
        "id": str(item_id),
        "tenant_id": "7",
        "tenant_name": "内部工作空间",
        "actor_id": "11",
        "actor_name": "平台管理员",
        "actor_login": "admin",
        "action": "release.publish",
        "target_type": "knowledge_base",
        "target_id": "2",
        "change_summary": '{"release_id": 5}',
        "request_id": None,
        "created_at": "2026-09-19T12:00:00+00:00",
    }


def test_space_audit_logs_require_space_admin_and_return_cursor(monkeypatch: Any) -> None:
    connection = AsyncMock()
    connection.fetch = AsyncMock(return_value=[audit_row(9), audit_row(8), audit_row(7)])
    connection.close = AsyncMock()
    context = {"user": {"id": "11", "platform_role": "platform_admin"}}
    require_space_admin = AsyncMock()
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=context))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr("app.main._require_space_admin", require_space_admin)

    with TestClient(create_app(Settings())) as client:
        response = client.get(
            "/api/v1/audit-logs",
            params={
                "tenant_id": 7,
                "action_prefix": "release.",
                "actor": "平台",
                "target_type": "knowledge_base",
                "limit": 2,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == ["9", "8"]
    assert body["items"][0]["change_summary"] == {"release_id": 5}
    assert body["next_cursor"] == "8"
    require_space_admin.assert_awaited_once_with(connection, context, 7)
    assert connection.fetch.await_args.args[1:] == (
        7,
        "release.",
        "平台",
        "knowledge_base",
        None,
        3,
    )
    connection.close.assert_awaited_once()


def test_platform_audit_logs_do_not_include_space_events(monkeypatch: Any) -> None:
    connection = AsyncMock()
    row = audit_row(5)
    row["tenant_id"] = None
    row["tenant_name"] = None
    connection.fetch = AsyncMock(return_value=[row])
    connection.close = AsyncMock()
    context = {"user": {"id": "11", "platform_role": "platform_admin"}}
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=context))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))

    with TestClient(create_app(Settings())) as client:
        response = client.get("/api/v1/audit-logs")

    assert response.status_code == 200
    assert response.json()["items"][0]["tenant_id"] is None
    assert connection.fetch.await_args.args[1] is None
    assert "al.tenant_id IS NULL" in connection.fetch.await_args.args[0]


def test_non_platform_user_cannot_read_platform_audit_logs(monkeypatch: Any) -> None:
    connection = AsyncMock()
    connection.close = AsyncMock()
    context = {"user": {"id": "12", "platform_role": None}}
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=context))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))

    with TestClient(create_app(Settings())) as client:
        response = client.get("/api/v1/audit-logs")

    assert response.status_code == 403
    assert response.json()["detail"] == "只有平台管理员可以查看平台日志"
    connection.fetch.assert_not_awaited()
    connection.close.assert_awaited_once()
