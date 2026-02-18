# AstrBot Desktop (Electron)

This document describes how to build the Electron desktop app from source.

## What This Package Contains

- Electron desktop shell (`desktop/main.js`)
- Bundled WebUI static files (`desktop/resources/webui`)
- Bundled backend runtime payload (`desktop/resources/backend`)
- App assets (`desktop/assets`)

Current behavior:

- Backend CPython runtime and source are bundled in the installer/package.
- App startup checks backend availability and auto-starts bundled backend when needed.
- Runtime data is stored under `~/.astrbot` by default, not as a full AstrBot source project.

## Prerequisites

- Python environment ready in repository root (`uv` available)
- Node.js available
- `pnpm` available
- A CPython runtime directory for packaged backend (contains runnable `python` and `site-packages`)

Desktop dependency management uses `pnpm` with a lockfile:

- `desktop/pnpm-lock.yaml`
- `pnpm --dir desktop install --frozen-lockfile`

## Build From Scratch

Run commands from repository root:

```bash
uv sync
export ASTRBOT_DESKTOP_CPYTHON_HOME=/path/to/cpython-runtime
pnpm --dir dashboard install
pnpm --dir dashboard build
pnpm --dir desktop install --frozen-lockfile
pnpm --dir desktop run dist:full
```

`ASTRBOT_DESKTOP_CPYTHON_HOME` must point to a standalone/distributable CPython runtime directory.
Virtual environments (for example `.venv`, detected by `pyvenv.cfg`) are not supported for packaged runtime builds.

```bash
export ASTRBOT_DESKTOP_CPYTHON_HOME=/path/to/cpython-runtime
pnpm --dir desktop run build:backend
```

Output files are generated under:

- `desktop/dist/`

## Local Run (Development)

Start backend first:

```bash
uv run main.py
```

Start Electron shell:

```bash
pnpm --dir desktop run dev
```

## Notes

- `dist:full` runs WebUI build + backend runtime packaging + Electron packaging.
- In packaged app mode, backend data root defaults to `~/.astrbot` (can be overridden by `ASTRBOT_ROOT`).
- Backend build requires a CPython runtime directory via `ASTRBOT_DESKTOP_BACKEND_RUNTIME` or `ASTRBOT_DESKTOP_CPYTHON_HOME`; if both are set, `ASTRBOT_DESKTOP_BACKEND_RUNTIME` takes precedence.

## Packaged Backend Layout

After `pnpm --dir desktop run build:backend`, backend payload is generated in `desktop/resources/backend`:

```text
desktop/resources/backend/
  app/                   # AstrBot backend source snapshot used in packaged mode
  python/                # Bundled CPython runtime directory
  launch_backend.py      # Launcher executed by Electron
  runtime-manifest.json  # Runtime metadata (Python path, entrypoint, app path)
```

Electron reads `runtime-manifest.json` and starts backend with:
- `python` from `python/`
- `launch_backend.py` as entrypoint

## Runtime Directory Layout

By default (`ASTRBOT_ROOT` not set), packaged desktop app uses this layout:

```text
~/.astrbot/
  data/
    config/         # Main configuration
    plugins/        # Installed plugins
    plugin_data/    # Plugin persistent data
    site-packages/  # Plugin dependency installation target in packaged mode
    temp/           # Runtime temp files
    skills/         # Skill-related runtime data
    knowledge_base/ # Knowledge base files
    backups/        # Backup data
```

The app does not store a full AstrBot source tree in home directory.

## Troubleshooting

Startup behavior:

- Packaged app shows a local startup page first, then switches to dashboard after backend is reachable.
- If startup page never switches, check logs and timeout settings below.

Runtime logs:

- Electron shell log: `~/.astrbot/logs/electron.log`
- Backend stdout/stderr log: `~/.astrbot/logs/backend.log`
- Both files rotate by size by default: `20MB` per file, keep `3` backups.
- Electron log rotation envs:
  - `ASTRBOT_ELECTRON_LOG_MAX_MB`
  - `ASTRBOT_ELECTRON_LOG_BACKUP_COUNT`
- Backend log rotation envs:
  - `ASTRBOT_BACKEND_LOG_MAX_MB`
  - `ASTRBOT_BACKEND_LOG_BACKUP_COUNT`
- Rotation debug logging:
  - `ASTRBOT_LOG_ROTATION_DEBUG=1` (or `NODE_ENV=development`) to print filesystem errors from rotation operations.
- On backend startup failure, the app dialog also shows the backend reason and backend log path.

Timeout and loading controls:

- `ASTRBOT_BACKEND_TIMEOUT_MS` controls how long Electron waits for backend reachability.
- In packaged mode, default is `0` (auto mode with a 5-minute safety cap).
- In development mode, default is `20000`.
- If backend startup times out, app shows startup failure dialog and exits.
- `ASTRBOT_DASHBOARD_TIMEOUT_MS` controls dashboard page load wait time after backend is ready (default `20000`).
- If you see `Unable to load the AstrBot dashboard.`, increase `ASTRBOT_DASHBOARD_TIMEOUT_MS`.

Startup page locale:

- Startup page language follows cached dashboard locale in `~/.astrbot/data/desktop_state.json`.
- Supported startup locales are `zh-CN` and `en-US`.
- Remove that file to reset locale fallback behavior.

Backend auto-start:

- `ASTRBOT_BACKEND_AUTO_START=0` disables Electron-managed backend startup.
- When disabled, backend must already be running at `ASTRBOT_BACKEND_URL` before launching app.

Backend build errors:

- `Missing CPython runtime source`: set `ASTRBOT_DESKTOP_CPYTHON_HOME` (or `ASTRBOT_DESKTOP_BACKEND_RUNTIME`).
- `Cannot find Python executable in runtime`: runtime directory is invalid or incomplete.
- `Failed to detect purelib from runtime Python`: runtime Python cannot run correctly.

If Electron download times out on restricted networks, configure mirrors before install:

```bash
export ELECTRON_MIRROR="https://npmmirror.com/mirrors/electron/"
export ELECTRON_BUILDER_BINARIES_MIRROR="https://npmmirror.com/mirrors/electron-builder-binaries/"
pnpm --dir desktop install --frozen-lockfile
```
