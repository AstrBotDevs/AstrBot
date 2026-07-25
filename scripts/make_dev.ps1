param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("run-backend", "run-dashboard", "stop-backend", "stop-dashboard", "status", "clean")]
    [string]$Action
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$runDir = Join-Path $repoRoot ".make"
$dashboardDir = Join-Path $repoRoot "dashboard"
$backendPidFile = Join-Path $runDir "backend.pid"
$dashboardPidFile = Join-Path $runDir "dashboard.pid"
$backendLog = Join-Path $repoRoot "backend_run.log"
$backendErrLog = Join-Path $repoRoot "backend_run.err.log"
$dashboardLog = Join-Path $repoRoot "frontend_run.log"
$dashboardErrLog = Join-Path $repoRoot "frontend_run.err.log"
$dashboardDist = Join-Path $dashboardDir "dist"
$dashboardViteCache = Join-Path $dashboardDir "node_modules/.vite"

function Ensure-RunDir {
    if (-not (Test-Path $runDir)) {
        New-Item -ItemType Directory -Path $runDir | Out-Null
    }
}

function Get-ApplicationCommandPath {
    param([string[]]$Names)

    foreach ($name in $Names) {
        $command = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($command) {
            return $command.Source
        }
    }

    return $null
}

function Remove-IfExists {
    param([string]$Path)
    if (Test-Path $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Remove-FilesByPattern {
    param(
        [string]$Root,
        [string]$Pattern
    )

    if (-not (Test-Path -LiteralPath $Root)) {
        return
    }

    Get-ChildItem -LiteralPath $Root -Recurse -Force -File -Filter $Pattern -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

function Remove-DirectoriesByName {
    param(
        [string]$Root,
        [string[]]$Names
    )

    if (-not (Test-Path -LiteralPath $Root)) {
        return
    }

    Get-ChildItem -LiteralPath $Root -Recurse -Force -Directory -ErrorAction SilentlyContinue |
        Where-Object { $Names -contains $_.Name } |
        ForEach-Object {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }
}

function New-EmptyFile {
    param([string]$Path)

    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path $parent)) {
        New-Item -ItemType Directory -Path $parent | Out-Null
    }

    $attempts = 50
    for ($index = 0; $index -lt $attempts; $index++) {
        try {
            Set-Content -Path $Path -Value "" -NoNewline
            return
        }
        catch [System.IO.IOException] {
            if ($index -eq ($attempts - 1)) {
                throw
            }
            Start-Sleep -Milliseconds 100
        }
    }
}

function Invoke-TaskKill {
    param([int]$TargetPid)

    if (-not $IsWindows) {
        throw "taskkill is only available on Windows."
    }

    $taskkill = Start-Process `
        -FilePath "taskkill.exe" `
        -ArgumentList @("/PID", $TargetPid, "/T", "/F") `
        -WindowStyle Hidden `
        -Wait `
        -PassThru

    if ($taskkill.ExitCode -in @(0, 128, 255)) {
        return
    }

    if (-not (Get-Process -Id $TargetPid -ErrorAction SilentlyContinue)) {
        return
    }

    throw "taskkill failed for PID $TargetPid with exit code $($taskkill.ExitCode)"
}

function Get-PosixProcessGroupId {
    param([int]$TargetPid)

    $psCommand = Get-ApplicationCommandPath -Names @("ps")
    if (-not $psCommand) {
        return $null
    }

    $groupId = & $psCommand "-o" "pgid=" "-p" $TargetPid 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $groupId) {
        return $null
    }

    $groupText = ($groupId | Select-Object -First 1).Trim()
    if ($groupText -match "^\d+$") {
        return [int]$groupText
    }

    return $null
}

function Stop-PosixProcess {
    param([int]$TargetPid)

    $process = Get-Process -Id $TargetPid -ErrorAction SilentlyContinue
    if (-not $process) {
        return
    }

    $killCommand = Get-ApplicationCommandPath -Names @("kill")
    $processGroupId = Get-PosixProcessGroupId -TargetPid $TargetPid
    if ($killCommand -and $processGroupId -eq $TargetPid) {
        & $killCommand "-s" "TERM" "--" "-$TargetPid" 2>$null
        for ($attempt = 0; $attempt -lt 20; $attempt++) {
            Start-Sleep -Milliseconds 200
            if (-not (Get-Process -Id $TargetPid -ErrorAction SilentlyContinue)) {
                return
            }
        }

        & $killCommand "-s" "KILL" "--" "-$TargetPid" 2>$null
        Start-Sleep -Milliseconds 200
    }
    else {
        Stop-Process -Id $TargetPid -Force -ErrorAction SilentlyContinue
    }

    if (Get-Process -Id $TargetPid -ErrorAction SilentlyContinue) {
        throw "Failed to stop PID $TargetPid"
    }
}

function Stop-FromPidFile {
    param([string]$PidFile)
    if (-not (Test-Path $PidFile)) {
        return
    }

    $pidValue = Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pidValue -and $pidValue -match "^\d+$") {
        $targetPid = [int]$pidValue
        try {
            if ($IsWindows) {
                Invoke-TaskKill -TargetPid $targetPid
            }
            else {
                Stop-PosixProcess -TargetPid $targetPid
            }
        }
        catch {
            if (Get-Process -Id $targetPid -ErrorAction SilentlyContinue) {
                throw
            }
        }
    }
    Remove-IfExists $PidFile
}

function Stop-ByPort {
    param([int]$Port)

    $pids = @()
    if ($IsWindows) {
        try {
            $pids += Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
                Select-Object -ExpandProperty OwningProcess -Unique
        }
        catch {
            $netstatLines = netstat -ano -p tcp | Select-String ":$Port "
            foreach ($line in $netstatLines) {
                $parts = ($line.Line -split "\s+") | Where-Object { $_ }
                if ($parts.Length -ge 5 -and $parts[3] -eq "LISTENING") {
                    $pids += $parts[4]
                }
            }
        }
    }
    else {
        $lsofCommand = Get-ApplicationCommandPath -Names @("lsof")
        if ($lsofCommand) {
            $pids += & $lsofCommand "-tiTCP:$Port" "-sTCP:LISTEN" 2>$null
        }

        if (-not $pids) {
            $ssCommand = Get-ApplicationCommandPath -Names @("ss")
            if ($ssCommand) {
                $ssLines = & $ssCommand "-ltnp" 2>$null
                foreach ($line in $ssLines) {
                    if ($line -match "[:\.]$Port\s" -and $line -match "pid=(\d+)") {
                        $pids += $matches[1]
                    }
                }
            }
        }

        if (-not $pids) {
            $netstatCommand = Get-ApplicationCommandPath -Names @("netstat")
            if ($netstatCommand) {
                $netstatLines = & $netstatCommand "-ltnp" 2>$null
                foreach ($line in $netstatLines) {
                    if ($line -match "[:\.]$Port\s" -and $line -match "\s(\d+)/") {
                        $pids += $matches[1]
                    }
                }
            }
        }
    }

    $pids = $pids | Where-Object { $_ } | Select-Object -Unique
    foreach ($procId in $pids) {
        try {
            if ($IsWindows) {
                Stop-Process -Id $procId -Force -ErrorAction Stop
            }
            else {
                Stop-PosixProcess -TargetPid ([int]$procId)
            }
        }
        catch {
            if ($IsWindows) {
                Invoke-TaskKill -TargetPid ([int]$procId)
            }
            elseif (Get-Process -Id ([int]$procId) -ErrorAction SilentlyContinue) {
                throw
            }
        }
    }
}

function Start-ManagedProcess {
    param(
        [string]$PidFile,
        [string]$WorkingDirectory,
        [string]$FilePath,
        [string[]]$ArgumentList = @(),
        [string]$StdoutPath,
        [string]$StderrPath,
        [int]$WarmupSeconds
    )

    Ensure-RunDir
    Stop-FromPidFile -PidFile $PidFile
    Remove-IfExists $StdoutPath
    Remove-IfExists $StderrPath
    New-EmptyFile -Path $StdoutPath
    New-EmptyFile -Path $StderrPath

    $resolvedFilePath = $FilePath
    $resolvedArgumentList = $ArgumentList

    if ($IsWindows -and -not [System.IO.Path]::IsPathRooted($resolvedFilePath)) {
        # Prefer an actual application shim such as .cmd over a PowerShell script shim.
        $applicationCommand = Get-ApplicationCommandPath -Names @($resolvedFilePath)
        if ($applicationCommand) {
            $resolvedFilePath = $applicationCommand
        }
    }
    elseif (-not $IsWindows) {
        $setsidCommand = Get-ApplicationCommandPath -Names @("setsid")
        if ($setsidCommand) {
            $resolvedFilePath = $setsidCommand
            $resolvedArgumentList = @($FilePath) + $ArgumentList
        }
    }

    $startProcessParams = @{
        FilePath               = $resolvedFilePath
        ArgumentList           = $resolvedArgumentList
        WorkingDirectory       = $WorkingDirectory
        RedirectStandardOutput = $StdoutPath
        RedirectStandardError  = $StderrPath
        PassThru               = $true
    }
    if ($IsWindows) {
        $startProcessParams.WindowStyle = "Hidden"
    }

    $proc = Start-Process @startProcessParams

    Set-Content -Path $PidFile -Value $proc.Id
    Start-Sleep -Seconds $WarmupSeconds
}

function Test-Url {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -Method Head -TimeoutSec 10
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    }
    catch {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 10
            return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
        }
        catch {
            return $false
        }
    }
}

function Show-DashboardCredentials {
    param(
        [string]$LogPath,
        [int]$TimeoutSeconds = 30
    )

    # The backend runs hidden with stdout redirected to the log, so the
    # initial username/password printed at startup never reaches this console.
    # Poll the log until the credentials banner shows up, then surface it.
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $pattern = "Initial username:|Initial password:|Change it after logging in|Username:"

    while ((Get-Date) -lt $deadline) {
        if (Test-Path $LogPath) {
            $lines = Get-Content -LiteralPath $LogPath -ErrorAction SilentlyContinue |
                Select-String -Pattern $pattern
            if ($lines) {
                Write-Host ""
                Write-Host "Dashboard credentials (from $(Split-Path -Leaf $LogPath)):"
                foreach ($line in $lines) {
                    Write-Host "  $($line.Line.Trim())"
                }
                Write-Host ""
                return
            }
        }
        Start-Sleep -Milliseconds 500
    }

    Write-Host "Dashboard credentials not found in $(Split-Path -Leaf $LogPath) yet."
    Write-Host "Check the log directly: $LogPath"
}

switch ($Action) {
    "run-backend" {
        Start-ManagedProcess `
            -PidFile $backendPidFile `
            -WorkingDirectory $repoRoot `
            -FilePath "uv" `
            -ArgumentList @("run", "main.py") `
            -StdoutPath $backendLog `
            -StderrPath $backendErrLog `
            -WarmupSeconds 6
        Show-DashboardCredentials -LogPath $backendLog
    }
    "run-dashboard" {
        Start-ManagedProcess `
            -PidFile $dashboardPidFile `
            -WorkingDirectory $dashboardDir `
            -FilePath "pnpm" `
            -ArgumentList @("dev") `
            -StdoutPath $dashboardLog `
            -StderrPath $dashboardErrLog `
            -WarmupSeconds 8
    }
    "stop-backend" {
        Stop-FromPidFile -PidFile $backendPidFile
        Stop-ByPort -Port 6185
        Remove-IfExists $backendPidFile
    }
    "stop-dashboard" {
        Stop-FromPidFile -PidFile $dashboardPidFile
        Stop-ByPort -Port 3000
        Remove-IfExists $dashboardPidFile
    }
    "status" {
        $backendOk = Test-Url -Url "http://127.0.0.1:6185/api/v1/openapi.json"
        $dashboardOk = Test-Url -Url "http://127.0.0.1:3000"

        Write-Host "Backend  : $(Split-Path -Leaf $backendPidFile) -> $(if ($backendOk) { 'up' } else { 'down' })"
        Write-Host "Dashboard: $(Split-Path -Leaf $dashboardPidFile) -> $(if ($dashboardOk) { 'up' } else { 'down' })"
    }
    "clean" {
        $rootCleanPaths = @(
            $runDir,
            $backendLog,
            $backendErrLog,
            $dashboardLog,
            $dashboardErrLog,
            $dashboardDist,
            $dashboardViteCache,
            (Join-Path $repoRoot ".tmp"),
            (Join-Path $repoRoot ".pytest_cache"),
            (Join-Path $repoRoot ".ruff_cache"),
            (Join-Path $repoRoot ".mypy_cache"),
            (Join-Path $repoRoot "htmlcov"),
            (Join-Path $repoRoot ".coverage"),
            (Join-Path $repoRoot "build"),
            (Join-Path $repoRoot "dist"),
            (Join-Path $repoRoot "data/dist"),
            (Join-Path $repoRoot "logs"),
            (Join-Path $repoRoot "temp")
        )

        Stop-FromPidFile -PidFile $dashboardPidFile
        Stop-FromPidFile -PidFile $backendPidFile
        Stop-ByPort -Port 3000
        Stop-ByPort -Port 6185

        foreach ($path in $rootCleanPaths) {
            Remove-IfExists $path
        }

        Remove-FilesByPattern -Root $repoRoot -Pattern "*.log"
        Remove-FilesByPattern -Root $repoRoot -Pattern "*.pyc"
        Remove-FilesByPattern -Root $repoRoot -Pattern "*.pyo"
        Remove-DirectoriesByName -Root $repoRoot -Names @("__pycache__")
    }
}
