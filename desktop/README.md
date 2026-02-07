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
- Node.js and npm available
- `pnpm` available for WebUI build

## Build From Scratch

Run commands from repository root:

```bash
uv sync
pnpm --dir dashboard install
pnpm --dir dashboard build
npm --prefix desktop ci
npm --prefix desktop run dist:full
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
npm --prefix desktop run dev
```

## Notes

- `dist:full` currently runs WebUI build preparation + Electron packaging.
- If you need backend built-in packaging again, you need to restore backend resource build and packaging config.
