@echo off
REM ============================================================================
REM  AstrBot Background Launcher
REM  Author : AstrBot Agent Harness Expert
REM  Time   : 2026-05-13 22:14 CST
REM ============================================================================

setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

set "SCRIPT_NAME=main_bg.py"
set "PYW="

REM ---- 1. locate pythonw.exe ----

if exist "D:\anaconda3\envs\astrbot\pythonw.exe" (
    set "PYW=D:\anaconda3\envs\astrbot\pythonw.exe"
    goto found
)
for /f "delims=" %%P in ('where pythonw.exe 2^>nul') do (
    set "PYW=%%P"
    goto found
)

echo [ERROR] pythonw.exe not found. Please install Python and add it to PATH.
pause
exit /b 1

:found
echo [INFO] Using Python: "%PYW%"

REM ---- 2. check main_bg.py ----
if not exist "%~dp0%SCRIPT_NAME%" (
    echo [ERROR] %SCRIPT_NAME% not found at %~dp0
    pause
    exit /b 1
)

REM ---- 3. prevent duplicate startup ----
set "ALREADY=0"
for /f "tokens=*" %%I in ('wmic process where "name='pythonw.exe' and CommandLine like '%%%SCRIPT_NAME%%%'" get ProcessId /value 2^>nul ^| find "ProcessId="') do (
    set "ALREADY=1"
    echo [WARN] AstrBot background process is already running: %%I
)
if "!ALREADY!"=="1" (
    echo        Use the tray menu to quit, then re-run this script.
    timeout /t 3 >nul
    exit /b 0
)

REM ---- 4. launch ----
echo [INFO] Starting AstrBot in background mode ...
echo Running "%PYW%" "%~dp0%SCRIPT_NAME%"
start /b "" "%PYW%" "%~dp0%SCRIPT_NAME%"
echo [SUCCESS] Astrbot is running in background.
pause
