"""真实 PostgreSQL 交接验收；仅在显式配置隔离测试数据库时运行。"""

from __future__ import annotations

import asyncio
import os
from typing import Any
from uuid import uuid4

import asyncpg
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.api_keys import hash_api_key
from app.core.config import Settings
from app.main import create_app

ISOLATED_DATABASE_URL = os.environ.get("RAGMANAGE_TEST_DATABASE_URL")


@pytest.mark.skipif(
    not ISOLATED_DATABASE_URL,
    reason="requires a disposable migrated database configured with RAGMANAGE_TEST_DATABASE_URL",
)
def test_key_handoff_end_to_end_in_isolated_postgres(monkeypatch: Any) -> None:
    """在独立 PostgreSQL 中创建、轮换、错贴、确认并复查医院 Key 交接状态。"""
    assert ISOLATED_DATABASE_URL is not None
    tenant_id, platform_user_id, hospital_user_id = asyncio.run(
        _seed_handoff_actors(ISOLATED_DATABASE_URL)
    )
    active_context: dict[str, Any] = {
        "user": {"id": str(platform_user_id), "platform_role": "platform_admin"},
        "spaces": [],
    }

    async def authenticated_context(*_: object, **__: object) -> dict[str, Any]:
        """Switch the API session identity while real PostgreSQL checks memberships."""
        return active_context

    monkeypatch.setattr("app.main._authenticated_user", authenticated_context)
    settings = Settings(
        database_url=ISOLATED_DATABASE_URL,
        api_key_encryption_secret=SecretStr("isolated-handoff-integration-encryption-key"),
    )
    older_key: str | None = None
    current_key: str | None = None
    try:
        with TestClient(create_app(settings)) as client:
            older_response = client.post(
                "/api/v1/api-keys",
                json={"tenant_id": tenant_id, "name": "旧医院 Key", "token_limit": 1000},
            )
            assert older_response.status_code == 201, older_response.text
            older_key = older_response.json()["raw_key"]

            current_response = client.post(
                "/api/v1/api-keys",
                json={"tenant_id": tenant_id, "name": "当前医院 Key", "token_limit": 1000},
            )
            assert current_response.status_code == 201, current_response.text
            current_key = current_response.json()["raw_key"]

            active_context["user"] = {
                "id": str(hospital_user_id),
                "platform_role": None,
            }
            initial_status = client.get(f"/api/v1/spaces/{tenant_id}/api-key/configuration")
            assert initial_status.status_code == 200, initial_status.text
            assert initial_status.json()["configured"] is False
            assert initial_status.json()["key_prefix"] == current_response.json()["key_prefix"]

            stale_confirmation = client.post(
                f"/api/v1/spaces/{tenant_id}/api-key/configuration",
                json={"api_key": older_key},
            )
            assert stale_confirmation.status_code == 400

            first_confirmation = client.post(
                f"/api/v1/spaces/{tenant_id}/api-key/configuration",
                json={"api_key": current_key},
            )
            assert first_confirmation.status_code == 200, first_confirmation.text
            assert first_confirmation.json()["configured"] is True
            assert current_key not in first_confirmation.text

            repeated_confirmation = client.post(
                f"/api/v1/spaces/{tenant_id}/api-key/configuration",
                json={"api_key": current_key},
            )
            assert repeated_confirmation.status_code == 200, repeated_confirmation.text
            assert (
                repeated_confirmation.json()["configured_at"]
                == first_confirmation.json()["configured_at"]
            )
            final_status = client.get(f"/api/v1/spaces/{tenant_id}/api-key/configuration")
            assert final_status.status_code == 200
            assert final_status.json()["configured"] is True

        asyncio.run(
            _assert_handoff_storage(
                ISOLATED_DATABASE_URL,
                tenant_id=tenant_id,
                actor_id=hospital_user_id,
                current_key=current_key,
                older_key=older_key,
            )
        )
    finally:
        asyncio.run(
            _remove_handoff_actors(
                ISOLATED_DATABASE_URL,
                tenant_id,
                [platform_user_id, hospital_user_id],
            )
        )


async def _seed_handoff_actors(database_url: str) -> tuple[int, int, int]:
    """Create isolated platform and hospital identities with a real space_admin membership."""
    connection = await asyncpg.connect(database_url)
    suffix = uuid4().hex[:12]
    try:
        async with connection.transaction():
            tenant_id = await connection.fetchval(
                "INSERT INTO tenants(code, name) VALUES ($1, $2) RETURNING id",
                f"handoff-{suffix}",
                f"Key 交接验收 {suffix}",
            )
            platform_role_id = await connection.fetchval(
                "SELECT id FROM roles WHERE code = 'platform_admin'"
            )
            space_admin_role_id = await connection.fetchval(
                "SELECT id FROM roles WHERE code = 'space_admin'"
            )
            platform_user_id = await connection.fetchval(
                """
                INSERT INTO users(login, display_name, password_hash, platform_role_id)
                VALUES ($1, '隔离测试系统管理员', 'unused-in-integration-test', $2)
                RETURNING id
                """,
                f"platform-{suffix}",
                platform_role_id,
            )
            hospital_user_id = await connection.fetchval(
                """
                INSERT INTO users(login, display_name, password_hash)
                VALUES ($1, '隔离测试医院管理员', 'unused-in-integration-test')
                RETURNING id
                """,
                f"hospital-{suffix}",
            )
            await connection.execute(
                """
                INSERT INTO tenant_members(tenant_id, user_id, role_id)
                VALUES ($1, $2, $3)
                """,
                tenant_id,
                hospital_user_id,
                space_admin_role_id,
            )
        return int(tenant_id), int(platform_user_id), int(hospital_user_id)
    finally:
        await connection.close()


async def _assert_handoff_storage(
    database_url: str,
    *,
    tenant_id: int,
    actor_id: int,
    current_key: str | None,
    older_key: str | None,
) -> None:
    """Verify the current hash, encrypted-at-rest credential and one-time audit transition."""
    assert current_key is not None
    assert older_key is not None
    connection = await asyncpg.connect(database_url)
    try:
        rows = await connection.fetch(
            """
            SELECT key_hash, encrypted_key, configured_at, configured_by
            FROM api_keys WHERE tenant_id = $1 ORDER BY id
            """,
            tenant_id,
        )
        assert len(rows) == 2
        assert rows[0]["key_hash"] == hash_api_key(older_key)
        assert rows[0]["configured_at"] is None
        assert rows[1]["key_hash"] == hash_api_key(current_key)
        assert current_key not in rows[1]["encrypted_key"]
        assert rows[1]["configured_at"] is not None
        assert rows[1]["configured_by"] == actor_id
        audit_count = await connection.fetchval(
            """
            SELECT count(*) FROM audit_logs
            WHERE tenant_id = $1 AND action = 'api_key.configure'
              AND target_type = 'api_key'
            """,
            tenant_id,
        )
        assert audit_count == 1
    finally:
        await connection.close()


async def _remove_handoff_actors(
    database_url: str,
    tenant_id: int,
    user_ids: list[int],
) -> None:
    """Delete only the uniquely created tenant so a shared isolated test DB stays repeatable."""
    connection = await asyncpg.connect(database_url)
    try:
        await connection.execute("DELETE FROM tenants WHERE id = $1", tenant_id)
        await connection.execute("DELETE FROM users WHERE id = ANY($1::bigint[])", user_ids)
    finally:
        await connection.close()
