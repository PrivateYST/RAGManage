$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location $projectRoot
try {
    $probeName = '.shared-volume-' + [guid]::NewGuid().ToString('N')
    docker compose --env-file .env -f infra/compose/dev.yaml exec -T api python -c "from pathlib import Path; Path('/data/files/$probeName').write_text('ragmanage-volume-check')"
    if ($LASTEXITCODE -ne 0) { throw 'API write failed' }
    docker compose --env-file .env -f infra/compose/dev.yaml exec -T worker python -c "from pathlib import Path; p=Path('/data/files/$probeName'); assert p.read_text() == 'ragmanage-volume-check'; p.unlink(); print('Shared storage verified')"
    if ($LASTEXITCODE -ne 0) { throw 'Worker read failed' }
} finally { Pop-Location }
