---
outline: deep
---

# Source Development

This page covers the general workflow for the current fork. See [Linux Development](/en/dev/linux) for Linux system dependencies and process-management details.

## Toolchain Baseline

- Python package requirement: 3.14 or later
- Current development, Docker, and CI Python: 3.14.6
- Node.js: 26.5.0
- Dashboard and docs pnpm: 11.21.0
- Python dependency manager: `uv`

These versions come from `.python-version`, workflows, the Dockerfile, and each package's `packageManager` field. A toolchain upgrade must update all matching declarations and lockfiles.

## First Setup

```bash
git clone https://github.com/Xero-Team/AstrBot.git
cd AstrBot
make doctor
make bootstrap
```

`make doctor` checks Python 3.14.x, `uv`, Node 26.x, and Dashboard pnpm 11.21.x. On POSIX it also checks `shfmt`, `shellcheck`, and `hadolint`. `make bootstrap` uses lockfiles to install Python development dependencies, root Node formatting tools, and Dashboard dependencies, but it does not install docs dependencies.

- Windows additionally requires GNU Make and PowerShell 7; PowerShell validation also needs PSScriptAnalyzer. `make doctor` does not currently validate those three requirements.
- Linux/macOS use Bash and do not require PowerShell. Strict checks require `shfmt`, `shellcheck`, and `hadolint`.

For component-only work, use the direct commands below without bypassing lockfiles:

```bash
uv sync --group dev --locked
npm ci
cd dashboard
pnpm install --frozen-lockfile
cd ..
cd docs
pnpm install --frozen-lockfile
cd ..
```

## Start the Development Environment

Use this for day-to-day integrated work:

```bash
make dev
```

It starts the backend and Vite Dashboard without a production build first:

- backend: `http://127.0.0.1:6185`
- Dashboard dev server: `http://localhost:3000`

`make run` synchronizes the locked runtime environment, builds the Dashboard and documentation, copies them to `data/dist` (docs under `help/`), and then starts both processes. It does not build a Python wheel or sdist. Use `make status` to inspect the processes and `make stop` to stop them. `make build-docs` only builds and syncs documentation; `make docs` starts a standalone VitePress preview with base `/`.

`make clean` is not an ordinary process-control command. It stops the processes and broadly removes generated content including `dashboard/dist`, `data/dist`, `.tmp`, build/dist directories, logs, test/format caches, and `__pycache__`. Inspect the worktree and any local artifacts you need before running it.

For backend-only work:

```bash
uv run main.py
```

For Dashboard-only work:

```bash
cd dashboard
pnpm dev
```

Runtime state is written under `data/` in the current runtime root. Tests and temporary checks must not read from or write to a developer's real `data/`; use pytest temporary fixtures or a separate `ASTRBOT_ROOT`.

The main SQLite schema is locked by SQLModel tables, `po/registry.py`, and `tests/unit/db/test_schema.py`. `initialize()` does not add or drop columns on an existing `data/data_v4.db`. Locally, stop the process, delete `data/data_v4.db*`, and start again; tests use temporary databases. See [Project Architecture](/en/dev/architecture#main-sqlite-database).

## Tests

```bash
uv run pytest
uv run pytest tests/unit
uv run pytest tests/unit/test_event_bus.py
uv run pytest tests/unit/test_event_bus.py::TestEventBusDispatch::test_dispatch_processes_event
uv run pytest --test-profile blocking
make test-blocking
```

The `blocking` profile excludes tests marked `slow`, `integration`, or `live`. `platform` and `provider` are domain tags and do not remove tests from the blocking gate. Tests under `tests/integration/` and `tests/e2e/` are classified as integration automatically; mark real outbound HTTP, vendor SDK, or required-secret tests as `live`. Put regression coverage beside the closest existing tests instead of assuming every focused test belongs in `tests/unit/`.

The Dashboard uses Vitest:

```bash
cd dashboard
pnpm test
```

The plugin Dashboard Extension Protocol also has browser-level Playwright E2E
coverage. Install Chromium, Firefox, and WebKit once; `playwright.config.ts`
starts the isolated test backend and Vite automatically without using a
developer's real `data/` directory:

```bash
cd dashboard
pnpm exec playwright install chromium firefox webkit
pnpm test:e2e
```

The specs live in `dashboard/tests/e2e/`, and the isolated backend entry point
is `tests/e2e/plugin_ui_test_server.py`. PR and push CI run the Chromium
project only. Firefox and WebKit stay defined in `playwright.config.ts` and
run on `workflow_dispatch`. Linux CI uses `playwright install --with-deps`
to install system dependencies as well.

## Formatting, Checks, and Quality Gates

Common commands:

```bash
make check       # strict checks for the current host platform
make quality     # typing, security, audit, and complexity gates
make test        # full pytest suite
make test-blocking  # pytest --test-profile blocking
make pr-test-full
```

`make check` selects checks by host platform. On POSIX, `make check-all-platforms` adds PowerShell validation. On Windows, `make check` already includes PowerShell, so that target repeats it and still does not emulate shell/Docker checks. Full CI is composed of several workflows and is not equivalent to a single Make target.

`make check` does not run writing formatters, but it is not filesystem read-only: the Dashboard build writes `dashboard/dist/` and may regenerate the tracked MDI subset assets.

Writing format targets include:

```bash
make format
make format-py
make format-web
make format-md
```

`make format` touches several tracked file types. `format-py`, `format-web`, and `format-md` narrow the scope only by file type and still process repository-wide files of that type. In a dirty worktree, run Ruff or Prettier directly on the intended paths when unrelated same-type edits must be preserved, then inspect `git diff`.

## Dashboard and OpenAPI

Ordinary Dashboard JSON APIs follow this layout:

- routes: `astrbot/dashboard/api/`
- domain services: `astrbot/dashboard/services/`
- request models: `astrbot/dashboard/schemas.py`
- source specification: `openspec/openapi-v1.yaml`

After changing routes, request/response schemas, or OpenAPI, regenerate both the frontend client and the in-app OpenAPI JSON:

```bash
cd dashboard
pnpm generate:api
cd ..
node node_modules/prettier/bin/prettier.cjs --write --ignore-path .gitignore "dashboard/src/api/generated/openapi-v1/**/*.ts"
uv run python docs/scripts/update_openapi_json.py
node node_modules/prettier/bin/prettier.cjs --write docs/public/openapi.json
```

Do not hand-edit `dashboard/src/api/generated/openapi-v1/` or the public JSON. The repository `.prettierignore` normally excludes generated clients, so the explicit `--ignore-path .gitignore` is required to reproduce their checked-in formatting. Both formatting commands are mechanical.

## Documentation

When equivalent Chinese and English pages exist, behavior, configuration, and workflow changes should update both trees and the navigation in `docs/.vitepress/config.mjs`.

```bash
cd docs
pnpm install --frozen-lockfile
pnpm run docs:dev
pnpm run docs:build
```

The production build validates internal links. Do not edit `docs/.vitepress/dist/`; it is generated. Production builds use base `/help/` and are served from the Dashboard. `make check-md` enumerates only Git-tracked Markdown, so run Prettier and markdownlint explicitly for new pages that have not yet been added to the index.

## Dependency Changes

Keep dependency files synchronized as groups:

- Python runtime: `pyproject.toml`, `requirements.txt`, `uv.lock`
- root Node tools: `package.json`, `package-lock.json`
- Dashboard: `dashboard/package.json`, `dashboard/pnpm-lock.yaml`
- docs: `docs/package.json`, `docs/pnpm-lock.yaml`

GitHub Actions must be pinned to full commit SHAs and grant each job only the scopes required for its actual state changes. Artifact publication, code-scanning uploads, and Issue maintenance are separate write use cases and must each be justified; do not grant broad workflow-wide write access.

## Before Submitting

Run tests proportional to the change, then at least:

```bash
make check
make quality
```

For Dashboard, startup, cross-platform script, or release-artifact changes, also run `make pr-test-full`. Use English Conventional Commits for commit and pull-request titles. Types, description rules, and breaking-change markers are in [CONTRIBUTING.md](https://github.com/Xero-Team/AstrBot/blob/master/CONTRIBUTING.md) at the repository root. Pick a typed template under `.github/PULL_REQUEST_TEMPLATE/`. AI-assisted commit messages must also follow `.agents/shared/conventional-commit/REFERENCE.md`.
