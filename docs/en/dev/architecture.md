---
outline: deep
---

# Project Architecture

This page describes the runtime structure and code boundaries of the current Xero-Team fork. When an upstream tutorial or historical document conflicts with this page, follow the current repository.

## Sources of Truth

No single prose document defines the entire project. Check the relevant source whenever behavior changes:

| Subject                        | Source of truth                                                                                                                            |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Version and Python requirement | `pyproject.toml`, `astrbot/__init__.py`, `.python-version`                                                                                 |
| Python dependencies            | `pyproject.toml`, `requirements.txt`, `uv.lock`                                                                                            |
| Dashboard toolchain            | `dashboard/package.json`, `dashboard/pnpm-lock.yaml`                                                                                       |
| Documentation toolchain        | `docs/package.json`, `docs/pnpm-lock.yaml`                                                                                                 |
| Defaults and WebUI metadata    | `astrbot/core/config/default.py`                                                                                                           |
| HTTP API contract              | `openspec/openapi-v1.yaml`                                                                                                                 |
| Current upstream sync point    | `upstream-sync.yaml`                                                                                                                       |
| Versioned change records       | `changelogs/`; they record absorbed version changes, not proof of fork publication; later commits are not yet in the latest version record |

The reproducible development and CI baseline is currently Python 3.14.6, Node.js 26.5.0, and pnpm 11.21.0. Package metadata supports Python 3.14 and later.

## Startup Flow

The source and CLI entry points have different preparation paths, but both eventually construct `RuntimeServices` explicitly and hand them to `InitialLoader`:

- The root `main.py` calls `runtime_bootstrap.initialize_runtime_bootstrap()` to configure the trusted CA before importing core modules, then applies startup environment options and validates Python and runtime paths. Dashboard resolution first honors an explicit `--webui-dir`, then checks a version-matched source-tree `dashboard/dist`, runtime `data/dist`, and bundled assets. It performs no network access and never serves mismatched or incomplete static files; without a compatible build, only the WebUI is disabled.
- The `astrbot` CLI resolves and locks its CLI runtime root and requires the `.astrbot` marker. Its `init` and `run` commands do not download or update Dashboard assets, and it does not invoke the root `runtime_bootstrap` path. Changes to startup security or asset resolution must therefore inspect both entry points.
- Both paths then call `create_runtime_services()` for configuration, database, preferences, HTML rendering, file-token, and dependency-installation services. `InitialLoader` initializes `AstrBotCoreLifecycle` and runs the core tasks and FastAPI Dashboard together.
- Failed initialization triggers cleanup. Shutdown must tolerate partial initialization and repeated calls. Importing `astrbot.core` alone must not construct runtime services or access user data.

## Runtime Ownership

`RuntimeServices` owns capabilities shared by one AstrBot process:

- `AstrBotConfig`
- `SQLiteDatabase`
- `SharedPreferences`
- the local Playwright `HtmlRenderer`
- `FileTokenService`
- `PipInstaller`
- demo-mode state

`AstrBotCoreLifecycle` builds Provider, Platform, Conversation, Persona, Memory, Knowledge Base, Cron, Plugin, SubAgent, and Pipeline managers on top of those services in dependency order. Pass shared capabilities through their existing owners; do not restore process-global service singletons.

## Message Pipeline

Platform adapters normalize inbound messages into `AstrMessageEvent` and enqueue them in a shared queue capped at 1024 items. `EventBus` selects the `PipelineScheduler` for the message's config profile and executes it under a concurrency semaphore.

The order in `astrbot/core/pipeline/stage_order.py` is:

1. `WakingCheckStage`
2. `WhitelistCheckStage`
3. `SessionStatusCheckStage`
4. `RateLimitStage`
5. `ContentSafetyCheckStage`
6. `PreProcessStage`
7. `ProcessStage`
8. `ResultDecorateStage`
9. `RespondStage`

`ProcessStage` runs plugin handlers and the Agent. `ResultDecorateStage` applies prefixes, segmentation, TTS, local text-to-image rendering, quoting, and related transformations. `RespondStage` uses the platform's unified send API. The scheduler supports both ordinary async stages and async-generator onion middleware; preserve stop-propagation and finalization semantics.

Group wake behavior is explicit. `platform_settings.group_wake_policy` separately controls whether mentioning or replying to the bot wakes a group message, and both values default to false. `WakingCheckStage` records the actual `wake_reasons` on the event. Built-in command availability is stored per handler in the command database; `disable_builtin_commands` is not migrated, accepted by Dashboard config writes, or read by the Pipeline.

### Command Parsing Subsystem

Command arguments are handled by the Orbit Command Syntax subsystem under `astrbot/core/command/`. `catalog.py` builds an immutable longest-match index for enabled commands, groups, and aliases at every level. `lexer.py` implements a deterministic POSIX word subset without expansions or operators. `schema.py` compiles handler signatures during registration, `binder.py` handles positionals, options, defaults, and conversion, and `engine.py` provides the resolve, lex, and bind flow.

The plugin manager explicitly owns a `CommandCatalogStore` for each Pipeline configuration. Plugin load, unload, reload, enablement changes, and Dashboard command enablement, rename, or alias updates build a new snapshot and atomically replace the reference. The `WakingCheckStage` hot path only reads the snapshot: it removes the wake prefix, performs longest command-header matching, lexes once after a match, and binds every matching handler independently by `handler_full_name`. A completely unknown root never enters Orbit, so ordinary LLM prompts containing `$`, URLs, or incomplete quotes are not intercepted by command parsing.

Core diagnostics retain only stable error codes, Unicode code-point spans, parameters, and hint codes. The zh-CN/en-US message and source caret are rendered at the presentation boundary. Supported plugin entry points are `astrbot.api.command` and `option`/`GreedyStr` from `astrbot.api.event.filter`; the internal catalog, engine, and handler metadata are not plugin APIs.

## Agents, Tools, and Skills

The Agent runtime is under `astrbot/core/agent/`, with main-request assembly in `astrbot/core/astr_main_agent.py`. Provider abstractions live in `astrbot/core/provider/`; concrete OpenAI, Anthropic, Gemini, and similar sources live in `provider/sources/` and are lazily registered through `provider_modules.py`. Dify, Coze, DashScope, and DeerFlow are external Agent Runners under `astrbot/core/agent/runners/`, not ordinary model providers.

Tools can come from the core, plugins, or MCP. MCP supports stdio and Streamable HTTP only. Remote HTTP connections reject localhost, private, link-local, and reserved addresses by default; a trusted configuration must explicitly set `allow_private_network` to opt in.

Skills can come from `data/skills`, plugin `skills/` directories, the sandbox, or the current session workspace. Workspace Skills are request-scoped and normally live under `data/workspaces/{normalized_umo}/skills/`.

SubAgents are exposed to the main Agent as `transfer_to_*` handoff tools. Enabling orchestration keeps the main Agent's own tools by default. Only the duplicate-tool option removes tools that overlap with enabled SubAgents.

The Tool Loop emits `agent_stats` after every completed model call, including intermediate model turns before tool execution. WebChat forwards each one as a request-identified protocol event instead of producing only one summary when the entire Agent finishes.

## Plugin Boundaries

Plugins are called Stars. Built-in Stars live in `astrbot/builtin_stars/`; user plugins load from `<runtime-root>/data/plugins/`.

Plugins and built-in Stars should use the SDK under `astrbot.api`, not concrete platform or provider sources. Only registration/discovery owners in shared core, such as `astrbot/core/platform/discovery.py` and the Provider module registry, may intentionally import concrete sources; ordinary shared modules must go through those owners. `tests/unit/test_import_boundaries.py` checks key absolute-import paths, but review is still required for relative imports and ownership:

- `astrbot/api/` cannot depend on Dashboard or concrete sources.
- only registration/discovery owners in shared `astrbot/core/` may directly import concrete platform or provider sources.
- `astrbot/builtin_stars/` cannot directly import concrete sources.

Use the Star KV API for small persistent values. From a `Star` instance, store files in the `data/plugin_data/<plugin>` directory returned by `self.context.storage.data_directory()`, not beside plugin source code.

Plugin Dashboard pages use Extension Protocol v1. Metadata declares both `requires.dashboard_extension: 1` and `dashboard`, `assets.v1.json` fully lists content-addressed static assets, and Python Actions can be registered only during `initialize()` through `astrbot.api.dashboard`. Pages run in a sandboxed iframe with only `allow-scripts`; privileged work must cross host-managed structured Actions. Legacy Page metadata, arbitrary HTTP proxies, and direct access to Dashboard authentication state are not supported. See the [Plugin Dashboard Extension Development Guide](/dev/star/plugin-dashboard-extension) for the complete contract.

## Dashboard and HTTP API

The Dashboard backend is a FastAPI application served by Hypercorn. HTTP routes live in `astrbot/dashboard/api/`, domain operations in `astrbot/dashboard/services/`, and request models in `astrbot/dashboard/schemas.py`.

Ordinary JSON APIs use a `status` / `message` / `data` envelope. Common statuses are `ok` and `error`, with `warning` in explicitly supported cases. File downloads, SSE, webhooks, static assets, and other protocol-native responses should use the appropriate FastAPI or Starlette response directly.

`astrbot/dashboard/api/router.py` assembles all `/api/v1` routes. The source specification is `openspec/openapi-v1.yaml`; both the Hey API Dashboard client and `docs/public/openapi.json` are generated from it. Do not hand-edit generated clients.

Live Chat WebSockets can run multiple requests concurrently on one connection. A unique `message_id` correlates each task, response, and interrupt. Follow-up capture, `run_started`, and per-call `agent_stats` must retain the originating request identity; do not reduce the protocol to a session-wide busy flag and one serialized request.

## Persistent Consistency

`AstrBotConfig.save_config_async()` deep-copies a stable snapshot before leaving the event loop and commits monotonically increasing revisions. An older write that finishes late cannot replace a newer configuration. Async callers should use this API and preserve its temporary-file, `fsync`, and atomic-replace semantics instead of assembling concurrent saves with `to_thread(save_config)`.

Knowledge-base uploads span media files, document metadata, chunk storage, and FAISS vectors. Validate vector shape and dimension before local writes. If any step fails before metadata commit, compensating cleanup must remove every already-written store so an API-reported failure never leaves a partially queryable document.

## Runtime Root

The source checkout and runtime root are separate concepts. The runtime root defaults to the current working directory, can be overridden with `ASTRBOT_ROOT`, and uses a dedicated user-directory root in packaged Desktop builds.

Mutable state normally lives under `<runtime-root>/data/`:

- `cmd_config.json` and `config/`
- `data_v4.db`
- `plugins/` and `plugin_data/`
- `skills/` and `workspaces/`
- `knowledge_base/`
- `t2i_templates/`
- `backups/`, `temp/`, and `webchat/`

Runtime-root helpers in `astrbot.core.utils.astrbot_path` currently return strings. Wrap those values in `Path(...)` before new core path arithmetic. Do not apply this rule to CLI helpers or the plugin storage capability's `data_directory()`, which already returns a `Path` object.

## Network and Security Defaults

- WebUI, built-in webhooks, and reverse WebSocket listeners bind to loopback by default. Remote access requires an explicit bind address plus suitable firewall, TLS, or trusted reverse-proxy controls.
- `dashboard.trust_proxy_headers` is off by default. Enable it only when a trusted proxy overwrites client-supplied forwarding headers.
- Downloads must verify TLS; do not add `ssl=False` or `verify=False` fallback paths.
- Parse untrusted XML with `defusedxml`.
- Sanitize dynamic Dashboard HTML with DOMPurify; frontend lint rejects unaudited `v-html` usage.
- Redact sensitive values before exposing Agent exceptions to users or logs.

## Where to Make Changes

| Change                     | Primary location                                     | Also verify                                                     |
| -------------------------- | ---------------------------------------------------- | --------------------------------------------------------------- |
| Messaging platform         | `astrbot/core/platform/sources/`                     | discovery, config metadata, platform docs, send/cleanup tests   |
| Model provider             | `astrbot/core/provider/sources/`                     | `provider_modules.py`, metadata, provider tests                 |
| Agent Runner               | `astrbot/core/agent/runners/`                        | provider config, runner docs, tools and streaming behavior      |
| Pipeline or wake behavior  | `astrbot/core/pipeline/`                             | stage order, wake reasons, stop propagation, streaming tests    |
| Command syntax and binding | `astrbot/core/command/`, `astrbot/core/star/filter/` | lexer/binder properties, catalog lifecycle, native command sync |
| Dashboard API              | `astrbot/dashboard/api/`, `services/`, `schemas.py`  | OpenAPI, generated client, backend/frontend tests               |
| Live Chat protocol         | `live_chat_service.py`, `webchat/`                   | request identity, concurrency, interrupts, frontend state tests |
| Plugin SDK/page protocol   | `astrbot/api/`, `astrbot/core/star/`                 | import boundaries, plugin docs, Vitest, Playwright              |
| Configuration persistence  | `astrbot/core/config/`                               | defaults/metadata, revisions, concurrent-save tests             |
| Knowledge-base writes      | `knowledge_base/`, `db/vec_db/`                      | multi-store rollback, failure injection, residual/query checks  |
| NapCat event models        | `scripts/napcat/`                                    | run `make napcat-check`; do not edit generated models           |
