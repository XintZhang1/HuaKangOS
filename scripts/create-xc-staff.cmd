@echo off
rem Create the XC trial staff accounts in the running local preview. Passwords are typed here.
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo 没有找到 .venv，请先双击 start-preview.cmd 完成一次启动准备。
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -X utf8 "scripts\create_xc_staff.py" %*
echo.
pause
