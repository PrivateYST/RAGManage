param(
    [Parameter(Mandatory = $true)]
    [string]$EnvFile
)

$ErrorActionPreference = 'Stop'

function New-RandomSecret {
    # 生成 32 字节十六进制密钥；脚本只在配置缺失时调用，避免轮换已用于解密的密钥。
    $bytes = [byte[]]::new(32)
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return [Convert]::ToHexString($bytes).ToLowerInvariant()
}

function Get-EnvValue([string]$name) {
    $match = [regex]::Match($content, "(?m)^$name=(.*)$")
    if ($match.Success) { return $match.Groups[1].Value }
    return ''
}

function Get-LegacyApiKeySecret {
    # 旧版本未配置显式密钥时使用此派生规则；保持兼容，避免已有客户 Key 无法解密。
    $databaseUrl = Get-EnvValue 'DATABASE_URL'
    if ([string]::IsNullOrWhiteSpace($databaseUrl)) {
        $password = Get-EnvValue 'POSTGRES_PASSWORD'
        if ([string]::IsNullOrWhiteSpace($password)) {
            throw 'Cannot derive the legacy API key secret without DATABASE_URL or POSTGRES_PASSWORD.'
        }
        $databaseUrl = "postgresql://ragmanage:$password@postgres:5432/ragmanage"
    }
    $input = "RAGManage/api-key/$databaseUrl/"
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hash = $sha256.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($input))
    } finally {
        $sha256.Dispose()
    }
    return [Convert]::ToHexString($hash).ToLowerInvariant()
}

if (-not (Test-Path -LiteralPath $EnvFile)) {
    throw "Missing production env file: $EnvFile"
}

$content = Get-Content -LiteralPath $EnvFile -Raw
$encoding = New-Object System.Text.UTF8Encoding($false)

foreach ($name in @('API_KEY_ENCRYPTION_SECRET', 'CSRF_SECRET')) {
    $pattern = "(?m)^$name=(.*)$"
    $match = [regex]::Match($content, $pattern)
    if ($match.Success -and -not [string]::IsNullOrWhiteSpace($match.Groups[1].Value)) {
        continue
    }

    $value = if ($name -eq 'API_KEY_ENCRYPTION_SECRET') {
        Get-LegacyApiKeySecret
    } else {
        New-RandomSecret
    }
    $line = "$name=$value"
    if ($match.Success) {
        $content = [regex]::Replace($content, $pattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($item) $line }, 1)
    } else {
        $content = $content.TrimEnd("`r", "`n") + "`r`n$line`r`n"
    }
}

[System.IO.File]::WriteAllText((Resolve-Path -LiteralPath $EnvFile), $content, $encoding)
