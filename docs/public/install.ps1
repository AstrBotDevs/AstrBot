#Requires -Version 5.1

# Install AstrBot with uv on Windows PowerShell.
[CmdletBinding()]
param(
    # Invoke-Expression validates omitted string parameters as empty values.
    [ValidateSet('', 'zh-CN', 'en-US', 'ja-JP')]
    [string]$Language,
    [ValidateSet('', 'china', 'official', 'custom')]
    [string]$DownloadSource,
    [string]$UvDownloadBaseUrl,
    [string]$PypiIndexUrl,
    [string]$PythonInstallMirror,
    [switch]$NonInteractive
)

$ErrorActionPreference = 'Stop'

# Windows PowerShell 5.1 may otherwise negotiate an obsolete TLS version.
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$UseColor = [string]::IsNullOrEmpty($env:NO_COLOR) -and [Console]::IsOutputRedirected -eq $false
$CanPrompt = -not $NonInteractive -and [Environment]::UserInteractive -and -not [Console]::IsInputRedirected
$Indent = '  '

# Keep the first-run experience predictable across machines. Users can still
# choose Chinese or Japanese explicitly in the language menu.
# Use JSON Unicode escapes so Windows PowerShell 5.1 can read this file
# with any system encoding, while downloaded UTF-8 scripts also work without a BOM.
$bootstrapText = ConvertFrom-Json @'
{
    "InstallerTitle": "\ud83c\udf0c AstrBot Installer",
    "LanguagePrompt": "Select language / \u8bf7\u9009\u62e9\u8bed\u8a00 / \u8a00\u8a9e\u3092\u9078\u629e\u3057\u3066\u304f\u3060\u3055\u3044",
    "Chinese": "\u7b80\u4f53\u4e2d\u6587",
    "English": "English",
    "Japanese": "\u65e5\u672c\u8a9e",
    "NextStepsEnglish": "Next, run these commands:",
    "NextStepsChinese": "\u63a5\u4e0b\u6765\u53ef\u4ee5\u4f9d\u6b21\u6267\u884c\u4ee5\u4e0b\u6307\u4ee4\u6765\u521d\u59cb\u5316\u548c\u542f\u52a8 AstrBot\uff1a",
    "NextStepsJapanese": "\u6b21\u306b\u3001\u4ee5\u4e0b\u3092\u9806\u756a\u306b\u5b9f\u884c\u3057\u3066\u304f\u3060\u3055\u3044\uff1a",
    "PythonFallbackEnglish": "Python mirror failed; retrying with the official source...",
    "PythonFallbackChinese": "Python \u955c\u50cf\u4e0b\u8f7d\u5931\u8d25\uff0c\u6b63\u5728\u5207\u6362\u5230\u5b98\u65b9\u6e90\u91cd\u8bd5\u2026",
    "PythonFallbackJapanese": "Python \u30df\u30e9\u30fc\u306b\u5931\u6557\u3057\u305f\u305f\u3081\u3001\u516c\u5f0f\u30bd\u30fc\u30b9\u3067\u518d\u8a66\u884c\u3057\u3066\u3044\u307e\u3059\u2026"
}
'@

$defaultLanguage = 'en-US'

if (-not $Language) {
    $Language = $defaultLanguage
    if ($CanPrompt) {
        $languages = @('en-US', 'zh-CN', 'ja-JP')
        $defaultChoice = [array]::IndexOf($languages, $Language) + 1
        Write-Host "`n$Indent$($bootstrapText.InstallerTitle)" -ForegroundColor Cyan
        Write-Host "$Indent-----------------------" -ForegroundColor DarkGray
        Write-Host "`n$Indent$($bootstrapText.LanguagePrompt)"
        Write-Host "$Indent  1. $($bootstrapText.English)"
        Write-Host "$Indent  2. $($bootstrapText.Chinese)"
        Write-Host "$Indent  3. $($bootstrapText.Japanese)"
        do {
            $choice = Read-Host "${Indent}1-3 [$defaultChoice]"
        } until ($choice -eq '' -or $choice -in @('1', '2', '3'))
        if ($choice) { $Language = $languages[[int]$choice - 1] }
    }
}

$messages = ConvertFrom-Json @'
{
    "zh-CN": {
        "ChooseSource": "\u8bf7\u9009\u62e9\u4e0b\u8f7d\u6e90",
        "China": "\u4e2d\u56fd\u5927\u9646\u52a0\u901f\u4e0b\u8f7d\u955c\u50cf\u6e90",
        "Official": "\u5b98\u65b9\u6e90",
        "Custom": "\u81ea\u5b9a\u4e49",
        "Choice": "\u8f93\u5165\u7f16\u53f7\uff0c\u6309\u56de\u8f66\u4f7f\u7528\u9ed8\u8ba4\u9009\u9879",
        "InvalidChoice": "\u8bf7\u8f93\u5165 1\u30012 \u6216 3\u3002",
        "UvUrl": "uv ZIP \u4e0b\u8f7d\u76ee\u5f55 URL\uff08\u4e0d\u542b\u6587\u4ef6\u540d\uff09",
        "PypiUrl": "PyPI simple \u7d22\u5f15 URL",
        "CustomRequired": "\u81ea\u5b9a\u4e49\u6e90\u9700\u8981\u540c\u65f6\u63d0\u4f9b UvDownloadBaseUrl \u548c PypiIndexUrl\u3002",
        "InvalidUrl": "\u4e0b\u8f7d\u6e90\u5fc5\u987b\u662f\u6709\u6548\u7684 HTTPS URL\uff1a{0}",
        "WindowsOnly": "\u8bf7\u5728 Windows \u4e0a\u8fd0\u884c\u6b64 PowerShell \u811a\u672c\uff1bLinux/macOS \u8bf7\u4f7f\u7528 install.sh\u3002",
        "Source": "\u4e0b\u8f7d\u6e90\uff1a{0}",
        "UvMirror": "uv \u4e0b\u8f7d\u76ee\u5f55\uff1a{0}",
        "Pypi": "PyPI \u7d22\u5f15\uff1a{0}",
        "PythonMirror": "Python \u4e0b\u8f7d\u955c\u50cf\uff1a{0}",
        "PythonDefault": "Python \u4e0b\u8f7d\u6cbf\u7528 uv \u7684\u914d\u7f6e\uff1b\u5982\u9700\u52a0\u901f\uff0c\u53ef\u901a\u8fc7 -PythonInstallMirror \u6307\u5b9a\u955c\u50cf\uff08PyPI \u955c\u50cf\u4e0d\u5305\u542b Python \u89e3\u91ca\u5668\uff09\u3002",
        "InstallingUv": "\u672a\u627e\u5230 uv\uff0c\u6b63\u5728\u5b89\u88c5\u2026",
        "TryingMirror": "\u6b63\u5728\u5c1d\u8bd5 uv \u955c\u50cf\uff1a{0}",
        "MirrorFailed": "uv \u955c\u50cf\u4e0b\u8f7d\u5931\u8d25\uff1a{0}",
        "OfficialFallback": "\u6b63\u5728\u5c1d\u8bd5 uv \u5b98\u65b9\u5b89\u88c5\u5668\u2026",
        "UnsupportedArch": "\u4e0d\u652f\u6301\u7684 Windows \u67b6\u7784\uff1a{0}",
        "InvalidChecksum": "uv \u538b\u7f29\u5305 SHA256 \u6821\u9a8c\u5931\u8d25\u3002",
        "MissingBinaries": "uv \u538b\u7f29\u5305\u4e2d\u7f3a\u5c11 uv.exe \u6216 uvx.exe\u3002",
        "UvFailed": "uv \u5b89\u88c5\u5931\u8d25\u3002\u8bf7\u53c2\u8003 https://docs.astral.sh/uv/getting-started/installation/",
        "InstallingAstrBot": "\u6b63\u5728\u4f7f\u7528 Python 3.12 \u5b89\u88c5 AstrBot\u2026",
        "AstrBotFailed": "AstrBot \u5b89\u88c5\u5931\u8d25\uff08\u9000\u51fa\u7801 {0}\uff09\u3002\u8bf7\u68c0\u67e5\u4e0a\u65b9\u7684\u4e0b\u8f7d\u6216\u4f9d\u8d56\u9519\u8bef\u3002",
        "Installed": "AstrBot \u5b89\u88c5\u5b8c\u6210\u3002",
        "ReloadShell": "\u8bf7\u6839\u636e\u4f60\u4f7f\u7528\u7684\u7ec8\u7aef\u91cd\u65b0\u52a0\u8f7d\u73af\u5883\uff1a",
        "RunCommands": "\u91cd\u65b0\u52a0\u8f7d\u540e\uff0c\u8bf7\u624b\u52a8\u8fd0\u884c\uff1a"
    },
    "en-US": {
        "ChooseSource": "Select a download source",
        "China": "Mainland China accelerated download mirrors",
        "Official": "Official sources",
        "Custom": "Custom",
        "Choice": "Enter a number, or press Enter to use the default",
        "InvalidChoice": "Please enter 1, 2, or 3.",
        "UvUrl": "uv ZIP download directory URL (without the filename)",
        "PypiUrl": "PyPI simple index URL",
        "CustomRequired": "Custom sources require both UvDownloadBaseUrl and PypiIndexUrl.",
        "InvalidUrl": "Download sources must be valid HTTPS URLs: {0}",
        "WindowsOnly": "Run this PowerShell script on Windows; use install.sh on Linux/macOS.",
        "Source": "Download source: {0}",
        "UvMirror": "uv download directory: {0}",
        "Pypi": "PyPI index: {0}",
        "PythonMirror": "Python download mirror: {0}",
        "PythonDefault": "Python downloads use the existing uv configuration. Set -PythonInstallMirror to use a mirror (PyPI mirrors do not include Python interpreters).",
        "InstallingUv": "uv was not found. Installing uv...",
        "TryingMirror": "Trying uv mirror: {0}",
        "MirrorFailed": "uv mirror download failed: {0}",
        "OfficialFallback": "Trying the official uv installer...",
        "UnsupportedArch": "Unsupported Windows architecture: {0}",
        "InvalidChecksum": "uv archive SHA256 verification failed.",
        "MissingBinaries": "The uv archive is missing uv.exe or uvx.exe.",
        "UvFailed": "Failed to install uv. See https://docs.astral.sh/uv/getting-started/installation/",
        "InstallingAstrBot": "Installing AstrBot with Python 3.12...",
        "AstrBotFailed": "AstrBot installation failed (exit code {0}). Check the download or dependency errors above.",
        "Installed": "AstrBot has been installed.",
        "ReloadShell": "Reload the environment for your shell:",
        "RunCommands": "Then run these commands manually:"
    },
    "ja-JP": {
        "ChooseSource": "\u30c0\u30a6\u30f3\u30ed\u30fc\u30c9\u5143\u3092\u9078\u629e\u3057\u3066\u304f\u3060\u3055\u3044",
        "China": "\u4e2d\u56fd\u672c\u571f\u5411\u3051\u9ad8\u901f\u30c0\u30a6\u30f3\u30ed\u30fc\u30c9\u30df\u30e9\u30fc",
        "Official": "\u516c\u5f0f\u30bd\u30fc\u30b9",
        "Custom": "\u30ab\u30b9\u30bf\u30e0",
        "Choice": "\u756a\u53f7\u3092\u5165\u529b\u3057\u3066\u304f\u3060\u3055\u3044\u3002Enter \u3067\u65e2\u5b9a\u5024\u3092\u4f7f\u7528\u3057\u307e\u3059",
        "InvalidChoice": "1\u30012\u30013 \u306e\u3044\u305a\u308c\u304b\u3092\u5165\u529b\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
        "UvUrl": "uv ZIP \u306e\u30c0\u30a6\u30f3\u30ed\u30fc\u30c9\u30c7\u30a3\u30ec\u30af\u30c8\u30ea URL\uff08\u30d5\u30a1\u30a4\u30eb\u540d\u3092\u9664\u304f\uff09",
        "PypiUrl": "PyPI simple \u30a4\u30f3\u30c7\u30c3\u30af\u30b9 URL",
        "CustomRequired": "\u30ab\u30b9\u30bf\u30e0\u30bd\u30fc\u30b9\u306b\u306f UvDownloadBaseUrl \u3068 PypiIndexUrl \u306e\u4e21\u65b9\u304c\u5fc5\u8981\u3067\u3059\u3002",
        "InvalidUrl": "\u30c0\u30a6\u30f3\u30ed\u30fc\u30c9\u5143\u306b\u306f\u6709\u52b9\u306a HTTPS URL \u3092\u6307\u5b9a\u3057\u3066\u304f\u3060\u3055\u3044\uff1a{0}",
        "WindowsOnly": "\u3053\u306e PowerShell \u30b9\u30af\u30ea\u30d7\u30c8\u306f Windows \u7528\u3067\u3059\u3002Linux/macOS \u3067\u306f install.sh \u3092\u4f7f\u7528\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
        "Source": "\u30c0\u30a6\u30f3\u30ed\u30fc\u30c9\u5143\uff1a{0}",
        "UvMirror": "uv \u30c0\u30a6\u30f3\u30ed\u30fc\u30c9\u30c7\u30a3\u30ec\u30af\u30c8\u30ea\uff1a{0}",
        "Pypi": "PyPI \u30a4\u30f3\u30c7\u30c3\u30af\u30b9\uff1a{0}",
        "PythonMirror": "Python \u30c0\u30a6\u30f3\u30ed\u30fc\u30c9\u30df\u30e9\u30fc\uff1a{0}",
        "PythonDefault": "Python \u306e\u30c0\u30a6\u30f3\u30ed\u30fc\u30c9\u306b\u306f\u65e2\u5b58\u306e uv \u8a2d\u5b9a\u3092\u4f7f\u7528\u3057\u307e\u3059\u3002\u30df\u30e9\u30fc\u3092\u4f7f\u3046\u306b\u306f -PythonInstallMirror \u3092\u6307\u5b9a\u3057\u3066\u304f\u3060\u3055\u3044\uff08PyPI \u30df\u30e9\u30fc\u306b Python \u672c\u4f53\u306f\u542b\u307e\u308c\u307e\u305b\u3093\uff09\u3002",
        "InstallingUv": "uv \u304c\u898b\u3064\u304b\u308a\u307e\u305b\u3093\u3002\u30a4\u30f3\u30b9\u30c8\u30fc\u30eb\u3057\u3066\u3044\u307e\u3059\u2026",
        "TryingMirror": "uv \u30df\u30e9\u30fc\u3092\u8a66\u3057\u3066\u3044\u307e\u3059\uff1a{0}",
        "MirrorFailed": "uv \u30df\u30e9\u30fc\u304b\u3089\u306e\u30c0\u30a6\u30f3\u30ed\u30fc\u30c9\u306b\u5931\u6557\u3057\u307e\u3057\u305f\uff1a{0}",
        "OfficialFallback": "uv \u306e\u516c\u5f0f\u30a4\u30f3\u30b9\u30c8\u30fc\u30e9\u30fc\u3092\u8a66\u3057\u3066\u3044\u307e\u3059\u2026",
        "UnsupportedArch": "\u672a\u5bfe\u5fdc\u306e Windows \u30a2\u30fc\u30ad\u30c6\u30af\u30c1\u30e3\uff1a{0}",
        "InvalidChecksum": "uv \u30a2\u30fc\u30ab\u30a4\u30d6\u306e SHA256 \u691c\u8a3c\u306b\u5931\u6557\u3057\u307e\u3057\u305f\u3002",
        "MissingBinaries": "uv \u30a2\u30fc\u30ab\u30a4\u30d6\u306b uv.exe \u307e\u305f\u306f uvx.exe \u304c\u3042\u308a\u307e\u305b\u3093\u3002",
        "UvFailed": "uv \u306e\u30a4\u30f3\u30b9\u30c8\u30fc\u30eb\u306b\u5931\u6557\u3057\u307e\u3057\u305f\u3002https://docs.astral.sh/uv/getting-started/installation/ \u3092\u53c2\u7167\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
        "InstallingAstrBot": "Python 3.12 \u3067 AstrBot \u3092\u30a4\u30f3\u30b9\u30c8\u30fc\u30eb\u3057\u3066\u3044\u307e\u3059\u2026",
        "AstrBotFailed": "AstrBot \u306e\u30a4\u30f3\u30b9\u30c8\u30fc\u30eb\u306b\u5931\u6557\u3057\u307e\u3057\u305f\uff08\u7d42\u4e86\u30b3\u30fc\u30c9 {0}\uff09\u3002\u4e0a\u8a18\u306e\u30c0\u30a6\u30f3\u30ed\u30fc\u30c9\u307e\u305f\u306f\u4f9d\u5b58\u95a2\u4fc2\u306e\u30a8\u30e9\u30fc\u3092\u78ba\u8a8d\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
        "Installed": "AstrBot \u306e\u30a4\u30f3\u30b9\u30c8\u30fc\u30eb\u304c\u5b8c\u4e86\u3057\u307e\u3057\u305f\u3002",
        "ReloadShell": "\u4f7f\u7528\u3059\u308b\u30b7\u30a7\u30eb\u306b\u5408\u308f\u305b\u3066\u74b0\u5883\u3092\u518d\u8aad\u307f\u8fbc\u307f\u3057\u3066\u304f\u3060\u3055\u3044\uff1a",
        "RunCommands": "\u305d\u306e\u5f8c\u3001\u4ee5\u4e0b\u306e\u30b3\u30de\u30f3\u30c9\u3092\u624b\u52d5\u3067\u5b9f\u884c\u3057\u3066\u304f\u3060\u3055\u3044\uff1a"
    }
}
'@
$Text = $messages.$Language

if (-not $DownloadSource) {
    $DownloadSource = if ($Language -eq 'zh-CN') { 'china' } else { 'official' }
    if ($CanPrompt) {
        $defaultChoice = if ($Language -eq 'zh-CN') { '1' } else { '2' }
        Write-Host "`n$Indent$($Text.ChooseSource)"
        Write-Host "$Indent  1. $($Text.China)"
        Write-Host "$Indent  2. $($Text.Official)"
        Write-Host "$Indent  3. $($Text.Custom)"
        do {
            $choice = Read-Host "$Indent$($Text.Choice) [$defaultChoice]"
            if ($choice -eq '') { $choice = $defaultChoice }
            if ($choice -notin @('1', '2', '3')) { Write-Host "$Indent$($Text.InvalidChoice)" }
        } until ($choice -in @('1', '2', '3'))
        $DownloadSource = @('china', 'official', 'custom')[[int]$choice - 1]
    }
}

$uvMirrorUrls = @()
switch ($DownloadSource) {
    'china' {
        # Use uv mirrors listed by MirrorZ; the release-directory layout is not GitHub's layout.
        $uvMirrorUrls = @(
            'https://mirrors.ustc.edu.cn/github-release/astral-sh/uv/LatestRelease'
        )
        $PypiIndexUrl = 'https://mirrors.cernet.edu.cn/pypi/web/simple/'
    }
    'official' { $PypiIndexUrl = 'https://pypi.org/simple/' }
    'custom' {
        if ($CanPrompt) {
            if (-not $UvDownloadBaseUrl) { $UvDownloadBaseUrl = Read-Host "$Indent$($Text.UvUrl)" }
            if (-not $PypiIndexUrl) { $PypiIndexUrl = Read-Host "$Indent$($Text.PypiUrl)" }
        }
        if (-not $UvDownloadBaseUrl -or -not $PypiIndexUrl) {
            throw $Text.CustomRequired
        }
        $uvMirrorUrls = @($UvDownloadBaseUrl.TrimEnd('/'))
    }
}

if (-not $PythonInstallMirror) {
    if ($env:UV_PYTHON_INSTALL_MIRROR) {
        $PythonInstallMirror = $env:UV_PYTHON_INSTALL_MIRROR
    } elseif ($DownloadSource -eq 'china') {
        $PythonInstallMirror = 'https://mirrors.ustc.edu.cn/github-release/astral-sh/python-build-standalone/'
    }
}

foreach ($url in @($uvMirrorUrls) + @($PypiIndexUrl, $PythonInstallMirror)) {
    if (-not $url) { continue }
    $parsedUrl = $null
    if (-not [Uri]::TryCreate($url, [UriKind]::Absolute, [ref]$parsedUrl) -or
        $parsedUrl.Scheme -ne 'https' -or -not $parsedUrl.Host -or $parsedUrl.UserInfo -or
        $parsedUrl.Query -or $parsedUrl.Fragment) {
        throw ($Text.InvalidUrl -f $url)
    }
}

if ($env:OS -ne 'Windows_NT') { throw $Text.WindowsOnly }

function Write-Status {
    param(
        [string]$Prefix,
        [string]$Message,
        [string]$Color
    )

    if ($UseColor) {
        Write-Host "$Indent$Prefix    $Message" -ForegroundColor $Color
    } else {
        Write-Host "$Indent$Prefix    $Message"
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

function Test-ZipArchive {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path) -or (Get-Item -LiteralPath $Path).Length -lt 4) {
        return $false
    }

    $stream = [System.IO.File]::OpenRead($Path)
    try {
        return $stream.ReadByte() -eq 0x50 -and
            $stream.ReadByte() -eq 0x4B -and
            $stream.ReadByte() -eq 0x03 -and
            $stream.ReadByte() -eq 0x04
    } finally {
        $stream.Dispose()
    }
}

function Invoke-UvToolInstall {
    param([string[]]$ArgumentList)

    $uvCommand = Get-Command 'uv' -ErrorAction Stop
    if ($uvCommand.CommandType -ne 'Application') {
        # This path also makes the installer straightforward to test without
        # downloading packages or changing the developer machine.
        & $uvCommand @ArgumentList
        return $LASTEXITCODE
    }

    # PowerShell may otherwise give console programs their own window in some
    # hosts. Explicitly keep uv and all of its installation output in this one.
    # Do not inherit the current directory: it may have been removed while an
    # existing PowerShell session was still located there.
    $workingDirectory = [System.IO.Path]::GetTempPath()
    $process = Start-Process -FilePath $uvCommand.Source -ArgumentList $ArgumentList `
        -WorkingDirectory $workingDirectory -NoNewWindow -Wait -PassThru
    return $process.ExitCode
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
    foreach ($dir in @($env:UV_INSTALL_DIR, $env:UV_UNMANAGED_INSTALL, $env:XDG_BIN_HOME)) {
        if ($dir) { $candidateDirs += $dir }
    }
    if ($env:XDG_DATA_HOME) {
        $candidateDirs += Join-Path $env:XDG_DATA_HOME '..\bin'
    }

    foreach ($dir in $candidateDirs) {
        if ((Test-Path $dir) -and (($env:PATH -split ';') -notcontains $dir)) {
            $env:PATH = "$dir;$env:PATH"
        }
    }
}

function Install-Uv {
    Info $Text.InstallingUv

    $tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString())
    $null = New-Item -ItemType Directory -Path $tempDir
    try {
        # PROCESSOR_ARCHITEW6432 identifies the native OS when PowerShell is emulated.
        $nativeArch = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
        $arch = switch ($nativeArch) {
            'AMD64' { 'x86_64' }
            'x86' { 'i686' }
            'ARM64' { 'aarch64' }
            default { throw ($Text.UnsupportedArch -f $_) }
        }
        $artifact = "uv-$arch-pc-windows-msvc.zip"
        $officialBaseUrl = 'https://github.com/astral-sh/uv/releases/latest/download'
        foreach ($baseUrl in @($uvMirrorUrls) + $officialBaseUrl) {
            try {
                if ($baseUrl -eq $officialBaseUrl) {
                    Info "$($Text.Official): $officialBaseUrl"
                } else {
                    Info ($Text.TryingMirror -f $baseUrl)
                }
                $archive = Join-Path $tempDir $artifact
                $checksumFile = Join-Path $tempDir "$artifact.sha256"
                Invoke-WebRequest -Uri "$baseUrl/$artifact" -OutFile $archive -TimeoutSec 90 -UseBasicParsing

                # USTC protects larger release assets with a lightweight
                # JavaScript cookie check. Reproduce that single documented
                # browser step when its verification page is returned.
                if (-not (Test-ZipArchive $archive) -and
                    ([Uri]$baseUrl).Host -eq 'mirrors.ustc.edu.cn') {
                    $challengePage = [System.IO.File]::ReadAllText($archive)
                    $addressMatch = [regex]::Match(
                        $challengePage,
                        'document\.cookie\s*=\s*"addr=([0-9A-Fa-f:.]+);'
                    )
                    if ($addressMatch.Success) {
                        # Windows PowerShell 5.1 silently drops a manually set
                        # Cookie header. A WebRequestSession works in both 5.1
                        # and modern PowerShell.
                        $webSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
                        $cookie = New-Object System.Net.Cookie(
                            'addr',
                            $addressMatch.Groups[1].Value,
                            '/',
                            'mirrors.ustc.edu.cn'
                        )
                        $webSession.Cookies.Add($cookie)
                        Invoke-WebRequest -Uri "$baseUrl/$artifact" -OutFile $archive `
                            -WebSession $webSession `
                            -TimeoutSec 90 -UseBasicParsing
                    }
                }

                if (-not (Test-ZipArchive $archive)) {
                    throw $Text.InvalidChecksum
                }
                Invoke-WebRequest -Uri "$baseUrl/$artifact.sha256" -OutFile $checksumFile -TimeoutSec 30 -UseBasicParsing
                $expectedHash = ((Get-Content $checksumFile -Raw).Trim() -split '\s+')[0]
                if ($expectedHash -notmatch '^[a-fA-F0-9]{64}$' -or
                    (Get-FileHash $archive -Algorithm SHA256).Hash -ne $expectedHash) {
                    throw $Text.InvalidChecksum
                }
                $unpacked = Join-Path $tempDir 'unpacked'
                Expand-Archive -Path $archive -DestinationPath $unpacked -Force
                if (-not (Test-Path (Join-Path $unpacked 'uv.exe')) -or
                    -not (Test-Path (Join-Path $unpacked 'uvx.exe'))) {
                    throw $Text.MissingBinaries
                }
            } catch {
                Warn ($Text.MirrorFailed -f $_.Exception.Message)
                Remove-Item (Join-Path $tempDir 'unpacked') -Recurse -Force -ErrorAction SilentlyContinue
                continue
            }

            # Respect uv's installation directory settings for every source.
            $installDir = if ($env:UV_INSTALL_DIR) { $env:UV_INSTALL_DIR }
                elseif ($env:UV_UNMANAGED_INSTALL) { $env:UV_UNMANAGED_INSTALL }
                elseif ($env:XDG_BIN_HOME) { $env:XDG_BIN_HOME }
                elseif ($env:XDG_DATA_HOME) { Join-Path $env:XDG_DATA_HOME '..\bin' }
                else { Join-Path $env:USERPROFILE '.local\bin' }
            $null = New-Item -ItemType Directory -Path $installDir -Force
            Copy-Item (Join-Path $unpacked '*.exe') -Destination $installDir -Force
            $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
            if (-not $env:UV_UNMANAGED_INSTALL -and -not $env:INSTALLER_NO_MODIFY_PATH -and
                ($userPath -split ';') -notcontains $installDir) {
                [Environment]::SetEnvironmentVariable('Path', "$installDir;$userPath", 'User')
            }
            Update-UvPath
            return
        }
        throw $Text.UvFailed
    } catch {
        Err $_.Exception.Message
        Err $Text.UvFailed
        exit 1
    } finally {
        Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Info ($Text.Source -f $(switch ($DownloadSource) {
    'china' { $Text.China }
    'official' { $Text.Official }
    'custom' { $Text.Custom }
}))
foreach ($url in $uvMirrorUrls) { Info ($Text.UvMirror -f $url) }
Info ($Text.Pypi -f $PypiIndexUrl)

# Recover an existing installation before downloading uv again.
Update-UvPath
if (-not (Test-Command "uv")) {
    Install-Uv
}

Update-UvPath

if (-not (Test-Command "uv")) {
    Err $Text.UvFailed
    exit 1
}

Ok (& uv --version)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($PythonInstallMirror) {
    Info ($Text.PythonMirror -f $PythonInstallMirror)
} else {
    Info $Text.PythonDefault
}

$previousPythonMirror = $env:UV_PYTHON_INSTALL_MIRROR
try {
    if ($PythonInstallMirror) { $env:UV_PYTHON_INSTALL_MIRROR = $PythonInstallMirror }
    Info $Text.InstallingAstrBot
    $toolInstallExitCode = Invoke-UvToolInstall -ArgumentList @(
        'tool', 'install', '--python', '3.12', 'astrbot', '--default-index', $PypiIndexUrl
    )
    if ($toolInstallExitCode -ne 0 -and $PythonInstallMirror) {
        $pythonFallback = switch ($Language) {
            'zh-CN' { $bootstrapText.PythonFallbackChinese }
            'ja-JP' { $bootstrapText.PythonFallbackJapanese }
            default { $bootstrapText.PythonFallbackEnglish }
        }
        Warn $pythonFallback
        $env:UV_PYTHON_INSTALL_MIRROR = $null
        $toolInstallExitCode = Invoke-UvToolInstall -ArgumentList @(
            'tool', 'install', '--python', '3.12', 'astrbot', '--default-index', $PypiIndexUrl
        )
    }
    if ($toolInstallExitCode -ne 0) {
        Err ($Text.AstrBotFailed -f $toolInstallExitCode)
        exit $toolInstallExitCode
    }
    Ok $Text.Installed
    try { & uv tool update-shell *> $null } catch { }
    Write-Host "`n$Indent$($Text.ReloadShell)"
    Write-Host "$($Indent)  Bash: source ~/.bashrc"
    Write-Host "$($Indent)  Zsh: source ~/.zshrc"
    Write-Host "$($Indent)  Fish: source ~/.config/fish/config.fish"
    Write-Host "$($Indent)  PowerShell: . `$PROFILE"
    Write-Host "`n$Indent$($Text.RunCommands)"
    Write-Host "$($Indent)$($Indent)astrbot init" -ForegroundColor Cyan
    Write-Host "$($Indent)$($Indent)astrbot run" -ForegroundColor Cyan
} finally {
    $env:UV_PYTHON_INSTALL_MIRROR = $previousPythonMirror
}
