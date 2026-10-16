"""离线 RAG 评测工具；只消费评测样本，不参与线上请求路径。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import ceil, isfinite
from typing import Any


@dataclass(frozen=True)
class RecallCase:
    """单条评测样本；旧的三字段构造方式继续兼容。"""

    case_id: str
    expected_ids: frozenset[str]
    retrieved_ids: tuple[str, ...]
    citation_ids: tuple[str, ...] = ()
    should_refuse: bool | None = None
    refused: bool | None = None
    latency_ms: float | None = None
    category: str = "uncategorized"
    split: str = "holdout"


@dataclass(frozen=True)
class RecallReport:
    """评测汇总；保留差距样本和分组指标，便于回查数据与检索策略。"""

    k: int
    case_count: int
    recall_case_count: int
    hit_count: int
    recall_at_k: float
    misses: tuple[str, ...]
    citation_case_count: int = 0
    citation_supported_count: int = 0
    citation_support_rate: float = 0.0
    refusal_case_count: int = 0
    refusal_correct_count: int = 0
    refusal_accuracy: float = 0.0
    latency_count: int = 0
    latency_p50_ms: float | None = None
    latency_p95_ms: float | None = None
    grouped: dict[str, dict[str, Any]] | None = None


def evaluate_recall_at_k(cases: Iterable[RecallCase], *, k: int = 10) -> RecallReport:
    """计算召回、引用支持、拒答、延迟及按类别/数据集分组指标。"""
    if k <= 0:
        raise ValueError("k 必须大于 0")
    materialized = tuple(cases)
    misses: list[str] = []
    hit_count = 0
    citation_cases = citation_supported = refusal_cases = refusal_correct = 0
    latencies: list[float] = []
    for case in materialized:
        if case.expected_ids:
            if set(case.retrieved_ids[:k]) & case.expected_ids:
                hit_count += 1
            else:
                misses.append(case.case_id)
        citation_applicable = bool(case.citation_ids) or (
            case.should_refuse is False and case.refused is False
        )
        if citation_applicable:
            citation_cases += 1
            if case.citation_ids and set(case.citation_ids).issubset(case.expected_ids):
                citation_supported += 1
        if case.should_refuse is not None and case.refused is not None:
            refusal_cases += 1
            refusal_correct += int(case.should_refuse == case.refused)
        if case.latency_ms is not None:
            if not isfinite(case.latency_ms) or case.latency_ms < 0:
                raise ValueError("latency_ms 必须是有限的非负数")
            latencies.append(case.latency_ms)
    total = len(materialized)
    recall_total = sum(bool(case.expected_ids) for case in materialized)
    grouped = _group_metrics(materialized, k=k)
    return RecallReport(
        k=k,
        case_count=total,
        recall_case_count=recall_total,
        hit_count=hit_count,
        recall_at_k=round(hit_count / recall_total, 4) if recall_total else 0.0,
        misses=tuple(misses),
        citation_case_count=citation_cases,
        citation_supported_count=citation_supported,
        citation_support_rate=_rate(citation_supported, citation_cases),
        refusal_case_count=refusal_cases,
        refusal_correct_count=refusal_correct,
        refusal_accuracy=_rate(refusal_correct, refusal_cases),
        latency_count=len(latencies),
        latency_p50_ms=_percentile(latencies, 0.50),
        latency_p95_ms=_percentile(latencies, 0.95),
        grouped=grouped,
    )


def case_from_mapping(value: dict[str, object]) -> RecallCase:
    """将扩展 JSONL 样本转换为强类型样本，并拒绝缺少核心标注的记录。"""
    case_id = str(value.get("case_id", "")).strip()
    expected = value.get("expected_document_ids")
    retrieved = value.get("retrieved_document_ids", [])
    if not case_id or not isinstance(expected, list):
        raise ValueError("样本必须包含 case_id 和 expected_document_ids")
    if not isinstance(retrieved, list):
        raise ValueError("retrieved_document_ids 必须是数组")
    citations = value.get("citation_document_ids", [])
    if not isinstance(citations, list):
        raise ValueError("citation_document_ids 必须是数组")
    should_refuse = _optional_bool(value.get("should_refuse"), "should_refuse")
    refused = _optional_bool(value.get("refused"), "refused")
    latency = value.get("latency_ms")
    if latency is not None and (isinstance(latency, bool) or not isinstance(latency, (int, float))):
        raise ValueError("latency_ms 必须是数字")
    category = _optional_text(value.get("category"), "category") or "uncategorized"
    split = _optional_text(value.get("split"), "split") or "holdout"
    return RecallCase(
        case_id,
        frozenset(str(item) for item in expected),
        tuple(str(item) for item in retrieved),
        tuple(str(item) for item in citations),
        should_refuse,
        refused,
        float(latency) if latency is not None else None,
        category,
        split,
    )


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, ceil(percentile * len(ordered)) - 1)], 2)


def _optional_bool(value: object, field: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{field} 必须是布尔值")
    return value


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} 必须是非空字符串")
    return value.strip()


def _group_metrics(cases: tuple[RecallCase, ...], *, k: int) -> dict[str, dict[str, Any]]:
    """按 split/category 汇总，避免整体均值掩盖某类问题。"""
    groups: dict[str, list[RecallCase]] = {}
    for case in cases:
        for dimension, value in (("split", case.split), ("category", case.category)):
            groups.setdefault(f"{dimension}:{value}", []).append(case)
    result: dict[str, dict[str, Any]] = {}
    for name, members in groups.items():
        recall_members = [case for case in members if case.expected_ids]
        hits = sum(bool(set(case.retrieved_ids[:k]) & case.expected_ids) for case in recall_members)
        citation_members = [
            case
            for case in members
            if case.citation_ids or (case.should_refuse is False and case.refused is False)
        ]
        refusal_members = [
            case
            for case in members
            if case.should_refuse is not None and case.refused is not None
        ]
        result[name] = {
            "case_count": len(members),
            "recall_case_count": len(recall_members),
            "hit_count": hits,
            "recall_at_k": _rate(hits, len(recall_members)),
            "citation_support_rate": _rate(
                sum(
                    bool(case.citation_ids)
                    and set(case.citation_ids).issubset(case.expected_ids)
                    for case in citation_members
                ),
                len(citation_members),
            ),
            "refusal_accuracy": _rate(
                sum(case.should_refuse == case.refused for case in refusal_members),
                len(refusal_members),
            ),
        }
    return result
