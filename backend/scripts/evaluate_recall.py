#!/usr/bin/env python3
"""读取 JSONL 评测集并输出 RAG 质量基线；脚本只读输入，不写线上数据。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.rag.evaluation import case_from_mapping, evaluate_recall_at_k


def main() -> None:
    """执行离线评测并打印可归档的 JSON 报告。"""
    parser = argparse.ArgumentParser(description="Evaluate Evidence Recall@K from JSONL")
    parser.add_argument("dataset", type=Path, help="JSONL 留出集路径")
    parser.add_argument("--k", type=int, default=10, help="评测前 K 条结果，默认 10")
    parser.add_argument("--split", help="只评测指定 split，例如 holdout")
    parser.add_argument("--category", help="只评测指定问题类型")
    args = parser.parse_args()
    cases = []
    for line_number, line in enumerate(args.dataset.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            cases.append(case_from_mapping(json.loads(line)))
        except (json.JSONDecodeError, ValueError) as cause:
            raise SystemExit(f"第 {line_number} 行样本无效：{cause}") from cause
    if args.split:
        cases = [case for case in cases if case.split == args.split]
    if args.category:
        cases = [case for case in cases if case.category == args.category]
    report = evaluate_recall_at_k(cases, k=args.k)
    print(json.dumps(report.__dict__, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
