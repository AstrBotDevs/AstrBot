# AstrBot plugin contract

This reference describes the current `Xero-Team/AstrBot` checkout. Read the linked
source guide when a detail is not covered here; do not substitute an upstream or
legacy example.

## Runtime and package boundary

- Read `[project].requires-python` from the checkout's `pyproject.toml` before generating a plugin. The current checkout declares `>=3.14`; `.python-version` pins `3.14.6` for development and CI. Generated plugin documentation must repeat the value read from the checkout, not a hand-maintained fallback.
- The plugin is a Python package-like directory loaded from `data/plugins/`.
- `metadata.yaml` requires `name`, `desc`, `version`, and `author`. `name` must be a legal Python identifier and a single directory name. Prefer `astrbot_plugin_<name>`.
- `main.py` contains the `Star` subclass and handler registrations. `requirements.txt`, `_conf_schema.json`, `.astrbot-plugin/i18n/`, `skills/`, and Dashboard files are opt-in.
- Develop an independent repository outside the AstrBot checkout and connect it with `uv run astrbot plug install --editable <plugin-dir>`.

Source: [AstrBot plugin development guide](../../../../docs/zh/dev/star/plugin-new.md) (in-app: `/help/dev/star/plugin-new.html`).

## Public SDK and lifecycle

Use imports from `astrbot.api` only, for example:

```python
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import PluginContext, Star
```

Handlers belong to the `Star` subclass and receive `self` and `event` first. Use
`initialize()` to create HTTP clients, tasks, database handles, or other owned
resources. Cancel and close them in `terminate()`, including on hot reload and
shutdown. Re-raise `asyncio.CancelledError` when broad exception handling is
needed.

Never import `astrbot.core`, `astrbot.dashboard`, concrete platform adapters,
provider source modules, or private runtime registries. Do not use old
`register` decorators, `event.bot`, `event.client`, or arbitrary raw platform
calls.

Source: [minimal plugin](../../../../docs/zh/dev/star/guides/simple.md) and the repository import-boundary rules in `AGENTS.md`.

## Configuration and persistence

`_conf_schema.json` must be strict JSON. Supported schema types include
`string`, `text`, `int`, `float`, `bool`, `list`, `file`, `object`, `dict`, and
`template_list`. Inject `AstrBotConfig` into the plugin constructor only when
configuration is required. Keep secrets out of logs and error details.

Use `self.context.storage.data_directory()` for files and databases, or the
plugin KV methods for small state. Never write persistent data into the plugin
source tree or another plugin's directory.

Sources: [plugin configuration](../../../../docs/zh/dev/star/guides/plugin-config.md) and [plugin storage](../../../../docs/zh/dev/star/guides/storage.md).

## Security and compatibility

- Runtime dependencies must support the checkout's Python floor; do not add pre-3.14 compatibility branches.
- Use `aiohttp` or `httpx` for asynchronous network I/O, with bounded timeouts and cancellation handling.
- Validate user-controlled URLs, paths, files, tool arguments, and remote responses.
- Return generic user-facing failures and log only redacted diagnostics.
- Keep the plugin's declared `astrbot_version` and `support_platforms` truthful; these declarations do not replace runtime capability checks.
- Treat a plugin-provided `skills/` directory as an optional AstrBot runtime Skill, distinct from this Codex skill.
