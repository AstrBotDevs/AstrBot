# Project Startup Guide

This document provides detailed instructions on how to start the AstrBot project, including initialization steps and configuration.

## Requirements

- Python 3.10 - 3.13
- uv package manager (recommended)

## Installation

### Method 1: One-Click Installation with uv (Recommended)

```bash
# Install AstrBot
uv tool install astrbot

# Initialize the project (first time only)
astrbot init

# Start the project
astrbot run
```

### Method 2: Development Mode Installation

```bash
# Clone the project
git clone https://github.com/AstrBotDevs/AstrBot
cd AstrBot

# Install development version
uv tool install git+https://github.com/AstrBotDevs/AstrBot@dev

# Initialize
astrbot init

# Start
astrbot run
```

### Method 3: Run from Source

```bash
git clone https://github.com/AstrBotDevs/AstrBot
cd AstrBot

# Create virtual environment
uv venv --seed
source .venv/bin/activate  # Linux/macOS
# or: .venv\Scripts\activate  # Windows

# Install dependencies
uv pip install -e .

# Initialize
astrbot init

# Start
astrbot run
```

## Initialization Details

The `astrbot init` command performs the following operations:

1. **Creates `.astrbot` marker file** - Identifies the AstrBot root directory
2. **Creates data directory structure**:
   - `data/` - Main data directory
   - `data/config/` - Configuration files
   - `data/plugins/` - Plugins directory
   - `data/temp/` - Temporary files directory
   - `data/skills/` - Skills directory
3. **Generates configuration file** `data/cmd_config.json`
4. **Generates environment file** `.env` (from `config.template`)
5. **Installs Dashboard** (optional, not recommended for server mode)

### Initialization Options

| Option | Description |
|--------|-------------|
| `-y, --yes` | Skip confirmation prompts |
| `-b, --backend-only` | Initialize backend only, skip Dashboard |
| `-u, --admin-username` | Set Dashboard admin username |
| `--root` | Specify AstrBot root directory |

## Startup Details

The `astrbot run` command starts the AstrBot service.

### Startup Options

| Option | Description |
|--------|-------------|
| `-H, --host` | Dashboard bind address |
| `-p, --port` | Dashboard bind port |
| `-r, --reload` | Enable plugin auto-reload |
| `-b, --backend-only` | Start backend only, skip WebUI |
| `-l, --log-level` | Log level (DEBUG, INFO, WARNING, ERROR) |
| `--ssl-cert` | SSL certificate path |
| `--ssl-key` | SSL private key path |
| `--ssl-ca` | SSL CA certificate path |
| `--debug` | Debug mode |
| `-c, --service-config` | Service configuration file path |

### Startup Output

Upon successful startup:

```
AstrBot is running...
Visit the dashboard at : https://dash.astrbot.men/
Backend Requests : localhost or based on https
```

## Environment Variables

### Core Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `ASTRBOT_ROOT` | AstrBot root directory | Auto-detected |
| `ASTRBOT_LOG_LEVEL` | Log level | INFO |
| `ASTRBOT_RELOAD` | Enable plugin hot-reload | - |
| `ASTRBOT_DISABLE_METRICS` | Disable metrics upload | - |

### Dashboard Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `ASTRBOT_DASHBOARD_ENABLE` | Enable Dashboard | True |
| `ASTRBOT_HOST` | Dashboard bind address | 0.0.0.0 |
| `ASTRBOT_PORT` | Dashboard bind port | 8000 |

### SSL Configuration

| Variable | Description |
|----------|-------------|
| `ASTRBOT_SSL_ENABLE` | Enable SSL |
| `ASTRBOT_SSL_CERT` | SSL certificate path |
| `ASTRBOT_SSL_KEY` | SSL private key path |
| `ASTRBOT_SSL_CA_CERTS` | CA certificate path |

### Proxy Configuration

| Variable | Description |
|----------|-------------|
| `http_proxy` | HTTP proxy address |
| `https_proxy` | HTTPS proxy address |
| `no_proxy` | Addresses to bypass proxy |

### Platform Integration

| Variable | Description |
|----------|-------------|
| `DASHSCOPE_API_KEY` | Alibaba DashScope API Key (for Rerank) |
| `COZE_API_KEY` | Coze API Key |
| `COZE_BOT_ID` | Coze Bot ID |
| `BAY_DATA_DIR` | Computer Use data directory |

## Directory Structure

```
AstrBot/
├── .astrbot              # AstrBot root marker
├── .env                  # Environment configuration
├── data/                 # Data directory
│   ├── config/
│   │   └── cmd_config.json  # Main configuration file
│   ├── plugins/          # Plugins directory
│   ├── skills/          # Skills directory
│   └── temp/            # Temporary files directory
├── astrbot/             # Core code
│   ├── cli/             # Command line tool
│   ├── core/            # Core modules
│   ├── dashboard/       # Dashboard frontend
│   └── ...
└── ...
```

## Configuration File

The main configuration file is located at `data/cmd_config.json`, containing:

- LLM provider configuration
- Platform adapter configuration
- Plugin settings
- Dashboard settings
- Proxy settings

## Troubleshooting

### Port Already in Use

If the port is already in use:

```bash
# Check process using the port
lsof -i :8000

# Or start on a different port
astrbot run --port 8080
```

### Multiple Instance Conflict

AstrBot uses a lock file mechanism to prevent multiple instances. To force start:

```bash
# Remove lock file
rm astrbot.lock

# Restart
astrbot run
```

### Dashboard Not Accessible

1. Verify `ASTRBOT_DASHBOARD_ENABLE` is `True`
2. Check firewall settings
3. Confirm port is not blocked

### Viewing Logs

```bash
# Start with debug mode for detailed logs
astrbot run --debug --log-level DEBUG
```

## Next Steps

- [Configure LLM Providers](../providers/llm.md)
- [Install Plugins](../use/plugin.md)
- [Use Skills](../use/skills.md)
- [Deploy to Server](./deploy/astrbot/docker.md)
