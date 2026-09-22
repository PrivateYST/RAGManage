# 模型网关 API Key 统一网关改造方案

> 文档版本：V1.0  
> 编写日期：2026-09-22  
> 适用项目：RAGManage  
> 文档性质：独立方案文档  
>
> 本文不替换、不追加、不修改《RAGManage全量业务实施计划.md》，只描述模型网关 API Key 的业务边界、当前实现和后续改造要求。

## 一、背景与目标

RAGManage 需要为医院、客服中心或其他客户提供一把由公司统一下发的 API Key。客户内部员工不需要逐个注册 Open WebUI 用户，也不需要接触 Open WebUI 的管理员凭据。客户只使用公司下发的：

```http
Authorization: Bearer sk-医院A
```

RAGManage 负责校验客户 Key、租户归属、启用状态、有效期和 Token 额度，然后使用内部统一配置的模型网关 Key 访问 Open WebUI，再把结果返回给客户。

本方案的目标是形成完整闭环：

1. 超级管理员在 RAGManage 中创建客户 Key。
2. 公司把客户 Key 发放给对应医院或客户。
3. 客户使用客户 Key 调用 RAGManage 模型网关接口。
4. RAGManage 完成认证、租户隔离和额度检查。
5. RAGManage 使用内部模型网关 Key 调用 Open WebUI。
6. RAGManage 读取模型返回的真实输入、输出和总 Token。
7. RAGManage 按实际用量结算，并保留可审计的用量流水。
8. Key 停用、删除、过期或额度耗尽后，后续调用立即被拒绝。

## 二、必须区分的两类 Key

### 2.1 客户网关 API Key

示例：

```text
sk-医院A随机串
sk-医院B随机串
```

定义：

- 由 RAGManage 超级管理员创建。
- 由公司发放给医院或其他客户。
- 一把 Key 代表一个客户租户或客户业务主体。
- 客户请求时放在 `Authorization: Bearer <客户Key>` 中。
- 用于 RAGManage 的客户身份认证、租户隔离和额度扣减。
- 不直接透传给 Open WebUI。
- 新 Key 统一使用 `sk-` 前缀。
- 数据库保存哈希和服务端加密密文，不保存可直接读取的明文。

### 2.2 内部模型网关 API Key

示例：

```text
MODEL_GATEWAY_API_KEY=<Open WebUI 管理员或模型网关 Key>
```

定义：

- 由公司配置，不下发给医院。
- 用于 RAGManage 访问内部 Open WebUI 或其他模型网关。
- 目前支持通过平台设置持久化保存，并由服务端加密。
- 可通过超级管理员页面替换。
- API 服务和 Worker 调用模型前加载该 Key。
- 客户 Key 与该 Key 完全隔离。

### 2.3 结论

当前推荐流程如下：

```text
医院 A
  Authorization: Bearer sk-医院A
          |
          v
RAGManage 客户网关
  校验客户 Key、租户、状态、有效期、额度
          |
          v
内部统一模型网关 Key
  Authorization: Bearer <MODEL_GATEWAY_API_KEY>
          |
          v
Open WebUI
          |
          v
Ollama / 本地模型
```

客户的 `sk-医院A` 不能直接拿去请求 Open WebUI。Open WebUI 只看到内部统一模型网关 Key。

## 三、客户使用方式

### 3.1 目标调用方式

建议对外提供 OpenAI 兼容入口：

```http
POST /v1/chat/completions
Authorization: Bearer sk-医院A
Content-Type: application/json
```

请求示例：

```json
{
  "model": "qwen3.8:27b",
  "messages": [
    {
      "role": "user",
      "content": "请根据医院知识库回答：办理出院需要哪些材料？"
    }
  ],
  "stream": false,
  "temperature": 0.2,
  "max_tokens": 1024
}
```

非流式响应建议保持 OpenAI 兼容结构：

```json
{
  "id": "chatcmpl_xxx",
  "object": "chat.completion",
  "created": 1780000000,
  "model": "qwen3.8:27b",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "根据已发布资料，办理出院通常需要……"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 120,
    "completion_tokens": 38,
    "total_tokens": 158
  }
}
```

流式请求应返回标准 SSE，并在最后一个 usage 帧中提供实际用量：

```text
data: {"choices":[{"delta":{"content":"根据"}}]}

data: {"choices":[{"delta":{"content":"资料"}}]}

data: {"choices":[],"usage":{"prompt_tokens":120,"completion_tokens":38,"total_tokens":158}}

data: [DONE]
```

### 3.2 Key 复制和展示

- 创建接口只在创建成功响应中返回一次完整 `raw_key`。
- 列表接口只返回脱敏后的 `key_prefix`。
- 超级管理员点击复制时，前端必须调用后端完整 Key 查询接口，不能从列表中的脱敏字段拼接。
- 完整 Key 的查询必须记录 `api_key.reveal` 审计事件。
- 业务客户不能访问管理页面、Key 列表或完整 Key 查询接口。

## 四、当前实现现状

### 4.1 已经具备的能力

当前代码已经具备以下基础闭环：

- 客户 Key 使用 `sk-` 前缀生成。
- Key 使用 SHA-256 哈希进行认证。
- Key 明文使用服务端密钥加密保存，支持超级管理员复制。
- Key 绑定客户租户。
- 只有平台超级管理员可以创建、查看、启用、停用和删除 Key。
- Key 支持状态切换、软删除、过期判断和额度耗尽判断。
- Key 支持 Token 总额度、已用额度和并发预留额度。
- Key 支持输入 Token、输出 Token、总 Token 分项统计。
- 模型调用时使用内部 `model_gateway_api_key`。
- 生成请求会先预扣保守额度，结束后按实际 usage 幂等结算。
- Open WebUI 返回 usage 时优先使用真实值。
- Open WebUI 缺少 usage 时保留估算来源标记。
- 异常退出时通过持久化 reservation 回收未结算预留。
- Key 的创建、读取、状态变更和删除会写入审计日志。
- 历史 `rmk_` Key 仍可通过数据库中的哈希继续兼容。

### 4.2 当前 RAGManage 原生接口

目前客户 Key 被限制在现有知识问答接口：

```text
GET  /api/v1/knowledge-bases
GET  /api/v1/conversations
POST /api/v1/conversations
GET  /api/v1/conversations/{id}
POST /api/v1/conversations/{id}/runs
GET  /api/v1/runs/{id}
GET  /api/v1/runs/{id}/events
POST /api/v1/runs/{id}/cancel
```

这套接口是 RAGManage 自己的会话和异步运行协议，不等同于 OpenAI 兼容的 `/v1/chat/completions`。

### 4.3 当前模型网关调用路径

RAGManage 内部模型客户端当前调用 Open WebUI 的接口形态主要是：

```text
POST {model_gateway_base_url}/api/chat/completions
POST {model_gateway_base_url}/api/embeddings
```

内部请求使用：

```http
Authorization: Bearer <MODEL_GATEWAY_API_KEY>
```

因此，当前已完成的是“RAGManage 原生问答接口 + 内部统一模型 Key + Token 计量”基础能力；如果要让第三方 SDK 直接按 OpenAI 方式接入，还需要补齐兼容入口。

## 五、目标系统架构

### 5.1 逻辑链路

```text
客户应用
  |
  | Authorization: Bearer sk-医院A
  v
RAGManage /v1/chat/completions
  |
  +-- 解析 Bearer Key
  +-- SHA-256 查询 api_keys
  +-- 检查 tenant、status、expires_at
  +-- 检查 token_used + token_reserved < token_limit
  +-- 固定 customer_tenant_id 和 api_key_id
  +-- 生成/复用内部 request_id
  |
  +-- 预扣请求预算
  |
  v
检索与问答编排
  |
  +-- 嵌入模型调用
  +-- 知识库检索
  +-- 生成模型调用
  +-- 捕获 gateway usage
  |
  v
按实际 usage 结算
  |
  +-- prompt_tokens
  +-- completion_tokens
  +-- total_tokens
  +-- model_usage
  +-- api_key_usage
  |
  v
OpenAI 兼容响应 / SSE
```

### 5.2 租户和用户映射

客户不需要为医院员工逐个注册 Open WebUI 用户。建议将客户 Key 作为“客户级服务身份”：

- `api_keys.tenant_id` 固定绑定医院租户。
- 请求上下文使用该租户的客户服务身份执行知识库权限检查。
- 不把请求者伪装成医院员工。
- 客户 Key 不能调用管理接口、模型配置接口或其他租户数据接口。
- 如未来需要员工级审计，可在客户自己的系统中维护员工身份，并通过 `X-Client-User-Id` 等受控字段传入；该字段不能改变租户和权限边界。

## 六、认证与权限规则

### 6.1 客户请求认证

1. 读取 `Authorization` 请求头。
2. 只接受 `Bearer <key>` 格式。
3. 对完整 Key 做 SHA-256 哈希。
4. 查询 `api_keys`，要求 `deleted_at IS NULL`。
5. 检查租户状态为 `active`。
6. 检查 Key 状态为 `active`。
7. 检查未超过 `expires_at`。
8. 检查 `token_used + token_reserved < token_limit`。
9. 更新 `last_used_at`。
10. 将 `api_key_id`、`api_key_tenant_id` 写入请求上下文。

认证失败统一返回，不泄露 Key 是否存在：

```json
{
  "error": {
    "code": "invalid_api_key",
    "message": "API Key 无效或不可用",
    "type": "authentication_error"
  }
}
```

### 6.2 管理接口权限

以下操作只能由平台超级管理员通过浏览器会话执行：

- 创建客户 Key。
- 查询客户 Key 列表。
- 查询完整 Key。
- 修改 Key 状态。
- 删除 Key。
- 查询 Key 用量明细。
- 替换内部 `MODEL_GATEWAY_API_KEY`。

客户 Key 即使绑定了平台创建人，也不能继承平台管理员权限。

## 七、Token 统计和额度结算

### 7.1 统计字段

每次模型请求至少记录：

| 字段 | 含义 |
| --- | --- |
| `prompt_tokens` | 模型输入 Token |
| `completion_tokens` | 模型输出 Token |
| `total_tokens` | 输入和输出总和 |
| `usage_source` | `gateway`、`estimate` 或 `unavailable` |
| `model_usage` | 嵌入模型、生成模型等分项用量 |
| `model_name` | 本次请求涉及的模型 |
| `request_id` | 客户请求幂等标识 |
| `api_key_id` | 实际消费的客户 Key |
| `tenant_id` | 实际消费的客户租户 |
| `status` | `completed`、`failed` 或 `cancelled` |

### 7.2 结算原则

结算优先级：

1. 网关响应中的真实 `usage`。
2. 网关没有返回 usage 时使用保守估算，并明确记录 `usage_source=estimate`。
3. 无法确认用量时记录 `usage_source=unavailable`，同时按系统策略释放或保留预扣额度，不能静默当作真实用量。

当前实现采用“两阶段额度”：

```text
请求开始
  -> 预扣输入估算 + 最大输出预算
  -> 调用嵌入和生成模型
  -> 读取真实 usage
  -> 幂等写入 api_key_usage
  -> token_used 增加真实 total_tokens
  -> token_reserved 释放预扣
```

预扣值必须大于等于 1，且不能超过剩余额度。这样可以防止并发请求在最终结算前重复消耗同一份额度。

### 7.3 额度耗尽行为

- 认证阶段发现无剩余额度：返回 `quota_exceeded`。
- 预扣阶段发现额度不足：不发起模型调用。
- 模型调用中途额度不能被其他请求抢占，因为已有 reservation。
- 请求完成后按实际 usage 结算。
- 结算后的 `token_used >= token_limit` 时，后续请求自动拒绝。

建议错误响应：

```json
{
  "error": {
    "code": "quota_exceeded",
    "message": "API Key Token 额度已用尽",
    "type": "rate_limit_error"
  }
}
```

## 八、数据模型和审计

### 8.1 `api_keys`

核心字段：

- `tenant_id`
- `name`
- `key_prefix`
- `key_hash`
- `encrypted_key`
- `token_limit`
- `token_used`
- `token_reserved`
- `status`
- `expires_at`
- `last_used_at`
- `created_by`
- `deleted_at`
- `revoked_at`

`key_hash` 用于认证，`encrypted_key` 只用于超级管理员复制。二者职责不能混用。

### 8.2 `api_key_usage`

按请求保存输入、输出、总 Token 和模型分项用量，建议保留以下约束：

- `(api_key_id, request_id)` 唯一。
- `prompt_tokens >= 0`。
- `completion_tokens >= 0`。
- `total_tokens >= 0`。
- `usage_source` 只能取 `gateway`、`estimate`、`unavailable`。
- `tenant_id` 与 `api_key_id` 的归属必须一致。

### 8.3 `api_key_reservations`

用于记录尚未结算的请求预留：

- 绑定 `run_id` 和 `api_key_id`。
- 保存预扣 Token 数。
- 保存最近一次可恢复 usage 快照。
- 超时或进程重启后可回收。

### 8.4 审计事件

至少记录：

```text
api_key.create
api_key.reveal
api_key.status.update
api_key.delete
api_key.usage.settle
api_key.quota.reject
model_gateway_key.update
```

审计日志不能写入完整 Key、内部模型网关 Key 或服务账号密码。

## 九、接口契约

### 9.1 客户接口

目标新增：

```text
POST /v1/chat/completions
```

必须支持：

- `Authorization: Bearer sk-...`
- `model`
- `messages`
- `stream`
- `temperature`
- `max_tokens`
- `request_id` 或等价幂等字段

建议兼容请求头：

```text
X-Request-ID: <uuid>
```

没有传入时由服务端生成，并在响应中返回。

### 9.2 管理接口

当前已存在并继续保留：

```text
GET    /api/v1/api-keys
POST   /api/v1/api-keys
GET    /api/v1/api-keys/{id}/key
PATCH  /api/v1/api-keys/{id}/status
DELETE /api/v1/api-keys/{id}
GET    /api/v1/api-keys/{id}/usage
```

这些接口只对超级管理员开放，不对客户 Key 开放。

### 9.3 内部模型接口

内部调用继续使用：

```text
POST {model_gateway_base_url}/api/chat/completions
POST {model_gateway_base_url}/api/embeddings
Authorization: Bearer <MODEL_GATEWAY_API_KEY>
```

内部接口和客户接口必须分离，不能把客户 Key 直接转发到 Open WebUI。

## 十、错误码

| HTTP | code | 场景 |
| --- | --- | --- |
| 401 | `invalid_api_key` | Key 不存在、格式错误或已失效 |
| 403 | `api_key_scope_forbidden` | 客户 Key 访问管理或配置接口 |
| 403 | `tenant_disabled` | 客户租户已停用 |
| 409 | `quota_exceeded` | 额度不足，无法预扣 |
| 409 | `api_key_disabled` | Key 已停用 |
| 409 | `api_key_expired` | Key 已过期 |
| 409 | `duplicate_request` | 相同 Key 和 request ID 已处理 |
| 502 | `model_gateway_error` | 上游模型网关失败 |
| 503 | `model_gateway_key_unavailable` | 内部模型网关 Key 未配置或不可解密 |

错误响应不应暴露数据库 ID、Key 哈希、内部模型网关地址或上游敏感响应正文。

## 十一、安全要求

- 生产环境必须配置独立的 `API_KEY_ENCRYPTION_SECRET`。
- 不允许把完整客户 Key 写入普通日志、异常栈、审计摘要或监控标签。
- 不允许把 `MODEL_GATEWAY_API_KEY` 返回给前端或客户。
- 复制完整客户 Key 必须经过超级管理员鉴权，并写入审计。
- Key 列表默认显示脱敏前缀。
- 删除采用软删除，保留用量流水和审计记录。
- 停用和删除后的 Key 必须在认证查询中立即失效。
- 对客户接口增加请求体大小、消息数量、单次 `max_tokens` 和并发限制。
- 记录上游耗时、状态和 usage，不记录医疗问题正文和模型完整上下文。
- 生产环境应通过 HTTPS 传输客户 Key。
- 内部模型网关 Key 替换后，API 服务和 Worker 必须从持久化平台设置重新加载。
- 不能依赖“医院员工不注册 Open WebUI”来放宽 RAGManage 的租户权限。

## 十二、分阶段实施计划

### 阶段一：统一术语和现有能力

- 将页面和接口文案统一为“客户模型网关 API Key”。
- 保持新 Key 的 `sk-` 前缀。
- 保留历史 `rmk_` Key 的哈希兼容。
- 检查所有列表、复制、状态和删除操作都走后端接口。
- 核对超级管理员权限和客户 Key 路由白名单。

### 阶段二：补齐 OpenAI 兼容入口

- 新增 `POST /v1/chat/completions`。
- 将客户 Key 接入现有 `_authenticated_user` 和租户上下文。
- 将请求转换到现有检索、问答和流式运行编排。
- 非流式响应转换为 OpenAI Chat Completion 格式。
- 流式响应转换为 OpenAI SSE 格式，并输出最终 usage 帧。
- 保留现有 `/api/v1/conversations` 原生接口，避免前端现有功能回归。

### 阶段三：补齐计量闭环

- 为兼容入口生成稳定的 `request_id`。
- 复用现有 reservation、usage 快照和幂等结算。
- 确认嵌入 Token 和生成 Token 均计入客户 Key。
- 确认上游真实 usage 缺失时的估算策略、标记和告警。
- 增加客户 Key 的日、月、总量统计接口或报表。

### 阶段四：联调和验收

- 使用两个租户和两把 Key 并发请求。
- 确认医院 A 不能读取医院 B 的会话、知识库和用量。
- 确认客户 Key 不能访问管理 API。
- 确认停用、删除、过期和额度用尽均立即阻断。
- 确认流式中断后 reservation 可以恢复。
- 确认相同 `request_id` 不重复扣费。
- 确认复制接口返回完整 Key，而列表仍然脱敏。
- 确认内部模型网关只收到统一的 `MODEL_GATEWAY_API_KEY`。

## 十三、验收标准

### 13.1 创建和发放

- 超级管理员可以为指定医院创建 Key。
- 新 Key 以 `sk-` 开头。
- 创建响应返回一次完整 Key。
- 数据库不存在客户 Key 明文。
- 客户 Key 与指定租户绑定。

### 13.2 调用和隔离

- 客户使用 `Authorization: Bearer sk-...` 可以调用目标问答入口。
- 不带 Key、Key 错误、Key 停用、Key 过期和 Key 删除均返回认证失败或对应业务错误。
- 客户 Key 不能访问超级管理员接口。
- 医院 A 的 Key 不能访问医院 B 的资源。
- 上游 Open WebUI 请求使用内部统一模型网关 Key。

### 13.3 计量和额度

- 返回真实 usage 时，输入、输出和总 Token 与网关一致。
- 没有 usage 时，记录估算来源，不能假装是真实值。
- 额度预扣可以阻止并发超额。
- 完成、失败、取消和中断恢复都不会重复扣费。
- Key 额度用尽后不能继续调用。

### 13.4 管理和审计

- 管理员可以查询 Key 列表和用量。
- 复制操作从后端读取完整 Key。
- 状态按钮可以快速启用或停用。
- 删除后 Key 不能继续使用，但历史用量和审计仍可查询。
- 所有敏感操作均有审计事件。

## 十四、当前实现与目标差距

| 项目 | 当前状态 | 目标状态 |
| --- | --- | --- |
| 客户 Key 生成 | 已完成，`sk-` 前缀 | 保持 |
| 客户 Key 鉴权 | 已完成，哈希校验 | 保持并接入兼容入口 |
| 租户绑定 | 已完成 | 保持 |
| 启用/停用/删除 | 已完成 | 保持 |
| 完整 Key 复制 | 已完成，后端查询 | 保持并强化审计 |
| 输入/输出/总 Token | 已完成 | 接入兼容入口并统一响应 |
| 真实 usage 优先 | 已完成 | 增加缺失 usage 告警 |
| 内部统一模型网关 Key | 已完成 | 保持不向客户透传 |
| 原生 RAGManage 问答 | 已完成 | 保持兼容 |
| OpenAI `/v1/chat/completions` | 尚未确认实现 | 需要新增适配入口 |
| OpenAI 兼容 SSE usage | 尚未确认实现 | 需要新增最终 usage 帧 |
| 客户端 SDK 直接接入 | 需依赖兼容入口 | 完成后支持 |

## 十五、最终业务结论

本项目最终采用“客户 Key 访问 RAGManage，RAGManage 使用统一内部 Key 访问 Open WebUI”的架构。

```text
客户持有：sk-医院A
客户调用：RAGManage
RAGManage 校验：客户 Key、医院租户、状态、额度、有效期
RAGManage 转发：MODEL_GATEWAY_API_KEY
模型服务：Open WebUI -> Ollama / 本地模型
```

因此：

- `sk-医院A` 是对外发放的客户模型网关 Key。
- `MODEL_GATEWAY_API_KEY` 是公司内部访问 Open WebUI 的上游 Key。
- 医院员工不需要逐个注册 Open WebUI 用户。
- 医院也不需要知道内部模型网关 Key。
- 计量、扣减、停用、删除、审计和租户隔离全部由 RAGManage 负责。
- 要完全实现第三方按 OpenAI SDK 使用的体验，还需要补齐 `/v1/chat/completions` 兼容入口。

## 十六、客户空间 API Key 配置入口

为避免管理员先进入模型页、再从客户列表中手动选择医院，平台管理中的“空间管理”页面提供客户级 Key 配置入口。

### 16.1 管理员操作流程

1. 超级管理员进入“平台管理 → 空间管理”。
2. 每个客户空间显示客户 API Key 的配置状态、脱敏前缀和 Token 已用/总额度。
3. 对尚未配置 Key 的启用客户空间，点击“配置 Key”。
4. 填写 Key 名称、Token 总额度和可选有效期。
5. 后端校验超级管理员身份、客户空间状态和额度参数后生成 `sk-...` 客户网关 Key。
6. 创建成功后仅在一次性弹窗中显示完整 Key，管理员复制后通过安全渠道发放给该客户。
7. 后续在空间管理或模型管理页面点击“复制完整 Key”时，前端调用
   `GET /api/v1/api-keys/{id}/key` 查询完整凭据，不从脱敏前缀拼接。

### 16.2 页面和接口职责

| 位置 | 能力 | 明文 Key 是否返回 |
| --- | --- | --- |
| `GET /api/v1/admin/tenants` | 返回空间及 Key 配置摘要 | 否 |
| 空间管理表格 | 查看状态、额度、脱敏前缀、配置入口 | 否 |
| `POST /api/v1/api-keys` | 为指定空间创建客户 Key | 仅创建响应一次返回 |
| `GET /api/v1/api-keys/{id}/key` | 管理员复制已有 Key | 是，且记录 `api_key.reveal` 审计 |
| 模型管理 / 医院网关 Key | 查看用量、启停、删除、批量管理 | 否，复制走受保护接口 |

### 16.3 客户边界

- 该入口只服务平台超级管理员，客户用户不能进入空间管理或调用管理接口。
- 客户不配置、也不接触 `MODEL_GATEWAY_API_KEY`。
- 客户拿到的仍是公司下发的 `Authorization: Bearer sk-...`，医院员工可以共用该客户级身份，无需逐个注册 Open WebUI 用户。
- 客户空间停用、客户 Key 停用、删除、过期或额度耗尽时，调用链立即阻断。

### 16.4 当前验收点

- 空间管理列表能区分“未配置”和“已配置”客户 Key。
- 已配置空间只显示 `key_prefix`，不会在列表接口泄露完整 Key。
- “配置 Key”按钮只对启用且未配置 Key 的空间显示。
- 创建完成后可以复制完整 `sk-...` Key，并能在模型管理页面再次通过接口复制。
- 同一客户空间已有未删除 Key 时，后端拒绝重复创建，必须先按生命周期流程停用、删除或轮换。
