@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo PhysicalAI SO101 Lab is not installed yet.
  echo.
  echo Run these commands once from PowerShell:
  echo   powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\bootstrap_upstream.ps1
  echo   uv sync --frozen
  echo.
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\lab.ps1" start
if errorlevel 1 (
  echo.
  echo The workbench did not start. Review the message above or run:
  echo   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\lab.ps1 logs
  pause
  exit /b 1
)

start "" "http://127.0.0.1:8000/"
exit /b 0
