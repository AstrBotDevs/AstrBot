$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$MainScript = Join-Path $Root "start_astrbot.ps1"

Write-Host "scripts\start_with_logs.ps1 is a compatibility wrapper."
Write-Host "Forwarding to start_astrbot.ps1 so config guard, health checks, and port protection are applied."

& powershell -NoProfile -ExecutionPolicy Bypass -File $MainScript @args
exit $LASTEXITCODE
