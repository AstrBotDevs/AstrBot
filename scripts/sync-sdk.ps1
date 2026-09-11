[CmdletBinding()]
param(
    [string]$RemoteName = "sdk-remote",
    [string]$RemoteBranch = "vendor-branch",
    [string]$Prefix = "astrbot-sdk",
    [switch]$NoWait
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )

    & git @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed with exit code $LASTEXITCODE."
    }
}

function Test-GitObjectPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Revision,
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    & git cat-file -e "$Revision`:$Path" 2>$null
    return $LASTEXITCODE -eq 0
}

function Assert-RemoteExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $remoteNames = (& git remote)
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to read git remotes."
    }

    if ($remoteNames -notcontains $Name) {
        throw "Git remote '$Name' is missing. Add it first, for example: git remote add $Name https://github.com/united-pooh/astrbot-sdk.git"
    }
}

function Assert-CleanWorktree {
    $statusOutput = (& git status --porcelain=v1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to inspect git worktree status."
    }

    if ($statusOutput) {
        throw "Worktree is not clean. Commit or stash changes before syncing the vendored SDK.`n$statusOutput"
    }
}

function Assert-LocalPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Reason
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Expected local path '$Path' is missing. $Reason"
    }
}

function Assert-RemotePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Revision,
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Reason
    )

    if (-not (Test-GitObjectPath -Revision $Revision -Path $Path)) {
        throw "Remote snapshot '$Revision' is missing '$Path'. $Reason"
    }
}

function Test-ShouldWaitBeforeExit {
    if ($NoWait.IsPresent) {
        return $false
    }

    if ($env:ASTRBOT_SYNC_SDK_NO_WAIT -eq "1") {
        return $false
    }

    try {
        return (
            [Environment]::UserInteractive -and
            -not [Console]::IsInputRedirected -and
            -not [Console]::IsOutputRedirected
        )
    } catch {
        return $false
    }
}

function Wait-BeforeExit {
    if (-not (Test-ShouldWaitBeforeExit)) {
        return
    }

    Write-Host ""
    Write-Host "Press any key to close this window..."
    $null = [System.Console]::ReadKey($true)
}

try {
    $repoRoot = (& git rev-parse --show-toplevel).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($repoRoot)) {
        throw "This script must run inside a git repository."
    }

    Set-Location -LiteralPath $repoRoot

    $localRequiredPaths = @(
        (Join-Path $Prefix "pyproject.toml"),
        (Join-Path $Prefix "README.md"),
        (Join-Path $Prefix "src/astrbot_sdk/__init__.py")
    )

    foreach ($requiredPath in $localRequiredPaths) {
        Assert-LocalPath -Path $requiredPath -Reason "The current AstrBot workspace expects '$Prefix' to keep the SDK's editable package layout."
    }

    Assert-RemoteExists -Name $RemoteName
    Assert-CleanWorktree

    Write-Host "Fetching $RemoteName/$RemoteBranch..."
    Invoke-Git fetch $RemoteName $RemoteBranch

    $remoteRef = "refs/remotes/$RemoteName/$RemoteBranch"
    $remoteCommit = (& git rev-parse $remoteRef).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($remoteCommit)) {
        throw "Unable to resolve remote ref '$remoteRef' after fetch."
    }

    # Fail fast if the source branch does not match the package layout the main repo
    # currently installs via `astrbot-sdk = { path = \"./astrbot-sdk\", editable = true }`.
    # Pulling an incompatible snapshot would silently break dependency resolution.
    $remoteRequiredPaths = @(
        "pyproject.toml",
        "README.md",
        "src/astrbot_sdk/__init__.py"
    )

    foreach ($requiredPath in $remoteRequiredPaths) {
        Assert-RemotePath -Revision $remoteRef -Path $requiredPath -Reason "The vendor branch must expose the full SDK package layout required by the main repo before subtree sync is allowed."
    }

    Write-Host "Pulling $RemoteName/$RemoteBranch into $Prefix with git subtree --squash..."
    Invoke-Git subtree pull "--prefix=$Prefix" $RemoteName $RemoteBranch --squash

    foreach ($requiredPath in $localRequiredPaths) {
        Assert-LocalPath -Path $requiredPath -Reason "The subtree pull finished, but the local SDK layout is incomplete."
    }

    Write-Host ""
    Write-Host "SDK sync completed successfully."
    Write-Host "Review the result with:"
    Write-Host "  git status --short"
    Write-Host "  Get-ChildItem $Prefix"
    Write-Host "  Test-Path $Prefix\\pyproject.toml"
    Write-Host "  Test-Path $Prefix\\src\\astrbot_sdk\\__init__.py"
} finally {
    # Keep interactive terminal windows open so manual sync runs do not disappear
    # before the user can inspect success or failure output.
    Wait-BeforeExit
}
