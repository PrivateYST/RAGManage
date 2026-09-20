# RAGManage

内部知识库管理与引用问答系统。当前交付包含 Vue 3 / TypeScript 管理界面、
FastAPI 身份与知识库接口、PostgreSQL + pgvector、Redis 和 Celery worker 开发容器。
已实现登录、空间/知识库管理、文档上传、异步解析、任务状态、版本详情、切片预览、
API Key 模型网关、索引构建、发布前校验、差异预览和不可变 Release 发布；
检索问答、回退和结构化记录按实施计划继续接入。

实施方案位于 [md/最终可行方案md](md/最终可行方案md/README.md)。
公司模型服务核验见 [模型报告](docs/model-compatibility.md)，工程验证见 [P02 记录](docs/evidence/p02-engineering.md)。

## 开发环境

- Node.js 24.13.0、pnpm 11.1.0（根目录 packageManager 固定）。
- Python 3.12，由 uv 0.12.15 创建隔离环境；依赖固定在 backend/uv.lock。
- Docker Desktop 使用 Linux containers；PowerShell 7 用于 Windows 辅助脚本。
- 公司 Open WebUI 模型网关地址在 `.env` 配置；本机不安装模型。API 和 Worker
  使用 API Key 访问网关，不直接连接 Ollama 模型端口。

### 首次安装（项目根目录）

```powershell
# uv 安装后执行；本项目现有本地副本也可使用 .tools/uv-bootstrap/bin/uv.exe
uv sync --project backend --frozen
pnpm install --frozen-lockfile
./infra/scripts/init-env.ps1
docker compose --env-file .env -f infra/compose/dev.yaml up -d --build
pnpm dev
```

`.env` 已存在时不要再次运行 init-env；脚本拒绝覆盖已有凭据。
Linux/macOS 可手动复制 `.env.example`，为 POSTGRES_PASSWORD 填入随机十六进制值，
并配置一致的 DATABASE_URL。不要将本地密码提交到版本控制。
本项目 PostgreSQL 主机端口为 `15432`，Redis 为 `16379`，容器内部仍为 `5432/6379`。

前端：[http://127.0.0.1:5173](http://127.0.0.1:5173)。
接口文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)。
前端 `/api` 经 Vite 转发到本地 API；浏览器不直接调用公司模型。
环境页显示真实健康状态，无法连接时提供错误及重试。

### 模型网关与 API Key

API Key 从 Open WebUI 的“账号 → API 密钥”创建，写入本机或部署环境的
`MODEL_GATEWAY_API_KEY`。部署可以在暂未拿到密钥时先启动，API 和 Worker 会在模型操作时
以 `MODEL_GATEWAY_API_KEY_NOT_CONFIGURED` 明确失败；配置密钥后才会使用
`Authorization: Bearer` 调用网关；
嵌入调用 OpenAI 兼容的 `/api/embeddings`，模型摘要通过受认证的
`/ollama/api/tags` 获取。`.env` 中 `MODEL_GATEWAY_ALLOWED_MODELS` 是业务侧白名单。
业务数据库仅保存 `env:MODEL_GATEWAY_API_KEY` 这一引用，密钥明文不进入数据库和 Git。

### 后端热更新

如需直接调试 Python，先停止 Compose 中的 api（避免占用同一端口），保留基础设施：

```powershell
docker compose --env-file .env -f infra/compose/dev.yaml stop api
cd backend
uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

本机 API 使用 `.env` 中的主机数据库地址和本地文件目录；容器使用内部服务名和共享卷。
API/worker 文件共享验收须在两者都运行于 Compose 时执行。正式业务任务在 P12 实现。

## 检查与停止

```powershell
./infra/scripts/check.ps1
./infra/scripts/verify-shared-storage.ps1
docker compose --env-file .env -f infra/compose/dev.yaml ps
docker compose --env-file .env -f infra/compose/dev.yaml down
```

`down` 保留数据卷。不要添加 `-v`，除非明确需要删除开发数据。
`health/live` 只检测 API 存活；`health/ready` 检测数据库扩展、Redis 与存储，失败返回 503。
模型容量与业务可用性由 P03/P08 单独验证，基础健康检查不会加载模型。

## 代码结构

```text
backend/app/          API、配置、健康检查与 worker 入口
backend/tests/        Python 行为测试
frontend/src/         应用外壳、环境页、服务状态与接口类型
infra/               开发 Compose 和脚本
eval/                评测数据约定（真实样本待提供）
docs/                当前基线与实测证据
md/                  历史方案与最终实施方案
```

前端采用 Composition API、script setup 和克制的 shadcn-vue 视觉方向。
App 负责外壳，EnvironmentPage 组合视图，EnvironmentStatus 管理检查请求与展示，
api/health 负责响应边界。正式 shadcn-vue 业务组件在 P17 按需求引入。
CI 配置已准备，推送到 GitHub 后才会执行远端检查。
