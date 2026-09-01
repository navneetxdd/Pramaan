@echo off
setlocal
cd /d "%~dp0"

pythonw "%~dp0desktop.py" --production
if errorlevel 1 (
  echo Pramaan failed to start. Run scripts\install-pramaan-desktop.ps1 once to install dependencies.
  pause
)
