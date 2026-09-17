from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_liveness_does_not_require_infrastructure() -> None:
    with TestClient(create_app(Settings())) as client:
        assert client.get("/api/v1/health/live").json() == {"status": "ok"}


def test_readiness_requires_every_dependency(monkeypatch) -> None:
    checks = {"database": "ok", "redis": "unavailable", "storage": "ok"}
    monkeypatch.setattr("app.main.check_dependencies", AsyncMock(return_value=checks))
    with TestClient(create_app(Settings())) as client:
        response = client.get("/api/v1/health/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "not_ready", "checks": checks}


def test_readiness_success(monkeypatch) -> None:
    checks = dict.fromkeys(("database", "redis", "storage"), "ok")
    monkeypatch.setattr("app.main.check_dependencies", AsyncMock(return_value=checks))
    with TestClient(create_app(Settings())) as client:
        assert client.get("/api/v1/health/ready").status_code == 200
