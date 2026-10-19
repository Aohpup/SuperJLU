@echo off
setlocal
title SuperJLU
cd /d "%~dp0"
if errorlevel 1 goto failed

where uv >nul 2>nul
if errorlevel 1 (
    echo [ERROR] uv was not found. Install uv, then reopen this launcher.
    pause
    exit /b 1
)

echo Starting SuperJLU from this folder...
echo The browser will open automatically.
echo Keep this window open while using the app. Press Ctrl+C to stop.
echo The first run or an update may take a moment to install dependencies.
echo.
uv run --extra captcha python start_local.py
if errorlevel 1 goto failed
exit /b 0

:failed
echo.
echo [ERROR] SuperJLU could not start. See the error above.
pause
exit /b 1
