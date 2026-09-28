#!/usr/bin/env python3
"""读取 JSONL 留出集并输出 Evidence Recall@K；脚本只读输入，不写线上数据。"""

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
    args = parser.parse_args()
    cases = []
    for line_number, line in enumerate(args.dataset.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            cases.append(case_from_mapping(json.loads(line)))
        except (json.JSONDecodeError, ValueError) as cause:
            raise SystemExit(f"第 {line_number} 行样本无效：{cause}") from cause
    report = evaluate_recall_at_k(cases, k=args.k)
    print(json.dumps(report.__dict__, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
