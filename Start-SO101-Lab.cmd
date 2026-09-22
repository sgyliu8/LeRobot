@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\workbench.ps1" %*
if errorlevel 1 (
  if "%~1"=="" pause
  exit /b 1
)
exit /b 0
