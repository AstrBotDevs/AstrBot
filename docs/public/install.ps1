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

# Keep localized status messages readable in Windows PowerShell consoles whose
# legacy code page cannot represent CJK characters.
try {
    if ($Host.Name -eq 'ConsoleHost') {
        # Windows PowerShell 5.1 may keep an OEM code page even when the
        # managed output encoding is UTF-8.
        $null = & chcp.com 65001 2>$null
    }
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [Console]::InputEncoding = $utf8
    [Console]::OutputEncoding = $utf8
} catch {
    # Some hosts do not expose mutable console encodings; continue normally.
}

# Windows PowerShell 5.1 may otherwise negotiate an obsolete TLS version.
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$UseColor = [string]::IsNullOrEmpty($env:NO_COLOR) -and [Console]::IsOutputRedirected -eq $false
$CanPrompt = -not $NonInteractive -and [Environment]::UserInteractive -and -not [Console]::IsInputRedirected
$Indent = '  '

# Keep the first-run experience predictable across machines. Users can still
# choose Chinese or Japanese explicitly in the language menu.
$bootstrapCompressed = [Convert]::FromBase64String(
    'H4sIAAAAAAAACqtW8swrLknMyUktCsksyUlVslL6ML+nR8GxuKTIKb9EAS6rpKPkk5iXXpqYnhpQlJ9bUKJkpRScmpOaXKKQAxVX0Fd4sX77y4bOZ90rX6xf+2JFA0hkRcOLVfMeN0162bjjWde8x43THzcue9zY/7hxwePGqY8bW5R0lJwzMvNSi0F2P1/X8GTv5Cc71j6b1q6ko+Sal56TWZyhZAVn6Sh5JRYkQlU/m7702Zw1L1bNU6oFAAIYB+vIAAAA'
)
$bootstrapInput = New-Object System.IO.MemoryStream(,$bootstrapCompressed)
$bootstrapGzip = New-Object System.IO.Compression.GZipStream(
    $bootstrapInput,
    [System.IO.Compression.CompressionMode]::Decompress
)
$bootstrapReader = New-Object System.IO.StreamReader($bootstrapGzip, [Text.Encoding]::UTF8)
$bootstrapText = ConvertFrom-Json $bootstrapReader.ReadToEnd()
$bootstrapReader.Dispose()

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

$compressedMessages = [Convert]::FromBase64String(
    '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'
)
$messageInput = New-Object System.IO.MemoryStream(,$compressedMessages)
$messageGzip = New-Object System.IO.Compression.GZipStream(
    $messageInput,
    [System.IO.Compression.CompressionMode]::Decompress
)
$messageReader = New-Object System.IO.StreamReader($messageGzip, [Text.Encoding]::UTF8)
$messages = ConvertFrom-Json $messageReader.ReadToEnd()
$messageReader.Dispose()
<#
$messages = @{
    'zh-CN' = @{
        ChooseSource = '请选择下载源'
        China = '中国大陆加速下载镜像源'
        Official = '官方源'
        Custom = '自定义'
        Choice = '输入编号，按回车使用默认选项'
        InvalidChoice = '请输入 1、2 或 3。'
        UvUrl = 'uv ZIP 下载目录 URL（不含文件名）'
        PypiUrl = 'PyPI simple 索引 URL'
        CustomRequired = '自定义源需要同时提供 UvDownloadBaseUrl 和 PypiIndexUrl。'
        InvalidUrl = '下载源必须是有效的 HTTPS URL：{0}'
        WindowsOnly = '请在 Windows 上运行此 PowerShell 脚本；Linux/macOS 请使用 install.sh。'
        Source = '下载源：{0}'
        UvMirror = 'uv 下载目录：{0}'
        Pypi = 'PyPI 索引：{0}'
        PythonMirror = 'Python 下载镜像：{0}'
        PythonDefault = 'Python 下载沿用 uv 的配置；如需加速，可通过 -PythonInstallMirror 指定镜像（PyPI 镜像不包含 Python 解释器）。'
        InstallingUv = '未找到 uv，正在安装…'
        TryingMirror = '正在尝试 uv 镜像：{0}'
        MirrorFailed = 'uv 镜像下载失败：{0}'
        OfficialFallback = '正在尝试 uv 官方安装器…'
        UnsupportedArch = '不支持的 Windows 架构：{0}'
        InvalidChecksum = 'uv 压缩包 SHA256 校验失败。'
        MissingBinaries = 'uv 压缩包中缺少 uv.exe 或 uvx.exe。'
        UvFailed = 'uv 安装失败。请参考 https://docs.astral.sh/uv/getting-started/installation/'
        InstallingAstrBot = '正在使用 Python 3.12 安装 AstrBot…'
        AstrBotFailed = 'AstrBot 安装失败（退出码 {0}）。请检查上方的下载或依赖错误。'
        Installed = 'AstrBot 安装完成。'
    }
    'en-US' = @{
        ChooseSource = 'Select a download source'
        China = 'Mainland China accelerated download mirrors'
        Official = 'Official sources'
        Custom = 'Custom'
        Choice = 'Enter a number, or press Enter to use the default'
        InvalidChoice = 'Please enter 1, 2, or 3.'
        UvUrl = 'uv ZIP download directory URL (without the filename)'
        PypiUrl = 'PyPI simple index URL'
        CustomRequired = 'Custom sources require both UvDownloadBaseUrl and PypiIndexUrl.'
        InvalidUrl = 'Download sources must be valid HTTPS URLs: {0}'
        WindowsOnly = 'Run this PowerShell script on Windows; use install.sh on Linux/macOS.'
        Source = 'Download source: {0}'
        UvMirror = 'uv download directory: {0}'
        Pypi = 'PyPI index: {0}'
        PythonMirror = 'Python download mirror: {0}'
        PythonDefault = 'Python downloads use the existing uv configuration. Set -PythonInstallMirror to use a mirror (PyPI mirrors do not include Python interpreters).'
        InstallingUv = 'uv was not found. Installing uv...'
        TryingMirror = 'Trying uv mirror: {0}'
        MirrorFailed = 'uv mirror download failed: {0}'
        OfficialFallback = 'Trying the official uv installer...'
        UnsupportedArch = 'Unsupported Windows architecture: {0}'
        InvalidChecksum = 'uv archive SHA256 verification failed.'
        MissingBinaries = 'The uv archive is missing uv.exe or uvx.exe.'
        UvFailed = 'Failed to install uv. See https://docs.astral.sh/uv/getting-started/installation/'
        InstallingAstrBot = 'Installing AstrBot with Python 3.12...'
        AstrBotFailed = 'AstrBot installation failed (exit code {0}). Check the download or dependency errors above.'
        Installed = 'AstrBot has been installed.'
    }
    'ja-JP' = @{
        ChooseSource = 'ダウンロード元を選択してください'
        China = '中国本土向け高速ダウンロードミラー'
        Official = '公式ソース'
        Custom = 'カスタム'
        Choice = '番号を入力してください。Enter で既定値を使用します'
        InvalidChoice = '1、2、3 のいずれかを入力してください。'
        UvUrl = 'uv ZIP のダウンロードディレクトリ URL（ファイル名を除く）'
        PypiUrl = 'PyPI simple インデックス URL'
        CustomRequired = 'カスタムソースには UvDownloadBaseUrl と PypiIndexUrl の両方が必要です。'
        InvalidUrl = 'ダウンロード元には有効な HTTPS URL を指定してください：{0}'
        WindowsOnly = 'この PowerShell スクリプトは Windows 用です。Linux/macOS では install.sh を使用してください。'
        Source = 'ダウンロード元：{0}'
        UvMirror = 'uv ダウンロードディレクトリ：{0}'
        Pypi = 'PyPI インデックス：{0}'
        PythonMirror = 'Python ダウンロードミラー：{0}'
        PythonDefault = 'Python のダウンロードには既存の uv 設定を使用します。ミラーを使うには -PythonInstallMirror を指定してください（PyPI ミラーに Python 本体は含まれません）。'
        InstallingUv = 'uv が見つかりません。インストールしています…'
        TryingMirror = 'uv ミラーを試しています：{0}'
        MirrorFailed = 'uv ミラーからのダウンロードに失敗しました：{0}'
        OfficialFallback = 'uv の公式インストーラーを試しています…'
        UnsupportedArch = '未対応の Windows アーキテクチャ：{0}'
        InvalidChecksum = 'uv アーカイブの SHA256 検証に失敗しました。'
        MissingBinaries = 'uv アーカイブに uv.exe または uvx.exe がありません。'
        UvFailed = 'uv のインストールに失敗しました。https://docs.astral.sh/uv/getting-started/installation/ を参照してください。'
        InstallingAstrBot = 'Python 3.12 で AstrBot をインストールしています…'
        AstrBotFailed = 'AstrBot のインストールに失敗しました（終了コード {0}）。上記のダウンロードまたは依存関係のエラーを確認してください。'
        Installed = 'AstrBot のインストールが完了しました。'
    }
}
#>
$Text = $messages.$Language

if (-not $DownloadSource) {
    $DownloadSource = 'official'
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
            'https://mirrors.ustc.edu.cn/github-release/astral-sh/uv/LatestRelease',
            'https://mirror.nyist.edu.cn/github-release/astral-sh/uv/LatestRelease'
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
        if ($uvMirrorUrls.Count -gt 0) {
            # PROCESSOR_ARCHITEW6432 identifies the native OS when PowerShell is emulated.
            $nativeArch = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
            $arch = switch ($nativeArch) {
                'AMD64' { 'x86_64' }
                'x86' { 'i686' }
                'ARM64' { 'aarch64' }
                default { throw ($Text.UnsupportedArch -f $_) }
            }
            $artifact = "uv-$arch-pc-windows-msvc.zip"
            foreach ($baseUrl in $uvMirrorUrls) {
                try {
                    Info ($Text.TryingMirror -f $baseUrl)
                    $archive = Join-Path $tempDir $artifact
                    $checksumFile = Join-Path $tempDir "$artifact.sha256"
                    Invoke-WebRequest -Uri "$baseUrl/$artifact" -OutFile $archive -TimeoutSec 60 -UseBasicParsing
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

                # Respect uv's installation directory settings when using a mirror too.
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
        }

        Info $Text.OfficialFallback
        $tempScript = Join-Path $tempDir 'uv-install.ps1'
        Invoke-WebRequest -Uri "https://astral.sh/uv/install.ps1" -OutFile $tempScript -UseBasicParsing
        & $tempScript
        if (-not $?) { throw $Text.UvFailed }
        Update-UvPath
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

if (-not $PythonInstallMirror) { $PythonInstallMirror = $env:UV_PYTHON_INSTALL_MIRROR }
if ($PythonInstallMirror) {
    Info ($Text.PythonMirror -f $PythonInstallMirror)
} else {
    Info $Text.PythonDefault
}

$previousPythonMirror = $env:UV_PYTHON_INSTALL_MIRROR
try {
    if ($PythonInstallMirror) { $env:UV_PYTHON_INSTALL_MIRROR = $PythonInstallMirror }
    Info $Text.InstallingAstrBot
    uv tool install --python 3.12 astrbot --default-index $PypiIndexUrl
    if ($LASTEXITCODE -ne 0) {
        Err ($Text.AstrBotFailed -f $LASTEXITCODE)
        exit $LASTEXITCODE
    }
    Ok $Text.Installed
} finally {
    $env:UV_PYTHON_INSTALL_MIRROR = $previousPythonMirror
}
