param(
  [Parameter(Mandatory = $true)]
  [string]$Tool,

  [Parameter(Mandatory = $true)]
  [string[]]$Patterns,

  [string]$ToolArgs = '',

  [int]$BatchSize = 64
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$files = @(git ls-files -- @Patterns | Where-Object { $_ })
if ($files.Count -eq 0) {
  exit 0
}

$extraArgs = @()
if ($ToolArgs) {
  $extraArgs = @($ToolArgs -split ';' | Where-Object { $_ })
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$toolExecutable = if ($IsWindows) { "$Tool.cmd" } else { $Tool }
$toolPath = Join-Path $repoRoot "node_modules/.bin/$toolExecutable"
if (-not (Test-Path -LiteralPath $toolPath -PathType Leaf)) {
  throw "Node tool '$Tool' is not installed. Run 'npm ci' at the repository root."
}

for ($index = 0; $index -lt $files.Count; $index += $BatchSize) {
  $end = [Math]::Min($index + $BatchSize - 1, $files.Count - 1)
  $batch = $files[$index..$end]
  & $toolPath @extraArgs @batch
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
}
