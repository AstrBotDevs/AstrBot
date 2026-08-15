# AGENTS.md

This file provides guidance to agents working in this repository.

## Project philosophy

This repository is a **modernized fork of AstrBot**. Keep it lean and
forward-looking instead of extending compatibility indefinitely.

- Do not add or preserve shims for legacy APIs, plugin formats, configuration
  shapes, or knowledge-base layouts. When touching an old/new split, build on
  the current path and remove the old one.
- Target Python 3.14+ only. Do not restore Python 3.10-3.13 fallbacks.
- Prefer the smallest current design that solves the actual problem. A change
  that only works by resurrecting a deprecated path is the wrong design.
- This fork does not currently publish its own PyPI package, release assets, or
  container image. Never present upstream artifacts as fork artifacts.
- `compose.yml` and `compose-with-napcat.yml` intentionally build this checkout
  with `build:` and tag it `astrbot:local`. Preserve that source-build contract;
  do not replace it with `soulter/astrbot` or another upstream prebuilt image.

## Toolchain and setup

The reproducible development/CI baseline is:

| Tool                | Baseline and source of truth                                                 |
| ------------------- | ---------------------------------------------------------------------------- |
| Python              | 3.14.6 in `.python-version`, CI, and `Dockerfile`; project floor is `>=3.14` |
| Node.js             | 26.5.0 in CI and `Dockerfile`                                                |
| root npm            | 12.0.2 in the root `package.json` `packageManager` field                     |
| Dashboard/docs pnpm | 11.21.0 in their `package.json` `packageManager` fields                      |
| Python manager      | `uv` (required, currently not patch-pinned)                                  |

Use the globally installed `npm` and `pnpm` commands. Workflows may instead use a
commit-pinned package-manager setup action and invoke its installed binary
directly. A toolchain upgrade must update every matching declaration,
workflow, image build, and lockfile in the same change.

Start a fresh checkout with:

```bash
make doctor
make bootstrap
```

`make doctor` is strict. It checks Python 3.14.x, `uv`, Node 26.x, and
pnpm 11.21.x; on POSIX it also requires `shellcheck`, `shfmt`, and `hadolint`.
Docker is optional. Windows additionally needs GNU Make and PowerShell 7, while
`check-ps` needs PSScriptAnalyzer; `doctor` does not currently validate those
three items. `make bootstrap` installs the locked Python development
environment, root Node formatting tools, and Dashboard dependencies. It does
not install docs dependencies.

For the integrated development servers:

```bash
make dev       # backend on 127.0.0.1:6185, Vite dev server on port 3000
make status
make stop
```

Windows uses `scripts/make_dev.ps1`; POSIX uses `scripts/make_dev.sh`. PID files
live in `.make/`, with backend logs in `backend_run*.log` and Dashboard logs in
`frontend_run*.log`. `make dev` starts source-mode servers without a production
Dashboard build. `make run` first syncs the locked runtime environment, builds
the Dashboard, and copies `dashboard/dist` into `data/dist`; it does not build a
Python wheel or sdist. The Vite command uses `--host`, so treat port 3000 as a
development-only surface rather than a production endpoint.

For focused work, use the component directly:

```bash
uv sync --group dev --locked
uv run main.py

cd dashboard
pnpm install --frozen-lockfile
pnpm dev
pnpm build
pnpm test
cd ..

cd docs
pnpm install --frozen-lockfile
pnpm run docs:dev
pnpm run docs:build
cd ..
```

On first backend startup the default Dashboard username is `astrbot`; a random
password is written to the startup log. Runtime state lives under `data/`.

### Dependency and lockfile matrix

Keep each dependency surface with its actual installer:

| Surface                 | Manifests / policy                                        | Authoritative install input                          |
| ----------------------- | --------------------------------------------------------- | ---------------------------------------------------- |
| Python runtime/dev      | `pyproject.toml`, `requirements.txt`                      | `uv.lock`; use `uv sync --locked`                    |
| root repository tooling | `package.json`                                            | `package-lock.json`; use `npm ci`                    |
| Dashboard               | `dashboard/package.json`, `dashboard/pnpm-workspace.yaml` | `dashboard/pnpm-lock.yaml`; use frozen pnpm installs |
| docs                    | `docs/package.json`, `docs/pnpm-workspace.yaml`           | `docs/pnpm-lock.yaml`; use frozen pnpm installs      |

Runtime Python dependency changes must update `pyproject.toml`,
`requirements.txt`, and `uv.lock`: local/quality jobs consume the uv lock, while
the Docker and smoke-test paths still install `requirements.txt`. The historical
root `pnpm-lock.yaml` is not used by the Makefile or CI for root tooling; do not
treat it as authoritative or update it instead of `package-lock.json`.

## Tests, checks, and formatting

```bash
uv run pytest
uv run pytest tests/unit
uv run pytest tests/unit/test_event_bus.py
uv run pytest tests/unit/test_event_bus.py::TestEventBusDispatch::test_dispatch_processes_event
uv run pytest --test-profile blocking
```

Tests use `pytest-asyncio`; mark async tests explicitly. `tests/conftest.py`
sets test-mode environment flags, prioritizes unit tests, and classifies slow,
provider/platform, and integration tests into tiers. Put a regression test next
to the nearest existing coverage (`tests/unit/`, `tests/test_*.py`,
`tests/agent/`, or a specialist directory). Dashboard Vitest files live under
`dashboard/tests/` as `*.vitest.ts`. Browser-level Dashboard tests live under
`dashboard/tests/e2e/` and use `dashboard/playwright.config.ts`; the plugin UI
suite starts its isolated backend through `tests/e2e/plugin_ui_test_server.py`.
Install the required Playwright browsers before running `pnpm
test:e2e` from `dashboard/`.

The repository gates are deliberately separate:

```bash
make check                 # host-platform format/lint/build gate
make check-all-platforms   # add PowerShell validation on POSIX
make test                  # full pytest suite
make quality               # focused pyright/security/audit/complexity gates
make quality-report        # broader report; not currently a required CI gate
```

`make check` is not a complete CI-equivalent umbrella:

- On Windows it checks Python, Dashboard, data, Markdown, TOML, YAML, and
  PowerShell.
- On POSIX it checks Python, Dashboard, data, Markdown, TOML, YAML, shell, and
  the Dockerfile.
- On POSIX, `make check-all-platforms` adds `check-ps`. On Windows,
  `make check` already includes `check-ps`, so the target repeats that check and
  still does not emulate the POSIX shell/Docker surfaces. CI runs those
  surfaces, tests, quality, docs, and security jobs separately.

`make check` does not invoke writing formatters, but it is not filesystem
read-only: the Dashboard build writes `dashboard/dist/` and may regenerate the
tracked MDI subset assets. `make quality-report` is not a required CI gate at
present, but its commands still propagate non-zero exit codes.

The native POSIX linters (`shellcheck`, `shfmt`, and `hadolint`) are required,
not optional. PowerShell checks require PowerShell 7 and PSScriptAnalyzer.

`make format` writes across all supported file types and normalizes line
endings. Targets such as `format-py`, `format-web`, and `format-md` are scoped
only by file type, not by the files changed for the current task. In a dirty
worktree, run Ruff or Prettier directly on the intended paths when unrelated
same-type edits must be preserved. Ruff uses line length 88, target `py314`,
and mccabe complexity 15. Pre-commit runs Ruff and `pyupgrade --py314-plus`.

## Architecture

AstrBot normalizes messages from IM platforms, sends them through an ordered
pipeline, invokes Stars and/or an agent, then responds through the originating
adapter.

### Startup and ownership

- `main.py` imports root-level `runtime_bootstrap` and calls
  `initialize_runtime_bootstrap()` before importing AstrBot core modules. This
  installs the certifi-backed verified aiohttp CA context. Keep imports above
  that call minimal.
- The `astrbot` console entry point has its own CLI initialization and
  Dashboard checks and does not currently invoke the root `runtime_bootstrap`
  path. When changing startup behavior, inspect and test both entry points
  instead of assuming they are identical.
- Startup-only environment flags are applied before core imports. Runtime paths
  and Dashboard assets are resolved before `create_runtime_services()` builds
  the runtime-owned configuration, SQLite database, preferences, Playwright
  renderer, file-token service, pip installer, and demo state.
- Importing `astrbot.core` or `astrbot.core.runtime_services` must stay inert:
  no user-data access, directory creation, logger configuration, scheduler
  startup, or service construction at import time. Construction belongs in the
  explicit factory after bootstrap; `tests/unit/test_core_import_smoke.py`
  protects this boundary.
- `InitialLoader` runs `AstrBotCoreLifecycle` and `AstrBotDashboard`.
  `AstrBotCoreLifecycle` owns manager initialization, bounded event queues,
  pipeline schedulers, plugins, cron, memory/persona runtime, knowledge bases,
  sub-agents, background tasks, and shutdown order.

### Message flow

1. Adapters under `astrbot/core/platform/sources/` normalize inbound traffic to
   `AstrMessageEvent` and enqueue it.
2. `EventBus` chooses the `PipelineScheduler` for the event's config id and
   dispatches it under bounded concurrency while retaining task references.
3. `astrbot/core/pipeline/stage_order.py` defines the fixed sequence from
   `WakingCheck` through `WhitelistCheck`, `SessionStatusCheck`, `RateLimit`,
   `ContentSafetyCheck`, `PreProcess`, `Process`, `ResultDecorate`, and finally
   `Respond`.

The scheduler supports async stages and async-generator onion middleware.
Preserve stage ordering, stop-propagation, and cancellation semantics.

Group wake behavior is explicit. `platform_settings.group_wake_policy`
controls whether mentioning or replying to the bot wakes a group message, and
`WakingCheckStage` records the selected `wake_reasons` on the event. Do not
restore implicit mention/reply wakeups. Built-in command availability is stored
per handler in the command database; the removed `disable_builtin_commands`
field is not migrated or read by runtime code and must not become a pipeline
switch again.

### Agents, providers, and runners

- `astrbot/core/agent/` contains the local LLM agent runtime, tool execution,
  MCP, context management, handoffs, and runner interfaces. Main-agent assembly
  is in `astr_main_agent.py`; `subagent_orchestrator.py` owns configured
  sub-agents.
- Provider primitives cover chat completion, STT, TTS, embeddings, and rerank.
  Concrete types register through the static type-to-module map in
  `astrbot/core/provider/provider_modules.py`; `ProviderManager` imports the
  selected module lazily. Add new built-in provider modules to that map instead
  of importing every source eagerly.
- Dify, Coze, DashScope applications, and DeerFlow are **third-party Agent
  runners** under `astrbot/core/agent/runners/`, not chat-provider source
  implementations. Keep their lifecycle and response mapping in the runner
  path even when their configuration records are provider-like.
- The tool-loop runner emits an `agent_stats` event after every completed model
  call, including intermediate calls before tools. WebChat consumes those
  events as request-scoped protocol messages. Preserve their ordering and do
  not collapse them back into a final-only summary.

### Stars and supporting subsystems

- The plugin system is under `astrbot/core/star/`; built-in Stars live in
  `astrbot/builtin_stars/`, and user Stars load from `data/plugins/`.
  Plugin-facing code imports the supported SDK from `astrbot.api`.
- Dashboard Extension Protocol v1 is owned by
  `astrbot/core/star/dashboard_extension.py` and exposed to plugins only through
  `astrbot.api.dashboard`. Extensions declare `requires.dashboard_extension: 1`,
  content-addressed `assets.v1.json` manifests, and structured Actions during
  plugin `initialize()`. Keep the sandboxed iframe and host-managed Action
  boundary; do not add arbitrary Dashboard HTTP proxies, legacy page metadata,
  or direct access to Dashboard authentication state.
- Long-lived resources must be owned by the lifecycle that creates them and
  have explicit termination. Re-raise `asyncio.CancelledError` when broad
  exception handling is unavoidable.
- Other major subsystems are `knowledge_base/`, `conversation_mgr.py`,
  `memory/`, `persona_runtime/`, `cron/`, `skills/`, `computer/`, `db/`, and
  `backup/`.

### Dashboard protocol

- FastAPI routes live in `astrbot/dashboard/api/`, are assembled under
  `/api/v1` by `api/router.py`, and delegate domain work to
  `astrbot/dashboard/services/`. Shared request models belong in
  `astrbot/dashboard/schemas.py`.
- Ordinary JSON endpoints use the structured `status` / `message` / `data`
  envelope from `dashboard/responses.py` (including `"status": "warning"` where
  explicitly supported). Do not wrap protocol responses that must remain raw:
  file/export downloads, SSE streams, WebSockets, third-party webhook
  callbacks, and static/public responses.
- The contract source is `openspec/openapi-v1.yaml`. Runtime routes, the source
  spec, generated clients/docs, frontend call sites, and backend/frontend tests
  must change together.
- Live Chat WebSockets multiplex concurrent chat runs by unique `message_id`.
  Request tasks, interrupts, follow-up capture, `run_started`, and streamed
  `agent_stats` metadata are request-scoped. Do not reintroduce a session-wide
  busy flag or emit a response without the originating request identity.

### Persistent state consistency

- `AstrBotConfig.save_config_async()` snapshots the configuration before
  leaving the event loop and uses monotonically increasing revisions so a late
  older write cannot replace a newer committed snapshot. Preserve atomic
  temporary-file replacement and use this API for async save paths instead of
  ad-hoc `to_thread(save_config)` calls.
- Knowledge-base uploads span parsed media, metadata storage, document storage,
  and FAISS vectors. Validate vector shape before local writes and keep
  compensating cleanup for every store when an upload fails before metadata
  commit. A partial document must never remain queryable after a reported
  upload failure.

The `astrbot` console entry point is in `astrbot/cli/__main__.py`. In this fork,
exercise it from the source checkout with `uv run astrbot ...`; installing the
PyPI package named `astrbot` installs the upstream distribution.

## Security invariants

Treat these as design constraints, not optional hardening:

- Dashboard binding defaults to `127.0.0.1`. Binding to `0.0.0.0` or another
  non-loopback address must be an explicit deployment choice with firewall,
  authentication, and preferably TLS/reverse-proxy protection.
- `dashboard.trust_proxy_headers` defaults to false. Enable it only behind a
  trusted proxy that overwrites forwarding headers; never trust spoofable
  client headers on a directly exposed server.
- Dashboard authentication rate limiting is enabled by default and its
  per-client registry is bounded. Do not bypass the login/TOTP checks or
  reintroduce attacker-controlled, unbounded limiter state.
- Download/update HTTP clients must verify certificates and hostnames. Do not
  restore `CERT_NONE`, `ssl=False`, `verify=False`, or an automatic insecure TLS
  retry after certificate failure.
- Remote MCP URLs reject localhost/private/link-local/reserved targets by
  default and HTTP clients do not follow redirects. Private-network access is
  allowed only through the explicit per-server `allow_private_network` opt-in;
  preserve DNS/IP validation and redirect blocking.
- Sanitize all untrusted rendered HTML with DOMPurify before `v-html`. Do not
  weaken the existing README, changelog, code-rendering, or config-hint
  sanitization paths to fix display issues.
- Parse untrusted XML with `defusedxml` (as the Satori adapter does), not the
  standard library parser without equivalent protections.
- User-facing agent failures remain generic. Redact provider errors, URLs,
  credentials, tokens, and sensitive configuration before logs or API/message
  responses; use `safe_error` / `redact_sensitive_text` and preserve config API
  redaction/restoration behavior.

## Generated artifacts and documentation

### OpenAPI

When changing Dashboard routes, schemas, or `openspec/openapi-v1.yaml`, run:

```bash
cd dashboard
pnpm generate:api
cd ..
node node_modules/prettier/bin/prettier.cjs --write --ignore-path .gitignore "dashboard/src/api/generated/openapi-v1/**/*.ts"
uv run python docs/scripts/update_openapi_json.py
node node_modules/prettier/bin/prettier.cjs --write docs/public/openapi.json
```

Commit the generated Hey API client under
`dashboard/src/api/generated/openapi-v1/` and the filtered public document at
`docs/public/openapi.json`. The repository-wide `.prettierignore` excludes
generated client code, so the explicit `--ignore-path .gitignore` is required
to reproduce its checked-in formatting. These formatting commands are
mechanical; do not hand-edit either generated output.

### Documentation

User/developer documentation is bilingual. A behavior, command, navigation, or
configuration change normally requires matching updates under `docs/zh/` and
`docs/en/`, plus `docs/.vitepress/config.mjs` when navigation changes. Keep the
two languages structurally aligned, but write natural translations rather than
copying stale text.

Validate documentation with:

```bash
cd docs
pnpm install --frozen-lockfile
pnpm run docs:build
cd ..
make check-md
```

`make check-md` enumerates tracked Markdown with `git ls-files`; run Prettier
and markdownlint explicitly on new untracked pages before they are added to the
index. During an uncommitted deletion, its wrapper may also pass the removed
tracked path to Prettier, so use an existing-file-filtered invocation for the
local check and still verify the post-commit target in CI.

Do not commit `docs/.vitepress/dist`, and do not create ad-hoc summary/report
Markdown files.

### NapCat generated models

`astrbot/core/platform/sources/napcat/generated/ob11_events.py` is generated
from NapCat's OneBot v11 TypeScript definitions. Never edit it by hand. Refresh
the source checkout under `.tmp/NapCatQQ` intentionally when consuming a new
NapCat revision, then run:

```bash
make napcat-check
```

This regenerates the schema/model, Ruff-formats the checked-in model, and runs
the focused NapCat adapter/codegen tests. Intermediate schema files under
`.tmp/napcat-schema` are not committed; review and commit the generated Python
diff with its runtime/test changes.

## Conventions

- **KISS / first principles:** do not add abstractions, dependencies, switches,
  or compatibility layers without a current need.
- **Inline first:** extract a helper when identical logic repeats at least three
  times or a continuous function would otherwise grow past roughly 50 lines.
  Do not fragment linear code into tiny wrappers.
- **Cross-platform:** consider Windows, macOS, Linux, Arm64, and x86 where the
  touched behavior applies, while retaining the Python 3.14+ baseline.
- **Paths:** use `pathlib.Path`. Runtime path helpers in
  `astrbot.core.utils.astrbot_path` return strings, so wrap them with `Path(...)`
  for path operations. Never hardcode runtime data/temp roots.
- **Runtime roots:** source checkout and runtime root differ. `ASTRBOT_ROOT` can
  relocate mutable state; most state belongs under `<root>/data/`. Tests must
  use temporary roots, never a developer's real `data/`.
- **Import boundaries:** `astrbot/api/` must not import Dashboard or concrete
  provider/platform sources. Shared core modules and built-in Stars must not
  depend on concrete sources except in the registration/discovery owners.
  `tests/unit/test_import_boundaries.py` guards key absolute-import paths;
  still review relative imports and ownership explicitly.
- **Docstrings:** use Google style (`Args:`, `Returns:`, `Raises:`). Write new
  comments in English; match surrounding Chinese only where consistency is
  materially clearer.
- **Version sync:** keep `[project].version` in `pyproject.toml` and
  `astrbot.__version__` synchronized. `astrbot/core/config/default.py` derives
  `VERSION`; do not hardcode it.
- **Fork URLs:** use `Xero-Team/AstrBot` for fork-owned repository metadata,
  clone/edit/source links, releases, and deployment claims. `AstrBotDevs`,
  `soulter`, and other upstream links are allowed only when deliberately citing
  provenance, the upstream sync source, or a service the fork still consumes;
  label that relationship instead of implying fork ownership.
- **Commits/PRs:** use English conventional commits (`feat:`, `fix:`,
  `refactor:`, `chore:`), with titles under about 70 characters.

## Upstream synchronization

The default upstream integration method is **cherry-pick**, not merge. Ensure
the remote is correct, fetch it, and enumerate commits oldest-first from the
full marker in `upstream-sync.yaml`:

```bash
# Run add when the remote is absent, or set-url when it already exists.
git remote add upstream https://github.com/AstrBotDevs/AstrBot.git
git remote set-url upstream https://github.com/AstrBotDevs/AstrBot.git
git fetch --prune --tags upstream
git log --reverse --topo-order --format="%H %s" <last_synced_sha>..upstream/master
```

Review and cherry-pick the displayed commits in order. A merge is reserved for
an explicitly justified bulk sync where per-commit cherry-picks are
impractical. Resolve conflicts in favor of this fork's no-legacy, Python
3.14-only policy, current dependency/toolchain choices, composition-based UI,
and fork documentation/deployment model.

You may skip an upstream version-bump commit, but after absorbing that release
you must still update `pyproject.toml`, `astrbot/__init__.py`, and the matching
`changelogs/vX.Y.Z.md`. Keep only entries for changes actually absorbed and
record fork-specific deviations.

Update `upstream-sync.yaml` in the same change set with the upstream repo and
branch, the full last-processed upstream object name, UTC timestamp, method,
`source_pr` provenance, and an honest note about included/skipped commits and
conflicts. `FETCH_HEAD`, abbreviated hashes, and git notes are not shared sync
state. Use `git rev-parse upstream/master` when recording the fetched upstream
head.

## Releases

Release preparation is a source-management workflow, not proof that assets will
be published. This fork's `.github` workflows do not publish GitHub assets, PyPI
packages, or container images. The documentation workflow only builds and uploads
a short-lived CI artifact; it has no deployment credentials or external publish
step.

`scripts/prepare_release.py` uses the latest tag reachable from the selected
base branch as its changelog lower bound. This fork currently has no
established local/origin tag baseline. After fetching and fast-forwarding the
selected base, always re-check the exact reachable baseline before a release:

```bash
git fetch --prune --tags <remote>
git describe --tags --abbrev=0 master
git merge-base --is-ancestor <reviewed-baseline-tag> master
```

If `git describe` fails, returns an upstream/unreviewed tag, or the ancestry
check fails, stop and have the maintainer establish a reviewed fork baseline
and release policy. The mere existence of local or remote tags is insufficient.
Running the script without a reachable reviewed tag drafts a changelog from
**all reachable history**, which is not a safe release range.

Once a valid baseline exists, start from a clean `master` and use a placeholder,
not an old example version:

```bash
uv run python scripts/prepare_release.py <next-version>
# optional: --generate-api-client --dashboard-build --commit --push
```

Pass the version without the leading `v`.

The script checks out and fast-forwards the base branch, fetches tags from the
selected `--remote`, creates `release/<version>`, bumps both version files, writes
`changelogs/v<version>.md`, and runs Ruff unless `--skip-checks` is supplied.
It does not replace the appropriate `make check`, `make test`, `make quality`,
Dashboard, or docs validation for the release's actual changes.
`--generate-api-client` assumes Dashboard dependencies are already installed
and regenerates only the Dashboard client; an OpenAPI change still requires the
public docs JSON command documented above.

The generated changelog is only a draft of raw commit subjects. Before the PR:

- group and rewrite entries into user-meaningful changes;
- remove merge/sync/internal noise and anything not shipped by the fork;
- include absorbed upstream work and security fixes accurately, noting
  fork-specific deviations;
- add compare/release links only when both referenced fork tags really exist.

After review, open the release branch PR to `master`. A post-merge tag does not
publish fork-owned PyPI, GitHub Release, or container artifacts; create a separate,
explicitly authorized publication workflow only when the fork establishes those
release targets and credentials.
