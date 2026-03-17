# AstrBot SDK Context API 参考文档

## 概述

`Context` 是插件与 AstrBot Core 交互的主要入口，每个 handler 调用都会创建一个新的 Context 实例。Context 组合了所有 capability 客户端，提供统一的访问接口。

## 目录

- [Context 类属性](#context-类属性)
- [核心客户端](#核心客户端)
- [LLM 客户端 (ctx.llm)](#llm-客户端)
- [Memory 客户端 (ctx.memory)](#memory-客户端)
- [Database 客户端 (ctx.db)](#database-客户端)
- [Files 客户端 (ctx.files)](#files-客户端)
- [Platform 客户端 (ctx.platform)](#platform-客户端)
- [Provider 客户端 (ctx.providers)](#provider-客户端)
- [HTTP 客户端 (ctx.http)](#http-客户端)
- [Metadata 客户端 (ctx.metadata)](#metadata-客户端)
- [LLM Tool 管理方法](#llm-tool-管理方法)
- [系统工具方法](#系统工具方法)

---

## Context 类属性

### 基本属性

```python
@dataclass
class Context:
    peer: Any                          # 协议对等端，用于底层通信
    plugin_id: str                     # 当前插件 ID
    logger: PluginLogger               # 绑定了插件 ID 的日志器
    cancel_token: CancelToken          # 取消令牌，用于处理请求取消
```

### 客户端属性

```python
ctx.llm: LLMClient                    # LLM 能力客户端
ctx.memory: MemoryClient              # 记忆能力客户端
ctx.db: DBClient                      # 数据库客户端
ctx.files: FileServiceClient          # 文件服务客户端
ctx.platform: PlatformClient          # 平台客户端
ctx.providers: ProviderClient         # Provider 客户端
ctx.provider_manager: ProviderManagerClient  # Provider 管理客户端
ctx.personas: PersonaManagerClient    # 人格管理客户端
ctx.conversations: ConversationManagerClient  # 对话管理客户端
ctx.kbs: KnowledgeBaseManagerClient   # 知识库管理客户端
ctx.http: HTTPClient                  # HTTP 客户端
ctx.metadata: MetadataClient          # 元数据客户端
```

---

## 核心客户端

### logger

绑定了插件 ID 的日志器，自动添加插件上下文信息。

```python
# 不同级别的日志
ctx.logger.debug("调试信息")
ctx.logger.info("普通信息")
ctx.logger.warning("警告信息")
ctx.logger.error("错误信息")

# 绑定额外上下文
logger = ctx.logger.bind(user_id="12345")
logger.info("用户操作")

# 流式日志监听
async for entry in ctx.logger.watch():
    print(f"[{entry.level}] {entry.message}")
```

### cancel_token

取消令牌，用于长时间运行的任务中检查是否需要取消。

```python
# 检查是否取消
ctx.cancel_token.raise_if_cancelled()

# 触发取消
ctx.cancel_token.cancel()

# 等待取消信号
await ctx.cancel_token.wait()
```

---

## LLM 客户端

### chat()

发送聊天请求并返回文本响应。

```python
async def chat(
    prompt: str,
    *,
    system: str | None = None,
    history: Sequence[ChatHistoryItem] | None = None,
    provider_id: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    **kwargs: Any,
) -> str
```

**使用示例：**

```python
# 简单对话
reply = await ctx.llm.chat("你好，介绍一下自己")

# 带系统提示词
reply = await ctx.llm.chat(
    "用 Python 写一个快速排序",
    system="你是一个专业的程序员助手"
)

# 带历史的对话
from astrbot_sdk.clients.llm import ChatMessage

history = [
    ChatMessage(role="user", content="我叫小明"),
    ChatMessage(role="assistant", content="你好小明！"),
]
reply = await ctx.llm.chat("你记得我的名字吗？", history=history)
```

### chat_raw()

发送聊天请求并返回完整响应对象。

```python
response = await ctx.llm.chat_raw("写一首诗", temperature=0.8)
print(f"生成文本: {response.text}")
print(f"Token 使用: {response.usage}")
print(f"结束原因: {response.finish_reason}")
```

### stream_chat()

流式聊天，逐块返回响应文本。

```python
async for chunk in ctx.llm.stream_chat("讲一个故事"):
    print(chunk, end="", flush=True)
```

---

## Memory 客户端

### search()

语义搜索记忆项。

```python
results = await ctx.memory.search("用户喜欢什么颜色")
for item in results:
    print(item["key"], item["content"])
```

### save()

保存记忆项。

```python
# 保存用户偏好
await ctx.memory.save("user_pref", {"theme": "dark", "lang": "zh"})

# 使用关键字参数
await ctx.memory.save("note", None, content="重要笔记", tags=["work"])
```

### get()

精确获取单个记忆项。

```python
pref = await ctx.memory.get("user_pref")
if pref:
    print(f"用户偏好主题: {pref.get('theme')}")
```

### save_with_ttl()

保存带过期时间的记忆项。

```python
# 保存临时会话状态，1小时后过期
await ctx.memory.save_with_ttl(
    "session_temp",
    {"state": "waiting"},
    ttl_seconds=3600
)
```

---

## Database 客户端

### get()

获取指定键的值。

```python
data = await ctx.db.get("user_settings")
if data:
    print(data["theme"])
```

### set()

设置键值对。

```python
await ctx.db.set("user_settings", {"theme": "dark", "lang": "zh"})
await ctx.db.set("greeted", True)
```

### delete()

删除指定键的数据。

```python
await ctx.db.delete("user_settings")
```

### list()

列出匹配前缀的所有键。

```python
keys = await ctx.db.list("user_")
# ["user_settings", "user_profile", "user_history"]
```

### get_many()

批量获取多个键的值。

```python
values = await ctx.db.get_many(["user:1", "user:2"])
```

### set_many()

批量写入多个键值对。

```python
await ctx.db.set_many({
    "user:1": {"name": "Alice"},
    "user:2": {"name": "Bob"}
})
```

### watch()

订阅 KV 变更事件（流式）。

```python
async for event in ctx.db.watch("user:"):
    print(event["op"], event["key"])
```

---

## Files 客户端

### register_file()

注册文件并获取令牌。

```python
token = await ctx.files.register_file("/path/to/file.jpg", timeout=3600)
```

### handle_file()

通过令牌解析文件路径。

```python
path = await ctx.files.handle_file(token)
```

---

## Platform 客户端

### send()

发送文本消息。

```python
await ctx.platform.send(event.session_id, "收到您的消息！")
```

### send_image()

发送图片消息。

```python
await ctx.platform.send_image(
    event.session_id,
    "https://example.com/image.png"
)
```

### send_chain()

发送富消息链。

```python
from astrbot_sdk.message_components import Plain, Image

chain = [Plain("文字"), Image(url="https://example.com/img.jpg")]
await ctx.platform.send_chain(event.session_id, chain)
```

### send_by_id()

主动向指定平台会话发送消息。

```python
await ctx.platform.send_by_id(
    platform_id="qq",
    session_id="user123",
    content="Hello",
    message_type="private"
)
```

### get_members()

获取群组成员列表。

```python
members = await ctx.platform.get_members("qq:group:123456")
for member in members:
    print(f"{member['nickname']} ({member['user_id']})")
```

---

## Provider 客户端

### list_all()

列出所有 Provider。

```python
providers = await ctx.providers.list_all()
for p in providers:
    print(f"{p.id}: {p.model}")
```

### get_using_chat()

获取当前使用的聊天 Provider。

```python
provider = await ctx.providers.get_using_chat()
if provider:
    print(f"当前使用: {provider.id}")
```

---

## HTTP 客户端

### register_api()

注册 Web API 端点。

```python
from astrbot_sdk.decorators import provide_capability

@provide_capability(
    name="my_plugin.http_handler",
    description="处理 HTTP 请求"
)
async def handle_http_request(request_id: str, payload: dict, cancel_token):
    return {"status": 200, "body": {"result": "ok"}}

await ctx.http.register_api(
    route="/my-api",
    handler=handle_http_request,
    methods=["GET", "POST"]
)
```

### unregister_api()

注销 Web API 端点。

```python
await ctx.http.unregister_api("/my-api")
```

### list_apis()

列出当前插件注册的所有 API。

```python
apis = await ctx.http.list_apis()
for api in apis:
    print(f"{api['route']}: {api['methods']}")
```

---

## Metadata 客户端

### get_plugin()

获取指定插件信息。

```python
plugin = await ctx.metadata.get_plugin("another_plugin")
if plugin:
    print(f"插件: {plugin.display_name}")
    print(f"版本: {plugin.version}")
```

### list_plugins()

获取所有插件列表。

```python
plugins = await ctx.metadata.list_plugins()
for plugin in plugins:
    print(f"{plugin.display_name} v{plugin.version}")
```

### get_current_plugin()

获取当前插件信息。

```python
current = await ctx.metadata.get_current_plugin()
if current:
    print(f"当前插件: {current.name} v{current.version}")
```

### get_plugin_config()

获取插件配置。

```python
config = await ctx.metadata.get_plugin_config()
if config:
    api_key = config.get("api_key")
```

---

## LLM Tool 管理方法

### register_llm_tool()

注册可执行的 LLM 工具。

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
    func_obj=search_weather,
    active=True
)
```

### add_llm_tools()

添加 LLM 工具规范。

```python
from astrbot_sdk.llm.tools import LLMToolSpec

tool_spec = LLMToolSpec(
    name="my_tool",
    description="我的工具",
    parameters_schema={...}
)

await ctx.add_llm_tools(tool_spec)
```

### activate_llm_tool() / deactivate_llm_tool()

激活/停用 LLM 工具。

```python
await ctx.activate_llm_tool("my_tool")
await ctx.deactivate_llm_tool("my_tool")
```

---

## 系统工具方法

### get_data_dir()

获取插件数据目录路径。

```python
data_dir = await ctx.get_data_dir()
print(f"数据目录: {data_dir}")
```

### text_to_image()

将文本渲染为图片。

```python
url = await ctx.text_to_image("Hello World", return_url=True)
```

### html_render()

渲染 HTML 模板。

```python
url = await ctx.html_render(
    tmpl="<h1>{{ title }}</h1>",
    data={"title": "标题"}
)
```

### send_message()

向会话发送消息。

```python
await ctx.send_message(event.session_id, "消息内容")
```

### send_message_by_id()

通过 ID 向平台发送消息。

```python
await ctx.send_message_by_id(
    type="private",
    id="user123",
    content="Hello",
    platform="qq"
)
```

### register_task()

注册后台任务。

```python
async def background_work():
    while True:
        await asyncio.sleep(60)
        ctx.logger.info("每分钟执行一次")

task = await ctx.register_task(background_work(), "定时任务")
```

---

## 常见使用模式

### 1. 基本对话流程

```python
from astrbot_sdk.decorators import on_message

@on_message()
async def handle_message(event: MessageEvent, ctx: Context):
    reply = await ctx.llm.chat(event.message_content)
    await ctx.platform.send(event.session_id, reply)
```

### 2. 带历史的对话

```python
@on_message()
async def handle_message(event: MessageEvent, ctx: Context):
    # 从 memory 获取历史
    history_data = await ctx.memory.get(f"history:{event.session_id}")
    history = history_data.get("messages", []) if history_data else []

    # 对话
    reply = await ctx.llm.chat(event.message_content, history=history)

    # 保存新消息到历史
    history.append(ChatMessage(role="user", content=event.message_content))
    history.append(ChatMessage(role="assistant", content=reply))
    await ctx.memory.save(f"history:{event.session_id}", {"messages": history})

    await ctx.platform.send(event.session_id, reply)
```

### 3. 使用数据库持久化

```python
@on_message()
async def handle_message(event: MessageEvent, ctx: Context):
    # 获取用户配置
    config = await ctx.db.get(f"user_config:{event.sender_id}")

    if not config:
        config = {"theme": "light", "lang": "zh"}
        await ctx.db.set(f"user_config:{event.sender_id}", config)

    # 使用配置
    reply = f"你的主题设置是: {config['theme']}"
    await ctx.platform.send(event.session_id, reply)
```

---

## 注意事项

1. **跨进程通信**：Context 通过 capability 协议与核心通信，所有方法调用都是异步的

2. **插件隔离**：每个插件有独立的 Context 实例，数据和配置是隔离的

3. **取消处理**：长时间运行的操作应定期检查 `ctx.cancel_token.raise_if_cancelled()`

4. **错误处理**：所有远程调用都可能失败，建议使用 try-except 处理

5. **Memory vs DB**：
   - Memory: 语义搜索，适合 AI 上下文
   - DB: 精确匹配，适合结构化数据

6. **文件操作**：使用 `ctx.files` 注册文件令牌，不要直接传递本地路径

7. **平台标识**：使用 UMO（统一消息来源标识）格式：`"platform:instance:session_id"`
