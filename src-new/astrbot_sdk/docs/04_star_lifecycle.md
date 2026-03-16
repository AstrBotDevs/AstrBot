# AstrBot SDK Star 类与生命周期指南

## 概述

`Star` 是 AstrBot v4 SDK 的原生插件基类，提供了完整的插件生命周期管理、上下文访问和能力集成。

## 目录

- [Star 类概述](#star-类概述)
- [生命周期流程](#生命周期流程)
- [生命周期钩子](#生命周期钩子)
- [Context 上下文使用](#context-上下文使用)
- [插件元数据访问](#插件元数据访问)
- [错误处理模式](#错误处理模式)
- [最佳实践](#最佳实践)

---

## Star 类概述

### 什么是 Star 类？

`Star` 是所有 v4 原生插件必须继承的基类，提供插件生命周期管理和能力集成。

### 核心特性

```python
from astrbot_sdk import Star, Context, MessageEvent
from astrbot_sdk.decorators import on_command, on_message

class MyPlugin(Star):
    """插件类示例"""

    @on_command("hello")
    async def hello(self, event: MessageEvent, ctx: Context):
        await event.reply("Hello!")
```

---

## 生命周期流程

### 完整生命周期

```
┌─────────────────────────────────────────────────────────────────┐
│                    插件加载阶段                                   │
├─────────────────────────────────────────────────────────────────┤
│  1. 插件发现 (discover_plugins)                                  │
│     ├─ 扫描插件目录                                              │
│     ├─ 读取 plugin.yaml                                         │
│     └─ 验证组件类 (main:MyPlugin)                               │
│                                                                 │
│  2. 插件加载   │
│     ├─ 动态导入插件模块                                          │
│     ├─ 实例化 Star 子类                                          │
│     ├─ 收集 __handlers__ 元组                                    │
│     └─ 注册装饰器元数据                                          │
│                                                                 │
│  3. Worker 启动 (PluginWorkerRuntime.start)                     │
│     ├─ 向 Core 注册 handlers/capabilities                       │
│     └─ 建立通信对等端                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    插件运行阶段                                   │
├─────────────────────────────────────────────────────────────────┤
│  4. on_start() 生命周期钩子                                      │
│     ├─ 绑定运行时上下文         │
│     ├─ 调用 on_start(ctx)                                        │
│     └─ 内部调用 initialize()                                    │
│                                                                 │
│  5. Handler 事件循环                                            │
│     ├─ 等待事件触发 (命令/消息/事件/定时)                        │
│     ├─ HandlerDispatcher.invoke()                              │
│     ├─ 创建 Context 和 MessageEvent                             │
│     ├─ 执行用户 handler                                         │
│     └─ 处理返回值/异常                                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    插件卸载阶段                                   │
├─────────────────────────────────────────────────────────────────┤
│  6. on_stop() 生命周期钩子                                       │
│     ├─ 调用 on_stop(ctx)                                        │
│     ├─ 内部调用 terminate()                                     │
│     ├─ 清理资源 (数据库连接、文件句柄等)                         │
│     └─ 重置运行时上下文                                          │
│                                                                 │
│  7. Worker 关闭                                                 │
│     ├─ 发送 finalize 消息给 Core                                │
│     ├─ 关闭通信传输层                                            │
│     └─ 退出子进程                                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 生命周期钩子

### 1. on_start() - 插件启动钩子

**触发时机**：Worker 启动后，在开始处理事件之前调用

**参数：**
- `ctx: Any | None` - 运行时上下文（通常为 Context 实例）

**用途：**
- 初始化数据库连接
- 加载配置文件
- 注册 LLM 工具
- 启动后台任务

**示例：**

```python
class MyPlugin(Star):
    async def on_start(self, ctx: Any | None = None) -> None:
        """插件启动时调用"""
        await super().on_start(ctx)

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
```

### 2. on_stop() - 插件停止钩子

**触发时机**：插件卸载或程序关闭前调用

**用途：**
- 关闭数据库连接
- 清理临时文件
- 注销 LLM 工具
- 保存状态数据

**示例：**

```python
class MyPlugin(Star):
    async def on_stop(self, ctx: Any | None = None) -> None:
        """插件停止时调用"""
        # 保存状态
        await self.put_kv_data("last_shutdown", time.time())

        # 确保 terminate 被调用
        await super().on_stop(ctx)
```

### 3. initialize() - 初始化钩子

**触发时机**：`on_start()` 内部自动调用

**用途：**
- 插件级别的初始化逻辑
- 不依赖 Context 的初始化

**示例：**

```python
class MyPlugin(Star):
    async def initialize(self) -> None:
        """初始化插件"""
        self._cache = {}
        self._counter = 0
```

### 4. terminate() - 终止钩子

**触发时机**：`on_stop()` 内部自动调用

**用途：**
- 插件级别的清理逻辑
- 不依赖 Context 的清理

**示例：**

```python
class MyPlugin(Star):
    async def terminate(self) -> None:
        """清理插件资源"""
        self._cache.clear()
        self.state = "stopped"
```

### 5. on_error() - 错误处理钩子

**触发时机**：任何 Handler 执行抛出异常时

**参数：**
- `error: Exception` - 捕获的异常
- `event` - 事件对象
- `ctx` - 上下文对象

**示例：**

```python
class MyPlugin(Star):
    async def on_error(self, error: Exception, event, ctx) -> None:
        """自定义错误处理"""
        from astrbot_sdk.errors import AstrBotError

        if isinstance(error, AstrBotError):
            await event.reply(error.hint or error.message)
        elif isinstance(error, ValueError):
            await event.reply(f"参数错误：{error}")
        else:
            await event.reply(f"发生错误: {type(error).__name__}")

        ctx.logger.error(f"Handler error: {error}", exc_info=error)
```

---

## Context 上下文使用

### 在 Handler 中访问

```python
class MyPlugin(Star):
    @on_command("test")
    async def test_handler(self, event: MessageEvent, ctx: Context):
        # Context 通过参数注入
        await ctx.db.set("key", "value")
        await event.reply("Done")
```

### 在生命周期钩子中访问

```python
class MyPlugin(Star):
    async def on_start(self, ctx):
        # 生命周期钩子中的 Context
        config = await ctx.metadata.get_plugin_config()
```

---

## 插件元数据访问

### plugin.yaml 配置

```yaml
_schema_version: 2
name: my_plugin
author: your_name
version: 1.0.0
desc: 我的插件描述
repo: https://github.com/user/repo
logo: logo.png

runtime:
  python: "3.12"

components:
  - class: main:MyPlugin

support_platforms:
  - aiocqhttp
  - telegram

astrbot_version: ">=4.13.0,<5.0.0"
```

### 访问元数据

```python
class MyPlugin(Star):
    async def on_start(self, ctx):
        # 获取当前插件元数据
        my_metadata = await ctx.metadata.get_current_plugin()
        print(f"Starting {my_metadata.name} v{my_metadata.version}")
```

---

## 错误处理模式

### 标准错误类型

```python
from astrbot_sdk.errors import AstrBotError

# 1. 输入无效错误
raise AstrBotError.invalid_input(
    "参数格式错误",
    hint="请使用 JSON 格式"
)

# 2. 能力未找到错误
raise AstrBotError.capability_not_found("unknown_capability")

# 3. 网络错误
raise AstrBotError.network_error(
    "连接超时",
    hint="请检查网络连接"
)
```

### 在 Handler 中捕获错误

```python
class MyPlugin(Star):
    @on_command("risky_operation")
    async def risky(self, event: MessageEvent, ctx: Context):
        try:
            result = await self.risky_operation()
            await event.reply(f"成功: {result}")
        except ValueError as e:
            await event.reply(f"参数错误: {e}")
        except ConnectionError as e:
            ctx.logger.error(f"Network error: {e}")
            await event.reply("网络连接失败")
        except Exception as e:
            ctx.logger.exception("Unexpected error")
            raise
```

---

## 最佳实践

### 1. 插件结构

```
my_plugin/
├── plugin.yaml          # 插件配置
├── main.py              # 主入口
├── handlers/            # 处理器模块
├── utils/               # 工具函数
├── requirements.txt     # Python 依赖
└── README.md            # 说明文档
```

### 2. 插件模板

```python
"""
插件说明
"""

from astrbot_sdk import Star, Context, MessageEvent
from astrbot_sdk.decorators import on_command, on_message

class MyPlugin(Star):
    """插件类"""

    async def initialize(self) -> None:
        """初始化"""
        self._cache = {}
        self._counter = 0

    async def on_start(self, ctx) -> None:
        """启动时调用"""
        await super().on_start(ctx)

        # 加载配置
        config = await ctx.metadata.get_plugin_config()
        self.setting = config.get("setting", "default")

        # 注册工具
        await ctx.register_llm_tool(
            name="my_tool",
            parameters_schema={...},
            desc="我的工具",
            func_obj=self.my_tool
        )

        ctx.logger.info(f"{ctx.plugin_id} started")

    async def on_stop(self, ctx) -> None:
        """停止时调用"""
        # 保存状态
        await self.put_kv_data("counter", self._counter)
        await super().on_stop(ctx)
        ctx.logger.info(f"{ctx.plugin_id} stopped")

    @on_command("hello", aliases=["hi"])
    async def hello(self, event: MessageEvent, ctx: Context) -> None:
        """打招呼命令"""
        await event.reply(f"你好，{event.sender_name}!")

    async def my_tool(self, param: str) -> str:
        """LLM 工具实现"""
        return f"处理结果: {param}"
```

### 3. 配置管理

```python
class MyPlugin(Star):
    async def on_start(self, ctx):
        # 获取配置
        config = await ctx.metadata.get_plugin_config()

        # 提供默认值
        self.timeout = config.get("timeout", 30)
        self.max_retries = config.get("max_retries", 3)
        self.debug = config.get("debug", False)

        # 验证必需配置
        if "api_key" not in config:
            raise ValueError("缺少必需配置: api_key")

        self.api_key = config["api_key"]
```

### 4. 数据持久化

```python
class MyPlugin(Star):
    async def on_start(self, ctx):
        # 加载状态
        self.last_update = await self.get_kv_data("last_update", 0)
        self.user_data = await self.get_kv_data("users", {})

    async def save_state(self):
        # 保存状态
        await self.put_kv_data("last_update", time.time())
        await self.put_kv_data("users", self.user_data)
```

### 5. 资源清理

```python
class MyPlugin(Star):
    async def on_start(self, ctx):
        # 创建需要清理的资源
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
