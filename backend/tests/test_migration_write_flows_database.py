"""可回滚 PostgreSQL 验收：覆盖迁移期间涉及的主要业务写入和异步解析闭环。"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import asyncpg
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.jobs.tasks import _process_document
from app.main import create_app
from app.rag.models import ModelGatewayClient

ISOLATED_DATABASE_URL = os.environ.get("RAGMANAGE_TEST_DATABASE_URL")


@pytest.mark.skipif(
    not ISOLATED_DATABASE_URL,
    reason="requires a disposable migrated database configured with RAGMANAGE_TEST_DATABASE_URL",
)
def test_migrated_write_flows_parse_and_build_in_isolated_postgres(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    """创建隔离空间后运行用户、菜单、成员、文档解析、构建和 API Key 写入并校验持久化。"""
    assert ISOLATED_DATABASE_URL is not None
    platform_user_id, suffix = asyncio.run(_seed_platform_user(ISOLATED_DATABASE_URL))
    tenant_id: int | None = None
    created_user_ids: list[int] = [platform_user_id]
    created_menu_id: int | None = None
    active_context: dict[str, Any] = {
        "user": {"id": str(platform_user_id), "platform_role": "platform_admin"},
        "spaces": [],
    }

    async def authenticated_context(*_: object, **__: object) -> dict[str, Any]:
        """Use an explicit test identity while PostgreSQL evaluates actual role membership."""
        return active_context

    async def test_model_revision(_: ModelGatewayClient) -> str:
        """Keep build creation independent of an external model gateway in the isolated test."""
        return "isolated-model-revision"

    monkeypatch.setattr("app.main._authenticated_user", authenticated_context)
    monkeypatch.setattr(ModelGatewayClient, "model_revision", test_model_revision)
    monkeypatch.setenv("DATABASE_URL", ISOLATED_DATABASE_URL)
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))
    settings = Settings(
        database_url=ISOLATED_DATABASE_URL,
        storage_root=tmp_path,
        api_key_encryption_secret=SecretStr("isolated-write-flow-encryption-secret"),
    )

    try:
        with TestClient(create_app(settings)) as client:
            # 平台管理员真实创建空间与角色用户，医院管理员随后维护该空间。
            tenant_response = client.post(
                "/api/v1/admin/tenants",
                json={"code": f"qa-{suffix}", "name": f"隔离验收医院 {suffix}"},
            )
            assert tenant_response.status_code == 201, tenant_response.text
            tenant_id = int(tenant_response.json()["id"])

            menus = client.get("/api/v1/admin/menus")
            assert menus.status_code == 200, menus.text
            system_menu_id = next(
                int(item["id"]) for item in menus.json()["items"] if item["code"] == "system"
            )
            menu_response = client.post(
                "/api/v1/admin/menus",
                json={
                    "code": f"qa-button-{suffix}",
                    "name": "隔离验收按钮",
                    "kind": "button",
                    "parent_id": system_menu_id,
                    "permission_code": f"qa:button:{suffix}",
                    "sort_order": 9998,
                },
            )
            assert menu_response.status_code == 201, menu_response.text
            created_menu_id = int(menu_response.json()["id"])
            menu_update = client.patch(
                f"/api/v1/admin/menus/{created_menu_id}",
                json={"visible": False, "status": "disabled"},
            )
            assert menu_update.status_code == 200, menu_update.text
            assert menu_update.json()["visible"] is False

            hospital_user = client.post(
                "/api/v1/admin/users",
                json={
                    "login": f"hospital-admin-{suffix}",
                    "display_name": "隔离医院管理员",
                    "password": f"Handoff-{suffix}-Strong-Password",
                    "tenant_id": tenant_id,
                    "tenant_role_code": "space_admin",
                },
            )
            assert hospital_user.status_code == 201, hospital_user.text
            hospital_user_id = int(hospital_user.json()["id"])
            created_user_ids.append(hospital_user_id)
            member_user = client.post(
                "/api/v1/admin/users",
                json={
                    "login": f"hospital-member-{suffix}",
                    "display_name": "隔离医院成员",
                    "password": f"Member-{suffix}-Strong-Password",
                },
            )
            assert member_user.status_code == 201, member_user.text
            member_user_id = int(member_user.json()["id"])
            created_user_ids.append(member_user_id)

            active_context["user"] = {"id": str(hospital_user_id), "platform_role": None}
            member = client.post(
                f"/api/v1/spaces/{tenant_id}/members",
                json={"login": f"hospital-member-{suffix}", "role_code": "space_member"},
            )
            assert member.status_code == 201, member.text
            member_id = int(member.json()["id"])
            member_update = client.patch(
                f"/api/v1/spaces/{tenant_id}/members/{member_id}",
                json={"status": "disabled"},
            )
            assert member_update.status_code == 200, member_update.text
            assert member_update.json()["status"] == "disabled"
            member_restore = client.patch(
                f"/api/v1/spaces/{tenant_id}/members/{member_id}",
                json={"status": "active"},
            )
            assert member_restore.status_code == 200, member_restore.text

            knowledge_base = client.post(
                "/api/v1/knowledge-bases",
                json={
                    "tenant_id": tenant_id,
                    "name": f"验收知识库 {suffix}",
                    "description": "仅存于可回滚测试空间",
                    "purpose": "test",
                },
            )
            assert knowledge_base.status_code == 201, knowledge_base.text
            knowledge_base_id = int(knowledge_base.json()["id"])

            upload = client.post(
                f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
                files={
                    "file": (
                        "handoff-policy.md",
                        "# 出院办理\n请携带医保卡和出院记录。\n".encode(),
                        "text/markdown",
                    )
                },
            )
            assert upload.status_code == 202, upload.text
            document_id = int(upload.json()["document"]["id"])
            parse_task_id = int(upload.json()["task"]["id"])

            # 运行同一文档解析任务实现，验证队列数据、临时文件和 PostgreSQL 可协作完成。
            asyncio.run(_process_document(parse_task_id))
            parse_result = asyncio.run(
                _read_parse_result(ISOLATED_DATABASE_URL, document_id, parse_task_id)
            )
            assert parse_result == ("complete", "completed", 2)

            build = client.post(f"/api/v1/knowledge-bases/{knowledge_base_id}/builds")
            assert build.status_code == 202, build.text
            assert build.json()["state"] == "queued"

            document_disable = client.post(f"/api/v1/documents/{document_id}/disable")
            assert document_disable.status_code == 204
            document_delete = client.delete(f"/api/v1/documents/{document_id}")
            assert document_delete.status_code == 204

            active_context["user"] = {
                "id": str(platform_user_id),
                "platform_role": "platform_admin",
            }
            api_key = client.post(
                "/api/v1/api-keys",
                json={"tenant_id": tenant_id, "name": "验收医院 Key", "token_limit": 1000},
            )
            assert api_key.status_code == 201, api_key.text
            api_key_id = api_key.json()["id"]
            quota = client.patch(
                f"/api/v1/api-keys/{api_key_id}/quota",
                json={"direction": "add", "amount": 200},
            )
            assert quota.status_code == 200, quota.text
            assert quota.json()["token_limit"] == 1200
            disable_key = client.patch(
                f"/api/v1/api-keys/{api_key_id}/status",
                json={"status": "disabled"},
            )
            assert disable_key.status_code == 200, disable_key.text
            enable_key = client.patch(
                f"/api/v1/api-keys/{api_key_id}/status",
                json={"status": "active"},
            )
            assert enable_key.status_code == 200, enable_key.text
            delete_key = client.delete(f"/api/v1/api-keys/{api_key_id}")
            assert delete_key.status_code == 200, delete_key.text

        persisted = asyncio.run(
            _read_write_flow_result(
                ISOLATED_DATABASE_URL,
                tenant_id=tenant_id,
                menu_id=created_menu_id,
                api_key_id=int(api_key_id),
            )
        )
        assert persisted == ("disabled", "revoked", 1200, "deleted")
    finally:
        asyncio.run(
            _remove_write_flow_data(
                ISOLATED_DATABASE_URL,
                tenant_id=tenant_id,
                menu_id=created_menu_id,
                user_ids=created_user_ids,
            )
        )


async def _seed_platform_user(database_url: str) -> tuple[int, str]:
    """Create an isolated platform identity used as actor for platform-scoped operations."""
    suffix = uuid4().hex[:12]
    connection = await asyncpg.connect(database_url)
    try:
        role_id = await connection.fetchval("SELECT id FROM roles WHERE code = 'platform_admin'")
        user_id = await connection.fetchval(
            """
            INSERT INTO users(login, display_name, password_hash, platform_role_id)
            VALUES ($1, '隔离迁移验收管理员', 'unused-in-integration-test', $2)
            RETURNING id
            """,
            f"migration-admin-{suffix}",
            role_id,
        )
        return int(user_id), suffix
    finally:
        await connection.close()


async def _read_parse_result(
    database_url: str,
    document_id: int,
    task_id: int,
) -> tuple[str, str, int]:
    """Read the parsed document, completed task, and persisted chunk count from PostgreSQL."""
    connection = await asyncpg.connect(database_url)
    try:
        row = await connection.fetchrow(
            """
            SELECT dv.parse_status, task.state, count(chunk.id)::int AS chunk_count
            FROM documents document
            JOIN document_versions dv ON dv.id = document.desired_version_id
            JOIN tasks task ON task.id = $2
            LEFT JOIN document_artifacts artifact ON artifact.document_version_id = dv.id
            LEFT JOIN chunks chunk ON chunk.artifact_id = artifact.id
            WHERE document.id = $1
            GROUP BY dv.parse_status, task.state
            """,
            document_id,
            task_id,
        )
        assert row is not None
        return str(row["parse_status"]), str(row["state"]), int(row["chunk_count"])
    finally:
        await connection.close()


async def _read_write_flow_result(
    database_url: str,
    *,
    tenant_id: int,
    menu_id: int,
    api_key_id: int,
) -> tuple[str, str, int, str]:
    """Confirm the menu edit, soft deletion, quota update, and document soft deletion persisted."""
    connection = await asyncpg.connect(database_url)
    try:
        menu = await connection.fetchrow(
            "SELECT status, visible FROM menus WHERE id = $1",
            menu_id,
        )
        api_key = await connection.fetchrow(
            "SELECT deleted_at, status, token_limit FROM api_keys WHERE id = $1",
            api_key_id,
        )
        document_status = await connection.fetchval(
            "SELECT status FROM documents WHERE tenant_id = $1 AND status = 'deleted' LIMIT 1",
            tenant_id,
        )
        assert menu is not None and api_key is not None
        assert menu["visible"] is False
        assert api_key["deleted_at"] is not None
        return (
            str(menu["status"]),
            str(api_key["status"]),
            int(api_key["token_limit"]),
            str(document_status),
        )
    finally:
        await connection.close()


async def _remove_write_flow_data(
    database_url: str,
    *,
    tenant_id: int | None,
    menu_id: int | None,
    user_ids: list[int],
) -> None:
    """Rollback only rows created by this run and preserve any other isolated test fixtures."""
    connection = await asyncpg.connect(database_url)
    try:
        if tenant_id is not None:
            await connection.execute("DELETE FROM tenants WHERE id = $1", tenant_id)
        if menu_id is not None:
            await connection.execute("DELETE FROM menus WHERE id = $1", menu_id)
        await connection.execute("DELETE FROM users WHERE id = ANY($1::bigint[])", user_ids)
    finally:
        await connection.close()
