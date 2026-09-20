$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$envFile = Join-Path $projectRoot '.env'
if (Test-Path -LiteralPath $envFile) { throw '.env already exists; leaving it unchanged.' }
$passwordBytes = [byte[]]::new(32)
[System.Security.Cryptography.RandomNumberGenerator]::Fill($passwordBytes)
$databasePassword = [Convert]::ToHexString($passwordBytes).ToLowerInvariant()
@"
POSTGRES_PASSWORD=$databasePassword
DATABASE_URL=postgresql://ragmanage:$databasePassword@127.0.0.1:15432/ragmanage_dev
REDIS_URL=redis://127.0.0.1:16379/0
STORAGE_ROOT=$($projectRoot.Replace('\', '/'))/data/files
MODEL_GATEWAY_BASE_URL=http://172.2.2.230:8080
MODEL_GATEWAY_API_KEY=
MODEL_GATEWAY_ALLOWED_MODELS=qwen3-embedding:0.6b,qwen3.8:27b
GENERATION_MODEL=qwen3.8:27b
EMBEDDING_MODEL=qwen3-embedding:0.6b
EMBEDDING_DIMENSIONS=1024
SESSION_TTL_HOURS=12
COOKIE_SECURE=false
"@ | Set-Content -LiteralPath $envFile -Encoding utf8
Write-Output 'Created local .env. Add the Open WebUI API Key before starting the application.'
