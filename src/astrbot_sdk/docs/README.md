# AstrBot SDK 插件开发文档

欢迎来到 AstrBot SDK 插件开发文档！本文档面向 SDK 插件开发者，提供从入门到精通的完整指南。

## 📚 文档目录

### 🚀 快速开始（初级使用者）

适合第一次接触 AstrBot SDK 的开发者：

- **[01. Context API 参考](./01_context_api.md)** - Context 类的核心客户端和系统工具方法
- **[02. 消息事件与组件](./02_event_and_components.md)** - MessageEvent 和消息组件的使用
- **[03. 装饰器使用指南](./03_decorators.md)** - 所有装饰器的详细说明
- **[04. Star 类与生命周期](./04_star_lifecycle.md)** - 插件基类和生命周期钩子
- **[05. 客户端 API 参考](./05_clients.md)** - 所有客户端的完整 API 文档

### 🔧 进阶主题（中级使用者）

适合已经掌握基础，希望深入了解 SDK 的开发者：

- **[06. 错误处理与调试](./06_error_handling.md)** - 完整的错误处理指南和调试技巧
- **[07. 高级主题](./07_advanced_topics.md)** - 并发处理、性能优化、安全最佳实践
- **[08. 测试指南](./08_testing_guide.md)** - 如何测试插件和 Mock 使用

### 📖 参考资料（高级使用者）

适合需要深入了解 SDK 架构和完整 API 的开发者：

- **[09. 完整 API 索引](./09_api_reference.md)** - 所有导出类和函数的完整参考
- **[10. 迁移指南](./10_migration_guide.md)** - 从旧版本或其他框架迁移
- **[11. 安全检查清单](./11_security_checklist.md)** - 安全开发检查清单和已知问题

---

## 🎯 学习路径推荐

### 初级路径：快速上手

```
1. 阅读本 README 的快速开始部分
2. 跟随下面的"创建第一个插件"教程
3. 查阅 01-05 文档了解基础 API
4. 参考文档中的示例代码
```

### 中级路径：进阶开发

```
1. 阅读 06 错误处理指南，建立健壮的错误处理机制
2. 学习 07 高级主题中的并发和性能优化
3. 按照 08 测试指南编写测试
4. 尝试开发复杂的插件功能
```

### 高级路径：精通 SDK

```
1. 阅读 09 完整 API 索引，了解所有可用功能
2. 研究 07 高级主题中的架构设计
3. 阅读 SDK 源码深入理解实现
4. 参与 SDK 贡献和改进
```

---

## 🚀 快速上手

### 创建第一个插件

```python
from astrbot_sdk import Star, Context, MessageEvent
from astrbot_sdk.decorators import on_command, on_message

class MyPlugin(Star):
    """我的第一个插件"""

    @on_command("hello")
    async def hello(self, event: MessageEvent, ctx: Context):
        """打招呼命令"""
        await event.reply(f"你好，{event.sender_name}!")

    @on_message(keywords=["帮助", "help"])
    async def help(self, event: MessageEvent, ctx: Context):
        """帮助信息"""
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

---

## 📖 核心概念

### Context - 能力访问入口

`Context` 是插件与 AstrBot Core 交互的主要入口：

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

### MessageEvent - 消息事件

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

### 装饰器 - 事件处理注册

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

---

## 🔧 常用功能速查

### 1. LLM 对话

```python
# 简单对话
reply = await ctx.llm.chat("你好")

# 带历史对话
from astrbot_sdk.clients.llm import ChatMessage

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

---

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

---

## 📋 最佳实践

### 1. 错误处理

```python
from astrbot_sdk.errors import AstrBotError

@on_command("risky")
async def risky_handler(self, event: MessageEvent, ctx: Context):
    try:
        result = await risky_operation()
        await event.reply(f"成功: {result}")
    except AstrBotError as e:
        # SDK 错误包含用户友好的提示
        await event.reply(e.hint or e.message)
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

---

## 🔍 注意事项

1. **异步操作**：所有客户端方法都是异步的，需要使用 `await`

2. **插件隔离**：每个插件有独立的 Context 实例

3. **错误处理**：所有远程调用都可能失败，建议使用 try-except

4. **Memory vs DB**：
   - Memory: 语义搜索，适合 AI 上下文
   - DB: 精确匹配，适合结构化数据

5. **平台标识**：使用 UMO 格式 `"platform:instance:session_id"`

6. **装饰器顺序**：事件触发 → 过滤器 → 限制器 → 修饰器

7. **安全提示**：
   - 不要在插件中存储敏感信息（API Key 等应使用配置）
   - 验证所有用户输入
   - 注意资源泄漏（任务、连接等需要正确清理）
   - 遵循最小权限原则

---

## 🐛 调试技巧

### 启用调试日志

```python
# 在插件中获取 logger
logger = ctx.logger

# 记录详细信息
logger.debug(f"收到消息: {event.text}")
logger.debug(f"用户ID: {event.user_id}")
```

### 使用测试框架

```python
from astrbot_sdk.testing import PluginTestHarness

async def test_my_plugin():
    harness = PluginTestHarness()
    plugin = harness.load_plugin("my_plugin.main:MyPlugin")
    
    # 模拟事件
    result = await harness.simulate_command("/hello")
    assert result.text == "Hello!"
```

---

## 📞 获取帮助

- **查看详细文档**：[docs/](./)
- **完整 API 索引**：[09_api_reference.md](./09_api_reference.md)
- **错误处理指南**：[06_error_handling.md](./06_error_handling.md)
- **安全检查清单**：[11_security_checklist.md](./11_security_checklist.md)
- **提交问题**：[GitHub Issues](https://github.com/your-repo/issues)
- **参与讨论**：[GitHub Discussions](https://github.com/your-repo/discussions)

---

## 📚 版本信息

- **SDK 版本**: v4.0
- **最后更新**: 2026-03-17
- **Python 要求**: >= 3.10
- **协议版本**: P0.6

---

## 📝 文档贡献

如果您发现文档中的错误或想改进文档，欢迎提交 PR！

**文档规范**：
- 使用清晰的代码示例
- 包含错误处理示例
- 标注 API 的稳定性和版本要求
- 提供初级和高级两种使用方式
