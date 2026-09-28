$ErrorActionPreference = 'Stop'
$appPath = Join-Path $PSScriptRoot 'dist\udown.exe'

if (-not (Test-Path $appPath)) {
    throw "Build the app first. Expected executable: $appPath"
}

foreach ($scheme in @('udown', 'ytdlp-gui')) {
    $protocolKey = "HKCU:\Software\Classes\$scheme"
    New-Item -Path $protocolKey -Force | Out-Null
    Set-Item -Path $protocolKey -Value 'URL:udown Desktop Protocol'
    New-ItemProperty -Path $protocolKey -Name 'URL Protocol' -Value '' -PropertyType String -Force | Out-Null
    $commandKey = Join-Path $protocolKey 'shell\open\command'
    New-Item -Path $commandKey -Force | Out-Null
    Set-Item -Path $commandKey -Value ('"{0}" "%1"' -f $appPath)
}
Write-Host 'Registered udown:// links for the current Windows user.'