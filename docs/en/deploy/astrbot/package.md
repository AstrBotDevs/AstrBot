# Package Manager Deployment (uv)

Use `uv` to install and run AstrBot quickly.

## Before You Start

If `uv` is not installed, install it first by following the official guide:
<https://docs.astral.sh/uv/>

`uv` supports Linux, Windows, and macOS.

## Important Notes

> [!WARNING]
> AstrBot deployed via `uv` **does not support upgrading through the WebUI**. To update, run `uv tool upgrade astrbot --python 3.12` from the command line.

AstrBot requires Python 3.12 or later. Use `--python 3.12` to ensure that `uv` creates the tool environment with Python 3.12; if Python downloads are enabled, `uv` will download Python 3.12 automatically when it is missing.

## Install and Start

### Linux / macOS / WSL Installation Wizard

Run with **Bash 3.2 or later**:

```bash
curl -fsSL https://docs.astrbot.app/install.sh | bash
```

Choose Simplified Chinese, English, or Japanese, then a download source. The mainland China mirrors, official sources, and custom sources work as described in the Windows section below. Piped installations read menu input from the terminal. Without an available terminal, menus are skipped and the defaults are the system language and official sources.

For unattended installation:

```bash
curl -fsSL https://docs.astrbot.app/install.sh -o install.sh
bash install.sh --language en-US --download-source china --non-interactive
```

Use `--download-source custom --uv-download-base-url <HTTPS-directory> --pypi-index-url <HTTPS-index>` for custom sources. The directory must contain `uv-<target>.tar.gz` and its matching `.sha256` file, using the official uv archive layout. Set `--python-install-mirror <HTTPS-URL>` for a separate Python interpreter mirror, or use the existing `UV_PYTHON_INSTALL_MIRROR` environment variable.

The script detects the macOS/Linux architecture and prefers static musl builds on Linux. Unavailable mirrors or checksum failures trigger a backup mirror and then the official installer. Downloads require `curl` or `wget`; mirror installation also requires `tar` and `sha256sum` or `shasum`. The uv directory is added to PATH for the current installation process, and mirror installations display the directory to add to PATH in new terminals.

### Windows Installation Wizard

Run the following in **Windows PowerShell 5.1 or PowerShell 7+**:

```powershell
irm https://docs.astrbot.app/install.ps1 | iex
```

The wizard offers Simplified Chinese, English, and Japanese, followed by a download source selection:

- **Mainland China accelerated download mirrors**: download uv from university mirrors listed by MirrorZ and install AstrBot and its Python package dependencies through `https://mirrors.cernet.edu.cn/pypi/web/simple/`. If a uv download or SHA256 verification fails, the installer tries the backup mirror and then the official installer.
- **Official sources**: use the official uv installer and PyPI.
- **Custom**: specify a uv ZIP download directory and a PyPI simple index. The uv directory must contain `uv-<architecture>-pc-windows-msvc.zip` and the matching `.sha256` file.

In interactive mode, the system language determines the initial language selection. The Chinese interface defaults to the mainland China mirrors; English and Japanese default to official sources. Both selections can be changed.

For unattended installation, download the script and pass explicit options:

```powershell
Invoke-WebRequest https://docs.astrbot.app/install.ps1 -OutFile install.ps1 -UseBasicParsing
.\install.ps1 -Language en-US -DownloadSource china -NonInteractive
```

`-Language` accepts `zh-CN`, `en-US`, or `ja-JP`; `-DownloadSource` accepts `china`, `official`, or `custom`. Unattended runs and redirected input skip all menus. Omitted options default to the system language and official sources.

For custom sources, replace these example HTTPS URLs with your own:

```powershell
.\install.ps1 -Language en-US -DownloadSource custom -NonInteractive `
    -UvDownloadBaseUrl 'https://mirror.example.com/uv/release' `
    -PypiIndexUrl 'https://mirror.example.com/pypi/simple/'
```

PyPI mirrors do not include Python interpreters. When Python 3.12 is missing, its download uses the existing uv configuration. Pass `-PythonInstallMirror <HTTPS-URL>` to specify a Python download mirror compatible with uv, or set `UV_PYTHON_INSTALL_MIRROR` beforehand. The script does not change global pip settings; a Python mirror passed as an option applies only during this installation.

### Manual Installation and Startup

```bash
uv tool install astrbot --python 3.12
astrbot
```
