# 评测资料与 P0 质量基线

真实业务原文已提供：`frontend/knowledgeBase/《国家基本公共卫生服务规范》第三版.pdf`。
`public-health-p0-review.md` 是基于该 PDF 整理的人工审核题集，不是最终金标准。
正式 JSONL 仍放在被 Git 忽略的 `private/` 中；必须在真实检索/问答链路回填结果后建立 pilot.jsonl，不能用空字段或虚构结果替代真实效果验收。
每条问题需记录 id、split（tuning/holdout）、question、知识库/身份范围、
source_version、证据位置、答案要点或无答案标签、评分规则。

离线脚本的 JSONL 最小字段为 `case_id`、`expected_document_ids`、
`retrieved_document_ids`。为了生成完整 P0 基线，建议同时记录：

- `category`：common、multi_document、no_answer、version_conflict、permission；
- `citation_document_ids`：回答实际引用的文档集合；
- `should_refuse` 与 `refused`：人工标注和系统实际拒答结果；
- `latency_ms`：从请求开始到最终结果的端到端耗时。

当前候选题集覆盖 common、multi_document、no_answer、version_conflict、permission 五类，共 20 题；题目、页码证据和答案要点见 `public-health-p0-review.md`。

执行示例：

```powershell
python backend/scripts/evaluate_recall.py .\private\pilot.jsonl --k 10
python backend/scripts/evaluate_recall.py .\private\pilot.jsonl --k 10 --split holdout --category no_answer
```

报告中的 `misses` 用于回查切片、元数据、版本、权限过滤或标注质量；真实资料和标注放在被 Git 忽略的 `private/` 中，不在仓库内生成虚构业务题目。
