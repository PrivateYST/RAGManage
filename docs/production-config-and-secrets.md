# 生产配置与凭据管理

本文说明生产环境所需配置、注入边界和轮换流程。真实值必须由部署平台的 Secret Manager 注入，不能写入 Git、镜像或数据库业务字段。

## 必需配置

| 配置 | 用途 | 管理要求 |
| --- | --- | --- |
| `POSTGRES_PASSWORD` / `DATABASE_URL` | PostgreSQL 连接 | 数据库专用账号；禁止复用模型网关密码 |
| `REDIS_URL` | Redis 连接 | 仅允许内网访问 |
| `MODEL_GATEWAY_API_KEY` | 模型网关认证 | 只注入 API 与 Worker；轮换后滚动重启 |
| `API_KEY_ENCRYPTION_SECRET` | 加密客户 Key | 32 字节以上随机值；丢失会导致已存客户 Key 无法解密 |
| `CSRF_SECRET` | Session CSRF HMAC | 所有 API Worker 必须一致；轮换会使旧 CSRF Cookie 失效 |
| `COOKIE_SECURE=true` | HTTPS Cookie 保护 | 生产必须开启 |

模型白名单、生成模型和嵌入维度必须与已验收的模型网关配置一致。修改嵌入模型或维度前，应先创建新的 Embedding/Runtime Profile，不得覆盖历史构建所依赖的配置。

## 注入与启动

1. 从 `.env.production.example` 复制模板到部署平台变量，不把生产文件放进仓库。
2. 由 Secret Manager 注入密码、API Key、加密密钥和 CSRF 密钥；普通配置可使用受保护的配置变量。
3. 使用 `docker compose --env-file <受保护配置文件> -f infra/compose/prod.yaml up -d --build` 部署。
4. 运行 `alembic upgrade head`，再检查 `/api/v1/health/ready`；未就绪时禁止切换流量。

## 轮换流程

- 模型网关 Key：先在网关创建新 Key，更新 Secret，滚动重启 API/Worker，验证模型健康检查后撤销旧 Key。
- 数据库密码：先创建新数据库凭据并更新连接串，短窗口滚动重启，再确认就绪检查和任务 Worker 正常。
- `API_KEY_ENCRYPTION_SECRET`：除非已有完整客户 Key 解密迁移方案，否则不得直接替换。
- `CSRF_SECRET`：安排维护窗口轮换，并通知浏览器用户重新登录；旧 Session 不应继续用于写操作。

## 禁止事项

- 不在日志、审计摘要、错误响应或前端代码中输出任何凭据。
- 不通过 `docker compose config`、截图或工单传播真实 `.env` 内容。
- 不使用开发环境的 `COOKIE_SECURE=false`、默认网关地址或共享管理员密码部署生产。
