# AstrBot SDK 客户端 API 参考文档

## 概述

本文档详细介绍 `astrbot_sdk/clients/` 目录下所有客户端的 API，包括方法签名、使用示例和注意事项。

## 目录

- [LLMClient - AI 对话客户端](#1-llmclient---ai-对话客户端)
- [MemoryClient - 记忆存储客户端](#2-memoryclient---记忆存储客户端)
- [DBClient - KV 数据库客户端](#3-dbclient---kv-数据库客户端)
- [PlatformClient - 平台消息客户端](#4-platformclient---平台消息客户端)
- [FileServiceClient - 文件服务客户端](#5-fileserviceclient---文件服务客户端)
- [HTTPClient - HTTP API 客户端](#6-httpclient---http-api-客户端)
- [MetadataClient - 插件元数据客户端](#7-metadataclient---插件元数据客户端)

---

## 1. LLMClient - AI 对话客户端

### 导入

```python
from astrbot_sdk.clients import LLMClient, ChatMessage, LLMResponse
```

### 方法

#### chat()

简单对话。

```python
reply = await ctx.llm.chat("你好，介绍一下自己")
```

#### chat_raw()

获取完整响应。

```python
response = await ctx.llm.chat_raw("写一首诗", temperature=0.8)
print(f"Token 使用: {response.usage}")
```

#### stream_chat()

流式对话。

```python
async for chunk in ctx.llm.stream_chat("讲一个故事"):
    print(chunk, end="")
```

---

## 2. MemoryClient - 记忆存储客户端

### 导入

```python
from astrbot_sdk.clients import MemoryClient
```

### 方法

#### search()

语义搜索。

```python
results = await ctx.memory.search("用户喜欢什么颜色")
```

#### save()

保存记忆。

```python
await ctx.memory.save("user_pref", {"theme": "dark", "lang": "zh"})
```

#### get()

获取记忆。

```python
pref = await ctx.memory.get("user_pref")
```

#### save_with_ttl()

保存带过期时间的记忆。

```python
await ctx.memory.save_with_ttl(
    "session_temp",
    {"state": "waiting"},
    ttl_seconds=3600
)
```

#### delete()

删除记忆。

```python
await ctx.memory.delete("old_note")
```

---

## 3. DBClient - KV 数据库客户端

### 导入

```python
from astrbot_sdk.clients import DBClient
```

### 方法

#### get() / set()

基本读写。

```python
data = await ctx.db.get("user_settings")
await ctx.db.set("user_settings", {"theme": "dark"})
```

#### delete()

删除数据。

```python
await ctx.db.delete("user_settings")
```

#### list()

列出键。

```python
keys = await ctx.db.list("user_")
```

#### get_many() / set_many()

批量操作。

```python
values = await ctx.db.get_many(["user:1", "user:2"])
await ctx.db.set_many({"user:1": {"name": "Alice"}, "user:2": {"name": "Bob"}})
```

#### watch()

监听变更。

```python
async for event in ctx.db.watch("user:"):
    print(event["op"], event["key"])
```

---

## 4. PlatformClient - 平台消息客户端

### 导入

```python
from astrbot_sdk.clients import PlatformClient
```

### 方法

#### send()

发送文本消息。

```python
await ctx.platform.send("qq:group:123456", "大家好！")
```

#### send_image()

发送图片。

```python
await ctx.platform.send_image(event.session_id, "https://example.com/image.png")
```

#### send_chain()

发送消息链。

```python
from astrbot_sdk.message_components import Plain, Image

chain = [Plain("文字"), Image(url="https://example.com/img.jpg")]
await ctx.platform.send_chain(event.session_id, chain)
```

#### send_by_id()

通过 ID 发送。

```python
await ctx.platform.send_by_id(
    platform_id="qq",
    session_id="user123",
    content="Hello",
    message_type="private"
)
```

#### get_members()

获取群成员。

```python
members = await ctx.platform.get_members("qq:group:123456")
```

---

## 5. FileServiceClient - 文件服务客户端

### 导入

```python
from astrbot_sdk.clients import FileServiceClient
```

### 方法

#### register_file()

注册文件。

```python
token = await ctx.files.register_file("/path/to/file.jpg", timeout=3600)
```

#### handle_file()

解析令牌。

```python
path = await ctx.files.handle_file(token)
```

---

## 6. HTTPClient - HTTP API 客户端

### 导入

```python
from astrbot_sdk.clients import HTTPClient
from astrbot_sdk.decorators import provide_capability
```

### 方法

#### register_api()

注册 API。

```python
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

#### unregister_api()

注销 API。

```python
await ctx.http.unregister_api("/my-api")
```

#### list_apis()

列出 API。

```python
apis = await ctx.http.list_apis()
```

---

## 7. MetadataClient - 插件元数据客户端

### 导入

```python
from astrbot_sdk.clients import MetadataClient
```

### 方法

#### get_plugin()

获取插件信息。

```python
plugin = await ctx.metadata.get_plugin("another_plugin")
if plugin:
    print(f"插件: {plugin.display_name}")
```

#### list_plugins()

列出所有插件。

```python
plugins = await ctx.metadata.list_plugins()
```

#### get_current_plugin()

获取当前插件。

```python
current = await ctx.metadata.get_current_plugin()
```

#### get_plugin_config()

获取配置。

```python
config = await ctx.metadata.get_plugin_config()
api_key = config.get("api_key")
```

---

## 客户端使用示例

### 1. 基本对话流程

```python
@on_message()
async def handle_message(event: MessageEvent, ctx: Context):
    reply = await ctx.llm.chat(event.message_content)
    await ctx.platform.send(event.session_id, reply)
```

### 2. 带历史的对话

```python
@on_message()
async def handle_message(event: MessageEvent, ctx: Context):
    history_data = await ctx.memory.get(f"history:{event.session_id}")
    history = history_data.get("messages", []) if history_data else []

    reply = await ctx.llm.chat(event.message_content, history=history)

    history.append(ChatMessage(role="user", content=event.message_content))
    history.append(ChatMessage(role="assistant", content=reply))
    await ctx.memory.save(f"history:{event.session_id}", {"messages": history})

    await ctx.platform.send(event.session_id, reply)
```

### 3. 使用数据库持久化

```python
@on_message()
async def handle_message(event: MessageEvent, ctx: Context):
    config = await ctx.db.get(f"user_config:{event.sender_id}")

    if not config:
        config = {"theme": "light", "lang": "zh"}
        await ctx.db.set(f"user_config:{event.sender_id}", config)

    reply = f"你的主题设置是: {config['theme']}"
    await ctx.platform.send(event.session_id, reply)
```

### 4. 注册 Web API

```python
@provide_capability(
    name="my_plugin.get_status",
    description="获取插件状态",
)
async def get_status(request_id: str, payload: dict, cancel_token):
    return {"status": "running", "version": "1.0.0"}

@on_command("setup_api")
async def setup_api(event: MessageEvent, ctx: Context):
    await ctx.http.register_api(
        route="/status",
        handler=get_status,
        methods=["GET"]
    )
    await ctx.platform.send(event.session_id, "API 已注册")
```

---

## 注意事项

1. 所有客户端方法都是异步的
2. 远程调用可能失败，建议使用 try-except
3. Memory 适合语义搜索，DB 适合精确匹配
4. 文件操作使用 file service 注册令牌
5. 平台标识使用 UMO 格式：`"platform:instance:session_id"`
