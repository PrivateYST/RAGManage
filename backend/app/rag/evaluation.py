"""离线检索评测工具：对留出集计算 Evidence Recall@K，不参与线上请求路径。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class RecallCase:
    """单条评测样本；expected_ids 是人工标注的可接受证据集合。"""

    case_id: str
    expected_ids: frozenset[str]
    retrieved_ids: tuple[str, ...]


@dataclass(frozen=True)
class RecallReport:
    """评测汇总，保留未召回样本便于定位资料或切片问题。"""

    k: int
    case_count: int
    hit_count: int
    recall_at_k: float
    misses: tuple[str, ...]


def evaluate_recall_at_k(cases: Iterable[RecallCase], *, k: int = 10) -> RecallReport:
    """计算“前 K 条结果是否命中任一标注证据”的样本级 Recall。"""
    if k <= 0:
        raise ValueError("k 必须大于 0")
    materialized = tuple(cases)
    misses: list[str] = []
    hit_count = 0
    for case in materialized:
        if set(case.retrieved_ids[:k]) & case.expected_ids:
            hit_count += 1
        else:
            misses.append(case.case_id)
    total = len(materialized)
    return RecallReport(
        k=k,
        case_count=total,
        hit_count=hit_count,
        recall_at_k=round(hit_count / total, 4) if total else 0.0,
        misses=tuple(misses),
    )


def case_from_mapping(value: dict[str, object]) -> RecallCase:
    """将 JSONL 样本转换为强类型样本，并拒绝缺少标注的记录。"""
    case_id = str(value.get("case_id", "")).strip()
    expected = value.get("expected_document_ids")
    retrieved = value.get("retrieved_document_ids", [])
    if not case_id or not isinstance(expected, list) or not expected:
        raise ValueError("样本必须包含 case_id 和非空 expected_document_ids")
    if not isinstance(retrieved, list):
        raise ValueError("retrieved_document_ids 必须是数组")
    return RecallCase(
        case_id,
        frozenset(str(item) for item in expected),
        tuple(str(item) for item in retrieved),
    )
