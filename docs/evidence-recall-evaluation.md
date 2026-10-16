# Evidence Recall@10 留出集

离线评测脚本用于验证正式检索质量，不会写入线上数据库，也不会修改 Release。报告输出 Recall@K、引用文档匹配率、拒答准确率、P50/P95 延迟、分组指标和未命中样本。

每行 JSONL 是一条样本：

```json
{"case_id":"discharge-001","split":"holdout","category":"common","query":"出院结算需要什么材料？","expected_document_ids":["document-13"],"retrieved_document_ids":["document-21","document-13"],"citation_document_ids":["document-13"],"should_refuse":false,"refused":false,"latency_ms":842}
```

在仓库根目录执行：

```powershell
python backend/scripts/evaluate_recall.py .\path\to\holdout.jsonl --k 10

# 只查看留出集中的某一类问题
python backend/scripts/evaluate_recall.py .\path\to\pilot.jsonl --k 10 --split holdout --category no_answer
```

字段约定：`case_id`、`expected_document_ids`、`retrieved_document_ids` 为核心字段；`split`、`category`、`citation_document_ids`、`should_refuse`、`refused` 和 `latency_ms` 用于扩展指标。Recall 分母只包含有可接受证据的样本；无答案样本参与拒答准确率，不拉低 Recall。

`citation_support_rate` 当前按人工标注的可接受文档集合计算，是文档级匹配代理，不能替代逐条语义支持性审核。正式验收需要将引用映射到具体证据片段并人工评估结论是否被片段支持。真实资料和标注放在被 Git 忽略的 `private/` 中，仓库不使用虚构业务题目替代真实效果验收。

输出中的 `recall_at_k` 是命中样本数除以有可接受证据的样本数；`misses` 列出未命中的 `case_id`，用于回查切片、发布版本或标注质量。
