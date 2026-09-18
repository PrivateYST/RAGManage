$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$uv = Join-Path $projectRoot '.tools/uv-bootstrap/bin/uv.exe'
if (-not (Test-Path -LiteralPath $uv)) { $uv = 'uv' }
Push-Location (Join-Path $projectRoot 'backend')
try {
    & $uv run --frozen alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw '数据库迁移失败' }
} finally { Pop-Location }
