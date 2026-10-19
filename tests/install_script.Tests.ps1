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
    $ast.Extent.Text -notmatch '\$Indent = ''  ''' -or
    $ast.Extent.Text -notmatch 'Write-Host "\$Indent\$Prefix    \$Message"' -or
    $ast.Extent.Text -notmatch 'Write-Host "\$\(\$Indent\)\$\(\$Indent\)astrbot init"' -or
    $ast.Extent.Text -notmatch 'Write-Host "\$\(\$Indent\)\$\(\$Indent\)astrbot run"' -or
    $ast.Extent.Text -notmatch 'if \(\$Language -eq ''zh-CN''\) \{ ''1'' \} else \{ ''2'' \}') {
    throw 'The bootstrap menu must remain ASCII-only, default to English, and select the source default by language.'
}
if ($ast.Extent.Text -match 'mirror\.nyist\.edu\.cn' -or
    $ast.Extent.Text -match 'https://astral\.sh/uv/install\.ps1' -or
    $ast.Extent.Text -notmatch 'https://github\.com/astral-sh/uv/releases/latest/download' -or
    $ast.Extent.Text -notmatch 'Microsoft\.PowerShell\.Commands\.WebRequestSession' -or
    $ast.Extent.Text -notmatch '-NoNewWindow -Wait -PassThru') {
    throw 'uv must use the verified ZIP flow, support the USTC cookie challenge, and keep installation in the current window.'
}

$zipFunctionAst = $ast.Find({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq 'Test-ZipArchive'
}, $true)
if (-not $zipFunctionAst) { throw 'Test-ZipArchive is missing.' }
Invoke-Expression $zipFunctionAst.Extent.Text

$archiveTestDir = Join-Path ([System.IO.Path]::GetTempPath()) ("astrbot-install-test-{0}" -f [guid]::NewGuid())
$null = New-Item -ItemType Directory -Path $archiveTestDir
try {
    $validArchive = Join-Path $archiveTestDir 'valid.zip'
    $htmlResponse = Join-Path $archiveTestDir 'verification.html'
    $shortFile = Join-Path $archiveTestDir 'short.bin'
    [System.IO.File]::WriteAllBytes($validArchive, [byte[]](0x50, 0x4B, 0x03, 0x04))
    [System.IO.File]::WriteAllText($htmlResponse, '<!doctype html><title>Verifying</title>')
    [System.IO.File]::WriteAllBytes($shortFile, [byte[]](0x50, 0x4B, 0x03))
    if (-not (Test-ZipArchive $validArchive) -or
        (Test-ZipArchive $htmlResponse) -or
        (Test-ZipArchive $shortFile) -or
        (Test-ZipArchive (Join-Path $archiveTestDir 'missing.zip'))) {
        throw 'ZIP signature validation did not accept only a valid archive signature.'
    }
} finally {
    Remove-Item -LiteralPath $archiveTestDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item Function:\Test-ZipArchive -ErrorAction SilentlyContinue
}

$global:UvArguments = @()
$global:UvPythonMirrors = @()
$global:FailNextToolInstall = $false
function global:uv {
    $global:UvArguments += ,@($args)
    $global:LASTEXITCODE = 0
    if ($args.Count -eq 1 -and $args[0] -eq '--version') {
        'uv test-version'
    } elseif ($args.Count -gt 1 -and $args[0] -eq 'tool' -and $args[1] -eq 'install') {
        $global:UvPythonMirrors += [string]$env:UV_PYTHON_INSTALL_MIRROR
        if ($global:FailNextToolInstall) {
            $global:FailNextToolInstall = $false
            $global:LASTEXITCODE = 1
        }
    }
}

$previousPythonMirror = $env:UV_PYTHON_INSTALL_MIRROR
$env:UV_PYTHON_INSTALL_MIRROR = $null
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

    $global:FailNextToolInstall = $true
    & $scriptPath -Language zh-CN -DownloadSource china -NonInteractive
    if ($LASTEXITCODE -ne 0) {
        throw "China mirror fallback failed with exit code $LASTEXITCODE."
    }
    $fallbackMirrors = @($global:UvPythonMirrors | Select-Object -Last 2)
    $ustcMirror = 'https://mirrors.ustc.edu.cn/github-release/astral-sh/python-build-standalone/'
    if ($fallbackMirrors.Count -ne 2 -or
        $fallbackMirrors[0] -ne $ustcMirror -or
        $fallbackMirrors[1] -ne '') {
        throw "Expected USTC then official Python sources; got: $($fallbackMirrors -join ', ')"
    }
} finally {
    $env:UV_PYTHON_INSTALL_MIRROR = $previousPythonMirror
    Remove-Item Function:\uv -ErrorAction SilentlyContinue
}

$uvInstallFunctionAst = $ast.Find({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq 'Invoke-UvToolInstall'
}, $true)
if (-not $uvInstallFunctionAst) { throw 'Invoke-UvToolInstall is missing.' }
Invoke-Expression $uvInstallFunctionAst.Extent.Text

$applicationTestDir = Join-Path ([System.IO.Path]::GetTempPath()) ("astrbot-uv-process-test-{0}" -f [guid]::NewGuid())
$null = New-Item -ItemType Directory -Path $applicationTestDir
$previousPath = $env:PATH
try {
    Copy-Item -LiteralPath "$env:SystemRoot\System32\cmd.exe" -Destination (Join-Path $applicationTestDir 'uv.exe')
    $env:PATH = "$applicationTestDir;$env:PATH"
    $exitCode = Invoke-UvToolInstall -ArgumentList @('/d', '/c', 'exit', '0')
    if ($exitCode -ne 0) {
        throw "The no-new-window uv process path returned exit code $exitCode."
    }
} finally {
    $env:PATH = $previousPath
    Remove-Item -LiteralPath $applicationTestDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item Function:\Invoke-UvToolInstall -ErrorAction SilentlyContinue
}

Write-Host "install.ps1 passed direct-file and Invoke-Expression tests on $($PSVersionTable.PSEdition) $($PSVersionTable.PSVersion)."
