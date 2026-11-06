param(
    [string]$Python = 'D:\Pycharm\python\python.exe',
    [string]$StockdbDirectory = 'D:\Free_stockdb\stockdb',
    [string]$ComposeFile = 'deploy/docker-compose.dev.yml'
)
$ErrorActionPreference = 'Stop'
$workspace = Split-Path $PSScriptRoot -Parent
$control = Join-Path $workspace 'stock_backend\data\stockdb-control'
New-Item -ItemType Directory -Force $control | Out-Null
$heartbeat = Join-Path $control 'heartbeat.json'
if (Test-Path $heartbeat) {
    $state = Get-Content -Raw $heartbeat | ConvertFrom-Json
    if (([DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - $state.time) -lt 30) {
        Write-Output 'StockDB update helper is already online'
        exit 0
    }
}
Start-Process -FilePath $Python -WindowStyle Hidden -WorkingDirectory $workspace `
    -ArgumentList @('"' + (Join-Path $workspace 'scripts\stockdb_update_agent.py') + '"',
        '--workspace', '"' + $workspace + '"', '--stockdb-dir', '"' + $StockdbDirectory + '"',
        '--compose', '"' + $ComposeFile + '"') `
    -RedirectStandardOutput (Join-Path $control 'agent.stdout.log') `
    -RedirectStandardError (Join-Path $control 'agent.stderr.log') | Out-Null
Write-Output 'StockDB update helper started'
