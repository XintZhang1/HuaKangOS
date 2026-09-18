$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE). Stop; do not skip the safety checks." } }
$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "Run start.ps1 once before installing optional maintenance." }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "Install Git first." }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Install and start Docker Desktop (Linux containers) first." }
& docker info; Check-Exit
& $Python -m pip install -r requirements-maintenance.txt; Check-Exit
# Build only from the original reviewed checkout, NEVER from an AI release.
& docker build -f maintenance/Dockerfile.test -t dealerdesk-tests:0.2 .; Check-Exit
Write-Host "Optional dependencies ready. Configure .env using docs/MAINTENANCE.md, then restart start.ps1."
