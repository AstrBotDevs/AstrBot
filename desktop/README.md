# AstrBot Desktop (Electron)

This document describes how to build the Electron desktop app from source.

## What This Package Contains

- Electron desktop shell (`desktop/main.js`)
- Bundled WebUI static files (`desktop/resources/webui`)
- App assets (`desktop/assets`)

Current behavior:

- Backend executable is bundled in the installer/package.
- App startup checks backend availability and auto-starts bundled backend when needed.
- Runtime data is stored under `~/.astrbot` by default, not as a full AstrBot source project.

## Prerequisites

- Python environment ready in repository root (`uv` available)
- Node.js available
- `pnpm` available

Desktop dependency management uses `pnpm` with lockfile:

- `desktop/pnpm-lock.yaml`
- `pnpm --dir desktop install --frozen-lockfile`

## Build From Scratch

Run commands from repository root:

```bash
uv sync
pnpm --dir dashboard install
pnpm --dir dashboard build
pnpm --dir desktop install --frozen-lockfile
pnpm --dir desktop run dist:full
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

- `dist:full` runs WebUI build + backend build + Electron packaging.
- In packaged app mode, backend data root defaults to `~/.astrbot` (can be overridden by `ASTRBOT_ROOT`).
- Backend build uses `uv run --with pyinstaller ...`, so no manual `PyInstaller` install is required.

## Runtime Directory Layout

By default (`ASTRBOT_ROOT` not set), packaged desktop app uses this layout:

```text
~/.astrbot/
  data/
    config/         # Main configuration
    plugins/        # Installed plugins
    plugin_data/    # Plugin persistent data
    temp/           # Runtime temp files
    skills/         # Skill-related runtime data
    knowledge_base/ # Knowledge base files
    backups/        # Backup data
```

The app does not store a full AstrBot source tree in home directory.

## Troubleshooting

Runtime logs:

- Backend stdout/stderr is written to `~/.astrbot/logs/backend.log` in packaged app mode.
- If UI stays blank, check that log first and then retry launching the app.
- Packaged app defaults to `ASTRBOT_BACKEND_TIMEOUT_MS=0` (wait until backend is reachable).
- Set `ASTRBOT_BACKEND_TIMEOUT_MS` to a positive number only if you need an explicit startup timeout.

If Electron download times out on restricted networks, configure mirrors before install:

```bash
export ELECTRON_MIRROR="https://npmmirror.com/mirrors/electron/"
export ELECTRON_BUILDER_BINARIES_MIRROR="https://npmmirror.com/mirrors/electron-builder-binaries/"
pnpm --dir desktop install --frozen-lockfile
```
