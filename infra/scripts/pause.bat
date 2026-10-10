@echo off
rem Pause all Compose containers and preserve containers and volumes.
setlocal
pushd "%~dp0\..\.."
docker compose --env-file .env -f infra/compose/dev.yaml pause
if errorlevel 1 (
    echo Failed to pause Compose services. Check that the stack is running.
    popd
    exit /b 1
)
echo RAGManage paused.
popd
exit /b 0
