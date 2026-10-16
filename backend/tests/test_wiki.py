"""P2 Wiki 回归：验证审核边界、别名匹配与来源隔离，防止草稿影响线上检索。"""

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app
from app.rag.wiki import (
    WikiContent,
    lookup_entries,
    match_entries,
    validate_content,
    validate_transition,
)


@pytest.mark.parametrize(
    "before,after",
    [
        ("draft", "review"),
        ("review", "published"),
        ("review", "draft"),
        ("published", "retired"),
        ("retired", "draft"),
    ],
)
def test_allowed_lifecycle(before, after):
    """每条允许路径都有明确状态，不能绕过审核直接发布。"""
    validate_transition(before, after)


@pytest.mark.parametrize(
    "before,after",
    [
        ("draft", "published"),
        ("published", "published"),
        ("retired", "published"),
    ],
)
def test_rejects_shortcuts_and_duplicate_publish(before, after):
    """重复发布和跳过审核返回冲突，让用户刷新状态。"""
    with pytest.raises(HTTPException) as error:
        validate_transition(before, after)
    assert error.value.status_code == 409


def test_aliases_normalize_and_longest_term_wins():
    """全角英文和中文别名均可匹配，最长名称排序优先且只取三个词条。"""
    entries = [
        {"id": "1", "term": "儿童健康", "aliases": ["儿保"], "chunk_ids": [21]},
        {"id": "2", "term": "0～6岁儿童健康管理服务", "aliases": ["儿童健康"], "chunk_ids": [22]},
        {"id": "3", "term": "RAG", "aliases": [], "chunk_ids": [23]},
    ]
    assert match_entries("0～6岁儿童健康管理服务包括哪些？", entries)[0]["id"] == "2"
    assert match_entries("解释 ＲＡＧ", entries)[0]["id"] == "3"
    assert match_entries("storage", entries) == []
    assert match_entries("如何办理出院", entries) == []


@pytest.mark.parametrize(
    "payload",
    [
        {"term": "  ", "definition": "定义"},
        {"term": "儿童", "definition": "   "},
        {"term": "儿童", "definition": "定义", "aliases": ["a"]},
        {
            "term": "儿童",
            "definition": "定义",
            "valid_from": "2026-10-02",
            "valid_until": "2026-10-01",
        },
        {"term": "儿童", "definition": "定义", "sources": [{"chunk_id": 2}, {"chunk_id": 2}]},
    ],
)
def test_rejects_invalid_content(payload):
    """拒绝空名称、空定义、反向有效期和重复来源，减少不可发布草稿。"""
    with pytest.raises(ValidationError):
        WikiContent(**payload)


def test_owner_and_cross_scope_source_validation():
    """有效成员校验先于写入；同库查询无结果时拒绝跨库/失效来源。"""
    connection = AsyncMock()
    connection.fetchval.return_value = False
    payload = WikiContent(term="儿童健康", definition="定义", owner_user_id=9)
    with pytest.raises(HTTPException):
        asyncio.run(validate_content(connection, 7, 8, payload))
    connection.fetchrow.assert_not_called()
    connection.fetchval.return_value = True
    connection.fetchrow.return_value = None
    payload = WikiContent(term="儿童健康", definition="定义", sources=[{"chunk_id": 999}])
    with pytest.raises(HTTPException):
        asyncio.run(validate_content(connection, 7, 8, payload))
    sql, *args = connection.fetchrow.call_args.args
    assert args == [999, 7, 8]
    assert "c.tenant_id=$2" in sql and "c.knowledge_base_id=$3" in sql


def test_lookup_excludes_unreviewed_expired_and_other_releases():
    """词条查找必须包含空间、发布状态、有效期和当前 Release 证据约束。"""
    connection = AsyncMock()
    connection.fetch.return_value = [
        {"id": "1", "term": "儿童健康", "aliases": ["儿保"], "chunk_ids": [21]},
    ]
    matches = asyncio.run(
        lookup_entries(
            connection,
            tenant_id=7,
            knowledge_base_id=8,
            release_id=9,
            query="儿保内容",
        )
    )
    assert matches[0]["term"] == "儿童健康"
    sql, *args = connection.fetch.call_args.args
    assert args == [7, 8, 9]
    for guard in [
        "e.tenant_id=$1",
        "e.knowledge_base_id=$2",
        "e.status='published'",
        "valid_from <= CURRENT_DATE",
        "valid_until >= CURRENT_DATE",
        "ri.release_id=$3",
        "d.status='active'",
        "d.deleted_at IS NULL",
    ]:
        assert guard in sql


def test_wiki_read_and_write_routes_enforce_existing_kb_access(monkeypatch):
    """越权请求不应读取词条列表或创建内容，复用 KB 授权统一返回拒绝。"""
    context = {"user": {"id": "7"}, "spaces": []}
    connection = AsyncMock()
    monkeypatch.setattr("app.main._authenticated_user", AsyncMock(return_value=context))
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr(
        "app.main._knowledge_base_access", AsyncMock(side_effect=HTTPException(404))
    )
    monkeypatch.setattr(
        "app.main._require_knowledge_base_role", AsyncMock(side_effect=HTTPException(403))
    )
    with TestClient(create_app(Settings())) as client:
        assert client.get("/api/v1/knowledge-bases/9/wiki-entries").status_code == 404
        assert (
            client.post(
                "/api/v1/knowledge-bases/9/wiki-entries",
                json={
                    "term": "儿童健康",
                    "definition": "定义",
                },
            ).status_code
            == 403
        )
    connection.fetch.assert_not_called()
    connection.execute.assert_not_called()
