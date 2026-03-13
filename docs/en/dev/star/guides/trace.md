---
outline: deep
---

# Request Tracing

AstrBot includes a built-in **per-request tracing system** that records the complete processing lifecycle of every message — from receipt to reply — covering pipeline stage timings, LLM call parameters and token usage, tool call arguments and results, and plugin handler invocations.

Trace data is visible in real-time on the **Dashboard → Trace** page and is also persisted to SQLite.

Plugin developers can use the `astrbot.api.trace` API to mark key operations inside their plugins as Spans, making them appear in the Trace tree for debugging and performance analysis.

---

## Enabling Tracing

Toggle the switch at the top of the **Trace** page in the dashboard, or set it in the config file:

```yaml
trace_enable: true
```

> [!NOTE]
> Tracing is **off by default**. When enabled, every message processing cycle produces Spans with a slight overhead (~5 μs per Span for memory allocation), but the overall performance impact is negligible.

---

## Core Concepts

### Trace and Span

- **Trace**: Represents one complete message processing cycle (from receiving a message to completing the reply). Each Trace has a unique `trace_id`.
- **Span**: A single execution node within a Trace, organized as a tree. Each Span records its name, type, duration, status, and input/output/metadata.

### Span Types

| `span_type` | Meaning |
|-------------|---------|
| `root` | Root node, corresponds to one message processing cycle |
| `pipeline_stage` | A pipeline stage (WakingCheck, Process, etc.) |
| `llm_agent` | One LLM Agent invocation |
| `llm_call` | A single LLM call step inside an Agent |
| `tool_call` | A tool call |
| `plugin_handler` | A plugin handler invocation |
| `span` (default) | Generic node, for custom plugin use |

### Span Fields

| Field | Description |
|-------|-------------|
| `name` | Span name |
| `span_type` | Span type |
| `status` | `running` / `ok` / `error` |
| `started_at` / `finished_at` | Unix timestamps |
| `duration_ms` | Duration in milliseconds |
| `input` | Input data (dict) |
| `output` | Output data (dict) |
| `meta` | Metadata (dict, e.g. token counts, model name) |

---

## Using Tracing in Plugins

### Import

```python
from astrbot.api.trace import span_record, span_context, get_current_span
```

Or via the unified `astrbot.api.all` import:

```python
from astrbot.api import *  # includes span_record, span_context, get_current_span
```

---

### Method 1: `@span_record` Decorator (Recommended)

Best for tracking the execution of an **entire function**. Works with both `async def` and regular `def`.

```python
from astrbot.api.star import Star, Context
from astrbot.api.event.filter import command
from astrbot.api.trace import span_record
from astrbot.core.platform.astr_message_event import AstrMessageEvent


@register("my_plugin")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @command("weather")
    @span_record("plugin.weather", span_type="plugin_call")
    async def get_weather(self, event: AstrMessageEvent, city: str):
        result = await self._fetch_weather(city)
        yield event.plain_result(result)

    @span_record("weather.fetch", span_type="io_call", record_input=True, record_output=True)
    async def _fetch_weather(self, city: str) -> str:
        # Actual HTTP request or data processing logic
        return f"{city}: Sunny, 25°C"
```

Resulting Span tree:

```
request (root)
  └─ plugin_handler                    ← created automatically by the framework
       └─ plugin.weather (plugin_call) ← created by @span_record
            └─ weather.fetch (io_call) ← created by @span_record, with args and return value
```

#### Parameter Reference

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str \| None` | function `__qualname__` | Span name. Defaults to the fully-qualified function name. |
| `span_type` | `str` | `"span"` | Span type label |
| `record_input` | `bool` | `False` | Whether to record function arguments into `input` (skips `self`, `cls`, `event`) |
| `record_output` | `bool` | `False` | Whether to record the return value into `output` (truncated to 2000 characters) |

> [!WARNING]
> `record_input=True` serializes function arguments as strings into the Trace. Be careful not to expose sensitive data (API keys, tokens, passwords, etc.).

---

### Method 2: `span_context` Context Manager

Best for tracking a **block of code** rather than a whole function, or when you need to **manually set input/output** at specific points.

```python
from astrbot.api.trace import span_context


@command("search")
async def search(self, event: AstrMessageEvent, query: str):
    async with span_context("web_search", span_type="io_call") as s:
        s.set_input(query=query, engine="tavily")

        results = await self._do_search(query)

        s.set_output(count=len(results), first=results[0] if results else "")

    yield event.plain_result(f"Found {len(results)} results")
```

`span_context` supports nesting:

```python
async with span_context("process_file", span_type="io_call") as outer:
    outer.set_input(filename=filename)

    async with span_context("parse_content") as inner:
        content = parse(raw_data)
        inner.set_output(size=len(content))

    async with span_context("upload_result") as inner:
        url = await upload(content)
        inner.set_output(url=url)

    outer.set_output(url=url)
```

#### `span_context` Parameter Reference

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Span name (required) |
| `span_type` | `str` | Span type, defaults to `"span"` |
| `parent` | `TraceSpan \| None` | Explicitly specify a parent Span. Defaults to the current context span. |
| `**meta` | `Any` | Key-value pairs written directly to `span.meta` |

---

### Method 3: `get_current_span()` for Manual Access

Best when you need to append data to the current Span from **anywhere in the call stack**, or when you need to pass the Span object to a deep utility function.

```python
from astrbot.api.trace import get_current_span


async def some_deep_function(data: list):
    span = get_current_span()
    if span:
        span.set_meta(item_count=len(data))

    # ... business logic ...
```

> [!NOTE]
> `get_current_span()` returns the most recently activated Span in the current coroutine context (which may be `plugin_handler`, `llm_agent`, or the root Span). Returns `None` if tracing is disabled or no Span is active.

---

### Span Data Methods

| Method | Description |
|--------|-------------|
| `span.set_input(**kwargs)` | Update the input dict |
| `span.set_output(**kwargs)` | Update the output dict |
| `span.set_meta(**kwargs)` | Update the meta dict |
| `span.finish(status="ok")` | Manually finish the Span (usually not needed — the context manager / decorator handles this automatically) |

---

### Behavior When Tracing is Disabled

When `trace_enable = false`:

- Functions decorated with `@span_record` are **called directly** with no extra object creation or ContextVar operations. Overhead is approximately 200 ns (one config dict lookup).
- `span_context` yields a `_NullSpan` object whose methods are all no-ops. Calls like `s.set_input(...)` succeed silently without side effects.
- `get_current_span()` returns `None`.

Therefore, plugin code **does not need to check** whether tracing is enabled before calling the trace API — the framework handles this transparently.

---

## Full Example: Plugin with Multi-Level Tracing

```python
from astrbot.api.star import Star, Context, register
from astrbot.api.event.filter import command
from astrbot.api.trace import span_record, span_context
from astrbot.core.platform.astr_message_event import AstrMessageEvent
import httpx


@register("weather_plugin", "Weather Query Plugin", "1.0.0", "author")
class WeatherPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.api_key = "your_api_key"

    @command("weather")
    @span_record("weather.handler", span_type="plugin_call", record_input=True)
    async def handle_weather(self, event: AstrMessageEvent, city: str = "London"):
        """Query weather for a city."""
        async with span_context("weather.api_call", span_type="io_call") as s:
            s.set_input(city=city, api_key_prefix=self.api_key[:4] + "***")
            try:
                data = await self._call_weather_api(city)
                s.set_output(temperature=data["temp"], condition=data["condition"])
            except Exception:
                # span_context automatically marks the span as error on exception
                raise

        result = f"🌤 {city}: {data['condition']}, {data['temp']}°C"
        yield event.plain_result(result)

    async def _call_weather_api(self, city: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.example.com/weather",
                params={"city": city, "key": self.api_key},
            )
            resp.raise_for_status()
            return resp.json()
```

---

## Viewing Traces in the Dashboard

1. Open the dashboard and navigate to the **Trace** page.
2. The left panel lists recent Traces with search support by message content or session origin.
3. Click any Trace to display the full **Span tree** on the right.
4. Click any node in the tree to view the **Input / Output / Metadata** details for that Span.
5. A copy button at the top-right of each detail panel copies the full JSON to the clipboard.

---

## Design Notes

### Implicit Span Propagation via ContextVar

The trace system propagates the active Span using Python's standard `contextvars.ContextVar` rather than passing Span objects explicitly through every function call.

```
execute(event)
  │  ← _current_span.set(event.trace)            root Span injected into context
  │
  ├── StarRequestSubStage
  │     ← _current_span.set(plugin_handler_span)  plugin Span injected into context
  │
  │     └── plugin handler function
  │           span_context / span_record           automatically get() plugin_handler_span
  │           and create child Spans under it
```

This means `span_context(...)` calls inside a plugin **do not need to know who the parent Span is** — the framework attaches the child node at the correct position automatically.

### Fault Isolation

Any error in the trace infrastructure (SSE broadcast failure, JSON serialization error, database write failure, etc.) **will not affect the normal execution of the original function**:

- `_on_root_finish()` (responsible for broadcasting and persistence) is wrapped entirely in `try/except`. Exceptions are recorded at debug level only.
- `finish()` calls inside `span_context` and `trace_span` are also exception-safe; the original business exception is always propagated correctly.
- Both the sync and async wrappers in `span_record` silently suppress any trace-related exceptions.

### Performance Overhead

| Scenario | Additional Overhead |
|----------|---------------------|
| Tracing disabled (default) | ~200 ns (one config dict lookup) |
| Tracing enabled, child Span creation | ~3–5 μs (dominated by `uuid4` generation) |
| Serialization and broadcast at request end | ~50–200 μs (one-time, non-blocking) |

For a typical LLM request (500 ms–5 s), total trace overhead is < 0.05% of total processing time.
