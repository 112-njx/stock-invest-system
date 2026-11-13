param(
    [string]$Python = 'D:\Pycharm\python\python.exe',
    [string]$Cargo = 'cargo',
    [ValidateSet('x86_64-pc-windows-msvc', 'x86_64-pc-windows-gnu')]
    [string]$Target = 'x86_64-pc-windows-msvc'
)

$ErrorActionPreference = 'Stop'
$crate = Join-Path (Split-Path $PSScriptRoot -Parent) 'native\market_indicators'
$targetDir = Join-Path $crate 'target'
$moduleDir = Join-Path $targetDir 'python'
$previousPython = $env:PYO3_PYTHON
try {
    $env:PYO3_PYTHON = (Resolve-Path -LiteralPath $Python).Path
    $buildArgs = @('build', '--release', '--locked', '--manifest-path', (Join-Path $crate 'Cargo.toml'),
                   '--target', $Target, '--target-dir', $targetDir)
    if ($Target -eq 'x86_64-pc-windows-gnu') {
        $buildArgs += @('--features', 'pyo3/generate-import-lib')
    }
    & $Cargo @buildArgs
    if ($LASTEXITCODE -ne 0) { throw 'market_indicators build failed' }

    New-Item -ItemType Directory -Path $moduleDir -Force | Out-Null
    $module = Join-Path $moduleDir 'market_indicators.pyd'
    Copy-Item -LiteralPath (Join-Path $targetDir "$Target\release\market_indicators.dll") -Destination $module
    & $Python -c 'import sys; sys.path.insert(0, sys.argv[1]); import market_indicators; print(market_indicators.__file__)' $moduleDir
    if ($LASTEXITCODE -ne 0) { throw 'market_indicators could not be loaded by Python' }
} finally {
    $env:PYO3_PYTHON = $previousPython
}
