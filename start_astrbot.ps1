param(
    [switch]$CheckOnly,
    [switch]$FullCheck,
    [switch]$RuntimeCheck,
    [switch]$BrowserCheck,
    [switch]$BrowserSmoke,
    [switch]$StartupSignals,
    [switch]$SearchSignals,
    [switch]$PostRestartCheck,
    [switch]$PostRestartSmokeCheck,
    [switch]$FailOnWarn,
    [switch]$StopExisting
)

$ErrorActionPreference = "Stop"

chcp 65001 | Out-Null
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
if (-not $env:HTTP_PROXY) {
    $env:HTTP_PROXY = "http://127.0.0.1:7897"
}
if (-not $env:HTTPS_PROXY) {
    $env:HTTPS_PROXY = "http://127.0.0.1:7897"
}
if (-not $env:QQTOOLS_BROWSER_PROXY) {
    $env:QQTOOLS_BROWSER_PROXY = $env:HTTPS_PROXY
}

$Root = $PSScriptRoot
$UvPath = "C:\Users\mai\.local\bin\uv.exe"
$PythonPath = Join-Path $Root ".venv\Scripts\python.exe"

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [string[]]$Arguments = @()
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

function Test-TcpPortOpen {
    param(
        [Parameter(Mandatory = $true)]
        [string]$HostName,
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    $Client = [System.Net.Sockets.TcpClient]::new()
    try {
        $Connect = $Client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $Connect.AsyncWaitHandle.WaitOne(750)) {
            return $false
        }
        $Client.EndConnect($Connect)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $Client.Close()
    }
}

function Get-ListeningPortOwner {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    $Connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $Connection) {
        return $null
    }

    $Process = Get-Process -Id $Connection.OwningProcess -ErrorAction SilentlyContinue
    $ProcessName = ""
    if ($Process) {
        $ProcessName = $Process.ProcessName
    }

    [pscustomobject]@{
        Port = $Port
        ProcessId = [int]$Connection.OwningProcess
        ProcessName = $ProcessName
    }
}

function Get-PortOwnerLabel {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    $Owner = Get-ListeningPortOwner -Port $Port
    if (-not $Owner) {
        return ""
    }
    if ($Owner.ProcessName) {
        return " (PID $($Owner.ProcessId), $($Owner.ProcessName))"
    }
    return " (PID $($Owner.ProcessId))"
}

function Get-ProcessChain {
    param(
        [Parameter(Mandatory = $true)]
        [int]$ProcessId
    )

    $Chain = @()
    $CurrentProcessId = $ProcessId
    for ($Depth = 0; $Depth -lt 8; $Depth++) {
        $ProcessInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $CurrentProcessId" -ErrorAction SilentlyContinue
        if (-not $ProcessInfo) {
            break
        }
        $Chain += $ProcessInfo
        if (-not $ProcessInfo.ParentProcessId -or $ProcessInfo.ParentProcessId -eq $CurrentProcessId) {
            break
        }
        $CurrentProcessId = [int]$ProcessInfo.ParentProcessId
    }
    return $Chain
}

function Test-IsCurrentAstrBotProcess {
    param(
        [Parameter(Mandatory = $true)]
        [int]$ProcessId
    )

    $Chain = Get-ProcessChain -ProcessId $ProcessId
    foreach ($ProcessInfo in $Chain) {
        if (Test-ProcessCommandBelongsToCurrentAstrBot -ProcessInfo $ProcessInfo) {
            return $true
        }
    }
    return $false
}

function Test-ProcessCommandBelongsToCurrentAstrBot {
    param(
        [Parameter(Mandatory = $true)]
        [object]$ProcessInfo
    )

    $CommandLine = [string]$ProcessInfo.CommandLine
    return (
        $CommandLine.IndexOf($Root, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $CommandLine.IndexOf("main.py", [System.StringComparison]::OrdinalIgnoreCase) -ge 0
    )
}

function Test-IsAstrBotRuntimeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [object]$ProcessInfo
    )

    $Name = ([string]$ProcessInfo.Name).ToLowerInvariant()
    $CommandLine = [string]$ProcessInfo.CommandLine
    return (
        @("python.exe", "python", "uv.exe", "uv") -contains $Name -and
        $CommandLine.IndexOf("main.py", [System.StringComparison]::OrdinalIgnoreCase) -ge 0
    )
}

function Get-AstrBotRuntimeProcesses {
    $AllProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    $RuntimeByProcessId = @{}

    foreach ($ProcessInfo in $AllProcesses) {
        if (
            (Test-IsAstrBotRuntimeCommand -ProcessInfo $ProcessInfo) -and
            ([string]$ProcessInfo.CommandLine).IndexOf($Root, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
        ) {
            $RuntimeByProcessId[[int]$ProcessInfo.ProcessId] = $ProcessInfo
        }
    }

    $Changed = $true
    while ($Changed) {
        $Changed = $false
        foreach ($ProcessInfo in $AllProcesses) {
            $ProcessId = [int]$ProcessInfo.ProcessId
            if ($RuntimeByProcessId.ContainsKey($ProcessId)) {
                continue
            }
            if (-not (Test-IsAstrBotRuntimeCommand -ProcessInfo $ProcessInfo)) {
                continue
            }

            $ParentProcessId = [int]$ProcessInfo.ParentProcessId
            $IsParentOfRuntime = $false
            foreach ($RuntimeProcess in $RuntimeByProcessId.Values) {
                if ([int]$RuntimeProcess.ParentProcessId -eq $ProcessId) {
                    $IsParentOfRuntime = $true
                    break
                }
            }

            if ($RuntimeByProcessId.ContainsKey($ParentProcessId) -or $IsParentOfRuntime) {
                $RuntimeByProcessId[$ProcessId] = $ProcessInfo
                $Changed = $true
            }
        }
    }

    return @($RuntimeByProcessId.Values | Sort-Object ProcessId)
}

function Format-ProcessSummary {
    param(
        [Parameter(Mandatory = $true)]
        [object]$ProcessInfo
    )

    $CommandLine = [string]$ProcessInfo.CommandLine
    if ($CommandLine.Length -gt 140) {
        $CommandLine = $CommandLine.Substring(0, 137) + "..."
    }
    return "PID $($ProcessInfo.ProcessId) ($($ProcessInfo.Name), PPID $($ProcessInfo.ParentProcessId)): $CommandLine"
}

function Stop-ExistingAstrBotOwners {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Owners
    )

    $ProcessIds = Get-AstrBotStopPlan -Owners $Owners
    foreach ($ProcessId in $ProcessIds) {
        Write-Host "Stopping old AstrBot process PID $ProcessId ..." -ForegroundColor Yellow
        Stop-Process -Id $ProcessId -Force
    }
    Start-Sleep -Seconds 2
}

function Get-AstrBotStopPlan {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Owners
    )

    $RuntimeProcesses = @(Get-AstrBotRuntimeProcesses)
    $RuntimeProcessIds = @($RuntimeProcesses | ForEach-Object { [int]$_.ProcessId })

    $ProcessIds = @()
    foreach ($Owner in $Owners) {
        if (
            ($RuntimeProcessIds -notcontains [int]$Owner.ProcessId) -and
            (-not (Test-IsCurrentAstrBotProcess -ProcessId $Owner.ProcessId))
        ) {
            throw "Refusing to stop PID $($Owner.ProcessId); its process chain does not clearly belong to $Root."
        }

        if ($ProcessIds -notcontains $Owner.ProcessId) {
            $ProcessIds += $Owner.ProcessId
        }

        foreach ($ProcessInfo in (Get-ProcessChain -ProcessId $Owner.ProcessId)) {
            if (
                (Test-ProcessCommandBelongsToCurrentAstrBot -ProcessInfo $ProcessInfo) -and
                ($ProcessIds -notcontains [int]$ProcessInfo.ProcessId)
            ) {
                $ProcessIds += [int]$ProcessInfo.ProcessId
            }
        }
    }

    foreach ($RuntimeProcessId in $RuntimeProcessIds) {
        if ($ProcessIds -notcontains $RuntimeProcessId) {
            $ProcessIds += $RuntimeProcessId
        }
    }

    return $ProcessIds
}

function Assert-NoStaleAstrBotProcesses {
    $RuntimeProcesses = @(Get-AstrBotRuntimeProcesses)
    if ($RuntimeProcesses.Count -eq 0) {
        return
    }

    if ($StopExisting) {
        $Owners = @()
        foreach ($ProcessInfo in $RuntimeProcesses) {
            $Owners += [pscustomobject]@{
                Port = 0
                ProcessId = [int]$ProcessInfo.ProcessId
                ProcessName = [string]$ProcessInfo.Name
            }
        }
        Stop-ExistingAstrBotOwners -Owners $Owners
        Assert-NoStaleAstrBotProcesses
        return
    }

    Write-Host "AstrBot runtime processes already exist. They may be a running instance or a stale hung chain:" -ForegroundColor Yellow
    foreach ($ProcessInfo in $RuntimeProcesses) {
        Write-Host "  - $(Format-ProcessSummary -ProcessInfo $ProcessInfo)" -ForegroundColor Yellow
    }
    Write-Host "If this is the old stuck instance, run this script with -StopExisting to stop only the matching AstrBot process chain." -ForegroundColor Yellow
    Write-Host "Or run with -CheckOnly -RuntimeCheck to inspect without starting a second instance." -ForegroundColor Yellow
    exit 2
}

function Assert-StartupPortsFree {
    $ConfigPath = Join-Path $Root "data\cmd_config.json"
    if (-not (Test-Path $ConfigPath)) {
        return
    }

    $Config = Get-Content $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $BusyPorts = @()
    $BusyOwners = @()

    if ($Config.dashboard -and $Config.dashboard.enable) {
        $DashboardPort = [int]$Config.dashboard.port
        if (Test-TcpPortOpen -HostName "127.0.0.1" -Port $DashboardPort) {
            $BusyPorts += "dashboard 127.0.0.1:$DashboardPort$(Get-PortOwnerLabel -Port $DashboardPort)"
            $Owner = Get-ListeningPortOwner -Port $DashboardPort
            if ($Owner) {
                $BusyOwners += $Owner
            }
        }
    }

    foreach ($Platform in @($Config.platform)) {
        if ($Platform.type -eq "aiocqhttp" -and $Platform.enable) {
            $WsPort = [int]$Platform.ws_reverse_port
            if (Test-TcpPortOpen -HostName "127.0.0.1" -Port $WsPort) {
                $BusyPorts += "OneBot reverse WebSocket 127.0.0.1:$WsPort$(Get-PortOwnerLabel -Port $WsPort)"
                $Owner = Get-ListeningPortOwner -Port $WsPort
                if ($Owner) {
                    $BusyOwners += $Owner
                }
            }
        }
    }

    if ($BusyPorts.Count -gt 0) {
        if ($StopExisting) {
            if ($BusyOwners.Count -eq 0) {
                throw "Ports are busy, but no owning process could be identified."
            }
            Stop-ExistingAstrBotOwners -Owners $BusyOwners
            Assert-StartupPortsFree
            return
        }

        Write-Host "AstrBot already appears to be running or its ports are occupied:" -ForegroundColor Yellow
        foreach ($BusyPort in $BusyPorts) {
            Write-Host "  - $BusyPort" -ForegroundColor Yellow
        }
        if ($BusyOwners.Count -gt 0) {
            try {
                $StopPlan = Get-AstrBotStopPlan -Owners $BusyOwners
                if ($StopPlan.Count -gt 0) {
                    Write-Host "If you run with -StopExisting, these current AstrBot PIDs will be stopped:" -ForegroundColor Yellow
                    foreach ($ProcessId in $StopPlan) {
                        $Process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
                        $ProcessName = if ($Process) { $Process.ProcessName } else { "unknown" }
                        Write-Host "  - PID $ProcessId ($ProcessName)" -ForegroundColor Yellow
                    }
                }
            }
            catch {
                Write-Host "Could not build a safe -StopExisting stop plan: $($_.Exception.Message)" -ForegroundColor Yellow
            }
        }
        Write-Host "To stop a listed PID manually, use: Stop-Process -Id <PID>" -ForegroundColor Yellow
        Write-Host "Or run this script with -StopExisting to stop a matching old AstrBot process safely." -ForegroundColor Yellow
        Write-Host "Stop the old process first, or run this script with -CheckOnly -RuntimeCheck to inspect it." -ForegroundColor Yellow
        exit 2
    }
}

if (-not (Test-Path (Join-Path $Root "main.py"))) {
    throw "main.py was not found. Please put this script in the AstrBotCore root directory."
}

if (-not (Test-Path $UvPath)) {
    $UvCommand = Get-Command "uv.exe" -ErrorAction SilentlyContinue
    if (-not $UvCommand) {
        throw "uv.exe not found. Please install uv or update `$UvPath in this script."
    }
    $UvPath = $UvCommand.Source
}

if (-not (Test-Path $PythonPath)) {
    Write-Host ".venv python was not found. Falling back to uv run python for config guard."
    $ConfigGuardCommand = $UvPath
    $ConfigGuardArgs = @("run", "python", ".\scripts\ensure_runtime_config.py")
    $HealthCheckCommand = $UvPath
    $HealthCheckArgs = @("run", "python", ".\scripts\diagnose_runtime_health.py")
}
else {
    $ConfigGuardCommand = $PythonPath
    $ConfigGuardArgs = @(".\scripts\ensure_runtime_config.py")
    $HealthCheckCommand = $PythonPath
    $HealthCheckArgs = @(".\scripts\diagnose_runtime_health.py")
}

Write-Host "AstrBot root: $Root"
Write-Host "uv path: $UvPath"
Write-Host "config guard: $ConfigGuardCommand"

Set-Location $Root

if ($FullCheck) {
    $CheckOnly = $true
    $RuntimeCheck = $true
    $BrowserCheck = $true
    $StartupSignals = $true
}

if ($PostRestartCheck) {
    $CheckOnly = $true
    $RuntimeCheck = $true
    $BrowserCheck = $true
    $StartupSignals = $true
    $SearchSignals = $true
}

if ($PostRestartSmokeCheck) {
    $CheckOnly = $true
    $RuntimeCheck = $true
    $BrowserCheck = $true
    $BrowserSmoke = $true
    $StartupSignals = $true
    $SearchSignals = $true
}

if ($CheckOnly) {
    Invoke-CheckedCommand -FilePath $ConfigGuardCommand -Arguments ($ConfigGuardArgs + @("--check"))
    $CheckArgs = $HealthCheckArgs
    if ($RuntimeCheck) {
        $CheckArgs = $CheckArgs + @("--runtime")
    }
    if ($BrowserCheck) {
        $CheckArgs = $CheckArgs + @("--browser")
    }
    if ($BrowserSmoke) {
        $CheckArgs = $CheckArgs + @("--browser-smoke")
    }
    if ($StartupSignals) {
        $CheckArgs = $CheckArgs + @("--startup-signals")
    }
    if ($SearchSignals) {
        $CheckArgs = $CheckArgs + @("--search-signals")
    }
    if ($FailOnWarn) {
        $CheckArgs = $CheckArgs + @("--fail-on-warn")
    }
    Invoke-CheckedCommand -FilePath $HealthCheckCommand -Arguments $CheckArgs
    Write-Host "Check completed. AstrBot was not started."
    exit 0
}

Invoke-CheckedCommand -FilePath $ConfigGuardCommand -Arguments $ConfigGuardArgs
Invoke-CheckedCommand -FilePath $HealthCheckCommand -Arguments ($HealthCheckArgs + @("--skip-logs"))
Assert-NoStaleAstrBotProcesses
Assert-StartupPortsFree
Invoke-CheckedCommand -FilePath $UvPath -Arguments @("run", "main.py")
