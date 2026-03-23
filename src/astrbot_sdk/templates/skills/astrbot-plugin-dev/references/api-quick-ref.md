# API Quick Reference

## Trigger Decorators

### @on_command

```python
@on_command(command, *, aliases=None, description=None)
```

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| command | `str \| Sequence[str]` | required | First item is canonical name |
| aliases | `list[str] \| None` | None | Alternative names |
| description | `str \| None` | None | Help text |

**Handler signature:** `async def handler(self, event: MessageEvent, ctx: Context) -> None`

With typed params: `async def handler(self, event: MessageEvent, ctx: Context, name: str, text: GreedyStr) -> None`

- Parameters after `event`/`ctx` are parsed positionally from command text.
- `GreedyStr` must be the **last** parameter — captures all remaining text.
- Supported types: `str`, `int`, `float`, `bool`, `GreedyStr`.

### @on_message

```python
@on_message(*, regex=None, keywords=None, platforms=None, message_types=None, description=None)
```

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| regex | `str \| None` | None | Python `re` pattern |
| keywords | `list[str] \| None` | None | Any keyword match triggers |
| platforms | `list[str] \| None` | None | Platform filter |
| message_types | `list[str] \| None` | None | "group", "private" |
| description | `str \| None` | None | — |

Must provide at least `regex` or `keywords`.

**Handler signature:** `async def handler(self, event: MessageEvent, ctx: Context) -> None`

**PITFALL:** Do not combine `@on_message(platforms=...)` with a separate `@platforms()` decorator.

### @on_event

```python
@on_event(event_type, *, description=None)
```

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| event_type | `str` | required | e.g., "group_member_join", "astrbot_loaded" |
| description | `str \| None` | None | — |

**Handler signature:** `async def handler(self, event, ctx: Context) -> None`

Note: `event` may not be a `MessageEvent` — it can be a raw dict depending on event type.

### @on_schedule

```python
@on_schedule(*, cron=None, interval_seconds=None, description=None)
```

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| cron | `str \| None` | None | Cron expression (e.g., "0 8 * * *") |
| interval_seconds | `int \| None` | None | Seconds between invocations |
| description | `str \| None` | None | — |

Must provide exactly one of `cron` or `interval_seconds`.

**Handler signature:** `async def handler(self, ctx: Context) -> None`

Optional: `async def handler(self, ctx: Context, schedule: ScheduleContext) -> None`

**PITFALL:** No `event` parameter — you cannot call `event.reply()`. Use `ctx.platform.send()` for proactive messages.

### @conversation_command

```python
@conversation_command(command, *, aliases=None, description=None, timeout=60, mode="replace", busy_message=None, grace_period=1.0)
```

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| command | `str \| Sequence[str]` | required | Command name(s) |
| aliases | `list[str] \| None` | None | — |
| description | `str \| None` | None | — |
| timeout | `int` | 60 | Session timeout in seconds (must be positive) |
| mode | `"replace" \| "reject"` | "replace" | "replace" cancels old session; "reject" denies new |
| busy_message | `str \| None` | None | Reply when rejecting (mode="reject") |
| grace_period | `float` | 1.0 | Cleanup grace period in seconds (must be positive) |

**Handler signature:** `async def handler(self, event: MessageEvent, ctx: Context, session: ConversationSession) -> None`

`ConversationSession` key methods:
- `await session.ask(prompt, timeout=None)` → `MessageEvent` (waits for user reply)
- `await session.reply(text)` → `None` (sends without waiting)
- `await session.reply_chain(chain)` → `None`
- `session.end()` → `None` (marks session completed)

Raises `TimeoutError`, `CancelledError`, or `ConversationReplaced` on session loss.

### @provide_capability

```python
@provide_capability(name, *, description, input_schema=None, output_schema=None, input_model=None, output_model=None, supports_stream=False, cancelable=False)
```

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| name | `str` | required | e.g., "my_plugin.calculate" — no reserved prefixes |
| description | `str` | required | — |
| input_schema | `dict \| None` | None | JSON Schema (mutually exclusive with input_model) |
| output_schema | `dict \| None` | None | JSON Schema (mutually exclusive with output_model) |
| input_model | `type[BaseModel] \| None` | None | Pydantic model (mutually exclusive with input_schema) |
| output_model | `type[BaseModel] \| None` | None | Pydantic model (mutually exclusive with output_schema) |
| supports_stream | `bool` | False | — |
| cancelable | `bool` | False | — |

**Handler signature:** `async def handler(self, payload: dict, ctx: Context) -> dict`

Reserved name prefixes (cannot use): `"handler."`, `"system."`, `"internal."`

### @register_llm_tool

```python
@register_llm_tool(name=None, *, description=None, parameters_schema=None, active=True)
```

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| name | `str \| None` | None | Defaults to function name |
| description | `str \| None` | None | — |
| parameters_schema | `dict \| None` | None | JSON Schema; auto-generated from signature if omitted |
| active | `bool` | True | Whether tool is active by default |

**Handler signature:** `async def handler(self, **kwargs) -> Any`

Parameters in the function signature are used for auto-schema generation.

### @http_api

```python
@http_api(route, *, methods=None, description="", capability_name=None)
```

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| route | `str` | required | e.g., "/api/status" |
| methods | `list[str] \| None` | ["GET"] | HTTP methods |
| description | `str` | "" | — |
| capability_name | `str \| None` | None | Optional capability name override |

**Handler signature:** `async def handler(self, payload: dict, ctx: Context) -> dict`

### @background_task

```python
@background_task(*, description="", auto_start=True, on_error="log")
```

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| description | `str` | "" | — |
| auto_start | `bool` | True | Start when plugin starts |
| on_error | `"log" \| "restart"` | "log" | Error handling strategy |

**Handler signature:** `async def handler(self, ctx: Context) -> None`

Typically contains a `while True:` loop with `await asyncio.sleep(...)`.

### @validate_config

```python
@validate_config(*, model=None, schema=None)
```

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| model | `type[BaseModel] \| None` | None | Pydantic model (mutually exclusive with schema) |
| schema | `dict \| None` | None | JSON Schema (mutually exclusive with model) |

Must provide exactly one of `model` or `schema`.

### @on_provider_change

```python
@on_provider_change(*, provider_types=None)
```

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| provider_types | `list[str] \| tuple[str, ...] \| None` | None | e.g., ["llm", "embedding", "tts"] |

**Handler signature:** `async def handler(self, ctx: Context) -> None`

### @mcp_server

```python
@mcp_server(*, name, scope="global", config=None, timeout=30.0, wait_until_ready=True)
```

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| name | `str` | required | Non-empty |
| scope | `"local" \| "global"` | "global" | — |
| config | `dict \| None` | None | — |
| timeout | `float` | 30.0 | Must be positive |
| wait_until_ready | `bool` | True | — |

### @register_skill

```python
@register_skill(*, name, path, description="")
```

Class-level decorator. Can stack multiple.

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| name | `str` | required | Non-empty |
| path | `str` | required | Skill file path, non-empty |
| description | `str` | "" | — |

### @register_agent

```python
@register_agent(name, *, description="", tool_names=None)
```

Must decorate a `BaseAgentRunner` subclass.

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| name | `str` | required | — |
| description | `str` | "" | — |
| tool_names | `list[str] \| None` | None | Available tool names |

---

## Filter / Guard Decorators

### @require_admin / @admin_only

No arguments. Restricts to admin users.

```python
@on_command("admin-cmd")
@require_admin
async def handler(self, event: MessageEvent, ctx: Context) -> None: ...
```

### @platforms

```python
@platforms(*names: str)
```

Restrict to specific platforms (e.g., "qq", "wechat").

**PITFALL:** Cannot combine with `@on_message(platforms=...)`.

### @group_only() / @private_only()

Called with parentheses. Restrict to group or private messages.

**PITFALL:** Cannot combine `@group_only()` with `@private_only()`.

### @message_types

```python
@message_types(*types: str)
```

e.g., `@message_types("group", "private")`

**PITFALL:** Cannot combine with `@group_only()` / `@private_only()`.

### @rate_limit

```python
@rate_limit(limit, window, *, scope="session", behavior="hint", message=None)
```

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| limit | `int` | required | Max invocations per window (positive) |
| window | `float` | required | Seconds (positive) |
| scope | `"session" \| "user" \| "group" \| "global"` | "session" | Limiter scope |
| behavior | `"hint" \| "silent" \| "error"` | "hint" | hint=reply, silent=drop, error=raise |
| message | `str \| None` | None | Custom message for "hint" |

### @cooldown

```python
@cooldown(seconds, *, scope="session", behavior="hint", message=None)
```

Shorthand for `@rate_limit(1, seconds, ...)`.

### @priority

```python
@priority(value: int)
```

Higher value = executed first.

### @custom_filter

```python
@custom_filter(CustomFilter(callable))
```

`callable` must be a sync function: `(event: MessageEvent) -> bool`.

Composition: `all_of(*filters)`, `any_of(*filters)`.

---

## Client APIs

### ctx.db — KV Store (DBClient)

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| get | `(key: str)` | `Any \| None` | None if key missing |
| set | `(key: str, value: Any)` | `None` | value must be JSON-serializable |
| delete | `(key: str)` | `None` | **Always None** — does not return bool |
| list | `(prefix: str \| None = None)` | `list[str]` | Key names only; empty list if no matches |
| get_many | `(keys: Sequence[str])` | `dict[str, Any \| None]` | Missing keys → None |
| set_many | `(items: Mapping \| Sequence[tuple])` | `None` | Accepts dict or list of tuples |
| watch | `(prefix: str \| None = None)` | `AsyncIterator[dict]` | Yields `{"op": "set"\|"delete", "key": str, "value": Any\|None}` |

### ctx.llm — AI Chat (LLMClient)

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| chat | `(prompt, *, system=None, history=None, contexts=None, provider_id=None, model=None, temperature=None, **kw)` | `str` | Text only |
| chat_raw | same as chat | `LLMResponse` | Has `.text`, `.usage`, `.finish_reason`, `.tool_calls` |
| stream_chat | same as chat | `AsyncGenerator[str]` | Yields text chunks |

`history`: `Sequence[ChatMessage \| dict]` — chat history for context.
`contexts`: takes precedence over `history` if both provided.

### ctx.memory — Semantic Storage (MemoryClient)

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| save | `(key, value=None, namespace=None, **extra)` | `None` | **value must be dict** (TypeError otherwise) |
| get | `(key, *, namespace=None)` | `dict \| None` | — |
| delete | `(key, *, namespace=None)` | `None` | — |
| search | `(query, *, mode="auto", limit=None, min_score=None, provider_id=None, namespace=None, include_descendants=True)` | `list[dict]` | Items have key, score, match_type |
| save_with_ttl | `(key, value, ttl_seconds, *, namespace=None)` | `None` | value must be dict; ttl_seconds >= 1 |
| get_many | `(keys, *, namespace=None)` | `list[dict]` | — |
| delete_many | `(keys, *, namespace=None)` | `int` | Count of deleted items |
| stats | `(*, namespace=None, include_descendants=True)` | `dict` | — |
| namespace | `(*parts)` | `MemoryClient` | **Not async**; returns derived client in child namespace |

### ctx.platform — Messaging (PlatformClient)

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| send | `(session, text)` | `dict` | session: str / SessionRef / MessageSession |
| send_image | `(session, image_url)` | `dict` | — |
| send_chain | `(session, chain)` | `dict` | chain: MessageChain / list[component] / list[dict] |
| send_by_session | `(session, content)` | `dict` | content: str / MessageChain / list |
| send_by_id | `(platform_id, session_id, content, *, message_type="private")` | `dict` | — |
| get_members | `(session)` | `list[dict]` | Items may have user_id, nickname, role |

### ctx.metadata — Plugin Metadata (MetadataClient)

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| get_plugin_config | `(name=None)` | `dict \| None` | **PermissionError** if accessing another plugin; None = current |
| save_plugin_config | `(config: dict)` | `dict` | TypeError if not dict |
| get_plugin | `(name: str)` | `StarMetadata \| None` | — |
| list_plugins | `()` | `list[StarMetadata]` | — |
| get_current_plugin | `()` | `StarMetadata \| None` | Current plugin's metadata |

### ctx.files — File Service (FileServiceClient)

File token registration and management.

### ctx.http — HTTP (HTTPClient)

HTTP API registration and listing.

### ctx.mcp — MCP Manager (MCPManagerClient)

MCP server lifecycle management.

### ctx.providers — Provider Query (ProviderClient)

Provider metadata queries and specialized provider proxy.

### ctx.message_history — Message History (MessageHistoryManagerClient)

Message history queries with pagination.

---

## Core Types

### MessageEvent

| Property | Type | Notes |
|----------|------|-------|
| text | `str` | Message content |
| user_id | `str` | Sender ID |
| group_id | `str \| None` | None for private |
| platform | `str` | e.g., "qq", "wechat" |
| platform_id | `str` | Platform instance ID |
| self_id | `str` | Bot's own ID |
| session_id | `str` | For reply routing |
| message_type | `str` | "group" / "private" |
| sender_name | `str` | Display name |
| is_admin | `bool` | — |
| raw | `dict` | Raw message data |

| Method | Returns | Notes |
|--------|---------|-------|
| `await reply(text)` | `dict` | Plain text reply |
| `await reply_image(url)` | `dict` | Image reply |
| `await reply_chain(chain)` | `dict` | Rich message reply |
| `stop_event()` | `None` | Prevent further handler processing |

### MessageBuilder (fluent API)

```python
chain = (
    MessageBuilder()
    .text("Hello ")
    .at("12345")
    .text(" check this: ")
    .image("https://example.com/img.png")
    .build()
)
await event.reply_chain(chain.components)
```

Methods: `.text(str)`, `.at(user_id)`, `.at_all()`, `.image(url)`, `.record(url)`, `.video(url)`, `.file(name, *, file="", url="")`, `.reply(**kw)`, `.append(component)`, `.extend(components)`, `.build()` → `MessageChain`

### Message Components

| Class | Constructor | Serialized type |
|-------|-----------|----------------|
| `Plain(text)` | `Plain("hello")` | `"text"` (not "plain") |
| `Image(file)` | `Image.fromURL(url)` / `Image.fromFileSystem(path)` / `Image.fromBase64(data)` | `"image"` |
| `At(qq)` | `At(qq="12345")` | `"at"` |
| `AtAll()` | `AtAll()` | `"at"` with qq="all" |
| `Record(file)` | `Record.fromURL(url)` / `Record.fromFileSystem(path)` | `"record"` |
| `Video(file)` | `Video.fromURL(url)` / `Video.fromFileSystem(path)` | `"video"` |
| `File(name, file, url)` | `File("doc.pdf", url="https://...")` | `"file"` |
| `Reply(**kw)` | `Reply(id="msg_id")` | `"reply"` |
| `Forward(id)` | `Forward(id="msg_id")` | `"forward"` |
| `Poke(poke_type)` | `Poke()` | `"poke"` |

### Other Key Types

- **GreedyStr**: Annotate the last command parameter to capture all remaining text.
- **ScheduleContext**: Injected into `@on_schedule` handlers. Has `schedule_id`, `plugin_id`, `handler_id`, `trigger_kind` ("cron"/"interval"/"once"), `cron`, `interval_seconds`.
- **ConversationSession**: Injected into `@conversation_command` handlers. Key methods: `ask()`, `reply()`, `reply_chain()`, `send_message()`, `end()`. States: ACTIVE, REJECTED_BUSY, REPLACED, TIMEOUT, COMPLETED, CANCELLED.
- **ChatMessage(role, content)**: For LLM history.
- **LLMResponse**: Has `.text`, `.usage`, `.finish_reason`, `.tool_calls`, `.role`, `.reasoning_content`.
- **CommandGroup**: For hierarchical command trees. Create with `command_group(name)`, add subgroups with `.group()`, add commands with `.command()`.

---

## Source basis

Derived from:
- `src/astrbot_sdk/decorators.py`
- `src/astrbot_sdk/clients/*.py`
- `src/astrbot_sdk/events.py`
- `src/astrbot_sdk/message/components.py`
- `src/astrbot_sdk/message/result.py`
- `src/astrbot_sdk/conversation.py`
- `src/astrbot_sdk/context.py`
