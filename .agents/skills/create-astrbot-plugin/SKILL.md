---
name: create-astrbot-plugin
description: Create, extend, or repair an AstrBot plugin (Star) from a feature request. Use when a task involves metadata.yaml, main.py, AstrBot event handlers, plugin configuration, storage, AI calls, platform actions, plugin Skills, or Dashboard Extension pages. Follow the current Xero-Team/AstrBot source checkout and its Python floor; do not use legacy plugin APIs or internal AstrBot modules.
---

# Create an AstrBot plugin

Create a standalone plugin package that targets the current AstrBot checkout. Keep the plugin small, use only the public SDK, and leave AstrBot core files unchanged unless the user explicitly requests a core change.

## Locked

- Public SDK only (`astrbot.api`). No `astrbot.core`, Dashboard, or concrete adapter/provider imports.
- Python floor from this checkout's `pyproject.toml`. No 3.10–3.13 branches.
- In-app docs at `/help/`. Do not point READMEs at `docs.astrbot.app`.
- Do not claim this fork publishes PyPI packages, images, or an official plugin market.
- Agents may commit the plugin tree only when the user asked and the files are inside this checkout. They must not merge. See `.agents/shared/ai-contribution/REFERENCE.md` and `AI_POLICY.md`.

## Open

Plugin name, commands, platforms, secrets, and whether tests or a Dashboard Extension page are required — ask only when those decisions are missing.

## Do not

- Restore legacy `register` decorators, `event.bot`, `event.client`, or raw platform clients.
- Overwrite an existing plugin directory unless the user passed `--force`.
- Write disposable state into a developer's real `data/`.
- Vendor a copy of this skill into a sibling plugin repo; call `scripts/check_plugin.py` from this checkout.

## Handoff

- Contract: `references/astrbot-plugin-contract.md`
- Patterns: `references/feature-patterns.md` (load only the selected feature)
- Checks: `references/verification.md`
- Commit shape: `.agents/shared/conventional-commit/REFERENCE.md`

## Required preflight

1. Read the repository `README.md` or `README_zh.md` and `pyproject.toml` before writing code.
2. Treat `[project].requires-python` in `pyproject.toml` as the source of truth for the plugin's minimum Python version. Also read `.python-version` for the repository's tested interpreter pin. Never add Python 3.10–3.13 compatibility branches or hardcode a different floor.
3. Read the relevant current-fork guide before choosing an API. Sources live under `docs/zh/dev/star/` in this checkout and are served in-app at `/help/dev/star/` after `make run`. Do not point generated READMEs at `docs.astrbot.app`.
   - [plugin development](../../../docs/zh/dev/star/plugin-new.md)
   - [minimal plugin](../../../docs/zh/dev/star/guides/simple.md)
   - [events and Orbit commands](../../../docs/zh/dev/star/guides/listen-message-event.md)
   - [configuration](../../../docs/zh/dev/star/guides/plugin-config.md)
   - [storage](../../../docs/zh/dev/star/guides/storage.md)
   - [messages](../../../docs/zh/dev/star/guides/send-message.md)
   - [AI](../../../docs/zh/dev/star/guides/ai.md)
   - [Dashboard Extension](../../../docs/zh/dev/star/plugin-dashboard-extension.md)
4. Ask only for missing decisions that change the package shape: plugin name, behavior, command/event, supported platforms, secrets/configuration, third-party dependencies, and whether tests or a Dashboard page are required.
5. Place a standalone plugin outside the AstrBot source tree when possible. Install it with `uv run astrbot plug install --editable <plugin-dir>` while developing.

For deterministic scaffolding, run the bundled script from the AstrBot checkout:

```bash
python .agents/skills/create-astrbot-plugin/scripts/scaffold_plugin.py \
  --astrbot-root . \
  --output ../astrbot_plugin_example \
  --name astrbot_plugin_example \
  --author "Your Name" \
  --description "A short plugin description" \
  --version 0.1.0
```

The script refuses to overwrite an existing directory and copies the Python floor from the checkout's `pyproject.toml` into the generated README. Pass `--force` only when the user explicitly wants replacement.

## Implementation workflow

### 1. Define the package contract

Generate or edit:

```text
plugin-root/
├── metadata.yaml       # name, desc, version, author; repo is recommended
├── main.py             # plugin class and registered handlers
├── README.md           # usage and the synchronized Python floor
├── requirements.txt    # only for real third-party runtime dependencies
├── _conf_schema.json   # only when WebUI configuration is needed
├── tests/              # focused regression tests when behavior warrants them
└── .astrbot-plugin/
    └── i18n/           # only when zh-CN/en-US text needs localization
```

`metadata.yaml:name` must be a legal Python identifier and a single directory name. Prefer the `astrbot_plugin_<name>` convention. Keep `display_name`, `short_desc`, `support_platforms`, and `astrbot_version` optional and add them only when they communicate a real contract.

### 2. Use the public SDK

Import from `astrbot.api` only. Typical imports are:

```python
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import PluginContext, Star
```

Implement handlers on the `Star` subclass. The first two handler parameters are `self` and `event`; command handlers are async generators that yield message results. Use `initialize()` for clients, tasks, and other resources, and `terminate()` for cancellation and cleanup.

Do not import `astrbot.core`, `astrbot.dashboard`, concrete platform adapters, or provider source modules. Do not restore legacy `register` decorators, `event.bot`, `event.client`, or arbitrary raw platform calls.

### 3. Select the smallest matching pattern

Load [references/feature-patterns.md](references/feature-patterns.md) only for the selected feature. Keep the default implementation minimal:

- command or command group: use `filter.command` / `filter.command_group` and typed Orbit parameters;
- event listener: use public filters and inspect `AstrMessageEvent` without parsing shell-like arguments manually;
- configuration: use strict JSON `_conf_schema.json`, inject `AstrBotConfig`, and validate external values in plugin code;
- persistence: use `self.context.storage.data_directory()` or the plugin KV methods, never the source directory;
- AI: use `event.request_llm`, `context.models.generate`, or `context.models.tool_loop` according to the documented need;
- active delivery: save `event.unified_msg_origin` as user data and use `context.messages.send()` with a result check;
- long-running session: use `context.messages.wait_for()` and handle timeout, cancellation, and `terminate()`;
- OneBot: use the typed facade and capability checks, not adapter internals;
- Dashboard Extension: read the protocol guide first; register actions only during `initialize()` and keep the sandboxed page allowlist intact;
- plugin-provided Skill: put it under the generated plugin's `skills/` only when the user asks for an AstrBot runtime Skill.

For commands, follow the Orbit conventions: use a short lowercase root, explicit subcommands for state changes, typed parameters, `GreedyStr` for trailing free text, and `Annotated[..., filter.option(...)]` for named options. Do not call `split()` on `event.message_str` to reimplement parsing.

### 4. Handle dependencies, data, and errors safely

- Add only Python 3.14+-compatible runtime dependencies to `requirements.txt`.
- Use `aiohttp` or `httpx` for network I/O; set timeouts and handle cancellation.
- Keep secrets in plugin configuration, mark sensitive hints appropriately, and never log them.
- Return short, generic user-facing failures; log only redacted diagnostic details.
- Store files and databases under the plugin data directory and close them in `terminate()`.
- Bound retries, queues, tool steps, file sizes, and remote inputs.

### 5. Add focused tests and documentation

Test the behavior nearest its boundary: command parsing, empty and quoted arguments, config defaults and old config shapes, provider unavailable/timeout/cancellation, storage paths, and hot reload when applicable. Mock providers and external services unless an integration test is explicitly enabled.

README content should state installation, commands, configuration, supported platforms, dependencies, and the exact Python floor read from the AstrBot checkout. Point users at the in-app documentation (`/help/` after starting AstrBot) rather than `docs.astrbot.app`. Do not claim that the Xero-Team fork publishes PyPI packages, images, or an official plugin market.

## Verification

Run the bundled checker from the AstrBot checkout:

```bash
python .agents/skills/create-astrbot-plugin/scripts/check_plugin.py \
  --astrbot-root . <plugin-dir>
```

Then run checks appropriate to the generated files:

```bash
python -m compileall <plugin-dir>
uv run ruff check <plugin-dir>
uv run ruff format --check <plugin-dir>
```

For an installation smoke test, run `uv run astrbot plug install --editable <plugin-dir>` from the intended AstrBot checkout or a disposable checkout. The CLI resolves its root from the current working directory, so do not assume setting `ASTRBOT_ROOT` alone isolates the CLI. Never write disposable state into the repository's real `data/`. If the plugin has tests, run the focused test file first and then the smallest relevant project test command.

Before handing off, report the generated files, the synchronized Python constraint and source path, checks run, and any unresolved assumption. Never claim a runtime or platform integration was tested when only static checks ran.

## Commits

Commit plugin files only when the user explicitly asks and the plugin tree is
inside this repository. Out-of-tree plugin packages are not AstrBot commits.
Follow `.agents/shared/conventional-commit/REFERENCE.md`, including the
`AI-Generated` and `Generated-At` footers. You may push a feature branch and
open a PR as part of that request. Do not merge. End the PR with
`## Agent note` (or ask the human author for `## Human note`).

## Bundled resources

- [references/astrbot-plugin-contract.md](references/astrbot-plugin-contract.md): compact current-fork contract and source links.
- [references/feature-patterns.md](references/feature-patterns.md): conditional patterns for common plugin capabilities.
- [references/verification.md](references/verification.md): validation matrix and failure boundaries.
- `scripts/scaffold_plugin.py`: deterministic base package generator.
- `scripts/check_plugin.py`: dependency-free static contract checker.
