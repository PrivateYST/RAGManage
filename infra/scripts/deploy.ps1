param(
    [string]$ComposeFile = "infra/compose/prod.yaml"
)

$ErrorActionPreference = "Stop"

docker compose --env-file .env -f $ComposeFile pull
docker compose --env-file .env -f $ComposeFile run --rm api alembic upgrade head
docker compose --env-file .env -f $ComposeFile up -d --remove-orphans

$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8081/api/v1/health/ready" -TimeoutSec 5 | Out-Null
        $ready = $true
        break
    } catch {
        Start-Sleep -Seconds 2
    }
}

if (-not $ready) {
    docker compose --env-file .env -f $ComposeFile ps
    throw "Production health check failed."
}

docker image prune -f
