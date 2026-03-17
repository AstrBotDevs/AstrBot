@echo off
setlocal EnableExtensions

cd /d "%~dp0" || exit /b 1

set "LOG_DIR=%~dp0data\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1
set "LOG_FILE=%LOG_DIR%\startup.log"

call :log "Startup shortcut triggered."

REM Force UTF-8 to avoid Loguru UnicodeEncodeError under GBK consoles.
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
chcp 65001 >nul

if not exist "main.py" (
    call :log "main.py not found in %CD%."
    exit /b 1
)

set "UV_EXE="
for /f "delims=" %%I in ('where uv 2^>nul') do (
    set "UV_EXE=%%I"
    goto :found_uv
)

if not defined UV_EXE if exist "%LOCALAPPDATA%\Programs\uv\uv.exe" set "UV_EXE=%LOCALAPPDATA%\Programs\uv\uv.exe"
if not defined UV_EXE if exist "%USERPROFILE%\.cargo\bin\uv.exe" set "UV_EXE=%USERPROFILE%\.cargo\bin\uv.exe"
if not defined UV_EXE for /f "delims=" %%I in ('dir /b /s "%LOCALAPPDATA%\\Programs\\Python\\Python*\\Scripts\\uv.exe" 2^>nul') do (
    set "UV_EXE=%%I"
    goto :found_uv
)

:found_uv
if defined UV_EXE (
    call :log "Using uv: %UV_EXE%"
    start "AstrBot" /min cmd /c "cd /d ""%~dp0"" && ""%UV_EXE%"" run main.py >> ""%LOG_FILE%"" 2>&1"
    call :log "Launch command dispatched."
    exit /b 0
)

if exist "%~dp0.venv\Scripts\python.exe" (
    call :log "uv.exe not found. Falling back to .venv python."
    start "AstrBot" /min cmd /c "cd /d ""%~dp0"" && ""%~dp0.venv\Scripts\python.exe"" main.py >> ""%LOG_FILE%"" 2>&1"
    call :log "Launch command dispatched (venv)."
    exit /b 0
)

call :log "uv.exe not found in PATH or common locations, and .venv python missing."
exit /b 1

:log
>>"%LOG_FILE%" echo [%date% %time%] %~1
goto :eof
