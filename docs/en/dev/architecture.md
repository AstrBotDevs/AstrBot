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
- The `astrbot` CLI resolves and locks its CLI runtime root and requires the `.astrbot` marker. Both `astrbot/cli/__main__.py` and `astrbot run` call `runtime_bootstrap.initialize_runtime_bootstrap()` to install the trusted CA. CLI `init` and `run` still do not download or update Dashboard assets, and they do not implement `main.py`'s `--webui-dir`. Changes to startup security, the runtime root, or Dashboard static-asset resolution must still inspect both `main.py` and the CLI.
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
7. `GroupMessageHistoryStage`
8. `ProcessStage`
9. `ResultDecorateStage`
10. `RespondStage`

`GroupMessageHistoryStage` persists inbound group messages other than WebChat before any plugin handles the event, for `GetGroupMessageHistoryTool`. Direct messages and WebChat skip this stage. `ProcessStage` runs plugin handlers and the Agent. `ResultDecorateStage` applies prefixes, segmentation, TTS, local text-to-image rendering, quoting, and related transformations. `RespondStage` uses the platform's unified send API. The scheduler supports both ordinary async stages and async-generator onion middleware; preserve stop-propagation and finalization semantics.

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

## Unified Authorization

Commands, Dashboard, WebChat, API keys, tools, and plugins all enter one runtime gate:

```text
authorize(subject, action, resource, context) -> Decision
```

The implementation lives in `astrbot/core/auth/`. `AuthorizationService` allows by the frozen action registry, relationship bindings, and at most one parent-resource hop. Unknown actions, missing subject/resource/context, policy failures, and a full high-risk audit queue fail closed. `event.role` is not an authorization field, and `event.is_admin()` is always `False`. Runtime code does not read `admins_id`, `tool_permissions`, or `disable_builtin_commands`; Dashboard config writes reject those fields. This fork does not migrate legacy permissions.

Cross-platform IM elevation has no runtime channel.

### Subjects, resources, and context

Subject IDs are namespaced, for example:

```text
im:<platform-instance>:<bot-account-id>:<sender-id>
dashboard-account:<account-id>
dashboard-session:<session-id>
api-key:<key-id>
plugin:<plugin-id>
agent:<agent-id>
system:<component>
guest:<id>
```

`dashboard-account` is the stable control-plane principal; `dashboard-session` only names the current authenticated session. `plugin:*` and `agent:*` are execution components and never inherit the caller's `root`/`operator`. Display names, nicknames, WebChat `username`, and caller-declared IDs are not authorization keys. `username` remains a compatibility field on WebChat/Open API.

Session resources use the versioned canonical string `session:v1:<encoded-config-id>:<encoded-umo>` and do not rewrite UMO routing. Inbound contexts carry an immutable `origin_session_resource_id`. Default `member`, session bindings, platform facts, and session-scoped tool authority apply only to that origin. Another session or a named `data` resource is denied by default.

### Fixed roles and relations

A role names who the subject is; the scope decides where that authority applies. The live relation table interprets `session_owner`/`session_admin` as `owner`/`admin`. `viewer`, `editor`, `executor`, and `caller` remain reserved.

| Role                | Scope                       | Meaning                                                       |
| ------------------- | --------------------------- | ------------------------------------------------------------- |
| `root`              | global                      | Highest Dashboard identity; account CRUD needs root + step-up |
| `operator`          | global                      | Global Dashboard operations                                   |
| `instance_operator` | `instance:<config-id>`      | One configuration profile                                     |
| `session_owner`     | `session:<config-id>/<umo>` | Current-session owner; platform guild owners map only here    |
| `session_admin`     | `session:<config-id>/<umo>` | Limited current-session management                            |
| `member`            | `session:<config-id>/<umo>` | Identified user                                               |
| `guest`             | session or none             | Unauthenticated or anonymous WebChat                          |

`root` and `operator` bind only to valid Dashboard accounts and never become IM group authority from a same-named message subject. A current-session owner may grant or revoke `session_admin` or `member` in that session only, and cannot delegate ownership. Platform owner/admin facts have a TTL, degrade after expiry, and never write global or instance bindings.

### Stable actions

Actions use `domain.verb`. Built-in commands declare them with `@filter.permission("session.manage")` and still call `authorize()`. High-risk actions are never inherited silently from a parent action.

| Action                                                    | Default roles                                  | High risk                          |
| --------------------------------------------------------- | ---------------------------------------------- | ---------------------------------- |
| `session.read`                                            | member+ on the current session                 | no                                 |
| `session.manage`                                          | session_admin+                                 | no                                 |
| `session.assign`                                          | session_owner+                                 | yes across sessions                |
| `provider.use` / `provider.read`                          | member+                                        | no; credentials are never returned |
| `provider.manage`                                         | instance_operator+                             | no                                 |
| `provider.credentials.write`                              | instance_operator+                             | yes                                |
| `platform.manage`                                         | instance_operator+                             | yes                                |
| `agent.manage`                                            | session_owner+                                 | partial                            |
| `extension.read` / `extension.manage`                     | member+ / instance_operator+                   | partial                            |
| `extension.plugin_install`                                | instance_operator+ with Dashboard step-up      | yes                                |
| `data.manage` / `data.export_all`                         | owner / instance_operator+                     | full export is high risk           |
| `system.manage`                                           | root; limited read for operator                | no                                 |
| `system.update` / `system.restart` / `system.pip_install` | root + step-up                                 | yes                                |
| `identity.manage`                                         | session_owner+ within scope                    | yes                                |
| `identity.operator.write` / `identity.root.write`         | root + step-up                                 | yes                                |
| `dashboard.account.manage`                                | root + step-up                                 | yes                                |
| `filesystem.read` / `filesystem.write`                    | operator, root                                 | no                                 |
| `filesystem.manage`                                       | root + step-up                                 | yes                                |
| `tool.file_read` / `tool.mcp_read`                        | member+                                        | no                                 |
| instance tools such as `tool.local_exec`                  | instance_operator+; WebChat also needs step-up | yes                                |

Plugin actions must use `plugin:<plugin-id>:<action>` and call `self.context.authz.authorize()` again. Undeclared plugin writes are denied. Tool authority is the intersection of user authorization, Persona tool policy, and the tool's own policy. Sub-agent handoff cannot escalate the caller.

### Step-up, audit, and API keys

Global high-risk operations accept only a one-time Dashboard password/TOTP step-up bound to the account, Dashboard `sid`, action, resource, and context digest. TTL is at most five minutes, and the token is consumed atomically. Dashboard-driven WebChat uses `/authorization/webchat-step-up` for six instance tools only: `tool.local_exec`, `tool.python_exec`, `tool.file_write`, `tool.browser_control`, `tool.mcp_write`, and `tool.computer_use`. Live Voice does not reuse that proof.

Denials, high-risk allows, step-up, and binding mutations write redacted audit events. A full bounded audit queue fails closed for high-risk allows. Binding mutations and step-up issuance commit in the same business transaction.

API keys use explicit capabilities only. Runtime authorization no longer expands `*` or `NULL` scopes. Historical `NULL` still means the frozen `DEFAULT_API_KEY_SCOPES` set, but high-risk actions always deny API keys. API keys cannot use the `system` scope or the data-file manager. `openspec/openapi-v1.yaml` is the complete Dashboard contract; public `docs/public/openapi.json` contains only API-key-facing paths.

Platform membership facts come only from inbound payloads: NapCat/aiocqhttp use group `sender.role`; Discord uses `guild.owner_id` and `administrator` already on the message; Telegram maps `status` only when present; Misskey maps a matching room owner. Lark, DingTalk, Kook, Slack, Mattermost, and Satori stay `member`/`unknown`. QQ Official, WeChat Official Account, WeCom, personal WeChat, Line, and WebChat never elevate from platform facts.

Operator usage is in [WebUI](/en/use/webui#accounts-and-authorization). Plugin filter examples are in [Listen to Message Events](/en/dev/star/guides/listen-message-event#permissions-and-actions).

## Dashboard and HTTP API

The Dashboard backend is a FastAPI application served by Hypercorn. HTTP routes live in `astrbot/dashboard/api/`, domain operations in `astrbot/dashboard/services/`, and request models in `astrbot/dashboard/schemas.py`.

Ordinary JSON APIs use a `status` / `message` / `data` envelope. Common statuses are `ok` and `error`, with `warning` in explicitly supported cases. File downloads, SSE, webhooks, static assets, and other protocol-native responses should use the appropriate FastAPI or Starlette response directly.

`astrbot/dashboard/api/router.py` assembles all `/api/v1` routes. The source specification is `openspec/openapi-v1.yaml`; both the Hey API Dashboard client and `docs/public/openapi.json` are generated from it. Do not hand-edit generated clients.

Live Chat WebSockets can run multiple requests concurrently on one connection. A unique `message_id` correlates each task, response, and interrupt. Follow-up capture, `run_started`, and per-call `agent_stats` must retain the originating request identity; do not reduce the protocol to a session-wide busy flag and one serialized request.

### Data file manager

Dashboard exposes a native runtime `data/` file manager at `/data`. It is not an iframe IDE and does not provide a terminal, code execution, Git, LSP, or arbitrary host-path access. The implementation lives in:

- `astrbot/dashboard/api/data_files.py`
- `astrbot/dashboard/services/data_file_service.py`
- `dashboard/src/views/DataFilesPage.vue`

Routes use a dedicated `Data Files` OpenAPI tag and are not in `PUBLIC_OPEN_API_TAGS`. Authentication reuses `require_dashboard_session_principal`; API keys always receive 403. Actions are `filesystem.read`, `filesystem.write`, and `filesystem.manage`. The collection resource is `Resource.named("filesystem", "collection")`; a single path uses `object_resource("filesystem", relative_path)`.

`DataFileService` resolves the root from `get_astrbot_data_path()`. User paths must be relative to `data/`: absolute paths, empty segments, `.`/`..`, control characters, and Windows reserved names are rejected. Symlinks are metadata-only and cannot escape the root. Classification is path-prefix-first: `plugins/` is read-only until `filesystem.manage` plus step-up; `plugin_data/` is ordinary data; `dist/`, `site-packages/`, and live databases plus WAL/SHM are hard read-only. A root Dashboard session may read raw `cmd_config.json` and `config/`; `operator` cannot bypass Config API redaction through file reads. Managed configuration saves must parse, validate, persist through the existing config service, and reload; they cannot write raw bytes.

The page lists directories, reads and writes UTF-8 text, creates/renames/moves/deletes, uploads and downloads, previews binaries, and searches filenames recursively. Limits are 1 MiB for editable text, 200 entries on the first directory page, 32 MiB per uploaded file, and 64 MiB per upload request. Search matches basename and relative path only, returns at most 100 hits, uses a 5,000-inode budget, and times out after 3 seconds. Writes use a SHA-256 etag and same-directory atomic replacement; conflicts return 409. Hidden files are shown. Demo mode is read-only. Audit records store a relative-path summary, never file contents.

Usage is in [WebUI](/en/use/webui#data-files).

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

| Change                     | Primary location                                             | Also verify                                                             |
| -------------------------- | ------------------------------------------------------------ | ----------------------------------------------------------------------- |
| Messaging platform         | `astrbot/core/platform/sources/`                             | discovery, config metadata, platform docs, send/cleanup tests           |
| Model provider             | `astrbot/core/provider/sources/`                             | `provider_modules.py`, metadata, provider tests                         |
| Agent Runner               | `astrbot/core/agent/runners/`                                | provider config, runner docs, tools and streaming behavior              |
| Pipeline or wake behavior  | `astrbot/core/pipeline/`                                     | stage order, wake reasons, stop propagation, streaming tests            |
| Command syntax and binding | `astrbot/core/command/`, `astrbot/core/star/filter/`         | lexer/binder properties, catalog lifecycle, native command sync         |
| Dashboard API              | `astrbot/dashboard/api/`, `services/`, `schemas.py`          | OpenAPI, generated client, backend/frontend tests                       |
| Authorization              | `astrbot/core/auth/`                                         | action registry, step-up, platform facts, audit, plugin `context.authz` |
| Data file manager          | `data_files.py`, `data_file_service.py`, `DataFilesPage.vue` | path escape, symlinks, etag, step-up, OpenAPI tag allowlist             |
| Live Chat protocol         | `live_chat_service.py`, `webchat/`                           | request identity, concurrency, interrupts, frontend state tests         |
| Plugin SDK/page protocol   | `astrbot/api/`, `astrbot/core/star/`                         | import boundaries, plugin docs, Vitest, Playwright                      |
| Configuration persistence  | `astrbot/core/config/`                                       | defaults/metadata, revisions, concurrent-save tests                     |
| Knowledge-base writes      | `knowledge_base/`, `db/vec_db/`                              | multi-store rollback, failure injection, residual/query checks          |
| NapCat event models        | `scripts/napcat/`                                            | run `make napcat-check`; do not edit generated models                   |
