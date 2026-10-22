# 生成本地开发配置和独立随机密钥；模型网关默认连接服务器 B，不覆盖已有 .env。
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$envFile = Join-Path $projectRoot '.env'
if (Test-Path -LiteralPath $envFile) { throw '.env already exists; leaving it unchanged.' }
$passwordBytes = [byte[]]::new(32)
[System.Security.Cryptography.RandomNumberGenerator]::Fill($passwordBytes)
$databasePassword = [Convert]::ToHexString($passwordBytes).ToLowerInvariant()
$csrfSecretBytes = [byte[]]::new(32)
[System.Security.Cryptography.RandomNumberGenerator]::Fill($csrfSecretBytes)
$csrfSecret = [Convert]::ToHexString($csrfSecretBytes).ToLowerInvariant()
$encryptionSecretBytes = [byte[]]::new(32)
[System.Security.Cryptography.RandomNumberGenerator]::Fill($encryptionSecretBytes)
$encryptionSecret = [Convert]::ToHexString($encryptionSecretBytes).ToLowerInvariant()
@"
POSTGRES_PASSWORD=$databasePassword
DATABASE_URL=postgresql://ragmanage:$databasePassword@127.0.0.1:15432/ragmanage_dev
REDIS_URL=redis://127.0.0.1:16379/0
STORAGE_ROOT=$($projectRoot.Replace('\', '/'))/data/files
MODEL_GATEWAY_BASE_URL=http://221.13.18.102:20000
API_KEY_ENCRYPTION_SECRET=$encryptionSecret
CSRF_SECRET=$csrfSecret
MODEL_GATEWAY_ALLOWED_MODELS=qwen3-embedding:0.6b,qwen3.8:27b
GENERATION_MODEL=qwen3.8:27b
GENERATION_MAX_TOKENS=1024
EMBEDDING_MODEL=qwen3-embedding:0.6b
EMBEDDING_DIMENSIONS=1024
SESSION_TTL_HOURS=12
COOKIE_SECURE=false
"@ | Set-Content -LiteralPath $envFile -Encoding utf8
Write-Output 'Created local .env. Configure the Open WebUI API Key from the platform model service page after startup.'
