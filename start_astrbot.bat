@echo off
setlocal

cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File ".\start_astrbot.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"

if "%~1"=="" (
    echo.
    echo AstrBot has stopped. Press any key to close this window.
    pause >nul
)

exit /b %EXIT_CODE%
