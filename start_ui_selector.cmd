@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=%CD%\.venv-gui\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo [ERROR] Cannot find Python virtualenv .venv-gui.
  echo Please run start.cmd first to initialize dependencies.
  pause
  exit /b 1
)

echo ====================================================
echo      WeChat AI Memory - UI Theme Selector
echo ====================================================
echo.
echo Please select a UI theme:
echo.
echo   [1] Modern Glass Dashboard (Option A)
echo   [2] Classic Tool UI
echo   [3] Exit
echo.

set /p choice=Please enter option (1/2/3): 

if "%choice%"=="1" goto modern
if "%choice%"=="2" goto classic
if "%choice%"=="3" goto end

echo.
echo Invalid option.
pause
goto end

:modern
echo.
echo Starting Modern Glass Dashboard...
"%PYTHON%" app_modern.py
goto end

:classic
echo.
echo Starting Classic UI...
"%PYTHON%" app.py
goto end

:end
endlocal
