"""验证文档版本对比按切片识别新增、删除和变更内容。"""

from app.main import _version_diff


def test_version_diff_reports_chunk_operations_and_short_previews() -> None:
    """差异结果应保留序号和截断摘要，不返回无限长正文。"""
    result = _version_diff(
        [{"ordinal": 1, "content": "same"}, {"ordinal": 2, "content": "old"}],
        [
            {"ordinal": 1, "content": "same"},
            {"ordinal": 3, "content": "new"},
            {"ordinal": 4, "content": "added"},
        ],
    )
    assert result["before_chunk_count"] == 2
    assert result["after_chunk_count"] == 3
    assert result["changed_chunks"] + result["added_chunks"] + result["removed_chunks"] >= 1
    assert all(
        len(preview) <= 240 for change in result["changes"] for preview in change["after_preview"]
    )
