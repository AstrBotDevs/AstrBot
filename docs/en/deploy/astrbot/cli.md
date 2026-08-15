# Deploy AstrBot from Source

> [!IMPORTANT]
> This fork does not currently publish an independent PyPI package or prebuilt Dashboard release. To run the backend and WebUI from this repository, install from the checkout and build the Dashboard locally.

## Prerequisites

- Git
- `uv`
- Node.js 26.5.0
- pnpm 11.21.0

Package metadata requires Python 3.14 or later. The checkout pins Python 3.14.6 in `.python-version`; `uv` can download that version when its managed-Python support is enabled.

## Clone the Repository

```bash
git clone https://github.com/Xero-Team/AstrBot.git
cd AstrBot
```

The default branch follows current development. Read the latest files under `changelogs/` and choose a commit to pin for your deployment. This fork does not yet have a release-tag sequence that deployments can rely on.

## Install Backend Dependencies

```bash
uv sync --locked
```

`--locked` prevents installation from silently rewriting `uv.lock`, keeping the checkout on the reviewed dependency resolution.

## Build the Current Dashboard

```bash
cd dashboard
pnpm install --frozen-lockfile
pnpm build
cd ..
uv run python scripts/sync_dashboard_dist.py
```

Do not skip this step. `astrbot init`, `astrbot run`, and the root startup entry point never download Dashboard assets; upstream static files are incompatible with this fork's FastAPI routes and frontend behavior.

## Optional: Install the Local T2I Browser

Run this once only if you enable local text-to-image or plugin HTML rendering:

```bash
uv run astrbot install-browser
```

## Start AstrBot

```bash
uv run main.py
```

After dependencies are synchronized, skip the startup sync check with:

```bash
uv run --no-sync main.py
```

First startup creates `data/`, generates a random initial WebUI password, and prints the credentials in the log. The default username is `astrbot`; WebUI listens only on `127.0.0.1:6185`.

## Remote Access

Replacing `localhost` with a server IP in the browser does not expose the service. Loopback is the secure default. For remote access, explicitly edit `data/cmd_config.json`:

```json
{
  "dashboard": {
    "host": "0.0.0.0",
    "port": 6185
  }
}
```

You can also override the bind address for one process:

::: code-group

```bash [Linux / macOS]
ASTRBOT_DASHBOARD_HOST=0.0.0.0 uv run main.py
```

```powershell [Windows PowerShell]
$env:ASTRBOT_DASHBOARD_HOST = '0.0.0.0'
uv run main.py
```

:::

`0.0.0.0` listens on every IPv4 interface. Configure the host firewall and preferably expose AstrBot through a trusted HTTPS reverse proxy. Enable `dashboard.trust_proxy_headers` only when that proxy overwrites client-supplied `X-Forwarded-For` and `X-Real-IP` headers.

## Update the Checkout

Stop AstrBot, then run:

```bash
git pull --ff-only
uv sync --locked
cd dashboard
pnpm install --frozen-lockfile
pnpm build
cd ..
uv run python scripts/sync_dashboard_dist.py
```

Back up `data/` and read the intervening changelogs before updating. Do not use `uv tool upgrade astrbot` for this fork; that command targets the upstream PyPI package.
