# 初始化平台管理员

数据库迁移完成后，使用交互式命令创建首个管理员。密码至少 12 个字符，不会写入仓库，也不会覆盖同名账号。

```powershell
cd D:\project\RAGManage\backend
..\.tools\uv-bootstrap\bin\uv.exe run --frozen ragmanage-bootstrap-admin --login admin
```

命令读取项目根目录 `.env` 的 `DATABASE_URL`，向 `users` 写入 Argon2id 哈希，并建立内部工作空间成员关系。创建完成后访问 `http://127.0.0.1:5173/login`。

生产环境应通过受控部署流程执行，禁止把密码写入迁移文件、镜像或日志。
