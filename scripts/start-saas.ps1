$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m venv .venv }
    else { & python -m venv .venv }
    if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed.' }
}
& $python -m pip install -e '.[monitor,saas,packets]' -c requirements-runtime.lock --cache-dir .cache/pip
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
$port = 8892
while (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) { $port++ }
$env:NETSEC_SAAS_ENABLED = '1'
$env:NETSEC_DATABASE_URL = ''
$env:NETSEC_DB = Join-Path $root 'data-saas\netsec.sqlite3'
$env:NETSEC_ORIGIN = "http://127.0.0.1:$port"
$env:NETSEC_MAIL_MODE = 'local'
$env:NETSEC_BILLING_MODE = 'mock'
$env:NETSEC_LAUNCH_CONFIRMED = '0'
$env:NETSEC_ENCRYPTION_KEY = ''
$env:NETSEC_EMBEDDED_WORKER = '1'
Write-Host "NetSec SaaS local test: http://127.0.0.1:$port"
Write-Host 'No actual billing. Synthetic data only. Keep this window open.'
& $python run.py monitor --port $port
exit $LASTEXITCODE
