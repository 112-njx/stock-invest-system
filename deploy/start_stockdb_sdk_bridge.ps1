param(
    [string]$Python = 'D:\Pycharm\python\python.exe',
    [string]$SdkDirectory = 'D:\Free_stockdb\stockdb\pybao'
)
$ErrorActionPreference = 'Stop'
$workspace = Split-Path $PSScriptRoot -Parent
$script = Join-Path $workspace 'scripts\stockdb_sdk_bridge.py'
if (Get-NetTCPConnection -LocalPort 7900 -State Listen -ErrorAction SilentlyContinue) {
    Write-Output 'StockDB SDK bridge is already listening on port 7900'
    exit 0
}
$logDirectory = Join-Path $workspace 'stock_backend\data'
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
Start-Process -FilePath $Python -ArgumentList @('"' + $script + '"', '--sdk-dir', '"' + $SdkDirectory + '"') `
    -WorkingDirectory $workspace -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logDirectory 'stockdb-sdk.stdout.log') `
    -RedirectStandardError (Join-Path $logDirectory 'stockdb-sdk.stderr.log') | Out-Null
