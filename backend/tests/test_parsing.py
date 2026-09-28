import io
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from docx import Document

from app.rag.parsing import (
    MAX_DOCX_EXPANDED_SIZE,
    MAX_DOCX_MEMBER_COMPRESSION_RATIO,
    MAX_PDF_DECLARED_STREAM_SIZE,
    parse_document,
    validate_document_container,
)


def _docx_fixture(document_xml: bytes = b"<document>safe text</document>") -> bytes:
    """构造包含 DOCX 必需成员的测试容器，便于复现元数据边界。"""
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", b"<Types/>")
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def test_markdown_preserves_evidence_location(tmp_path: Path) -> None:
    path = tmp_path / "rules.md"
    path.write_text("# Booking\n\n## Time\n\nSeven days.\n", encoding="utf-8")
    parsed = parse_document(path)
    block = parsed.blocks[-1]
    assert parsed.status == "complete"
    assert block.section_path == ("Booking", "Time")
    assert block.locator == {"line_start": 5, "line_end": 5}
    assert block.text == "Seven days."


def test_invalid_and_empty_text_are_not_complete(tmp_path: Path) -> None:
    path = tmp_path / "input.txt"
    path.write_bytes(b"\xff\x00")
    assert parse_document(path).status == "failed"
    path.write_bytes(b"")
    assert parse_document(path).status == "unsupported"


def test_raw_html_is_flagged_not_silently_dropped(tmp_path: Path) -> None:
    path = tmp_path / "input.md"
    path.write_text("<script>alert(1)</script>\n", encoding="utf-8")
    parsed = parse_document(path)
    assert parsed.status == "partial"
    assert parsed.warnings


def test_invalid_pdf_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "input.pdf"
    path.write_bytes(b"not a pdf")
    assert parse_document(path).status == "failed"


def test_damaged_pdf_with_valid_signature(tmp_path: Path) -> None:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.7\nnot a document")
    assert parse_document(path).status == "failed"


def test_docx_expanded_size_limit_is_enforced(tmp_path: Path) -> None:
    """DOCX 声明展开总量超过上限时，解析器必须在读取 XML 前失败。"""
    path = tmp_path / "expanded.docx"
    path.write_bytes(_docx_fixture(b"x" * (MAX_DOCX_EXPANDED_SIZE + 1)))

    assert parse_document(path).status == "failed"
    assert "INVALID_OR_DAMAGED_DOCUMENT" in parse_document(path).warnings


def test_docx_member_compression_ratio_is_bounded() -> None:
    """单个高压缩比成员即使总量不大也应被识别为压缩炸弹。"""
    payload = b"a" * (MAX_DOCX_MEMBER_COMPRESSION_RATIO * 2 * 1024)
    try:
        validate_document_container(_docx_fixture(payload), ".docx")
    except ValueError as error:
        assert str(error) == "UNSAFE_ARCHIVE_RATIO"
    else:
        raise AssertionError("高压缩比 DOCX 必须拒绝")


def test_docx_archive_path_traversal_is_rejected() -> None:
    """DOCX 中的绝对或父目录成员名必须在解压前被拒绝。"""
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
        archive.writestr("../outside.xml", "untrusted")

    try:
        validate_document_container(buffer.getvalue(), ".docx")
    except ValueError as error:
        assert str(error) == "UNSAFE_ARCHIVE_PATH"
    else:
        raise AssertionError("越界 ZIP 路径必须拒绝")


def test_pdf_declared_stream_limit_is_enforced() -> None:
    """PDF 流长度超过单流上限时应在 PDF 库开始解析前拒绝。"""
    raw = f"%PDF-1.7\n1 0 obj\n<< /Length {MAX_PDF_DECLARED_STREAM_SIZE + 1} >>\nendobj".encode()

    try:
        validate_document_container(raw, ".pdf")
    except ValueError as error:
        assert str(error) == "UNSAFE_PDF_STREAM"
    else:
        raise AssertionError("超大 PDF 流声明必须拒绝")


def test_docx_tables_require_review(tmp_path: Path) -> None:
    path = tmp_path / "rules.docx"
    document = Document()
    document.add_heading("Rules", level=1)
    document.add_paragraph("Booking policy")
    document.add_table(rows=1, cols=1).cell(0, 0).text = "Unverified table"
    document.save(str(path))
    parsed = parse_document(path)
    assert parsed.status == "partial"
    assert parsed.blocks[-1].locator == {"paragraph": 2}
    assert parsed.blocks[-1].section_path == ("Rules",)


def test_sample_corpus_preserves_every_source() -> None:
    directory = Path(__file__).resolve().parents[2] / "frontend/docs/knowledgeBase"
    if not directory.is_dir():
        import pytest

        pytest.skip("Local pilot corpus is not distributed in CI")
    paths = sorted(directory.glob("*.md"))
    assert paths
    for path in paths:
        result = parse_document(path)
        assert result.status == "complete", path.name
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        for block in result.blocks:
            start, end = block.locator["line_start"], block.locator["line_end"]
            assert block.text == "\n".join(lines[start - 1 : end])
