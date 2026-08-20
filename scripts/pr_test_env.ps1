param(
    [ValidateSet("neo", "full")]
    [string]$TestProfile = "neo",
    [switch]$WithDashboard,
    [switch]$NoDashboard,
    [switch]$SkipSync,
    [switch]$SkipLint,
    [switch]$WithQuality,
    [switch]$SkipSmoke
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$runSync = -not $SkipSync
$runLint = -not $SkipLint
$runQuality = $WithQuality.IsPresent
$runSmoke = -not $SkipSmoke
$runDashboard = $false
$dashboardMode = "auto"

if ($WithDashboard) {
    $runDashboard = $true
    $dashboardMode = "force-on"
}
if ($NoDashboard) {
    $runDashboard = $false
    $dashboardMode = "force-off"
}
if ($TestProfile -eq "full" -and $dashboardMode -eq "auto") {
    $runDashboard = $true
}

function Split-CommandLineArgs {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return @()
    }

    $regexMatches = [regex]::Matches($Value, '("([^"\\]|\\.)*"|''([^''\\]|\\.)*''|[^\s]+)')
    $arguments = [System.Collections.Generic.List[string]]::new()
    foreach ($match in $regexMatches) {
        $token = $match.Value.Trim()
        if (
            ($token.StartsWith('"') -and $token.EndsWith('"')) -or
            ($token.StartsWith("'") -and $token.EndsWith("'"))
        ) {
            $token = $token.Substring(1, $token.Length - 2)
        }
        if ($token.Length -gt 0) {
            $arguments.Add($token)
        }
    }
    return $arguments
}

function Invoke-NativeCommand {
    param(
        [string]$Description,
        [string]$FilePath,
        [string[]]$ArgumentList = @(),
        [string]$WorkingDirectory = $repoRoot
    )

    Write-Host "==> $Description"
    Push-Location $WorkingDirectory
    try {
        & $FilePath @ArgumentList
        if ($LASTEXITCODE -ne 0) {
            throw "$FilePath exited with code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }
}

function Run-SmokeTest {
    $smokeLog = Join-Path ([System.IO.Path]::GetTempPath()) ("astrbot-smoke-{0}.log" -f [guid]::NewGuid())
    $smokeErrLog = Join-Path ([System.IO.Path]::GetTempPath()) ("astrbot-smoke-{0}.err.log" -f [guid]::NewGuid())

    Write-Host "==> Starting smoke test on http://localhost:6185"
    $startProcessParams = @{
        FilePath               = "uv"
        ArgumentList           = @("run", "main.py")
        WorkingDirectory       = $repoRoot
        RedirectStandardOutput = $smokeLog
        RedirectStandardError  = $smokeErrLog
        PassThru               = $true
    }
    if ($IsWindows) {
        $startProcessParams.WindowStyle = "Hidden"
    }

    $process = Start-Process @startProcessParams

    try {
        for ($attempt = 0; $attempt -lt 60; $attempt++) {
            Start-Sleep -Seconds 1

            try {
                $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:6185" -TimeoutSec 5
                if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                    Write-Host "==> Smoke test passed"
                    return
                }
            }
            catch {
                if ($process.HasExited) {
                    break
                }
            }

            $process.Refresh()
            if ($process.HasExited) {
                break
            }
        }

        $stdout = if (Test-Path $smokeLog) { Get-Content -LiteralPath $smokeLog -Raw } else { "" }
        $stderr = if (Test-Path $smokeErrLog) { Get-Content -LiteralPath $smokeErrLog -Raw } else { "" }
        throw "Smoke test failed.`nSTDOUT:`n$stdout`nSTDERR:`n$stderr"
    }
    finally {
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
            $process.WaitForExit()
        }
        Remove-Item -LiteralPath $smokeLog, $smokeErrLog -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "==> Profile: $TestProfile"
Write-Host "==> Sync dependencies: $runSync"
Write-Host "==> Run lint: $runLint"
Write-Host "==> Run quality checks: $runQuality"
Write-Host "==> Run smoke test: $runSmoke"
Write-Host "==> Build dashboard: $runDashboard"

if ($runSync) {
    Invoke-NativeCommand -Description "Syncing dependencies with uv" -FilePath "uv" -ArgumentList @("sync", "--group", "dev", "--locked")
}

Write-Host "==> Preparing test directories"
New-Item -ItemType Directory -Force -Path "data/plugins", "data/config", "data/temp", "data/skills" | Out-Null
$env:TESTING = if ($env:TESTING) { $env:TESTING } else { "true" }
$env:ZHIPU_API_KEY = if ($env:ZHIPU_API_KEY) { $env:ZHIPU_API_KEY } else { "test-api-key" }

if ($runLint) {
    Invoke-NativeCommand -Description "Running Ruff format check" -FilePath "uv" -ArgumentList @("run", "ruff", "format", "--check", ".")
    Invoke-NativeCommand -Description "Running Ruff lint check" -FilePath "uv" -ArgumentList @("run", "ruff", "check", ".")
}

if ($runQuality) {
    Invoke-NativeCommand -Description "Running focused Pyright quality checks" -FilePath "uv" -ArgumentList @("run", "pyright", "--project", "pyrightconfig.quality.json")
    Invoke-NativeCommand -Description "Running focused Bandit security checks" -FilePath "uv" -ArgumentList @(
        "run",
        "bandit",
        "-r",
        "astrbot/api",
        "astrbot/cli",
        "astrbot/core/backup",
        "astrbot/core/knowledge_base",
        "astrbot/core/skills",
        "astrbot/utils",
        "-c",
        "pyproject.toml"
    )
    Invoke-NativeCommand -Description "Running dependency vulnerability audit" -FilePath "uv" -ArgumentList @("run", "pip-audit")
    Invoke-NativeCommand -Description "Running complexity reports" -FilePath "uv" -ArgumentList @(
        "run",
        "radon",
        "cc",
        "astrbot/api",
        "astrbot/cli",
        "astrbot/core/backup",
        "astrbot/core/config",
        "astrbot/core/knowledge_base",
        "astrbot/core/skills",
        "astrbot/utils",
        "-s",
        "-n",
        "C"
    )
    Invoke-NativeCommand -Description "Running maintainability reports" -FilePath "uv" -ArgumentList @(
        "run",
        "radon",
        "mi",
        "astrbot/api",
        "astrbot/cli",
        "astrbot/core/backup",
        "astrbot/core/config",
        "astrbot/core/knowledge_base",
        "astrbot/core/skills",
        "astrbot/utils",
        "-s"
    )
}

$pytestArgs = [System.Collections.Generic.List[string]]::new()
$pytestArgs.Add("run")
$pytestArgs.Add("pytest")

if ($TestProfile -eq "neo") {
    $pytestArgs.AddRange([string[]]@(
            "-q",
            "tests/unit/test_neo_skill_sync.py",
            "tests/unit/test_neo_skill_tools.py",
            "tests/unit/test_computer_skill_sync.py",
            "tests/unit/test_skill_manager_sandbox_cache.py",
            "tests/unit/dashboard/test_dashboard.py::test_neo_skills_routes"
        ))
}
else {
    $pytestCmd = [System.Collections.Generic.List[string]]::new()
    $pytestCmd.AddRange([string[]]@("--cov=astrbot", "--cov-branch", "-v"))
    if (-not [string]::IsNullOrWhiteSpace($env:PYTEST_DEBUG)) {
        $pytestCmd.AddRange([string[]]@("-o", "log_cli=true", "-o", "log_level=DEBUG"))
    }
    $pytestArgs.AddRange($pytestCmd)
}

$extraPytestArgs = [string[]](Split-CommandLineArgs -Value $env:PYTEST_ARGS)
if ($extraPytestArgs -and $extraPytestArgs.Count -gt 0) {
    $pytestArgs.AddRange($extraPytestArgs)
}
Invoke-NativeCommand -Description "Running pytest" -FilePath "uv" -ArgumentList $pytestArgs

if ($runSmoke) {
    Run-SmokeTest
}

if ($runDashboard) {
    $dashboardDir = Join-Path $repoRoot "dashboard"
    Invoke-NativeCommand -Description "Building dashboard dependencies" -FilePath "pnpm" -ArgumentList @(
        "install",
        "--frozen-lockfile"
    ) -WorkingDirectory $dashboardDir
    Invoke-NativeCommand -Description "Building dashboard" -FilePath "pnpm" -ArgumentList @(
        "run",
        "build"
    ) -WorkingDirectory $dashboardDir
}

Write-Host "==> PR checks completed successfully"
