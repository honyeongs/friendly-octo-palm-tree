$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m venv .venv }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { & python -m venv .venv }
    else { throw 'Install Python 3.11 or newer, then run this launcher again.' }
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
$fingerprint = (Get-FileHash -LiteralPath (Join-Path $root 'pyproject.toml') -Algorithm SHA256).Hash
$marker = Join-Path $root '.venv\monitor-version.txt'
$installed = if (Test-Path -LiteralPath $marker) { (Get-Content -LiteralPath $marker -Raw).Trim() } else { '' }
if ($installed -ne $fingerprint) {
    & $python -m pip install -e '.[monitor]' --cache-dir .cache/pip
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check the internet connection.' }
    Set-Content -LiteralPath $marker -Value $fingerprint -Encoding ascii
}
Write-Host 'NetSec Monitor: http://127.0.0.1:8890'
Write-Host 'Keep this window open while using NetSec. Press Ctrl+C to stop.'
if (Test-Path -LiteralPath (Join-Path $root '.env')) {
    & $python run.py monitor --env-file .env
} else {
    & $python run.py monitor
}
exit $LASTEXITCODE
