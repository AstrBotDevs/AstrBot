# Star 类 - 插件基类完整参考

## 概述

`Star` 是 AstrBot SDK 的插件基类，所有 v4 原生插件都必须继承此类。它提供了完整的插件生命周期管理、上下文访问和能力集成。

**模块路径**: `astrbot_sdk.star.Star`

---

## 类定义

```python
class Star(PluginKVStoreMixin):
    """v4 原生插件基类"""

    __handlers__: tuple[str, ...]  # 自动收集的处理器列表

    # 生命周期钩子
    async def on_start(self, ctx: Any | None = None) -> None
    async def on_stop(self, ctx: Any | None = None) -> None
    async def initialize(self) -> None
    async def terminate(self) -> None
    async def on_error(self, error: Exception, event, ctx) -> None

    # 便捷属性
    @property
    def context(self) -> Context | None

    # 便捷方法
    async def text_to_image(self, text: str, *, return_url: bool = True) -> str
    async def html_render(self, tmpl: str, data: dict, *, return_url: bool = True) -> str

    # KV 存储方法（继承自 PluginKVStoreMixin）
    async def put_kv_data(self, key: str, value: Any) -> None
    async def get_kv_data(self, key: str, default: _VT) -> _VT
    async def delete_kv_data(self, key: str) -> None
```

---

## 导入方式

```python
# 从主模块导入（推荐）
from astrbot_sdk import Star

# 从子模块导入
from astrbot_sdk.star import Star

# 常用配套导入
from astrbot_sdk import Context, MessageEvent  # 上下文和事件
from astrbot_sdk.decorators import on_command, on_message  # 装饰器
from astrbot_sdk.errors import AstrBotError  # 错误处理
```

---

## 核心属性

### `__handlers__`

自动收集的事件处理器元组。

```python
class MyPlugin(Star):
    @on_command("cmd1")
    async def cmd1_handler(self, event, ctx):
        pass

# MyPlugin.__handlers__ == ("cmd1_handler",)
```

**说明**: 在子类创建时，`__init_subclass__()` 会自动扫描所有装饰了 `@on_command`、`@on_message` 等装饰器的方法，并将处理器名称收集到此元组中。

### `context`

获取当前运行时上下文的属性。

```python
class MyPlugin(Star):
    async def some_method(self):
        ctx = self.context
        if ctx:
            await ctx.db.set("key", "value")
```

**返回**: `Context | None` - 仅在生命周期钩子和 Handler 执行期间可用

**注意**: 不要存储此引用，它在插件停止后会被清除

---

## 生命周期钩子

### 1. `on_start(ctx)` - 插件启动钩子

**签名**:
```python
async def on_start(self, ctx: Any | None = None) -> None
```

**参数**:
- `ctx`: 运行时上下文（通常为 `Context` 实例）

**触发时机**: Worker 启动后，在开始处理事件之前调用

**用途**:
- 初始化数据库连接
- 加载配置文件
- 注册 LLM 工具
- 启动后台任务
- 验证外部依赖

**示例**:

```python
class MyPlugin(Star):
    async def on_start(self, ctx) -> None:
        # 确保 initialize 被调用
        await super().on_start(ctx)

        # 获取插件数据目录
        data_dir = await ctx.get_data_dir()

        # 加载配置
        config = await ctx.metadata.get_plugin_config()
        self.api_key = config.get("api_key", "")

        # 注册 LLM 工具
        await ctx.register_llm_tool(
            name="search",
            parameters_schema={...},
            desc="搜索信息",
            func_obj=self.search_tool
        )

        # 启动后台任务
        await ctx.register_task(
            self.background_sync(),
            desc="后台数据同步"
        )

        ctx.logger.info(f"{ctx.plugin_id} 启动成功")
```

**注意事项**:
1. 始终调用 `await super().on_start(ctx)` 确保 `initialize()` 被调用
2. 在此方法中抛出的异常会导致插件加载失败
3. 此方法中 `ctx` 参数保证不为 `None`

---

### 2. `on_stop(ctx)` - 插件停止钩子

**签名**:
```python
async def on_stop(self, ctx: Any | None = None) -> None
```

**参数**:
- `ctx`: 运行时上下文

**触发时机**: 插件卸载或程序关闭前调用

**用途**:
- 关闭数据库连接
- 清理临时文件
- 注销 LLM 工具
- 保存状态数据

**示例**:

```python
class MyPlugin(Star):
    async def on_stop(self, ctx) -> None:
        # 保存状态
        await self.put_kv_data("last_shutdown", time.time())

        # 注销工具
        if hasattr(self, '_tool_name'):
            await ctx.unregister_llm_tool(self._tool_name)

        # 确保 terminate 被调用
        await super().on_stop(ctx)

        ctx.logger.info(f"{ctx.plugin_id} 已停止")
```

**注意事项**:
1. 始终调用 `await super().on_stop(ctx)` 确保 `terminate()` 被调用
2. 此方法中的异常会被捕获并记录，不会阻止插件关闭
3. 此时可能没有活跃的事件处理，避免发送消息

---

### 3. `initialize()` - 初始化钩子

**签名**:
```python
async def initialize(self) -> None
```

**触发时机**: `on_start()` 内部自动调用

**用途**:
- 插件级别的初始化逻辑
- 不依赖 Context 的初始化

**示例**:

```python
class MyPlugin(Star):
    async def initialize(self) -> None:
        """初始化插件"""
        self._cache = {}
        self._counter = 0
        self.state = "ready"
```

**与 `on_start` 的区别**:
- `initialize()` 无 `Context` 参数，用于不依赖外部资源的初始化
- `on_start(ctx)` 有 `Context` 参数，用于需要访问 Core 的初始化

**调用顺序**:
```
插件实例化
    ↓
initialize()      ← 先调用（无 Context）
    ↓
on_start(ctx)     ← 后调用（有 Context）
```

---

### 4. `terminate()` - 终止钩子

**签名**:
```python
async def terminate(self) -> None
```

**触发时机**: `on_stop()` 内部自动调用

**用途**:
- 插件级别的清理逻辑
- 不依赖 Context 的清理

**示例**:

```python
class MyPlugin(Star):
    async def terminate(self) -> None:
        """清理插件资源"""
        self._cache.clear()
        self.state = "stopped"
```

**与 `on_stop` 的区别**:
- `terminate()` 无 `Context` 参数，用于清理插件内部资源
- `on_stop(ctx)` 有 `Context` 参数，用于清理需要与 Core 交互的资源

**调用顺序**:
```
on_stop(ctx)      ← 先调用（有 Context）
    ↓
terminate()       ← 后调用（无 Context）
    ↓
插件卸载
```

---

### 5. `on_error(error, event, ctx)` - 错误处理钩子

**签名**:
```python
    async def on_error(self, error: Exception, event, ctx) -> None

    # 类方法
    @classmethod
    def __astrbot_is_new_star__(cls) -> bool
```

**参数**:
- `error`: 捕获的异常
- `event`: 事件对象（可能是 `MessageEvent` 或其他类型）
- `ctx`: 上下文对象

**触发时机**: 任何 Handler 执行抛出异常时

**默认行为**:
- `AstrBotError`：根据错误类型发送友好提示
- 其他异常：发送通用错误消息
- 记录错误日志

**示例**:

```python
from astrbot_sdk.errors import AstrBotError

class MyPlugin(Star):
    async def on_error(self, error: Exception, event, ctx) -> None:
        """自定义错误处理"""

        # SDK 标准错误
        if isinstance(error, AstrBotError):
            lines = []
            if error.retryable:
                lines.append("请求失败，请稍后重试")
            elif error.hint:
                lines.append(error.hint)
            else:
                lines.append(error.message)

            if error.docs_url:
                lines.append(f"文档：{error.docs_url}")

            await event.reply("\n".join(lines))

        # 业务逻辑错误
        elif isinstance(error, ValueError):
            await event.reply(f"参数错误：{error}")

        # 网络错误
        elif isinstance(error, ConnectionError):
            await event.reply("网络连接失败，请检查网络设置")

        # 未知错误
        else:
            await event.reply(f"出错了：{type(error).__name__}")

        # 记录详细错误
        ctx.logger.error(f"Handler failed: {error}", exc_info=error)
```

**覆盖建议**:
1. 始终记录错误日志
2. 向用户提供友好的错误提示
3. 调用 `await super().on_error(...)` 作为后备

---

## 类方法

### `__astrbot_is_new_star__()`

标识类为 v4 原生插件。

**签名**:
```python
@classmethod
def __astrbot_is_new_star__(cls) -> bool
```

**返回**: `bool` - 始终返回 `True`

**说明**: 此方法用于运行时识别插件类型，v4 原生插件返回 `True`，旧版插件无此方法。

---

## 便捷方法

### `text_to_image()`

将文本渲染为图片。

**签名**:
```python
async def text_to_image(
    self,
    text: str,
    *,
    return_url: bool = True
) -> str
```

**参数**:
- `text`: 要渲染的文本
- `return_url`: 是否返回 URL（False 则返回本地路径）

**返回**: 图片 URL 或路径

**示例**:

```python
class MyPlugin(Star):
    @on_command("text_img")
    async def text_to_image_cmd(self, event: MessageEvent):
        url = await self.text_to_image("Hello World")
        await event.reply_image(url)
```

**等价于**:
```python
url = await ctx.text_to_image("Hello World")
```

---

### `html_render()`

渲染 HTML 模板。

**签名**:
```python
async def html_render(
    self,
    tmpl: str,
    data: dict,
    *,
    return_url: bool = True,
    options: dict[str, Any] | None = None
) -> str
```

**参数**:
- `tmpl`: HTML 模板内容
- `data`: 模板数据
- `return_url`: 是否返回 URL
- `options`: 渲染选项

**返回**: 渲染结果 URL 或路径

**示例**:

```python
class MyPlugin(Star):
    @on_command("card")
    async def card_cmd(self, event: MessageEvent):
        url = await self.html_render(
            tmpl="<h1>{{ title }}</h1><p>{{ content }}</p>",
            data={"title": "标题", "content": "内容"}
        )
        await event.reply_image(url)
```

**等价于**:
```python
url = await ctx.html_render(tmpl, data)
```

---

## KV 存储方法

这些方法继承自 `PluginKVStoreMixin`，提供简单的键值存储能力。

### `put_kv_data()`

存储数据。

**签名**:
```python
async def put_kv_data(self, key: str, value: Any) -> None
```

**示例**:

```python
await self.put_kv_data("last_run", time.time())
```

### `get_kv_data()`

获取数据。

**签名**:
```python
async def get_kv_data(self, key: str, default: _VT) -> _VT
```

**示例**:

```python
last_run = await self.get_kv_data("last_run", 0)
```

### `delete_kv_data()`

删除数据。

**签名**:
```python
async def delete_kv_data(self, key: str) -> None
```

**示例**:

```python
await self.delete_kv_data("temp_data")
```

---

## 完整插件示例

```python
"""
完整的插件示例
"""

from astrbot_sdk import Star, Context, MessageEvent
from astrbot_sdk.decorators import on_command, on_message, provide_capability
from astrbot_sdk.errors import AstrBotError
import asyncio
import time

class CompletePlugin(Star):
    """完整功能插件"""

    async def initialize(self) -> None:
        """初始化"""
        self._stats = {
            "start_time": time.time(),
            "command_count": 0
        }

    async def on_start(self, ctx) -> None:
        """启动"""
        await super().on_start(ctx)

        # 加载配置
        config = await ctx.metadata.get_plugin_config()
        self.greeting = config.get("greeting", "你好")

        # 注册 LLM 工具
        await ctx.register_llm_tool(
            name="get_time",
            parameters_schema={
                "type": "object",
                "properties": {},
                "required": []
            },
            desc="获取当前时间",
            func_obj=self.get_time_tool
        )

        # 启动后台任务
        await ctx.register_task(
            self.background_sync(),
            desc="后台数据同步"
        )

        ctx.logger.info("Plugin started")

    async def on_stop(self, ctx) -> None:
        """停止"""
        # 保存统计
        await self.put_kv_data("stats", self._stats)
        await super().on_stop(ctx)
        ctx.logger.info("Plugin stopped")

    @on_command("hello", aliases=["hi", "greet"])
    async def hello(self, event: MessageEvent, ctx: Context) -> None:
        """打招呼命令"""
        self._stats["command_count"] += 1
        await event.reply(f"{self.greeting}，{event.sender_name}!")

    @on_command("stats")
    async def stats(self, event: MessageEvent, ctx: Context) -> None:
        """统计信息"""
        uptime = time.time() - self._stats["start_time"]
        await event.reply(f"""
        运行时间: {uptime:.0f}秒
        命令次数: {self._stats['command_count']}
        """)

    @on_message(keywords=["帮助"])
    async def help(self, event: MessageEvent, ctx: Context) -> None:
        """帮助信息"""
        await event.reply("""
        可用命令：
        /hello - 打招呼
        /stats - 统计信息
        /time - 当前时间
        """)

    @on_command("time")
    async def time_cmd(self, event: MessageEvent, ctx: Context) -> None:
        """获取时间"""
        result = await self.get_time_tool()
        await event.reply(result)

    async def get_time_tool(self) -> str:
        """LLM 工具实现"""
        return f"当前时间: {time.strftime('%Y-%m-%d %H:%M:%S')}"

    async def background_sync(self):
        """后台任务"""
        while True:
            await asyncio.sleep(3600)
            # 执行同步逻辑
            pass

    async def on_error(self, error: Exception, event, ctx) -> None:
        """错误处理"""
        if isinstance(error, AstrBotError):
            await event.reply(error.hint or error.message)
        else:
            await event.reply(f"发生错误: {type(error).__name__}")
        ctx.logger.error(f"Error: {error}", exc_info=error)
```

---

## plugin.yaml 配置

```yaml
_schema_version: 2
name: my_plugin
author: Your Name <email@example.com>
version: 1.0.0
desc: 我的插件描述
repo: https://github.com/user/repo
logo: assets/logo.png

runtime:
  python: "3.12"

components:
  - class: main:MyPlugin

support_platforms:
  - aiocqhttp
  - telegram
  - discord

astrbot_version: ">=4.13.0,<5.0.0"

config:
  timeout: 30
  max_retries: 3
  api_key: ""
```

---

## 最佳实践

### 1. 资源初始化与清理

```python
class MyPlugin(Star):
    async def on_start(self, ctx):
        # 创建资源
        self._session = aiohttp.ClientSession()
        self._task = asyncio.create_task(self.background_task())

    async def on_stop(self, ctx):
        # 清理资源
        if hasattr(self, '_task'):
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        if hasattr(self, '_session'):
            await self._session.close()
```

### 2. 配置管理

```python
class MyPlugin(Star):
    async def on_start(self, ctx):
        config = await ctx.metadata.get_plugin_config()

        # 提供默认值
        self.timeout = config.get("timeout", 30)

        # 验证必需配置
        if "api_key" not in config:
            raise ValueError("缺少必需配置: api_key")

        self.api_key = config["api_key"]
```

### 3. 状态持久化

```python
class MyPlugin(Star):
    async def on_start(self, ctx):
        # 加载状态
        self.last_update = await self.get_kv_data("last_update", 0)
        self.user_data = await self.get_kv_data("users", {})

    async def on_stop(self, ctx):
        # 保存状态
        await self.put_kv_data("last_update", time.time())
        await self.put_kv_data("users", self.user_data)
```

### 4. 错误处理

```python
class MyPlugin(Star):
    async def on_error(self, error, event, ctx):
        # 根据错误类型发送不同的提示
        if isinstance(error, ValueError):
            await event.reply("参数错误")
        elif isinstance(error, ConnectionError):
            await event.reply("网络连接失败")
        else:
            # 使用默认处理
            await super().on_error(error, event, ctx)

        # 记录日志
        ctx.logger.error(f"Handler error: {error}", exc_info=error)
```

---

## 注意事项

1. **异步方法**: 所有生命周期钩子都是异步方法，必须使用 `async def` 声明

2. **super() 调用**: 在 `on_start` 和 `on_stop` 中始终调用 `await super().xxx(ctx)` 确保 `initialize`/`terminate` 被调用

3. **context 属性**: 仅在生命周期钩子和 Handler 执行期间可用，不要存储此引用

4. **异常处理**: `on_start` 中的异常会导致插件加载失败，`on_stop` 中的异常会被捕获并记录

5. **资源清理**: 确保在 `on_stop` 或 `terminate` 中清理所有资源（连接、任务、文件等）

---

## 相关模块

- **装饰器**: `astrbot_sdk.decorators` - 事件处理装饰器
- **上下文**: `astrbot_sdk.context.Context` - 运行时上下文
- **事件**: `astrbot_sdk.events.MessageEvent` - 消息事件
- **错误**: `astrbot_sdk.errors.AstrBotError` - SDK 错误类

---

**版本**: v4.0
**模块**: `astrbot_sdk.star.Star`
**最后更新**: 2026-03-17
