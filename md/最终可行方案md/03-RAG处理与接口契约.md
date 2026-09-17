# RAG 处理与接口契约

## 1. 入库契约

输入为文件版本，输出为结构树、chunks、embedding 和可发布清单。

结构块至少包含 type、text、section_path、顺序和 locator。PDF locator 包含原文件页码及可获得的坐标；DOCX 使用标题路径/段落序号，不编造固定页码；Markdown/TXT 使用行号或字符区间。原文件 hash 与解析器版本共同标识定位依据。

解析质量状态为 complete/partial/unsupported/failed。检测空文本、异常乱码、极少文本扫描页和表格遗漏。partial 必须在管理员确认局限后才能纳入 release；unsupported/failed 不允许发布。

切片先按标题和段落，再用 tokenizer 控制长度；合并短段不跨章节；超长段以句子切分，必要时使用有限 overlap。保存原文 content 与实际 embed_text；标题前缀计入 token 预算。

对输入校验 MIME、扩展名、文件头、大小；DOCX 解压限制文件数/总大小，解析 worker 限时限内存且不访问公网。HTML、Office 宏执行不在首版范围。

嵌入输出检查批次条数、维度、有限数值、非零、归一化规则。缓存计算结果的键覆盖 tenant、embed_text hash、模型/revision、指令、维度、归一化及 tokenizer 规则。复用计算不复用来源身份或权限。

## 2. 检索与回答契约

1. 确定 user/tenant/kb 与会话 owner，读取 active release/runtime/profile。
2. 对追问进行有限历史解析；历史必须仍可见。原始 query 与 rewritten_query 同时保存。
3. 向量召回与词法召回使用完全一致的授权和有效内容集合。
4. 候选以 chunk_id 去重。启用 RRF 时按名次融合，公式为各路 `weight/(60+rank)` 求和，rank 从 1 开始；不能直接相加不同量纲原始分数。
5. 若启用重排，只重排受限候选，保存原路分数和重排分数；重排超时默认降级为融合排序并明确记录，严格场景可配置失败关闭。
6. 证据组装按预算与去重处理，保留标题路径和来源编号；可补同一 artifact 邻接块，但补充内容仍需当前授权和 token 检查。
7. 根据评测校准的规则判断是否缺证据。相似度不等于可信概率，不设置跨模型通用阈值。
8. 生成只接收授权上下文和有限历史；遇冲突明确列来源/版本，不擅自推断哪个制度优先。
9. 生成后校验引用编号、来源范围和必要论断支持性；无效引用导致回答标记不可靠或重试一次，不伪造来源。

首版不缓存完整答案或授权后检索结果。可缓存相同 profile 的 query embedding，但检索仍重新检查权限与发布状态。

生成请求保存实际 endpoint/model revision、prompt version、输入证据清单和 token 使用；模型服务无法提供某字段时标注 unknown，不能用配置期望值冒充实测值。

## 3. API 通用规范

- 前缀 `/api/v1`，同源 cookie session；所有写操作校验 CSRF，登录限速。
- UUID request_id；资源 ID 作为字符串；时间为 ISO 8601 UTC。
- 列表使用 cursor/limit（默认 20，最大 100），返回 items/next_cursor。
- 标准错误：`{"error":{"code":"...","message":"...","details":{}},"request_id":"..."}`。
- 状态码：400 参数、401 未认证、403 无权限、404 无可见资源、409 版本冲突、413 大小超限、422 内容不支持、429 容量限制、503 模型/索引不可用。
- 跨租户/未知对象统一 404，避免对象枚举。前端隐藏按钮不能替代服务器授权。
- 写接口支持 Idempotency-Key；作用域含用户/组织/接口，保存 payload hash。相同 key 不同 payload 返回 409。
- 修改资源与发布携带 expected_version/expected_active_release，冲突返回当前版本，不做静默覆盖。

## 4. 接口清单

| 模块 | 方法与路径 | 结果/约束 |
|---|---|---|
| 身份 | POST /auth/login；POST /auth/logout；GET /auth/me | 服务端 session；登出撤销 token |
| 用户 | GET/POST /users；PATCH /users/{id} | 组织管理员创建/停用，不开放公开注册 |
| 知识库 | GET/POST /knowledge-bases；GET/PATCH /knowledge-bases/{kb} | 检查组织与成员，创建默认 dataset |
| 成员 | GET/POST /knowledge-bases/{kb}/members；PATCH/DELETE /.../members/{user} | 管理员，增加 auth_epoch |
| 文档 | GET/POST /knowledge-bases/{kb}/documents | POST multipart，202 返回 document/version/task |
| 文档版本 | POST /documents/{doc}/versions；GET /documents/{doc}/versions | 上传新版本不自动替换线上版本 |
| 文档详情 | GET /documents/{doc}；GET /document-versions/{ver}/preview | 读者仅能看有效发布内容，编辑者可看草稿 |
| 文件 | GET /document-versions/{ver}/download | 每次鉴权；服务端代理，禁止公开静态路径 |
| 切片 | GET /artifacts/{artifact}/chunks | 分页、来源定位；草稿权限同文档 |
| 停用/删除 | POST /documents/{doc}/disable；DELETE /documents/{doc} | 同步屏蔽，异步清理，不暴露越权历史 |
| 任务 | GET /tasks/{task}；POST /tasks/{task}/retry；POST /tasks/{task}/cancel | 仅有管理该资源权限者可操作 |
| 配置 | GET/POST /knowledge-bases/{kb}/runtime-profiles | 新建不可变版本，校验预算/endpoint/model |
| 配置激活 | POST /knowledge-bases/{kb}/activate-runtime | expected_version + runtime_id，验证索引兼容性 |
| 索引配置 | POST /knowledge-bases/{kb}/ingestion-profiles | schema 验证，不允许自由代码 |
| 构建 | POST /knowledge-bases/{kb}/builds；GET /builds/{id} | 参数包含目标 profile 和 scope，202 task |
| 发布 | POST /knowledge-bases/{kb}/publish | release_id、expected_active_release、expected_epoch |
| 回退 | POST /knowledge-bases/{kb}/rollback | 目标 release/runtime，保留期与有效性检查 |
| 检索测试 | POST /knowledge-bases/{kb}/search-test | 管理员可指定 ready 候选 release，返回候选与耗时 |
| 会话 | GET/POST /conversations；GET/DELETE /conversations/{id} | 单库、当前用户 owner |
| 消息 | GET /conversations/{id}/messages | 重新授权，对来源不可见回答整体隐藏 |
| 生成 | POST /conversations/{id}/runs | 消息+幂等键；返回 SSE 格式流 |
| 取消 | POST /runs/{run_id}/cancel；GET /runs/{run_id} | 主动停止与重连后状态读取 |
| 引用 | GET /messages/{id}/citations/{no} | 知识库、会话、当前源状态三重检查 |
| 反馈 | POST /messages/{id}/feedback | 赞/踩、错误原因，不触发自动训练 |
| 追踪 | GET /messages/{id}/trace | owner 且具调试权限，或显式受审计诊断授权 |
| 健康 | GET /health/live；GET /health/ready | 只暴露概要，不泄漏连接串 |

## 5. 流式协议与生命周期

请求 JSON：message、client_request_id、expected_conversation_version。服务端立即建立 user message 和 assistant placeholder、固定 release/runtime，然后发出事件。

```text
event: start
data: {"run_id":"...","message_id":"...","release_id":"..."}

event: delta
data: {"seq":1,"text":"根据资料"}

event: citations
data: {"items":[{"no":1,"title":"制度","locator":{"page":3}}]}

event: done
data: {"state":"completed","usage":{},"trace_id":"..."}
```

错误事件为 error，含 code/message/retryable；取消为 cancelled；来源撤销为 invalidated。每个 run 只有一个终态。事件内容通过 JSON 序列化，前端按 SSE 边界解析，不能假设每个网络 chunk 恰好一条事件。

首版不支持断点续传 token。连接断开后前端 GET run 状态；服务端检测断开后尽力取消模型调用并保存 partial 内容；worker/进程崩溃由 run 超时回收器标记 interrupted。重试创建新 run，不自动重复原请求。Idempotency-Key 命中已存在 run 时返回其状态链接，不能再收费/生成一次。

设置 heartbeat、代理关闭缓冲、有限超时；序号用于去重和检测丢事件。结构化引用以服务端 evidence 编号为准，不能把模型生成的任意 URL 当可信来源。

## 6. 结构化记录 V1.1

明确支持 JSONL/规范 CSV 导入，不等同于任意 Excel 理解或数据库实时同步。

新增 record_sources、records、record_versions。records 以 `(tenant,kb,source,external_id)` 唯一；原字段 payload 与用于嵌入的文本分开保存。映射模板只允许声明字段/标题/格式，不执行任意 Python/SQL。

artifact 增加 record_version_id，与 document_version_id 恰好一个非空；release_items 同样区分源类型并保证每个逻辑记录只出现一个版本。已有文档链路回归通过后迁移。

导入项明确 op=upsert/delete，未出现在增量文件的记录不默认删除；只有显式全量快照模式才将缺失项作为删除候选并展示差异确认。增量任务记录源水位、失败项、content_hash 和模式，重试不能跳过失败记录。

记录引用显示数据源、external_id、字段和值、同步时间。问“所有订单合计金额”时，文本 RAG 不保证完整集合与计算正确；首版明确不支持，后续引入授权后的参数化只读查询服务。

接口：POST /record-sources、POST /record-sources/{id}/imports、GET /record-imports/{id}/diff、POST /record-imports/{id}/commit。预览与提交之间使用版本令牌，提交后进入同一 build/release 生命周期。
