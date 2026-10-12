@echo off
rem Start only backend dependencies and application so the frontend can run locally with Vite HMR.
setlocal
pushd "%~dp0\..\.."
if not exist ".env" (
    echo .env is missing. Run infra\scripts\init-env.ps1 first.
    popd
    exit /b 1
)
docker compose --env-file .env -f infra/compose/dev.yaml up -d --build postgres redis api worker
if errorlevel 1 (
    echo Failed to start backend services. Check that Docker Desktop is running.
    popd
    exit /b 1
)
docker compose --env-file .env -f infra/compose/dev.yaml run --rm api alembic upgrade head
if errorlevel 1 (
    echo Database migration failed.
    popd
    exit /b 1
)
echo Backend started: http://127.0.0.1:8000
popd
exit /b 0
