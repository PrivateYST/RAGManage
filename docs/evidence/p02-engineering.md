# P02 工程基础验证

负责人：Codex；日期：2026-09-17。工程基础验证完成，P01 业务资料与 P03 模型容量仍未完整验收。

## 交付

- Python 3.12.14 隔离环境与 `backend/uv.lock`；Node 24.13.0、pnpm 11.1.0 与 `pnpm-lock.yaml`。
- Vue 3 / TypeScript / Vite / Router / Pinia 最小工程，shadcn-vue 风格环境状态页。
- FastAPI 存活/就绪接口、Celery worker 入口；公司模型配置通过环境变量传入，尚未实现业务模型适配器。
- 固定 digest 的 Python、PostgreSQL + pgvector、Redis 镜像；独立数据库、Redis 和文件卷。
- `.env.example`、随机开发密码初始化脚本、统一检查入口、共享卷验证脚本与 GitHub CI 配置。
- README 启动、检查、热更新及停止说明。

## 实际验证命令与结果

| 命令 / 检查 | 结果 |
|---|---|
| `./infra/scripts/check.ps1` | frozen 依赖安装、Ruff 检查/格式、mypy、前端格式、vue-tsc、Vitest、构建全部通过 |
| 后端 pytest | 3 passed；存在 2 条上游 TestClient 弃用警告，未隐藏 |
| 前端 Vitest | 3 passed；覆盖 503 明细、异常状态码和无效响应 |
| Compose `config --quiet` | 通过，不打印解析后的凭据 |
| Compose `up -d --build --wait --wait-timeout 120` | 成功；API/数据库/Redis 健康，worker 运行 |
| PostgreSQL SQL 查询 | PostgreSQL 16.14，vector 扩展 0.8.2 |
| `./infra/scripts/verify-shared-storage.ps1` | API 写入、worker 读取相同文件并删除探针，成功 |
| Celery `inspect ping --timeout 5` | 1 node online / pong |
| `GET :8000/api/v1/health/ready` | 200，database/redis/storage 均 ok |
| `GET :5173/api/v1/health/ready` | 200，Vite 代理到后端成功 |
| API 容器访问公司 Ollama `/api/version` | 返回 0.34.1；未再次加载模型 |
| 浏览器环境页 | 先验证连接失败提示，再点击重新检查，显示三项正常 |
| `git check-ignore` | `.env`、本地工具、Python 虚拟环境均忽略 |

首次启动发现现有服务占用主机 5432，因此固定本项目主机映射为 PostgreSQL 15432、Redis 16379，
同步更新模板、初始化脚本与本地 `.env`。未停止其他项目服务。

当前访问：前端 `http://127.0.0.1:5173`，API 文档 `http://127.0.0.1:8000/docs`。
仅监听 loopback；开发数据卷保留。CI 配置仅已落盘，尚未运行 GitHub 远端 CI。

## 依赖与镜像记录

Python 包元数据许可证清单见 `python-licenses.json`；pnpm 包声明清单见 `frontend-licenses.json`。
这些记录是依赖自带声明盘点，不是完整法律审查或生产安全认证。

- Python 基础镜像：`sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea`。
- pgvector/pgvector 0.8.2-pg16：`sha256:00ba258a66dac104fd5171074a0084462a64a1369d8513f3d0a634e2f24d15bc`。
- Redis 7.4.2-alpine：`sha256:02419de7eddf55aa5bcf49efb74e88fa8d931b4d77c07eff8a6b2144472b6952`。
- Redis 服务端 7.4 的 RSALv2/SSPLv1 与 Python redis 客户端的 MIT 是不同许可；当前限定内部开发，生产部署阶段复核服务端许可与受维护补丁版本。

## 阶段边界

本阶段不包含认证、正式数据迁移、业务任务/outbox、上传、检索或问答。
P03 仍需补协议适配、流式/取消、错误处理、资源与并发；P04 需要业务资料和真实问题。
新开发机需安装 README 所列运行时并重复执行验证；本轮实际验证范围为当前 Windows 主机与全新项目容器/卷。
