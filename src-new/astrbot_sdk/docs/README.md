# AstrBot SDK 插件开发文档

欢迎来到 AstrBot SDK 插件开发文档！本文档面向 SDK 插件开发者，提供完整的 API 参考和使用指南。

## 📚 文档目录

### 快速开始

- [01. Context API 参考](./01_context_api.md) - Context 类的核心客户端和系统工具方法
- [02. 消息事件与组件](./02_event_and_components.md) - MessageEvent 和消息组件的使用
- [03. 装饰器使用指南](./03_decorators.md) - 所有装饰器的详细说明
- [04. Star 类与生命周期](./04_star_lifecycle.md) - 插件基类和生命周期钩子
- [05. 客户端 API 参考](./05_clients.md) - 所有客户端的完整 API 文档

## 🚀 快速上手

### 创建插件

```python
from astrbot_sdk import Star, Context, MessageEvent
from astrbot_sdk.decorators import on_command, on_message

class MyPlugin(Star):
    """我的插件"""

    @on_command("hello")
    async def hello(self, event: MessageEvent, ctx: Context):
        await event.reply("Hello, World!")

    @on_message(keywords=["帮助"])
    async def help(self, event: MessageEvent, ctx: Context):
        await event.reply("可用命令: /hello")
```

### 插件配置 (plugin.yaml)

```yaml
_schema_version: 2
name: my_plugin
author: your_name
version: 1.0.0
desc: 我的插件描述

runtime:
  python: "3.12"

components:
  - class: main:MyPlugin

support_platforms:
  - aiocqhttp
  - telegram
```

## 📖 核心概念

### Context

`Context` 是插件与 AstrBot Core 交互的主要入口，提供对所有能力客户端的访问：

```python
# LLM 对话
reply = await ctx.llm.chat("你好")

# 数据存储
await ctx.db.set("key", "value")
data = await ctx.db.get("key")

# 记忆存储
await ctx.memory.save("pref", {"theme": "dark"})

# 发送消息
await ctx.platform.send(event.session_id, "消息内容")

# 获取配置
config = await ctx.metadata.get_plugin_config()
```

### MessageEvent

`MessageEvent` 表示接收到的消息事件：

```python
# 回复消息
await event.reply("回复内容")

# 获取消息组件
images = event.get_images()

# 判断消息类型
if event.is_group_chat():
    await event.reply("这是群聊消息")

# 构建返回结果
return event.plain_result("返回内容")
```

### 装饰器

装饰器用于注册事件处理器：

```python
from astrbot_sdk.decorators import (
    on_command,    # 命令触发
    on_message,    # 消息触发
    on_event,      # 事件触发
    on_schedule,   # 定时任务
    require_admin, # 权限控制
    rate_limit,    # 速率限制
)

@on_command("test")
@rate_limit(5, 60)
async def test_handler(self, event: MessageEvent, ctx: Context):
    await event.reply("测试")
```

## 🔧 常用功能

### 1. LLM 对话

```python
# 简单对话
reply = await ctx.llm.chat("你好")

# 带历史对话
history = [
    ChatMessage(role="user", content="我叫小明"),
    ChatMessage(role="assistant", content="你好小明！"),
]
reply = await ctx.llm.chat("你记得我吗？", history=history)

# 流式对话
async for chunk in ctx.llm.stream_chat("讲个故事"):
    print(chunk, end="")
```

### 2. 数据持久化

```python
# DB 客户端（精确匹配）
await ctx.db.set("user:123", {"name": "Alice"})
data = await ctx.db.get("user:123")

# Memory 客户端（语义搜索）
await ctx.memory.save("user_pref", {"theme": "dark"})
results = await ctx.memory.search("用户喜欢什么颜色")
```

### 3. 消息发送

```python
# 简单文本
await ctx.platform.send(event.session_id, "消息内容")

# 图片
await ctx.platform.send_image(event.session_id, "https://example.com/img.jpg")

# 消息链
from astrbot_sdk.message_components import Plain, Image

chain = [Plain("文字"), Image(url="https://example.com/img.jpg")]
await ctx.platform.send_chain(event.session_id, chain)
```

### 4. 文件处理

```python
from astrbot_sdk.message_components import Image

# 注册文件到文件服务
img = Image.fromFileSystem("/path/to/image.jpg")
public_url = await img.register_to_file_service()
```

## 🛠️ 高级功能

### 1. LLM 工具注册

```python
async def search_weather(location: str) -> str:
    return f"{location} 今天晴天"

await ctx.register_llm_tool(
    name="search_weather",
    parameters_schema={
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "城市名称"}
        },
        "required": ["location"]
    },
    desc="搜索天气信息",
    func_obj=search_weather
)
```

### 2. Web API 注册

```python
from astrbot_sdk.decorators import provide_capability

@provide_capability(
    name="my_plugin.api",
    description="处理 HTTP 请求"
)
async def handle_api(request_id: str, payload: dict, cancel_token):
    return {"status": 200, "body": {"result": "ok"}}

await ctx.http.register_api(
    route="/my-api",
    handler=handle_api,
    methods=["GET", "POST"]
)
```

### 3. 后台任务

```python
async def background_work():
    while True:
        await asyncio.sleep(60)
        ctx.logger.info("每分钟执行一次")

task = await ctx.register_task(background_work(), "定时任务")
```

## 📋 最佳实践

### 1. 错误处理

```python
@on_command("risky")
async def risky_handler(self, event: MessageEvent, ctx: Context):
    try:
        result = await risky_operation()
        await event.reply(f"成功: {result}")
    except ValueError as e:
        await event.reply(f"参数错误: {e}")
    except Exception as e:
        ctx.logger.error(f"操作失败: {e}", exc_info=e)
        raise
```

### 2. 日志记录

```python
# 不同级别的日志
ctx.logger.debug("调试信息")
ctx.logger.info("普通信息")
ctx.logger.warning("警告信息")
ctx.logger.error("错误信息")

# 绑定上下文
logger = ctx.logger.bind(user_id=event.user_id)
logger.info("用户操作")
```

### 3. 配置管理

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

### 4. 资源清理

```python
class MyPlugin(Star):
    async def on_start(self, ctx):
        self._session = aiohttp.ClientSession()
        self._task = asyncio.create_task(self.background_task())

    async def on_stop(self, ctx):
        if hasattr(self, '_task'):
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        if hasattr(self, '_session'):
            await self._session.close()
```

## 🔍 注意事项

1. **异步操作**：所有客户端方法都是异步的，需要使用 `await`

2. **插件隔离**：每个插件有独立的 Context 实例

3. **错误处理**：所有远程调用都可能失败，建议使用 try-except

4. **Memory vs DB**：
   - Memory: 语义搜索，适合 AI 上下文
   - DB: 精确匹配，适合结构化数据

5. **平台标识**：使用 UMO 格式 `"platform:instance:session_id"`

6. **装饰器顺序**：事件触发 → 过滤器 → 限制器 → 修饰器

## 📞 获取帮助

- 查看完整 API 参考：[docs/](./)
- 提交问题：[GitHub Issues](https://github.com/your-repo/issues)
- 参与讨论：[GitHub Discussions](https://github.com/your-repo/discussions)

---

**版本**: v4.0
**最后更新**: 2026-03-17
