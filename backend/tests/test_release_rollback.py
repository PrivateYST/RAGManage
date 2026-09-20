from typing import Any
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


class FakeTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeRollbackConnection:
    def __init__(self, *, invalid_source: bool = False) -> None:
        self.invalid_source = invalid_source
        self.execute_calls: list[tuple[Any, ...]] = []
        self.closed = False

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "FROM kb_releases WHERE id" in query:
            return {
                "id": 1,
                "tenant_id": 1,
                "knowledge_base_id": 2,
                "build_id": 3,
                "manifest_hash": "manifest-1",
                "state": "retired",
            }
        if "FROM knowledge_bases" in query and "FOR UPDATE" in query:
            return {"id": 2, "tenant_id": 1, "active_release_id": 2}
        if "UPDATE kb_releases SET state = 'ready'" in query:
            return {
                "id": "1",
                "build_id": "3",
                "manifest_hash": "manifest-1",
                "state": "ready",
                "created_at": "2026-09-17T00:00:00Z",
            }
        raise AssertionError(f"未处理的 fetchrow 查询：{query}")

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        if "LIMIT 2" in query:
            return [{"id": "1", "state": "retired"}]
        if "FROM release_items" in query:
            return [{"document_id": "9", "title": "已停用文档"}] if self.invalid_source else []
        raise AssertionError(f"未处理的 fetch 查询：{query}")

    async def fetchval(self, query: str, *args: object) -> int:
        assert "UPDATE knowledge_bases" in query
        return 2

    async def execute(self, query: str, *args: object) -> None:
        self.execute_calls.append((query, *args))

    async def close(self) -> None:
        self.closed = True


class FakePublishConflictConnection:
    def __init__(self) -> None:
        self.closed = False

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()

    async def fetchrow(self, query: str, *args: object) -> dict[str, object]:
        assert "FROM knowledge_bases" in query
        return {"id": 2, "tenant_id": 1, "active_release_id": 2}

    async def close(self) -> None:
        self.closed = True


def _configure_rollback_test(monkeypatch: Any, connection: FakeRollbackConnection) -> None:
    context = {"user": {"id": "7"}}
    access = {"id": 2, "tenant_id": 1, "active_release_id": 2}
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=context))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr("app.main._require_knowledge_base_role", AsyncMock(return_value=access))


def test_rollback_switches_active_release_and_writes_audit_log(monkeypatch: Any) -> None:
    connection = FakeRollbackConnection()
    _configure_rollback_test(monkeypatch, connection)

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/releases/1/rollback",
            json={"expected_active_release_id": 2},
        )

    assert response.status_code == 200
    assert response.json()["id"] == "1"
    assert response.json()["previous_release_id"] == "2"
    assert any("release.rollback" in call[0] for call in connection.execute_calls)
    assert connection.closed


def test_rollback_rejects_disabled_or_invalid_sources(monkeypatch: Any) -> None:
    connection = FakeRollbackConnection(invalid_source=True)
    _configure_rollback_test(monkeypatch, connection)

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/releases/1/rollback",
            json={"expected_active_release_id": 2},
        )

    assert response.status_code == 409
    assert "已删除、停用或失效来源" in response.json()["detail"]
    assert not connection.execute_calls
    assert connection.closed


def test_publish_rejects_stale_expected_active_release(monkeypatch: Any) -> None:
    connection = FakePublishConflictConnection()
    context = {"user": {"id": "7"}}
    access = {"id": 2, "tenant_id": 1, "active_release_id": 2}
    preview = {"build_record": {"knowledge_base_id": 2}}
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=context))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr("app.main._load_release_preview", AsyncMock(return_value=preview))
    monkeypatch.setattr("app.main._require_knowledge_base_role", AsyncMock(return_value=access))

    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/v1/builds/3/publish",
            json={"expected_active_release_id": 1},
        )

    assert response.status_code == 409
    assert "当前发布版本已变化" in response.json()["detail"]
    assert connection.closed
