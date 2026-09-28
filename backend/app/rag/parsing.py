from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Literal
from zipfile import BadZipFile, ZipFile

import pdfplumber
from docx import Document
from lxml.etree import XMLSyntaxError
from markdown_it import MarkdownIt
from pdfminer.pdfexceptions import PDFException
from pdfplumber.utils.exceptions import PdfminerException

MAX_DOCUMENT_SIZE = 50 * 1024 * 1024
MAX_DOCX_ENTRIES = 10_000
MAX_DOCX_EXPANDED_SIZE = 100 * 1024 * 1024
MAX_DOCX_MEMBER_COMPRESSION_RATIO = 1_000
MAX_PDF_PAGES = 500
MAX_PDF_OBJECTS = 100_000
MAX_PDF_STREAMS = 20_000
MAX_PDF_DECLARED_STREAM_SIZE = 64 * 1024 * 1024
MAX_PDF_DECLARED_STREAM_TOTAL = 200 * 1024 * 1024
MAX_PDF_EXTRACTED_TEXT_BYTES = 50 * 1024 * 1024
_PDF_OBJECT_PATTERN = re.compile(rb"(?:^|\n)\s*\d+\s+\d+\s+obj\b")
_PDF_LENGTH_PATTERN = re.compile(rb"/Length\s+(\d+)\b")


@dataclass(frozen=True)
class Block:
    text: str
    section_path: tuple[str, ...]
    locator: dict[str, int]


@dataclass
class ParsedDocument:
    name: str
    sha256: str
    parser: str
    status: Literal["complete", "partial", "unsupported", "failed"] = "complete"
    blocks: list[Block] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def parse_document(path: Path) -> ParsedDocument:
    if path.stat().st_size > MAX_DOCUMENT_SIZE:
        raise ValueError("FILE_TOO_LARGE")
    raw = path.read_bytes()
    suffix = path.suffix.lower()
    result = ParsedDocument(path.name, hashlib.sha256(raw).hexdigest(), f"{suffix}:v1")
    try:
        if suffix in {".md", ".txt"}:
            text = raw.decode("utf-8-sig")
            if "\x00" in text or "\ufffd" in text:
                raise ValueError("INVALID_TEXT")
            if suffix == ".txt":
                result.blocks = [
                    Block(line, (), {"line_start": i, "line_end": i})
                    for i, line in enumerate(text.splitlines(), 1)
                    if line.strip()
                ]
            else:
                _markdown(text, result)
        elif suffix == ".docx":
            _docx(raw, result)
        elif suffix == ".pdf":
            _pdf(raw, result)
        else:
            result.status = "unsupported"
            result.warnings.append("UNSUPPORTED_FORMAT")
    except (
        ValueError,
        UnicodeError,
        BadZipFile,
        PDFException,
        PdfminerException,
        XMLSyntaxError,
        KeyError,
    ):
        result.status = "failed"
        result.blocks.clear()
        result.warnings.append("INVALID_OR_DAMAGED_DOCUMENT")
    if not result.blocks and result.status == "complete":
        result.status = "unsupported"
        result.warnings.append("EMPTY_TEXT")
    elif result.warnings and result.status == "complete":
        result.status = "partial"
    return result


def _markdown(text: str, result: ParsedDocument) -> None:
    tokens = MarkdownIt("commonmark").parse(text)
    headings: list[tuple[int, str]] = []
    lines = text.splitlines()
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            level = int(token.tag[1:])
            while headings and headings[-1][0] >= level:
                headings.pop()
            headings.append((level, tokens[index + 1].content))
        if token.type == "html_block":
            result.warnings.append(f"HTML_NOT_INTERPRETED:{token.map}")
        if token.type not in {"inline", "fence", "code_block", "html_block"}:
            continue
        if token.map and token.content.strip():
            start, end = token.map
            result.blocks.append(
                Block(
                    "\n".join(lines[start:end]),
                    tuple(h[1] for h in headings),
                    {"line_start": start + 1, "line_end": end},
                )
            )


def _docx(raw: bytes, result: ParsedDocument) -> None:
    _validate_docx_container(raw)
    document = Document(BytesIO(raw))
    if document.tables or document.inline_shapes:
        result.warnings.append("TABLES_OR_IMAGES_NOT_EXTRACTED")
    heading: tuple[str, ...] = ()
    for i, paragraph in enumerate(document.paragraphs, 1):
        if not paragraph.text.strip():
            continue
        if paragraph.style and paragraph.style.name.startswith("Heading"):
            heading = (paragraph.text,)
        result.blocks.append(Block(paragraph.text, heading, {"paragraph": i}))


def _pdf(raw: bytes, result: ParsedDocument) -> None:
    _validate_pdf_container(raw)
    extracted_text_bytes = 0
    with pdfplumber.open(BytesIO(raw)) as pdf:
        if len(pdf.pages) > MAX_PDF_PAGES:
            raise ValueError("PAGE_LIMIT")
        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            extracted_text_bytes += len(text.encode("utf-8"))
            if extracted_text_bytes > MAX_PDF_EXTRACTED_TEXT_BYTES:
                raise ValueError("PDF_TEXT_LIMIT")
            if len(text.strip()) < 20:
                result.warnings.append(f"LOW_TEXT_PAGE:{i}")
            if page.find_tables():
                result.warnings.append(f"TABLE_LAYOUT_UNVERIFIED:{i}")
            if text.strip():
                result.blocks.append(Block(text, (), {"page": i}))


def validate_document_container(raw: bytes, suffix: str) -> None:
    """在上传落盘前验证容器元数据，避免把压缩炸弹交给异步解析器。"""
    if suffix == ".docx":
        _validate_docx_container(raw)
    elif suffix == ".pdf":
        _validate_pdf_container(raw)


def _validate_docx_container(raw: bytes) -> None:
    """验证 DOCX ZIP 的成员边界、压缩比和 Office 必需文件。"""
    try:
        with ZipFile(BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_DOCX_ENTRIES:
                raise ValueError("UNSAFE_ARCHIVE_ENTRY_COUNT")
            expanded_size = 0
            for entry in entries:
                normalized_name = entry.filename.replace("\\", "/")
                if normalized_name.startswith("/") or ".." in normalized_name.split("/"):
                    raise ValueError("UNSAFE_ARCHIVE_PATH")
                if entry.flag_bits & 0x1:
                    raise ValueError("ENCRYPTED_DOCX")
                expanded_size += entry.file_size
                if expanded_size > MAX_DOCX_EXPANDED_SIZE:
                    raise ValueError("UNSAFE_ARCHIVE_SIZE")
                if entry.file_size > 1 * 1024 * 1024:
                    compressed_size = max(entry.compress_size, 1)
                    if entry.file_size / compressed_size > MAX_DOCX_MEMBER_COMPRESSION_RATIO:
                        raise ValueError("UNSAFE_ARCHIVE_RATIO")
            members = {entry.filename for entry in entries}
    except BadZipFile as error:
        raise ValueError("INVALID_DOCX") from error
    if not {"[Content_Types].xml", "word/document.xml"}.issubset(members):
        raise ValueError("INVALID_DOCX")


def _validate_pdf_container(raw: bytes) -> None:
    """验证 PDF 的轻量结构边界，避免异常对象和流元数据放大解析成本。"""
    if not raw.startswith(b"%PDF-"):
        raise ValueError("INVALID_PDF")
    object_count = len(_PDF_OBJECT_PATTERN.findall(raw))
    stream_count = len(re.findall(rb"\bstream\r?\n", raw))
    if object_count > MAX_PDF_OBJECTS or stream_count > MAX_PDF_STREAMS:
        raise ValueError("UNSAFE_PDF_STRUCTURE")
    declared_lengths = [int(value) for value in _PDF_LENGTH_PATTERN.findall(raw)]
    if any(length > MAX_PDF_DECLARED_STREAM_SIZE for length in declared_lengths):
        raise ValueError("UNSAFE_PDF_STREAM")
    if sum(declared_lengths) > MAX_PDF_DECLARED_STREAM_TOTAL:
        raise ValueError("UNSAFE_PDF_STREAM")
