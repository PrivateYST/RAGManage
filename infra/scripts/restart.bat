@echo off
rem Restart all Compose containers, then run database migrations.
setlocal
pushd "%~dp0\..\.."
docker compose --env-file .env -f infra/compose/dev.yaml restart
if errorlevel 1 (
    echo Failed to restart Compose services. Run infra\scripts\start.bat first.
    popd
    exit /b 1
)
docker compose --env-file .env -f infra/compose/dev.yaml run --rm api alembic upgrade head
if errorlevel 1 (
    echo Database migration failed.
    popd
    exit /b 1
)
echo RAGManage restarted: http://127.0.0.1:5173
popd
exit /b 0
