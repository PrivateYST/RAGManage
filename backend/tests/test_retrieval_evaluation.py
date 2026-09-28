"""离线 Evidence Recall@K 评测的边界回归，防止结果截断或空数据误报。"""

import pytest

from app.rag.evaluation import RecallCase, evaluate_recall_at_k


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
