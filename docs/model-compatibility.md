# 公司模型服务器核验

日期：2026-09-17。P03 状态：接口冒烟通过，容量与完整兼容性验收未完成。

## 实际访问结果

| 入口 | 结果 |
|---|---|
| `http://192.168.2.59:11434` | Ollama 0.34.1；version/tags/ps/show 可访问 |
| `http://172.2.2.230:11434` | 同版本、同模型清单及 digest；网络映射关系未核实 |
| `http://172.2.2.230:8080` | Open WebUI 0.11.3，API Key 认证、模型列表和嵌入接口正常 |
| `192.168.2.59:3389` | TCP 连通；本轮未登录远程桌面 |
| SSH / WinRM | 两地址 SSH 22 未连通；192.168.2.59:5985 未连通 |

正式后端接入地址调整为 `http://172.2.2.230:8080`，通过 Open WebUI API Key 网关访问；
业务 API 和 Worker 不再直接连接 Ollama 端口。
本轮通过 HTTP API 检查，未安装、更新或重启服务器软件，也未修改模型配置。
测试使用无业务信息的短文本；推理请求会临时加载模型，keep_alive 设置为 1 分钟。
账号密码不写入工程或报告。

## 已确认模型

| 用途 | 精确服务标识 | 服务声明参数 | 量化 | 结果 |
|---|---|---|---|---|
| 生成 | `qwen3.8:27b` | 27.3B，GGUF，family=qwen35 | Q4_K_M | `/api/chat` 正常生成 |
| 嵌入 | `qwen3-embedding:0.6b` | 595.78M，GGUF，1024 维 | Q8_0 | `/api/embed` 实际返回 1024 维 |

标签、架构和参数均为服务器响应，不将服务标签当作上游模型来源证明。
模型 digest 与元数据见 [原始清单](evidence/server-model-inventory.json)。
不可变 profile 应登记此 GGUF digest、量化和服务版本，不等同于未量化 Hugging Face 权重。

## 实际冒烟结果

网关：携带 Bearer API Key 调用 `/api/models` 可读取两个白名单模型；
`/api/embeddings` 与 `/api/v1/embeddings` 均返回 1024 维向量，
`/ollama/api/embed` 兼容接口也返回 1024 维向量。工程采用 OpenAI 兼容的
`/api/embeddings`，并通过受认证的 `/ollama/api/tags` 保存 Ollama 模型 digest。

嵌入：两条短文本、truncate=false；耗时 4.939 秒，其中加载 4.725 秒；
返回 2×1024 维，L2 norm 分别约 1.00000048、1.00000026，prompt_eval_count=39。
该检查仅验证维度和数值形态，未验证检索效果与正式 query 指令模板。

生成：用户消息“这是接口连通性测试，请只回复：连接成功。”；
stream=false、think=false、num_ctx=4096、num_predict=24、temperature=0。
返回“连接成功。”，done=true，done_reason=stop。
墙钟耗时 33.036 秒；服务加载耗时 32.387 秒；输入 25 token、输出 4 token。
这是单次冷加载冒烟，不是首字延迟、稳定吞吐或并发 SLA。

Ollama `/api/ps` 在各自请求后报告：

- 嵌入：size_vram=5,776,426,925 bytes（约 5.38 GiB），context_length=32768。
- 生成：size_vram=17,278,110,267 bytes（约 16.09 GiB），context_length=4096。
- 两次快照分别只列出一个模型，不能证明可同时驻留。

## 仍需核验

1. 服务器操作系统、CPU、RAM、GPU 型号/数量/总显存、驱动、磁盘与部署进程配置。
2. 模型的可靠来源、tokenizer 精确版本、query/doc 编码模板、截断及空输入处理。
3. 流式生成、超时/取消、错误响应及 OpenAI 兼容路径（当前仅验证 Ollama 原生协议）。
4. 热请求、代表长度、并发和两模型共存峰值；嵌入默认大窗口的资源成本。
5. 真实资料召回与引用质量；重排暂关闭，未发现已安装的重排模型。

结论：无需在开发机重复部署模型，可以使用公司已有服务继续技术验证；P03 暂不勾选完成。
