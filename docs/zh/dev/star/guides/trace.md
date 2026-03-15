---
outline: deep
---

# 链路追踪（Trace）

AstrBot 内置了一套**请求级链路追踪**系统，可以记录每条消息从接收到回复的完整处理过程，包括管道各阶段耗时、LLM 调用参数与 token 用量、工具调用入参与结果、插件处理过程等。

追踪数据可在 **管理面板 → Trace** 页面实时查看，也会持久化到 SQLite 数据库。

插件开发者可以通过 `astrbot.api.trace` 提供的 API，将自己插件内部的关键操作标记为 Span，让它们出现在 Trace 树中，方便排查问题和分析性能。

---

## 启用 Trace

在管理面板的 **Trace** 页面顶部开关打开即可，或在配置文件中设置：

```yaml
trace_enable: true
```

> [!NOTE]
> Trace 默认关闭。开启后所有消息处理流程都会产生 Span，会有轻微的额外内存分配（每个 Span 约 5 μs），但对整体性能几乎没有影响。

---

## 核心概念

### Trace 与 Span

- **Trace**：代表一次完整的消息处理周期（从收到消息到完成回复）。每个 Trace 有唯一的 `trace_id`。
- **Span**：Trace 中的一个执行节点，形成树形结构。每个 Span 记录名称、类型、耗时、状态、输入/输出/元数据。

### Span 类型

| `span_type` | 含义 |
|-------------|------|
| `root` | 根节点，对应一次消息处理 |
| `pipeline_stage` | 管道阶段（WakingCheck、Process 等） |
| `llm_agent` | 一次 LLM Agent 调用 |
| `llm_call` | Agent 内的单步 LLM 调用 |
| `tool_call` | 工具调用 |
| `plugin_handler` | 插件 handler 调用 |
| `span`（默认） | 通用节点，插件自定义使用 |

### Span 数据字段

| 字段 | 说明 |
|------|------|
| `name` | Span 名称 |
| `span_type` | Span 类型 |
| `status` | `running` / `ok` / `error` |
| `started_at` / `finished_at` | Unix 时间戳 |
| `duration_ms` | 耗时（毫秒） |
| `input` | 输入数据（dict） |
| `output` | 输出数据（dict） |
| `meta` | 元数据（dict，如 token 数量、模型名等） |

---

## 在插件中使用 Trace

### 导入

```python
from astrbot.api.trace import span_record, span_context, get_current_span
```

或通过 `astrbot.api.all` 统一导入：

```python
from astrbot.api import *  # 包含 span_record, span_context, get_current_span
```

---

### 方式一：`@span_record` 装饰器（推荐）

适合标记**整个函数**的执行过程。支持 `async def` 和普通 `def`。

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
        # 实际的 HTTP 请求或数据处理逻辑
        return f"{city} 今天晴天，25°C"
```

生成的 Span 树：

```
request (root)
  └─ plugin_handler                    ← 框架自动创建
       └─ plugin.weather (plugin_call) ← @span_record 创建
            └─ weather.fetch (io_call) ← @span_record 创建，含入参和返回值
```

#### 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | `str \| None` | 函数的 `__qualname__` | Span 名称，不填则自动使用函数全限定名 |
| `span_type` | `str` | `"span"` | Span 类型标签 |
| `record_input` | `bool` | `False` | 是否将函数参数记录到 `input`（会跳过 `self`、`cls`、`event`） |
| `record_output` | `bool` | `False` | 是否将函数返回值记录到 `output`（截断至 2000 字符） |

> [!WARNING]
> `record_input=True` 会将函数参数序列化为字符串存入 Trace，注意不要泄露敏感信息（密钥、token 等）。

---

### 方式二：`span_context` 上下文管理器

适合标记**代码块**而非整个函数，或需要在过程中**手动设置输入/输出**的场景。

```python
from astrbot.api.trace import span_context


@command("search")
async def search(self, event: AstrMessageEvent, query: str):
    async with span_context("web_search", span_type="io_call") as s:
        s.set_input(query=query, engine="tavily")

        results = await self._do_search(query)

        s.set_output(count=len(results), first=results[0] if results else "")

    yield event.plain_result(f"找到 {len(results)} 条结果")
```

`span_context` 支持嵌套：

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

#### `span_context` 参数说明

| 参数 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | Span 名称（必填） |
| `span_type` | `str` | Span 类型，默认 `"span"` |
| `parent` | `TraceSpan \| None` | 显式指定父 Span，默认自动从当前上下文继承 |
| `**meta` | `Any` | 直接写入 `span.meta` 的键值对 |

---

### 方式三：`get_current_span()` 手动操作

适合需要在函数**任意位置**追加数据到当前 Span 的场景，或需要将 Span 对象传递给深层工具函数时。

```python
from astrbot.api.trace import get_current_span


async def some_deep_function(data: list):
    span = get_current_span()
    if span:
        span.set_meta(item_count=len(data))

    # ... 业务逻辑 ...
```

> [!NOTE]
> `get_current_span()` 返回的是当前协程上下文中最近被设置的 Span（可能是 `plugin_handler`、`llm_agent` 或根 Span）。如果 Trace 未启用或当前没有活跃 Span，返回 `None`。

---

### Span 的 input / output / meta 方法

| 方法 | 说明 |
|------|------|
| `span.set_input(**kwargs)` | 更新 input 字典 |
| `span.set_output(**kwargs)` | 更新 output 字典 |
| `span.set_meta(**kwargs)` | 更新 meta 字典 |
| `span.finish(status="ok")` | 手动结束 Span（通常不需要，上下文管理器/装饰器会自动调用） |

---

### Trace 禁用时的行为

当 `trace_enable = false` 时：

- `@span_record` 装饰的函数被**直接调用**，无任何额外对象创建或 ContextVar 操作，开销约 200 ns（一次配置项读取）。
- `span_context` 会 yield 一个 `_NullSpan` 对象，其所有方法为空操作，代码中的 `s.set_input(...)` 等调用不会报错，也不会有任何副作用。
- `get_current_span()` 返回 `None`。

因此，插件代码**无需**在调用 trace API 前判断 Trace 是否启用，框架已经处理了这一逻辑。

---

## 完整示例：带多层追踪的插件

```python
from astrbot.api.star import Star, Context, register
from astrbot.api.event.filter import command
from astrbot.api.trace import span_record, span_context
from astrbot.core.platform.astr_message_event import AstrMessageEvent
import httpx


@register("weather_plugin", "天气查询插件", "1.0.0", "作者名")
class WeatherPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.api_key = "your_api_key"

    @command("weather")
    @span_record("weather.handler", span_type="plugin_call", record_input=True)
    async def handle_weather(self, event: AstrMessageEvent, city: str = "北京"):
        """查询天气"""
        async with span_context("weather.api_call", span_type="io_call") as s:
            s.set_input(city=city, api_key_prefix=self.api_key[:4] + "***")
            try:
                data = await self._call_weather_api(city)
                s.set_output(temperature=data["temp"], condition=data["condition"])
            except Exception as e:
                # span_context 会自动将异常记录为 error 状态
                raise

        result = f"🌤 {city}：{data['condition']}，{data['temp']}°C"
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

## 在 Trace 页面查看

1. 打开管理面板，进入 **Trace** 页面。
2. 左侧面板显示最近的 Trace 列表，支持按消息内容或会话来源搜索。
3. 点击任意一条 Trace，右侧展示完整的 **Span 树**。
4. 点击树中的任意 Span 节点，查看该节点的 **Input / Output / Metadata** 详情。
5. 每个详情面板右上角有复制按钮，可复制完整 JSON。

---

## 设计说明

### ContextVar 隐式传播

Trace 系统通过 Python 标准库的 `contextvars.ContextVar` 传播当前活跃 Span，而不是显式地将 Span 对象传递给每一个函数。

```
execute(event)
  │  ← _current_span.set(event.trace)          根 Span 注入上下文
  │
  ├── StarRequestSubStage
  │     ← _current_span.set(plugin_handler_span) 插件 Span 注入上下文
  │
  │     └── 插件 handler 函数
  │           span_context / span_record         自动 get() 到 plugin_handler_span
  │           并以其为父节点创建子 Span
```

这意味着插件中的 `span_context(...)` 调用**不需要知道父 Span 是谁**，框架会自动在正确的位置挂载子节点。

### 容错隔离

Trace 基础设施的任何错误（SSE 广播失败、JSON 序列化异常、数据库写入失败等）**都不会影响原函数的正常执行**：

- `_on_root_finish()`（负责广播和持久化）整体包裹在 `try/except` 中，异常仅记录 debug 日志。
- `span_context` 和 `trace_span` 的 `finish()` 调用同样有异常保护，原始业务异常始终被正确传播。
- `span_record` 装饰器的 sync/async 两个包装器中，trace 相关操作的异常均被静默处理。

### 性能开销

| 场景 | 额外开销 |
|------|---------|
| Trace 关闭（默认） | ~200 ns（一次配置读取） |
| Trace 开启，子 Span 创建 | ~3–5 μs（uuid4 生成为主要耗时） |
| 请求结束时序列化和广播 | ~50–200 μs（一次性，不阻塞） |

对于典型 LLM 请求（500 ms–5 s），Trace 总开销占比 < 0.05%。
