@echo off
rem Start RAGManage, build Compose services, and run database migrations.
setlocal
pushd "%~dp0\..\.."
if not exist ".env" (
    echo .env is missing. Configure the environment file first.
    popd
    exit /b 1
)
docker compose --env-file .env -f infra/compose/dev.yaml up -d --build
if errorlevel 1 (
    echo Failed to start Compose services. Check that Docker Desktop is running.
    popd
    exit /b 1
)
docker compose --env-file .env -f infra/compose/dev.yaml run --rm api alembic upgrade head
if errorlevel 1 (
    echo Database migration failed.
    popd
    exit /b 1
)
echo RAGManage started: http://127.0.0.1:5173
popd
exit /b 0
