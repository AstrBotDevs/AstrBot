@echo off
chcp 65001 >nul
echo ============================================
echo    AstrBot 开机自启动设置工具
echo ============================================
echo.

:: 检查管理员权限
net session >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [错误] 请以管理员身份运行此脚本！
    echo.
    echo 右键点击此脚本 -^> 以管理员身份运行
    pause
    exit /b 1
)

set "ASTRBOT_DIR=%~dp0"
set "TASK_NAME=AstrBotAutoStart"
set "LAUNCHER_SCRIPT=%ASTRBOT_DIR%start_astrbot_silent.bat"

:: 检查启动脚本是否存在
if not exist "%LAUNCHER_SCRIPT%" (
    echo [错误] 找不到 start_astrbot_silent.bat
    echo 请确保文件存在于: %LAUNCHER_SCRIPT%
    pause
    exit /b 1
)

echo 当前 AstrBot 目录: %ASTRBOT_DIR%
echo.
echo 请选择操作:
echo [1] 启用开机自启动
echo [2] 禁用开机自启动
echo [3] 查看当前状态
echo [4] 测试启动脚本
echo [5] 退出
echo.
set /p choice=请输入选项 (1-5):

if "%choice%"=="1" goto enable
if "%choice%"=="2" goto disable
if "%choice%"=="3" goto status
if "%choice%"=="4" goto test
if "%choice%"=="5" goto end
echo 无效选项，请重新运行脚本。
pause
goto end

:enable
echo.
echo 正在设置开机自启动...

:: 删除旧任务（如果存在）
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

:: 创建XML任务定义文件
set "TASK_XML=%TEMP%\astrbot_task.xml"

:: 获取当前用户名
for /f "tokens=*" %%u in ('whoami') do set "CURRENT_USER=%%u"

:: 创建任务XML（延迟60秒启动，确保网络就绪）
(
echo ^<?xml version="1.0" encoding="UTF-16"?^>
echo ^<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"^>
echo   ^<RegistrationInfo^>
echo     ^<Description^>AstrBot 机器人框架开机自启动^</Description^>
echo   ^</RegistrationInfo^>
echo   ^<Triggers^>
echo     ^<LogonTrigger^>
echo       ^<Enabled^>true^</Enabled^>
echo       ^<Delay^>PT60S^</Delay^>
echo     ^</LogonTrigger^>
echo   ^</Triggers^>
echo   ^<Principals^>
echo     ^<Principal id="Author"^>
echo       ^<UserId^>%CURRENT_USER%^</UserId^>
echo       ^<LogonType^>InteractiveToken^</LogonType^>
echo       ^<RunLevel^>LeastPrivilege^</RunLevel^>
echo     ^</Principal^>
echo   ^</Principals^>
echo   ^<Settings^>
echo     ^<MultipleInstancesPolicy^>IgnoreNew^</MultipleInstancesPolicy^>
echo     ^<DisallowStartIfOnBatteries^>false^</DisallowStartIfOnBatteries^>
echo     ^<StopIfGoingOnBatteries^>false^</StopIfGoingOnBatteries^>
echo     ^<AllowHardTerminate^>true^</AllowHardTerminate^>
echo     ^<StartWhenAvailable^>true^</StartWhenAvailable^>
echo     ^<RunOnlyIfNetworkAvailable^>false^</RunOnlyIfNetworkAvailable^>
echo     ^<IdleSettings^>
echo       ^<StopOnIdleEnd^>false^</StopOnIdleEnd^>
echo       ^<RestartOnIdle^>false^</RestartOnIdle^>
echo     ^</IdleSettings^>
echo     ^<AllowStartOnDemand^>true^</AllowStartOnDemand^>
echo     ^<Enabled^>true^</Enabled^>
echo     ^<Hidden^>false^</Hidden^>
echo     ^<RunOnlyIfIdle^>false^</RunOnlyIfIdle^>
echo     ^<DisallowStartOnRemoteAppSession^>false^</DisallowStartOnRemoteAppSession^>
echo     ^<UseUnifiedSchedulingEngine^>true^</UseUnifiedSchedulingEngine^>
echo     ^<WakeToRun^>false^</WakeToRun^>
echo     ^<ExecutionTimeLimit^>PT0S^</ExecutionTimeLimit^>
echo     ^<Priority^>7^</Priority^>
echo   ^</Settings^>
echo   ^<Actions Context="Author"^>
echo     ^<Exec^>
echo       ^<Command^>cmd.exe^</Command^>
echo       ^<Arguments^>/c "%LAUNCHER_SCRIPT%"^</Arguments^>
echo       ^<WorkingDirectory^>%ASTRBOT_DIR%^</WorkingDirectory^>
echo     ^</Exec^>
echo   ^</Actions^>
echo ^</Task^>
) > "%TASK_XML%"

:: 使用XML导入任务
schtasks /create /tn "%TASK_NAME%" /xml "%TASK_XML%" /f

if %ERRORLEVEL% equ 0 (
    echo.
    echo [成功] 开机自启动已设置！
    echo.
    echo 任务详情:
    echo   任务名称: %TASK_NAME%
    echo   启动脚本: %LAUNCHER_SCRIPT%
    echo   触发时机: 用户登录后延迟60秒
    echo   执行用户: %CURRENT_USER%
    echo.
    echo 你也可以在"任务计划程序"中查看和修改此任务。
    echo 运行 taskschd.msc 打开任务计划程序。
) else (
    echo.
    echo [失败] 设置开机自启动时出错！
    echo 错误代码: %ERRORLEVEL%
    echo.
    echo 请尝试手动创建任务：
    echo 1. 运行 taskschd.msc
    echo 2. 创建任务 -^> 触发器 -^> 登录时
    echo 3. 操作 -^> 启动程序 -^> %LAUNCHER_SCRIPT%
)

:: 清理临时文件
del "%TASK_XML%" >nul 2>&1

pause
goto end

:disable
echo.
echo 正在禁用开机自启动...
schtasks /delete /tn "%TASK_NAME%" /f

if %ERRORLEVEL% equ 0 (
    echo.
    echo [成功] 开机自启动已禁用！
) else (
    echo.
    echo [提示] 任务可能不存在或已被删除。
)
pause
goto end

:status
echo.
echo 正在查询开机自启动状态...
echo.
schtasks /query /tn "%TASK_NAME%" /v /fo list 2>nul
if %ERRORLEVEL% neq 0 (
    echo [状态] 开机自启动未设置
)
pause
goto end

:test
echo.
echo 正在测试启动脚本...
echo 这将启动 AstrBot，请确认是否继续？
echo.
set /p confirm=输入 Y 确认:
if /i "%confirm%"=="Y" (
    call "%LAUNCHER_SCRIPT%"
) else (
    echo 已取消测试。
)
pause
goto end

:end
