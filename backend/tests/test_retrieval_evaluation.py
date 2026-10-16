"""离线 Evidence Recall@K 评测的边界回归，防止结果截断或空数据误报。"""

import pytest

from app.rag.evaluation import RecallCase, case_from_mapping, evaluate_recall_at_k


def test_recall_at_k_counts_a_hit_only_inside_top_k() -> None:
    report = evaluate_recall_at_k(
        [
            RecallCase("hit", frozenset({"doc-1"}), ("doc-1",)),
            RecallCase("miss", frozenset({"doc-2"}), ("doc-3", "doc-2")),
        ],
        k=1,
    )
    assert report.recall_at_k == 0.5
    assert report.misses == ("miss",)


def test_recall_rejects_non_positive_k_and_handles_empty_set() -> None:
    assert evaluate_recall_at_k([], k=10).recall_at_k == 0
    with pytest.raises(ValueError, match="大于 0"):
        evaluate_recall_at_k([], k=0)


def test_quality_baseline_reports_citations_refusal_latency_and_groups() -> None:
    report = evaluate_recall_at_k(
        [
            RecallCase(
                "answered",
                frozenset({"doc-1"}),
                ("doc-1",),
                citation_ids=("doc-1",),
                should_refuse=False,
                refused=False,
                latency_ms=100,
                category="common",
            ),
            RecallCase(
                "refused",
                frozenset({"doc-2"}),
                (),
                should_refuse=True,
                refused=True,
                latency_ms=300,
                category="no_answer",
            ),
        ],
        k=10,
    )
    assert report.recall_at_k == 0.5
    assert report.citation_support_rate == 1.0
    assert report.refusal_accuracy == 1.0
    assert report.latency_p50_ms == 100
    assert report.latency_p95_ms == 300
    assert report.grouped is not None
    assert report.grouped["category:common"]["recall_at_k"] == 1.0


def test_quality_baseline_rejects_negative_latency() -> None:
    with pytest.raises(ValueError, match="有限的非负数"):
        evaluate_recall_at_k(
            [RecallCase("bad", frozenset({"doc"}), (), latency_ms=-1)],
        )


def test_answer_without_citations_counts_as_unsupported() -> None:
    report = evaluate_recall_at_k(
        [
            RecallCase(
                "uncited-answer",
                frozenset({"doc-1"}),
                ("doc-1",),
                should_refuse=False,
                refused=False,
            )
        ]
    )
    assert report.citation_case_count == 1
    assert report.citation_support_rate == 0.0


def test_no_answer_case_can_have_empty_expected_documents() -> None:
    case = case_from_mapping(
        {
            "case_id": "no-answer",
            "expected_document_ids": [],
            "retrieved_document_ids": [],
            "should_refuse": True,
            "refused": True,
            "category": "no_answer",
        }
    )
    report = evaluate_recall_at_k([case])
    assert report.case_count == 1
    assert report.recall_case_count == 0
    assert report.refusal_accuracy == 1.0
