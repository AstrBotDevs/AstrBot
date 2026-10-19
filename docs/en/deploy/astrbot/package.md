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

`--download-source` accepts `china`, `official`, or `custom`. If omitted, the system language and official sources are used.

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

`-DownloadSource` accepts `china`, `official`, or `custom`. If omitted, the system language and official sources are used.

## Start AstrBot

Initialize the directory once, then start AstrBot:

```bash
astrbot init
astrbot run
```

> AstrBot installed by script does not support upgrades through the WebUI. Run `uv tool upgrade astrbot --python 3.12` to update it.
