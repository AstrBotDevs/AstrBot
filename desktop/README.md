# AstrBot Desktop (Electron)

This document describes how to build the Electron desktop app from source.

## What This Package Contains

- Electron desktop shell (`desktop/main.js`)
- Bundled WebUI static files (`desktop/resources/webui`)
- App assets (`desktop/assets`)

Current behavior:

- Packaging is frontend-only.
- Backend is not bundled in the installer/package.
- If backend is unavailable on app startup, the app will show a startup failure dialog and exit.

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

- `dist:full` currently runs WebUI build preparation + Electron packaging.
- If you need backend built-in packaging again, you need to restore backend resource build and packaging config.

## Troubleshooting

If Electron download times out on restricted networks, configure mirrors before install:

```bash
export ELECTRON_MIRROR="https://npmmirror.com/mirrors/electron/"
export ELECTRON_BUILDER_BINARIES_MIRROR="https://npmmirror.com/mirrors/electron-builder-binaries/"
pnpm --dir desktop install --frozen-lockfile
```
