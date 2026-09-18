$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
function Invoke-Checked([string]$program, [string[]]$arguments) {
    & $program @arguments
    if ($LASTEXITCODE -ne 0) { throw "Check failed: $program $arguments" }
}
Push-Location $projectRoot
try {
    $uv = Join-Path $projectRoot '.tools/uv-bootstrap/bin/uv.exe'
    if (-not (Test-Path -LiteralPath $uv)) { $uv = 'uv' }
    Invoke-Checked $uv @('sync', '--project', 'backend', '--frozen')
    Invoke-Checked $uv @('run', '--project', 'backend', '--frozen', 'ruff', 'check', 'backend/app', 'backend/tests')
    Invoke-Checked $uv @('run', '--project', 'backend', '--frozen', 'ruff', 'format', '--check', 'backend/app', 'backend/tests')
    Invoke-Checked $uv @('run', '--project', 'backend', '--frozen', 'mypy', '--config-file', 'backend/pyproject.toml', 'backend/app')
    Invoke-Checked $uv @('run', '--project', 'backend', '--frozen', 'pytest', 'backend/tests', '-q')
    Invoke-Checked 'pnpm' @('install', '--frozen-lockfile')
    foreach ($task in @('lint', 'typecheck', 'test', 'build')) {
        Invoke-Checked 'pnpm' @($task)
    }
} finally { Pop-Location }
