# Evidence Recall@10 留出集

离线评测脚本用于验证正式检索是否在前 10 条证据中召回人工标注的正确文档，不会写入线上数据库，也不会修改 Release。

每行 JSONL 是一条样本：

```json
{"case_id":"discharge-001","query":"出院结算需要什么材料？","expected_document_ids":["document-13"],"retrieved_document_ids":["document-21","document-13"]}
```

在仓库根目录执行：

```powershell
python backend/scripts/evaluate_recall.py .\path\to\holdout.jsonl --k 10
```

输出中的 `recall_at_k` 是命中样本数除以样本总数；`misses` 列出未命中的 `case_id`，用于回查切片、发布版本或标注质量。
