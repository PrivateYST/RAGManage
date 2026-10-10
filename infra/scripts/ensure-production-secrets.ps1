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

    $line = "$name=$(New-RandomSecret)"
    if ($match.Success) {
        $content = [regex]::Replace($content, $pattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($item) $line }, 1)
    } else {
        $content = $content.TrimEnd("`r", "`n") + "`r`n$line`r`n"
    }
}

[System.IO.File]::WriteAllText((Resolve-Path -LiteralPath $EnvFile), $content, $encoding)
