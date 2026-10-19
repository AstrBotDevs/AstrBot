# Script Deployment

AstrBot provides installation scripts for Linux, macOS, WSL, and Windows. The scripts install `uv`, AstrBot, and Python 3.12.

## Linux / macOS / WSL

Interactive installation:

```bash
curl -fsSL https://docs.astrbot.app/install.sh | bash
```

Unattended installation:

```bash
curl -fsSL https://docs.astrbot.app/install.sh -o install.sh
bash install.sh --language en-US --download-source official --non-interactive
```

`--download-source` accepts `china`, `official`, or `custom`. The default language is English. If the source is omitted, Chinese uses the mainland China mirrors; English and Japanese use official sources.

## Windows

Run these commands in PowerShell 5.1 or PowerShell 7+.

Interactive installation:

```powershell
irm https://docs.astrbot.app/install.ps1 | iex
```

Unattended installation:

```powershell
Invoke-WebRequest https://docs.astrbot.app/install.ps1 -OutFile install.ps1 -UseBasicParsing
.\install.ps1 -Language en-US -DownloadSource official -NonInteractive
```

`-DownloadSource` accepts `china`, `official`, or `custom`. The default language is English. If the source is omitted, Chinese uses the mainland China mirrors; English and Japanese use official sources.

The mainland China option also configures the USTC mirror for Python 3.12 and retries with the official Python source on failure. Existing Python mirror environment variables or explicit options take priority.

## After Installation

The installer runs `uv tool update-shell`. Reload the environment for your shell:

```bash
# Bash
source ~/.bashrc
# Zsh
source ~/.zshrc
# Fish
source ~/.config/fish/config.fish
# PowerShell
. $PROFILE
```

Then run these commands manually:

```bash
astrbot init
astrbot run
```

> AstrBot installed by script does not support upgrades through the WebUI. Run `uv tool upgrade astrbot --python 3.12` to update it.
