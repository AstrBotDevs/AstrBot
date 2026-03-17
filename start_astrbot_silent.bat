@echo off
setlocal EnableExtensions

cd /d "%~dp0" || exit /b 1

:: 设置日志
set "LOG_DIR=%~dp0data\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1
set "LOG_FILE=%LOG_DIR%\autostart-astrbot.log"

echo [%date% %time%] Autostart triggered. >> "%LOG_FILE%"

REM Force UTF-8 to avoid encoding issues
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if not exist "main.py" (
    echo [%date% %time%] main.py not found in %CD%. >> "%LOG_FILE%"
    exit /b 1
)

set "UV_EXE="
for /f "delims=" %%I in ('where uv 2^>nul') do (
    set "UV_EXE=%%I"
    goto :found_uv
)

if not defined UV_EXE if exist "%LOCALAPPDATA%\Programs\uv\uv.exe" set "UV_EXE=%LOCALAPPDATA%\Programs\uv\uv.exe"
if not defined UV_EXE if exist "%USERPROFILE%\.cargo\bin\uv.exe" set "UV_EXE=%USERPROFILE%\.cargo\bin\uv.exe"

:found_uv
if defined UV_EXE (
    echo [%date% %time%] Using uv: %UV_EXE% >> "%LOG_FILE%"
    start "AstrBot" /min cmd /c "cd /d "%~dp0" && "%UV_EXE%" run main.py >> "%LOG_FILE%" 2>&1"
    echo [%date% %time%] AstrBot launched. >> "%LOG_FILE%"
    exit /b 0
)

if exist "%~dp0.venv\Scripts\python.exe" (
    echo [%date% %time%] uv.exe not found. Falling back to .venv python. >> "%LOG_FILE%"
    start "AstrBot" /min cmd /c "cd /d "%~dp0" && "%~dp0.venv\Scripts\python.exe" main.py >> "%LOG_FILE%" 2>&1"
    echo [%date% %time%] AstrBot launched (venv). >> "%LOG_FILE%"
    exit /b 0
)

echo [%date% %time%] uv.exe not found and .venv python missing. >> "%LOG_FILE%"
exit /b 1
