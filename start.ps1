param([switch]$Demo)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE). See the error above." } }
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m venv .venv; Check-Exit }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { & python -m venv .venv; Check-Exit }
    else { throw "Please install Python 3.11, 3.12 or 3.13 first (and enable PATH)." }
}
$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $Python -c "import sys; assert (3,11) <= sys.version_info[:2] < (3,14), 'Use Python 3.11-3.13'"; Check-Exit
& $Python -m pip install -r requirements.txt; Check-Exit
if ($Demo) { & $Python -m app.cli init --demo }
else { & $Python -m app.cli init }
Check-Exit
Write-Host "Open http://127.0.0.1:8000 in your browser. Keep this window open. Ctrl+C stops the service."
& $Python -m maintenance.supervisor
Check-Exit
