[CmdletBinding()]
param(
    [string]$NapCatRepoUrl = "https://github.com/NapNeko/NapCatQQ",
    [string]$CloneDir = "",
    [string]$OutputDir = "",
    [string]$TypeName = "OB11AllEvent",
    [string]$Revision = "",
    [switch]$ForceClone
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

if ([string]::IsNullOrWhiteSpace($TypeName)) {
    throw "TypeName must not be empty."
}

function Get-RepoRoot {
    $scriptDir = Split-Path -Parent $PSCommandPath
    return [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($scriptDir, "..", ".."))
}

function Require-Command {
    param([string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

function Ensure-Directory {
    param([string]$Path)

    New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

function Get-RelativePath {
    param(
        [string]$BasePath,
        [string]$TargetPath
    )

    $baseUri = [System.Uri]((Resolve-Path -LiteralPath $BasePath).Path + [System.IO.Path]::DirectorySeparatorChar)
    $targetUri = [System.Uri](Resolve-Path -LiteralPath $TargetPath).Path
    return $baseUri.MakeRelativeUri($targetUri).ToString()
}

function Convert-PathForTsConfig {
    param([string]$Path)

    return $Path.Replace("\", "/")
}

function Write-MinimalTsConfig {
    param(
        [string]$ConfigPath,
        [string]$EventFile,
        [string]$SegmentFile
    )

    $configDir = Split-Path -Parent $ConfigPath
    $eventRelative = Convert-PathForTsConfig (Get-RelativePath -BasePath $configDir -TargetPath $EventFile)
    $segmentRelative = Convert-PathForTsConfig (Get-RelativePath -BasePath $configDir -TargetPath $SegmentFile)

    $config = [ordered]@{
        compilerOptions = [ordered]@{
            target = "ES2020"
            module = "ESNext"
            moduleResolution = "bundler"
            strict = $true
            skipLibCheck = $true
            allowImportingTsExtensions = $true
            resolveJsonModule = $true
            isolatedModules = $true
            noEmit = $true
        }
        files = @(
            $eventRelative,
            $segmentRelative
        )
    }

    $json = $config | ConvertTo-Json -Depth 8
    Set-Content -LiteralPath $ConfigPath -Value $json -Encoding UTF8
}

function Ensure-NapCatRepo {
    param(
        [string]$RepoUrl,
        [string]$Path,
        [bool]$ResetClone,
        [string]$PinnedRevision
    )

    if ($ResetClone -and (Test-Path -LiteralPath $Path)) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }

    if (Test-Path -LiteralPath $Path) {
        Write-Host "Reusing NapCat repository at $Path"
        return
    }

    Ensure-Directory -Path (Split-Path -Parent $Path)
    git clone --depth 1 --filter=blob:none $RepoUrl $Path
    if ($LASTEXITCODE -ne 0) {
        throw "git clone failed: $RepoUrl"
    }
    git fetch --depth 1 origin $PinnedRevision
    git checkout --detach $PinnedRevision
}

Require-Command -Name "git"
Require-Command -Name "pnpm"

$repoRoot = Get-RepoRoot
$revisionFile = [System.IO.Path]::Combine($repoRoot, "scripts", "napcat", "napcat-revision.txt")
if ([string]::IsNullOrWhiteSpace($Revision)) {
    $Revision = (Get-Content -LiteralPath $revisionFile -Raw).Trim()
}
if ([string]::IsNullOrWhiteSpace($Revision)) {
    throw "NapCat revision must not be empty."
}
if ([string]::IsNullOrWhiteSpace($CloneDir)) {
    $CloneDir = [System.IO.Path]::Combine($repoRoot, ".tmp", "NapCatQQ")
}
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = [System.IO.Path]::Combine($repoRoot, ".tmp", "napcat-schema")
}

$cloneDir = [System.IO.Path]::GetFullPath($CloneDir)
$outputDir = [System.IO.Path]::GetFullPath($OutputDir)

Ensure-NapCatRepo -RepoUrl $NapCatRepoUrl -Path $cloneDir -ResetClone:$ForceClone.IsPresent -PinnedRevision $Revision
if ((git -C $cloneDir rev-parse HEAD).Trim() -ne $Revision) {
    git -C $cloneDir fetch --depth 1 origin $Revision
    git -C $cloneDir checkout --detach $Revision
}
Ensure-Directory -Path $outputDir

$eventFile = [System.IO.Path]::Combine(
    $cloneDir,
    "packages",
    "napcat-webui-frontend",
    "src",
    "types",
    "onebot",
    "event.ts"
)
$segmentFile = [System.IO.Path]::Combine(
    $cloneDir,
    "packages",
    "napcat-webui-frontend",
    "src",
    "types",
    "onebot",
    "segment.ts"
)

if (-not (Test-Path -LiteralPath $eventFile)) {
    throw "NapCat event type file not found: $eventFile"
}
if (-not (Test-Path -LiteralPath $segmentFile)) {
    throw "NapCat segment type file not found: $segmentFile"
}

$schemaTestDir = Join-Path $outputDir "ob11-schema-test"
Ensure-Directory -Path $schemaTestDir
$tsconfigPath = Join-Path $schemaTestDir "tsconfig.json"
Write-MinimalTsConfig -ConfigPath $tsconfigPath -EventFile $eventFile -SegmentFile $segmentFile

$schemaPath = Join-Path $outputDir "ob11-all-event.schema.json"
if ($schemaPath -eq $tsconfigPath) {
    throw "Schema output path must not collide with the generated tsconfig path."
}

$env:PNPM_HOME = [System.IO.Path]::Combine($repoRoot, ".tmp", "pnpm-home")
$env:PNPM_STORE_DIR = [System.IO.Path]::Combine($repoRoot, ".tmp", "pnpm-store")
$env:XDG_CACHE_HOME = [System.IO.Path]::Combine($repoRoot, ".tmp", "xdg-cache")
Ensure-Directory -Path $env:PNPM_HOME
Ensure-Directory -Path $env:PNPM_STORE_DIR
Ensure-Directory -Path $env:XDG_CACHE_HOME

& pnpm dlx typescript-json-schema `
    $tsconfigPath `
    $TypeName `
    --noExtraProps `
    --required `
    --topRef `
    --out $schemaPath
if ($LASTEXITCODE -ne 0) {
    throw "typescript-json-schema generation failed for $TypeName"
}

if (-not (Test-Path -LiteralPath $schemaPath)) {
    throw "Schema file was not created: $schemaPath"
}

try {
    $rawJson = [System.IO.File]::ReadAllText($schemaPath, [System.Text.Encoding]::UTF8)
    $null = $rawJson | ConvertFrom-Json
}
catch {
    throw "Generated schema is not valid JSON: $schemaPath"
}

Write-Host "Generated schema:"
Write-Host "  $schemaPath"
Write-Host "Generated tsconfig:"
Write-Host "  $tsconfigPath"
