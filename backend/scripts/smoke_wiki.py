"""P2 真实环境冒烟：临时账号走 HTTP 生命周期，并核对真实 DB 检索与版本。

在 API 容器中执行：docker exec -i ragmanage-dev-api-1 python < backend/scripts/smoke_wiki.py
仅创建/清理带唯一前缀的测试账号和词条，不修改业务文档、索引与已发布配置。
"""

from __future__ import annotations

import asyncio
import json
import secrets
from datetime import date, timedelta
from uuid import uuid4

import asyncpg
import httpx

from app.core.auth import password_hasher
from app.core.config import Settings
from app.rag.wiki import lookup_entries


async def main() -> None:
    """使用真实认证、CSRF、数据库和发布证据验证 P2 全链路，并清理测试数据。"""
    settings = Settings()
    connection = await asyncpg.connect(settings.database_url)
    prefix = "p2-smoke-" + uuid4().hex[:10]
    password = secrets.token_urlsafe(24)
    users: list[int] = []
    entry_ids: list[int] = []
    checks: list[str] = []
    try:
        fixture = await connection.fetchrow(
            """SELECT kb.id, kb.tenant_id, kb.active_release_id, c.id AS chunk_id
               FROM knowledge_bases kb JOIN release_items ri ON ri.release_id=kb.active_release_id
               JOIN chunks c ON c.artifact_id=ri.artifact_id
               JOIN documents d ON d.id=ri.document_id AND d.status='active'
               WHERE kb.status <> 'disabled' ORDER BY kb.id DESC, c.ordinal LIMIT 1""",
        )
        assert fixture, "至少需要一个包含原文切片的已发布知识库"
        kb_id, tenant_id, release_id, chunk_id = (
            int(fixture[field]) for field in ("id", "tenant_id", "active_release_id", "chunk_id")
        )
        for suffix, role in [("admin", "space_admin"), ("reader", "customer_reader")]:
            user_id = await connection.fetchval(
                """INSERT INTO users(login,display_name,password_hash) VALUES($1,$2,$3)
                   RETURNING id""",
                prefix + suffix,
                "P2 临时验收",
                password_hasher.hash(password),
            )
            users.append(user_id)
            await connection.execute(
                """INSERT INTO tenant_members(tenant_id,user_id,role_id)
                   SELECT $1,$2,id FROM roles WHERE code=$3""",
                tenant_id,
                user_id,
                role,
            )
        async with httpx.AsyncClient(
            base_url="http://127.0.0.1:8000",
            timeout=180,
            headers={"Origin": "http://127.0.0.1:8000"},
        ) as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={
                    "login": prefix + "admin",
                    "password": password,
                },
            )
            assert response.status_code == 200, response.text
            csrf = (await client.get("/api/v1/auth/csrf")).json()["csrf_token"]
            client.headers["X-CSRF-Token"] = csrf
            route = f"/api/v1/knowledge-bases/{kb_id}/wiki-entries"
            options = await client.get(f"/api/v1/knowledge-bases/{kb_id}/wiki-options")
            assert options.status_code == 200 and options.json()["sources"]
            assert any(member["id"] == str(users[0]) for member in options.json()["members"])
            checks.append("auth_csrf_options")

            payload = {
                "term": prefix + "儿童服务",
                "definition": "测试定义，原文为正式证据。",
                "aliases": [prefix + "儿保"],
                "owner_user_id": users[0],
                "sources": [{"chunk_id": chunk_id, "note": "验收关联原文"}],
            }
            result = await client.post(route, json=payload)
            assert result.status_code == 201, result.text
            entry = result.json()
            entry_id = int(entry["id"])
            entry_ids.append(entry_id)
            assert entry["status"] == "draft" and entry["sources"][0]["document_id"]
            assert (
                await lookup_entries(
                    connection,
                    tenant_id=tenant_id,
                    knowledge_base_id=kb_id,
                    release_id=release_id,
                    query=payload["aliases"][0],
                )
                == []
            )
            checks.append("draft_excluded_from_retrieval")

            duplicate = await client.post(route, json=payload)
            assert duplicate.status_code == 409
            invalid = await client.post(
                route,
                json={
                    **payload,
                    "term": prefix + "bad",
                    "sources": [{"chunk_id": 9223372036854775806}],
                },
            )
            assert invalid.status_code == 400
            other = await connection.fetchval(
                "SELECT id FROM chunks WHERE knowledge_base_id <> $1 LIMIT 1",
                kb_id,
            )
            if other:
                cross = await client.post(
                    route,
                    json={
                        **payload,
                        "term": prefix + "cross",
                        "sources": [{"chunk_id": int(other)}],
                    },
                )
                assert cross.status_code == 400, cross.text
            checks.append("duplicate_invalid_and_cross_kb_source_rejected")

            status_route = f"/api/v1/wiki-entries/{entry_id}/status"
            shortcut = await client.post(
                status_route, json={"status": "published", "expected_version": 1}
            )
            assert shortcut.status_code == 409
            for version, status in [(1, "review"), (2, "published")]:
                result = await client.post(
                    status_route, json={"status": status, "expected_version": version}
                )
                assert result.status_code == 200, result.text
            checks.append("review_publish_lifecycle")
            matches = await lookup_entries(
                connection,
                tenant_id=tenant_id,
                knowledge_base_id=kb_id,
                release_id=release_id,
                query=payload["aliases"][0],
            )
            assert matches and matches[0]["id"] == str(entry_id)
            assert chunk_id in matches[0]["chunk_ids"]
            checks.append("published_alias_matches_real_release")

            # 搜索诊断走真实模型网关/召回链路，证明词条已进入线上检索路径。
            search = await client.post(
                "/api/v1/search-test",
                json={
                    "knowledge_base_id": kb_id,
                    "query": payload["aliases"][0],
                    "top_k": 5,
                },
            )
            assert search.status_code == 200, search.text
            search_body = search.json()
            assert any(
                item["id"] == str(entry_id) for item in search_body.get("wiki_entries", [])
            ), search.text
            assert any(str(item["chunk_id"]) == str(chunk_id) for item in search_body["items"]), (
                search.text
            )
            trace = await connection.fetchval(
                "SELECT profiles FROM retrieval_traces WHERE id=$1",
                int(search_body["trace_id"]),
            )
            assert str(entry_id) in str(trace)
            checks.append("real_gateway_search_alias_and_trace")

            stale = await client.patch(
                f"/api/v1/wiki-entries/{entry_id}", json={**payload, "expected_version": 1}
            )
            assert stale.status_code == 409
            updated = await client.patch(
                f"/api/v1/wiki-entries/{entry_id}", json={**payload, "expected_version": 3}
            )
            assert updated.status_code == 200 and updated.json()["status"] == "draft", updated.text
            assert (
                await lookup_entries(
                    connection,
                    tenant_id=tenant_id,
                    knowledge_base_id=kb_id,
                    release_id=release_id,
                    query=payload["aliases"][0],
                )
                == []
            )
            checks.append("edit_conflict_and_draft_reset")

            for version, status in [(4, "review"), (5, "published"), (6, "retired")]:
                result = await client.post(
                    status_route, json={"status": status, "expected_version": version}
                )
                assert result.status_code == 200, result.text
            assert (
                await lookup_entries(
                    connection,
                    tenant_id=tenant_id,
                    knowledge_base_id=kb_id,
                    release_id=release_id,
                    query=payload["aliases"][0],
                )
                == []
            )
            checks.append("retired_excluded_from_retrieval")

            history = await client.get(f"/api/v1/wiki-entries/{entry_id}/revisions")
            assert history.status_code == 200 and len(history.json()["items"]) == 7
            audit_count = await connection.fetchval(
                "SELECT count(*) FROM audit_logs WHERE target_type='wiki_entry' AND target_id=$1",
                str(entry_id),
            )
            assert audit_count == 7
            checks.append("seven_immutable_revisions_and_audits")

            # 过期词条可以保存为草稿，但不能送审进入线上。
            expired = await client.patch(
                f"/api/v1/wiki-entries/{entry_id}",
                json={
                    **payload,
                    "expected_version": 7,
                    "valid_until": (date.today() - timedelta(days=1)).isoformat(),
                },
            )
            assert expired.status_code == 200
            expired_review = await client.post(
                status_route, json={"status": "review", "expected_version": 8}
            )
            assert expired_review.status_code == 400
            checks.append("expired_publish_rejected")

            await client.post(
                "/api/v1/auth/login", json={"login": prefix + "reader", "password": password}
            )
            client.headers["X-CSRF-Token"] = (await client.get("/api/v1/auth/csrf")).json()[
                "csrf_token"
            ]
            listing = await client.get(route)
            assert listing.status_code == 200 and not listing.json()["can_manage"]
            assert not any(item["id"] == str(entry_id) for item in listing.json()["items"])
            assert (await client.post(route, json=payload)).status_code == 403
            assert (
                await client.get(f"/api/v1/wiki-entries/{entry_id}/revisions")
            ).status_code == 403
            checks.append("reader_cannot_write_or_read_draft_history")
        print(json.dumps({"passed": checks, "count": len(checks)}, ensure_ascii=False))
    finally:
        if entry_ids:
            await connection.execute(
                "DELETE FROM wiki_entries WHERE id=ANY($1::bigint[])", entry_ids
            )
        if users:
            await connection.execute(
                "DELETE FROM retrieval_trace_items WHERE trace_id IN "
                "(SELECT id FROM retrieval_traces WHERE user_id=ANY($1::bigint[]))", users,
            )
            await connection.execute(
                "DELETE FROM retrieval_traces WHERE user_id=ANY($1::bigint[])", users,
            )
            await connection.execute(
                "DELETE FROM audit_logs WHERE actor_id=ANY($1::bigint[])", users
            )
            await connection.execute("DELETE FROM sessions WHERE user_id=ANY($1::bigint[])", users)
            await connection.execute(
                "DELETE FROM tenant_members WHERE user_id=ANY($1::bigint[])", users
            )
            await connection.execute("DELETE FROM users WHERE id=ANY($1::bigint[])", users)
        await connection.close()


if __name__ == "__main__":
    asyncio.run(main())
