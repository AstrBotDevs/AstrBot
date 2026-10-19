[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$scriptPath = (Resolve-Path (Join-Path $PSScriptRoot '..\docs\public\install.ps1')).Path
$scriptBytes = [System.IO.File]::ReadAllBytes($scriptPath)

if ($scriptBytes.Length -ge 3 -and
    $scriptBytes[0] -eq 0xEF -and
    $scriptBytes[1] -eq 0xBB -and
    $scriptBytes[2] -eq 0xBF) {
    throw 'install.ps1 must be UTF-8 without BOM because Invoke-WebRequest preserves the BOM before Invoke-Expression.'
}

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $scriptPath,
    [ref]$tokens,
    [ref]$parseErrors
)
if ($parseErrors.Count -ne 0) {
    throw "install.ps1 has parser errors: $($parseErrors.Message -join '; ')"
}
if (-not $ast.ParamBlock) {
    throw 'install.ps1 must retain its top-level param block.'
}
if ($ast.Extent.Text -notmatch '\$bootstrapCompressed = \[Convert\]::FromBase64String' -or
    $ast.Extent.Text -notmatch '\$languages = @\(''en-US'', ''zh-CN'', ''ja-JP''\)' -or
    $ast.Extent.Text -notmatch '\$defaultLanguage = ''en-US''' -or
    $ast.Extent.Text -notmatch 'if \(\$Language -eq ''zh-CN''\) \{ ''1'' \} else \{ ''2'' \}') {
    throw 'The bootstrap menu must remain ASCII-only, default to English, and select the source default by language.'
}

$global:UvArguments = @()
function global:uv {
    $global:UvArguments += ,@($args)
    $global:LASTEXITCODE = 0
    if ($args.Count -eq 1 -and $args[0] -eq '--version') {
        'uv test-version'
    }
}

try {
    & $scriptPath -Language en-US -DownloadSource official -NonInteractive
    if ($LASTEXITCODE -ne 0) {
        throw "Direct script execution failed with exit code $LASTEXITCODE."
    }

    # Decode the raw bytes ourselves so this exercises the same parser path as
    # `Invoke-WebRequest ... | Invoke-Expression`, including any leading BOM.
    $downloadedScript = [System.Text.Encoding]::UTF8.GetString($scriptBytes)
    $downloadedScript | Invoke-Expression
    if ($LASTEXITCODE -ne 0) {
        throw "Invoke-Expression execution failed with exit code $LASTEXITCODE."
    }
} finally {
    Remove-Item Function:\uv -ErrorAction SilentlyContinue
}

$versionCalls = @($global:UvArguments | Where-Object { $_.Count -eq 1 -and $_[0] -eq '--version' })
$installCalls = @($global:UvArguments | Where-Object {
    $_.Count -eq 7 -and
    $_[0] -eq 'tool' -and
    $_[1] -eq 'install' -and
    $_[2] -eq '--python' -and
    $_[3] -eq '3.12' -and
    $_[4] -eq 'astrbot' -and
    $_[5] -eq '--default-index' -and
    $_[6] -eq 'https://pypi.org/simple/'
})

if ($versionCalls.Count -ne 2 -or $installCalls.Count -ne 2) {
    throw "Expected both execution modes to reach uv; got $($versionCalls.Count) version calls and $($installCalls.Count) install calls."
}

Write-Host "install.ps1 passed direct-file and Invoke-Expression tests on $($PSVersionTable.PSEdition) $($PSVersionTable.PSVersion)."
