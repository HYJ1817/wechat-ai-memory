@echo off
setlocal
cd /d "%~dp0"

set "PYTHONW=%CD%\.venv-gui\Scripts\pythonw.exe"
set "PYTHON=%CD%\.venv-gui\Scripts\python.exe"

if not exist "%PYTHONW%" (
  if not exist "%PYTHON%" (
    echo [ERROR] Cannot find Python virtualenv in .venv-gui.
    echo Please run start.cmd first to initialize dependencies.
    pause
    exit /b 1
  )
  set "PYTHONW=%PYTHON%"
)

rem Launch with pythonw and exit cmd console immediately
start "" "%PYTHONW%" app_modern.py %*
exit /b 0
