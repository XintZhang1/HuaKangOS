param([switch]$Demo)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "命令执行失败（$LASTEXITCODE），请查看上方错误。" } }
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m venv .venv; Check-Exit }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { & python -m venv .venv; Check-Exit }
    else { throw "请先安装 Python 3.11、3.12 或 3.13，并启用命令行访问。" }
}
$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $Python -c "import sys; assert (3,11) <= sys.version_info[:2] < (3,14), 'Use Python 3.11-3.13'"; Check-Exit
& $Python -m pip install -r requirements.txt; Check-Exit
if ($Demo) { & $Python -m app.cli init --demo }
else { & $Python -m app.cli init }
Check-Exit
Write-Host "请在浏览器打开 http://127.0.0.1:8000。保持此窗口运行；按 Ctrl+C 停止服务。"
& $Python -m app.run
Check-Exit
