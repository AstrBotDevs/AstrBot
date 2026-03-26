---
name: {{ skill_dir_name }}
description: Design, implement, test, and package AstrBot SDK v4 plugins. Activate when the request involves AstrBot plugins, plugin.yaml, main.py, Star base class, Context, MessageEvent, SDK decorators (on_command, on_message, on_event, on_schedule, conversation_command, provide_capability, register_llm_tool, http_api, background_task), PluginHarness, or astrbot-sdk CLI commands (init, validate, dev, build).
---

# AstrBot Plugin Dev

Turn plugin requirements into working AstrBot SDK v4 plugins. Default to the stable public SDK surface and CLI workflow.

## Project Context

- Plugin name: `{{ plugin_name }}`
- Display name: `{{ display_name }}`
- Plugin root: `{{ plugin_root }}`
- Target agent: `{{ agent_display_name }}`

## Step 1 — Classify the task

- **New plugin**: scaffold with `astrbot-sdk init <name>` (fallback: `python -m astrbot_sdk init <name>`).
- **Existing plugin**: read `plugin.yaml` + component module first; never run `init` inside it.
- **Migration**: v3→v4 conversion — see migration notes at the end.

## Step 2 — Map intent to decorators

| User wants … | Decorator |
|---|---|
| Slash-style command (`/hello`) | `@on_command` |
| Keyword or regex reaction | `@on_message` |
| Non-message platform event (join, load …) | `@on_event` |
| Periodic / cron task | `@on_schedule` |
| Multi-turn dialogue / form flow | `@conversation_command` |
| Expose HTTP endpoint | `@http_api` |
| Inter-plugin callable capability | `@provide_capability` |
| Give the LLM a callable tool | `@register_llm_tool` |
| Continuous background loop | `@background_task` |
| MCP server exposure | `@mcp_server` |

Add guards as needed: `@require_admin`, `@platforms(...)`, `@group_only()`, `@private_only()`, `@rate_limit(...)`, `@cooldown(...)`, `@priority(...)`.

## Step 3 — Implement

### Handler signatures (must match trigger type)

```python
# Command / message / event handlers
async def handler(self, event: MessageEvent, ctx: Context) -> None: ...

# Command with typed parameters (GreedyStr MUST be last)
async def handler(self, event: MessageEvent, ctx: Context, name: str, content: GreedyStr) -> None: ...

# Schedule handler — NO event parameter
async def handler(self, ctx: Context) -> None: ...

# Conversation command — receives ConversationSession
async def handler(self, event: MessageEvent, ctx: Context, session: ConversationSession) -> None: ...

# Capability handler
async def handler(self, payload: dict, ctx: Context) -> dict: ...

# LLM tool — keyword arguments matching schema
async def handler(self, city: str, unit: str = "celsius") -> dict: ...

# Background task
async def handler(self, ctx: Context) -> None: ...
```

### Imports

```python
# Core — always needed
from astrbot_sdk import Star, Context, MessageEvent

# Decorators — import only what you use
from astrbot_sdk.decorators import on_command, on_message, on_schedule  # etc.

# Typed command params
from astrbot_sdk import GreedyStr

# Rich messages
from astrbot_sdk import MessageBuilder, MessageChain, Plain, Image, At, AtAll, File

# Conversation
from astrbot_sdk import ConversationSession

# Config validation
from pydantic import BaseModel
from astrbot_sdk.decorators import validate_config
```

### Public API boundaries

**Use freely:** `astrbot_sdk.*`, `astrbot_sdk.decorators.*`, `astrbot_sdk.clients.*`, `astrbot_sdk.testing.*`

**Never use in plugin code:** `astrbot_sdk.runtime.*`, Worker/Supervisor, Loader, Peer/Transport internals.

## Step 4 — Validate and test

```bash
# Validate structure + imports + handler discovery
astrbot-sdk validate --plugin-dir <dir>

# Single-shot local test
astrbot-sdk dev --local --plugin-dir <dir> --event-text "<sample>"

# Run tests
python -m pytest tests -q

# Package (optional)
astrbot-sdk build --plugin-dir <dir>
```

If `astrbot-sdk` is not on PATH, use `python -m astrbot_sdk <subcommand>` instead.

## Guardrails — MUST follow

### Context handling
- **NEVER** store `ctx` on `self` outside the active handler or lifecycle call.
- In `on_start` / `on_stop`, always call `await super().on_start(ctx)` / `await super().on_stop(ctx)`.

### Client API semantics (prevents common bugs)
- `ctx.db.delete(key)` returns **None**, not bool. Check existence with `ctx.db.get()` first if you need to know.
- `ctx.db.get(key)` returns **None** for missing keys, does not raise.
- `ctx.db.list(prefix)` returns `list[str]` of key names, not values.
- `ctx.memory.save(key, value)` — value **must** be `dict`, not `str`/`int`. Raises `TypeError` otherwise.
- `ctx.memory.delete_many(keys)` returns `int` (count deleted), not list.
- `ctx.llm.chat(prompt)` returns `str`; use `chat_raw()` for `LLMResponse` with usage/tool_calls.
- `ctx.metadata.get_plugin_config()` raises `PermissionError` if accessing another plugin's config.

### Parameter injection
- `GreedyStr` must be the **last** parameter in the handler signature.
- Typed parameters (`str`, `int`, `float`, `bool`) are parsed positionally from command text.
- `@on_schedule` handlers have **no** `event` parameter.
- `@conversation_command` handlers receive `ConversationSession` via injection.

### Decorator stacking order
Place trigger decorator **first** (topmost), then guards below:
```python
@on_command("admin-cmd")   # trigger first
@require_admin             # then guard
@rate_limit(5, 60.0)      # then throttle
async def admin_cmd(self, event: MessageEvent, ctx: Context) -> None: ...
```

### Testing
- **NEVER** use `from main import MyPlugin` in tests — pollutes `sys.modules["main"]`.
- Use `PluginHarness.from_plugin_dir(plugin_dir)` exclusively.
- Ignore `__pycache__` / `*.pyc` when copying fixtures.
- `dispatch_text()` returns `list[RecordedSend]`; check `record.text` for reply content.

### Message components
- `Plain` serializes as `type: "text"`, not `"plain"`.
- Use `Image.fromURL(url)` or `Image.fromFileSystem(path)` factory methods; the constructor takes `file` param directly.
- `MessageBuilder` is fluent: `.text("hi").at("123").image("url").build()` → `MessageChain`.

## v3 → v4 Migration

- `astrbot.api.star.Star` → `astrbot_sdk.Star`
- Old filter decorators → `astrbot_sdk.decorators.*`
- `self.context` in handlers → injected `ctx` parameter
- Direct KV helpers → `ctx.db.*` or `PluginKVStoreMixin`

## References

Read only files needed for the task:

- `references/api-quick-ref.md` — complete decorator parameters, client methods with return types
- `references/plugin-patterns.md` — full working plugin examples by pattern
- `references/project-structure.md` — plugin.yaml schema, testing patterns, CLI commands
