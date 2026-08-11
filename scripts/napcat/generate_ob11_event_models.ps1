[CmdletBinding()]
param(
    [string]$SchemaPath = "",
    [string]$OutputPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

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

Require-Command -Name "uv"
Require-Command -Name "uvx"

$repoRoot = Get-RepoRoot
if ([string]::IsNullOrWhiteSpace($SchemaPath)) {
    $SchemaPath = [System.IO.Path]::Combine($repoRoot, ".tmp", "napcat-schema", "ob11-all-event.normalized.schema.json")
}
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = [System.IO.Path]::Combine($repoRoot, ".tmp", "napcat-schema", "ob11_event_models.py")
}

$SchemaPath = [System.IO.Path]::GetFullPath($SchemaPath)
$OutputPath = [System.IO.Path]::GetFullPath($OutputPath)

if (-not (Test-Path -LiteralPath $SchemaPath)) {
    throw "Schema file not found: $SchemaPath"
}
if ($SchemaPath -eq $OutputPath) {
    throw "SchemaPath and OutputPath must be different."
}

try {
    $schemaJson = [System.IO.File]::ReadAllText($SchemaPath, [System.Text.Encoding]::UTF8)
    $null = $schemaJson | ConvertFrom-Json
}
catch {
    throw "Schema file is not valid JSON: $SchemaPath"
}

Ensure-Directory -Path (Split-Path -Parent $OutputPath)
$temporaryOutputPath = "$OutputPath.tmp.py"

& uvx --python 3.14 --from datamodel-code-generator datamodel-codegen `
    --input $SchemaPath `
    --input-file-type jsonschema `
    --output $temporaryOutputPath `
    --output-model-type pydantic_v2.BaseModel `
    --target-python-version 3.14 `
    --formatters builtin `
    --disable-timestamp `
    --extra-fields forbid `
    --use-schema-description `
    --field-constraints `
    --use-generic-base-class
if ($LASTEXITCODE -ne 0) {
    throw "datamodel-code-generator failed for $SchemaPath"
}

if (-not (Test-Path -LiteralPath $temporaryOutputPath)) {
    throw "Python models file was not created: $temporaryOutputPath"
}

try {
    $null = Get-Content -LiteralPath $OutputPath -Raw
}
catch {
    throw "Generated Python models could not be read: $OutputPath"
}

& uv run ruff check --fix $temporaryOutputPath
if ($LASTEXITCODE -ne 0) {
    throw "ruff check --fix failed for generated models: $temporaryOutputPath"
}

& uv run ruff format $temporaryOutputPath
if ($LASTEXITCODE -ne 0) {
    throw "ruff format failed for generated models: $temporaryOutputPath"
}

Move-Item -LiteralPath $temporaryOutputPath -Destination $OutputPath -Force

Write-Host "Generated Python models:"
Write-Host "  $OutputPath"
