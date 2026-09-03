# deploy-cli.ps1 - Install astrbot with uv on Windows PowerShell.

#Requires -Version 7.0

$ErrorActionPreference = 'Stop'

$UseColor = [string]::IsNullOrEmpty($env:NO_COLOR) -and [Console]::IsOutputRedirected -eq $false

function Write-Status {
    param(
        [string]$Prefix,
        [string]$Message,
        [string]$Color
    )

    if ($UseColor) {
        Write-Host "$Prefix    $Message" -ForegroundColor $Color
    } else {
        Write-Host "$Prefix    $Message"
    }
}

function Info { Write-Status "[INFO]" "$args" "Cyan" }
function Warn { Write-Status "[WARN]" "$args" "Yellow" }
function Ok { Write-Status "[OK]" "$args" "Green" }
function Err { Write-Status "[ERROR]" "$args" "Red" }

function Test-Command {
    param([string]$Name)
    $null = Get-Command $Name -ErrorAction SilentlyContinue
    return $?
}

function Update-UvPath {
    $candidateDirs = @()

    if ($HOME) {
        $candidateDirs += Join-Path $HOME ".local\bin"
    }
    if ($env:USERPROFILE) {
        $candidateDirs += Join-Path $env:USERPROFILE ".local\bin"
    }
    if ($env:LOCALAPPDATA) {
        $candidateDirs += Join-Path $env:LOCALAPPDATA "uv"
    }

    foreach ($dir in $candidateDirs) {
        if ((Test-Path $dir) -and (($env:PATH -split ';') -notcontains $dir)) {
            $env:PATH = "$dir;$env:PATH"
        }
    }
}

function Install-Uv {
    Info "uv was not found. Installing uv..."

    $tempScript = [System.IO.Path]::GetTempFileName() + ".ps1"
    try {
        Invoke-WebRequest -Uri "https://astral.sh/uv/install.ps1" -OutFile $tempScript -UseBasicParsing
        & $tempScript
        Update-UvPath
    } catch {
        Err "Failed to install uv."
        Err "Please install uv manually: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    } finally {
        Remove-Item $tempScript -ErrorAction SilentlyContinue
    }
}

if (-not (Test-Command "uv")) {
    Install-Uv
}

Update-UvPath

if (-not (Test-Command "uv")) {
    Err "uv was not found after installation."
    Err "Please install uv manually: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
}

Ok (& uv --version)
Info "Installing AstrBot with Python 3.12..."
uv tool install --python 3.12 astrbot
Ok "AstrBot has been installed."
