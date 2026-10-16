"""章节抽取回归：证据范围、原文保真、重复概念、跨库访问及旧预览保护。"""

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.rag.wiki_extraction import extract_candidates, normalized_term, preview_extraction


def chunk(number, text):
    """测试来源携带稳定版本和页码，用于验证不会跨章节关联。"""
    return {
        "chunk_id": str(number),
        "document_version_id": "7",
        "content": text,
        "document_id": "3",
        "document_title": "规范",
        "version_no": 1,
        "locator": {"page": number},
    }


def test_section_evidence_does_not_mix_child_and_tcm():
    """章节明确分界后，儿童健康草稿不得引用儿童中医药来源。"""
    items = extract_candidates(
        [
            chunk(33, "0～6 岁儿童健康管理服务规范\n服务对象：常住儿童"),
            chunk(34, "（五）健康问题处理\n及时转诊"),
            chunk(91, "0～36个月儿童中医药健康管理服务\n中医饮食指导"),
        ],
        "公卫规范",
    )
    assert len(items) == 2
    assert [s["chunk_id"] for s in items[0]["sources"]] == ["33", "34"]
    assert [s["chunk_id"] for s in items[1]["sources"]] == ["91"]
    assert "及时转诊" in items[0]["definition"]
    assert "中医饮食" not in items[0]["definition"]
    assert items[0]["key"] != items[1]["key"]


def test_markdown_and_plain_document_keep_verbatim_definition():
    """Markdown章节和无标题文档均可提取，摘要只能由原文组成。"""
    items = extract_candidates(
        [chunk(1, "## 布局\n侧栏240px"), chunk(2, "## 字体\n正文14px")], "设计"
    )
    assert [i["term"] for i in items] == ["布局", "字体"]
    assert items[0]["definition"] == "## 布局\n侧栏240px"
    plain = extract_candidates([chunk(3, "工作日8点到17点")], "客服规则")
    assert plain[0]["term"] == "客服规则"
    assert plain[0]["definition"] == "工作日8点到17点"


def test_evidence_limit_is_explicit_and_toc_not_a_heading():
    """超长章节明确告知截断；目录点线不产生伪候选。"""
    rows = [chunk(1, "居民健康管理服务规范......1")]
    rows += [chunk(i, "原文内容") for i in range(2, 34)]
    items = extract_candidates(rows, "文档")
    assert len(items) == 1 and len(items[0]["sources"]) == 30
    assert items[0]["warning"]
    assert normalized_term("0～6 岁儿童健康管理服务规范") == normalized_term(
        "0～6岁儿童健康管理服务"
    )


def test_preview_requires_current_release_and_detects_existing():
    """只接受可用的本库发布文档，预览不会执行数据库写操作。"""
    connection = AsyncMock()
    connection.fetchrow.return_value = {
        "active_release_id": 5,
        "document_version_id": 7,
        "title": "规范",
    }
    connection.fetch.side_effect = [
        [chunk(33, "儿童健康管理服务规范\n原文")],
        [{"term": "儿童健康管理服务"}],
    ]
    result = asyncio.run(preview_extraction(connection, 1, 4, 3))
    assert result["items"][0]["existing"] is True
    connection.execute.assert_not_called()
    connection.fetchrow.return_value = None
    with pytest.raises(HTTPException) as error:
        asyncio.run(preview_extraction(connection, 1, 4, 999))
    assert error.value.status_code == 404


def test_extraction_routes_reject_reader_before_reading_sources(monkeypatch):
    """普通读者不能生成/导入，复用知识库写权限且失败时不读取原文。"""
    connection = AsyncMock()
    monkeypatch.setattr(
        "app.main._authenticated_user", AsyncMock(return_value={"user": {"id": "1"}})
    )
    monkeypatch.setattr("app.main._database", AsyncMock(return_value=connection))
    monkeypatch.setattr(
        "app.main._require_knowledge_base_role", AsyncMock(side_effect=HTTPException(403))
    )
    with TestClient(create_app(Settings())) as client:
        assert (
            client.post(
                "/api/v1/knowledge-bases/4/wiki-extraction-preview", json={"document_id": 7}
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/v1/knowledge-bases/4/wiki-extraction-import",
                json={
                    "document_id": 7,
                    "release_id": 5,
                    "document_version_id": 7,
                    "candidate_keys": ["anything"],
                },
            ).status_code
            == 403
        )
    connection.fetch.assert_not_called()
    connection.execute.assert_not_called()
