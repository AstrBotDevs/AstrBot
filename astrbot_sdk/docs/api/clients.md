# 客户端 API 完整参考

## 概述

本文档详细介绍 `astrbot_sdk/clients/` 目录下所有客户端的 API。客户端是 Context 中暴露的各种能力接口，每个客户端负责一类特定的功能。

**模块路径**: `astrbot_sdk.clients`

---

## 目录

- [LLMClient - AI 对话客户端](#llmclient---ai-对话客户端)
- [MemoryClient - 记忆存储客户端](#memoryclient---记忆存储客户端)
- [DBClient - KV 数据库客户端](#dbclient---kv-数据库客户端)
- [PlatformClient - 平台消息客户端](#platformclient---平台消息客户端)
- [FileServiceClient - 文件服务客户端](#fileserviceclient---文件服务客户端)
- [HTTPClient - HTTP API 客户端](#httpclient---http-api-客户端)
- [MetadataClient - 插件元数据客户端](#metadataclient---插件元数据客户端)
- [ProviderClient - Provider 发现客户端](#providerclient---provider-发现客户端)
- [ProviderManagerClient - Provider 管理客户端](#providermanagerclient---provider-管理客户端)
- [PersonaManagerClient - 人格管理客户端](#personamanagerclient---人格管理客户端)
- [ConversationManagerClient - 对话管理客户端](#conversationmanagerclient---对话管理客户端)
- [KnowledgeBaseManagerClient - 知识库管理客户端](#knowledgebasemanagerclient---知识库管理客户端)

---

## LLMClient - AI 对话客户端

提供与大语言模型交互的能力，支持普通聊天、流式聊天和结构化响应。

### 导入

```python
from astrbot_sdk.clients import LLMClient, ChatMessage, LLMResponse
```

### 方法

#### `chat(prompt, *, system, history, contexts, provider_id, model, temperature, **kwargs)`

发送聊天请求并返回文本响应。

**参数**:
- `prompt` (`str`): 用户输入的提示文本
- `system` (`str | None`): 系统提示词
- `history` / `contexts` (`Sequence[ChatHistoryItem] | None`): 对话历史
- `provider_id` (`str | None`): 指定使用的 provider
- `model` (`str | None`): 指定模型名称
- `temperature` (`float | None`): 生成温度（0-1）
- `**kwargs`: 额外透传参数（如 `image_urls`, `tools`）

**返回**: `str` - 生成的文本内容

**示例**:

```python
# 简单对话
reply = await ctx.llm.chat("你好，介绍一下自己")

# 带系统提示词
reply = await ctx.llm.chat(
    "翻译成英文",
    system="你是一个专业翻译助手"
)

# 带对话历史
history = [
    ChatMessage(role="user", content="我叫小明"),
    ChatMessage(role="assistant", content="你好小明！"),
]
reply = await ctx.llm.chat("你记得我吗？", history=history)

# 使用字典格式的对话历史
history = [
    {"role": "user", "content": "我叫小明"},
    {"role": "assistant", "content": "你好小明！"},
]
reply = await ctx.llm.chat("你记得我吗？", history=history)
```

---

#### `chat_raw(prompt, *, system, history, contexts, provider_id, model, temperature, **kwargs)`

发送聊天请求并返回完整响应对象。

**返回**: `LLMResponse` 对象，包含：
- `text`: 生成的文本内容
- `usage`: Token 使用统计
- `finish_reason`: 结束原因
- `tool_calls`: 工具调用列表
- `role`: 响应角色

**示例**:

```python
response = await ctx.llm.chat_raw("写一首诗", temperature=0.8)
print(f"生成文本: {response.text}")
print(f"Token 使用: {response.usage}")
print(f"结束原因: {response.finish_reason}")

# 处理工具调用
if response.tool_calls:
    for tool_call in response.tool_calls:
        print(f"工具调用: {tool_call}")
```

---

#### `stream_chat(prompt, *, system, history, contexts, provider_id, model, temperature, **kwargs)`

流式聊天，逐块返回响应文本。

**返回**: 异步生成器，逐块生成文本

**示例**:

```python
# 实时显示生成内容
async for chunk in ctx.llm.stream_chat("讲一个故事"):
    print(chunk, end="", flush=True)

# 收集完整响应
full_text = ""
async for chunk in ctx.llm.stream_chat("写一篇文章"):
    full_text += chunk
    # 实时处理每个 chunk
```

---

## MemoryClient - 记忆存储客户端

提供 AI 记忆的存储和检索能力，支持语义搜索。与 DBClient 不同，MemoryClient 使用向量相似度进行语义匹配。

### 导入

```python
from astrbot_sdk.clients import MemoryClient
```

### 方法

#### `search(query)`

语义搜索记忆项。

**参数**:
- `query` (`str`): 搜索查询文本（自然语言）

**返回**: `list[dict]` - 匹配的记忆项列表，按相关度排序

**示例**:

```python
# 搜索用户偏好
results = await ctx.memory.search("用户喜欢什么颜色")
for item in results:
    print(f"Key: {item['key']}, Content: {item['content']}")

# 搜索对话摘要
summaries = await ctx.memory.search("之前讨论过什么技术话题")
```

---

#### `save(key, value, **extra)`

保存记忆项。

**参数**:
- `key` (`str`): 记忆项的唯一标识键
- `value` (`dict | None`): 要存储的数据字典
- `**extra`: 额外的键值对，会合并到 value 中

**示例**:

```python
# 保存用户偏好
await ctx.memory.save("user_pref", {
    "theme": "dark",
    "lang": "zh",
    "favorite_color": "blue"
})

# 使用关键字参数
await ctx.memory.save(
    "note",
    None,
    content="重要笔记",
    tags=["work"],
    timestamp="2024-01-01"
)
```

---

#### `get(key)`

精确获取单个记忆项。

**参数**:
- `key` (`str`): 记忆项的唯一键

**返回**: `dict | None` - 记忆项内容字典，不存在则返回 None

**示例**:

```python
pref = await ctx.memory.get("user_pref")
if pref:
    print(f"用户偏好主题: {pref.get('theme')}")
```

---

#### `delete(key)`

删除记忆项。

**参数**:
- `key` (`str`): 要删除的记忆项键名

**示例**:

```python
await ctx.memory.delete("old_note")
```

---

#### `save_with_ttl(key, value, ttl_seconds)`

保存带过期时间的记忆项。

**参数**:
- `key` (`str`): 记忆项的唯一标识键
- `value` (`dict`): 要存储的数据字典
- `ttl_seconds` (`int`): 存活时间（秒），必须大于 0

**异常**:
- `TypeError`: value 不是 dict 类型
- `ValueError`: ttl_seconds 小于 1

**示例**:

```python
# 保存临时会话状态，1小时后过期
await ctx.memory.save_with_ttl(
    "session_temp",
    {"state": "waiting", "step": 1},
    ttl_seconds=3600
)

# 保存验证码，5分钟后过期
await ctx.memory.save_with_ttl(
    "verification_code",
    {"code": "123456", "user_id": "user123"},
    ttl_seconds=300
)
```

---

#### `get_many(keys)`

批量获取多个记忆项。

**参数**:
- `keys` (`list[str]`): 记忆项键名列表

**返回**: `list[dict]` - 记忆项列表

**示例**:

```python
items = await ctx.memory.get_many(["pref1", "pref2", "pref3"])
for item in items:
    if item["value"]:
        print(f"{item['key']}: {item['value']}")
```

---

#### `delete_many(keys)`

批量删除多个记忆项。

**参数**:
- `keys` (`list[str]`): 要删除的记忆项键名列表

**返回**: `int` - 实际删除的记忆项数量

**示例**:

```python
deleted = await ctx.memory.delete_many(["old1", "old2", "old3"])
print(f"删除了 {deleted} 条记忆")
```

---

#### `stats()`

获取记忆系统统计信息。

**返回**: `dict` - 统计信息字典

**示例**:

```python
stats = await ctx.memory.stats()
print(f"记忆库共有 {stats['total_items']} 条记录")
if 'ttl_entries' in stats:
    print(f"其中 {stats['ttl_entries']} 条有过期时间")
```

---

## DBClient - KV 数据库客户端

提供键值存储能力，用于持久化插件数据。数据永久保存直到显式删除。

### 导入

```python
from astrbot_sdk.clients import DBClient
```

### 方法

#### `get(key)`

获取指定键的值。

**参数**:
- `key` (`str`): 数据键名

**返回**: `Any | None` - 存储的值，键不存在则返回 None

**示例**:

```python
data = await ctx.db.get("user_settings")
if data:
    print(data["theme"])
```

---

#### `set(key, value)`

设置键值对。

**参数**:
- `key` (`str`): 数据键名
- `value` (`Any`): 要存储的 JSON 值

**示例**:

```python
# 存储字典
await ctx.db.set("user_settings", {"theme": "dark", "lang": "zh"})

# 存储列表
await ctx.db.set("recent_commands", ["help", "status", "info"])

# 存储基本类型
await ctx.db.set("greeted", True)
await ctx.db.set("counter", 42)
await ctx.db.set("last_seen", "2024-01-01T00:00:00Z")
```

---

#### `delete(key)`

删除指定键的数据。

**参数**:
- `key` (`str`): 要删除的数据键名

**示例**:

```python
await ctx.db.delete("user_settings")
```

---

#### `list(prefix=None)`

列出匹配前缀的所有键。

**参数**:
- `prefix` (`str | None`): 键前缀过滤，None 表示列出所有键

**返回**: `list[str]` - 匹配的键名列表

**示例**:

```python
# 列出所有用户设置相关的键
keys = await ctx.db.list("user_")
# ["user_settings", "user_profile", "user_history"]

# 列出所有键
all_keys = await ctx.db.list()
```

---

#### `get_many(keys)`

批量获取多个键的值。

**参数**:
- `keys` (`Sequence[str]`): 要读取的键列表

**返回**: `dict[str, Any | None]` - 字典，value 为对应值（不存在则为 None）

**示例**:

```python
values = await ctx.db.get_many(["user:1", "user:2", "user:3"])
if values["user:1"] is None:
    print("user:1 不存在")

# 遍历结果
for key, value in values.items():
    print(f"{key}: {value}")
```

---

#### `set_many(items)`

批量写入多个键值对。

**参数**:
- `items` (`Mapping[str, Any] | Sequence[tuple[str, Any]]`): 键值对集合

**示例**:

```python
# 使用字典
await ctx.db.set_many({
    "user:1": {"name": "Alice"},
    "user:2": {"name": "Bob"},
    "user:3": {"name": "Charlie"}
})

# 使用元组列表
await ctx.db.set_many([
    ("counter:1", 10),
    ("counter:2", 20),
    ("counter:3", 30)
])
```

---

#### `watch(prefix=None)`

订阅 KV 变更事件（流式）。

**参数**:
- `prefix` (`str | None`): 键前缀过滤

**返回**: 异步迭代器，产生变更事件

**事件格式**: `{"op": "set"|"delete", "key": str, "value": Any|None}`

**示例**:

```python
# 监听所有变更
async for event in ctx.db.watch():
    print(f"{event['op']}: {event['key']}")

# 监听特定前缀的变更
async for event in ctx.db.watch("user:"):
    if event["op"] == "set":
        print(f"用户 {event['key']} 更新: {event['value']}")
    else:
        print(f"用户 {event['key']} 删除")
```

---

## PlatformClient - 平台消息客户端

提供向聊天平台发送消息和获取信息的能力。

### 导入

```python
from astrbot_sdk.clients import PlatformClient
```

### 方法

#### `send(session, text)`

发送文本消息。

**参数**:
- `session` (`str | SessionRef | MessageSession`): 统一消息来源标识
- `text` (`str`): 要发送的文本内容

**返回**: `dict[str, Any]` - 发送结果

**示例**:

```python
# 使用字符串 UMO
await ctx.platform.send(
    "qq:group:123456",
    "大家好！"
)

# 使用 MessageSession
from astrbot_sdk.message_session import MessageSession

session = MessageSession(
    platform_id="qq",
    message_type="group",
    session_id="123456"
)
await ctx.platform.send(session, "你好！")

# 使用事件中的 session_id
await ctx.platform.send(event.session_id, "收到您的消息！")
```

---

#### `send_image(session, image_url)`

发送图片消息。

**参数**:
- `session`: 会话标识
- `image_url` (`str`): 图片 URL 或本地文件路径

**返回**: `dict[str, Any]` - 发送结果

**示例**:

```python
# 使用 URL
await ctx.platform.send_image(
    event.session_id,
    "https://example.com/image.png"
)

# 使用本地路径
await ctx.platform.send_image(
    "qq:private:789",
    "/path/to/local/image.jpg"
)
```

---

#### `send_chain(session, chain)`

发送富消息链。

**参数**:
- `session`: 会话标识
- `chain` (`MessageChain | list[BaseMessageComponent] | list[dict]`): 消息链

**返回**: `dict[str, Any]` - 发送结果

**示例**:

```python
from astrbot_sdk.message_components import Plain, Image

# 使用 MessageChain
chain = MessageChain([
    Plain("你好 "),
    At("123456"),
    Plain("！"),
])
await ctx.platform.send_chain(event.session_id, chain)

# 使用组件列表
await ctx.platform.send_chain(
    event.session_id,
    [Plain("文本"), Image(url="https://example.com/img.jpg")]
)

# 使用序列化的 payload
await ctx.platform.send_chain(
    event.session_id,
    [
        {"type": "text", "data": {"text": "文本"}},
        {"type": "image", "data": {"url": "https://example.com/a.png"}}
    ]
)
```

---

#### `send_by_session(session, content)`

主动向指定会话发送消息。

**参数**:
- `session`: 会话标识
- `content`: 消息内容（支持多种格式）

**示例**:

```python
# 发送文本
await ctx.platform.send_by_session("qq:group:123456", "公告：...")

# 发送消息链
chain = MessageChain([Plain("重要通知"), Image.fromURL(...)])
await ctx.platform.send_by_session("qq:group:123456", chain)
```

---

#### `send_by_id(platform_id, session_id, content, *, message_type)`

主动向指定平台会话发送消息。

**参数**:
- `platform_id` (`str`): 平台 ID
- `session_id` (`str`): 会话 ID
- `content`: 消息内容
- `message_type` (`str`): 消息类型（`"private"` 或 `"group"`）

**示例**:

```python
# 发送私聊消息
await ctx.platform.send_by_id(
    platform_id="qq",
    session_id="123456",
    content="Hello",
    message_type="private"
)

# 发送群消息
await ctx.platform.send_by_id(
    platform_id="qq",
    session_id="789",
    content="群公告",
    message_type="group"
)
```

---

#### `get_members(session)`

获取群组成员列表。

**参数**:
- `session`: 群组会话标识

**返回**: `list[dict]` - 成员信息列表

**示例**:

```python
members = await ctx.platform.get_members("qq:group:123456")
for member in members:
    print(f"{member['nickname']} ({member['user_id']})")
```

---

## FileServiceClient - 文件服务客户端

提供文件令牌注册与解析能力，用于跨进程文件传递。

### 导入

```python
from astrbot_sdk.clients import FileServiceClient, FileRegistration
```

### 方法

#### `register_file(path, timeout=None)`

注册文件到文件服务，获取访问令牌。

**参数**:
- `path` (`str`): 文件路径
- `timeout` (`float | None`): 超时时间（秒）

**返回**: `str` - 文件访问令牌

**示例**:

```python
token = await ctx.files.register_file("/path/to/file.jpg", timeout=3600)
```

---

#### `handle_file(token)`

通过令牌解析文件路径。

**参数**:
- `token` (`str`): 文件访问令牌

**返回**: `str` - 文件路径

**示例**:

```python
path = await ctx.files.handle_file(token)
with open(path, 'rb') as f:
    data = f.read()
```

---

## HTTPClient - HTTP API 客户端

提供 Web API 注册能力，允许插件暴露自定义 HTTP 端点。

### 导入

```python
from astrbot_sdk.clients import HTTPClient
```

### 方法

#### `register_api(route, handler_capability=None, *, handler=None, methods=None, description="")`

注册 Web API 端点。

**参数**:
- `route` (`str`): API 路由路径
- `handler_capability` (`str | None`): 处理此路由的 capability 名称
- `handler` (`Any | None`): 使用 `@provide_capability` 标记的方法引用
- `methods` (`list[str] | None`): HTTP 方法列表
- `description` (`str`): API 描述

**示例**:

```python
from astrbot_sdk.decorators import provide_capability

# 1. 声明处理 HTTP 请求的 capability
@provide_capability(
    name="my_plugin.http_handler",
    description="处理 /my-api 的 HTTP 请求"
)
async def handle_http_request(request_id: str, payload: dict, cancel_token):
    return {"status": 200, "body": {"result": "ok"}}

# 2. 注册路由
await ctx.http.register_api(
    route="/my-api",
    handler_capability="my_plugin.http_handler",
    methods=["GET", "POST"],
    description="我的 API"
)

# 或使用 handler 参数
await ctx.http.register_api(
    route="/my-api",
    handler=handle_http_request,
    methods=["GET"]
)
```

---

#### `unregister_api(route, methods=None)`

注销 Web API 端点。

**参数**:
- `route` (`str`): API 路由路径
- `methods` (`list[str] | None`): HTTP 方法列表

**示例**:

```python
await ctx.http.unregister_api("/my-api")
```

---

#### `list_apis()`

列出当前插件注册的所有 API。

**返回**: `list[dict]` - API 列表

**示例**:

```python
apis = await ctx.http.list_apis()
for api in apis:
    print(f"{api['route']}: {api['methods']}")
```

---

## MetadataClient - 插件元数据客户端

提供插件元数据查询能力。

### 导入

```python
from astrbot_sdk.clients import MetadataClient, PluginMetadata
```

### 方法

#### `get_plugin(name)`

获取指定插件的元数据。

**参数**:
- `name` (`str`): 插件名称

**返回**: `PluginMetadata | None` - 插件元数据

**示例**:

```python
plugin = await ctx.metadata.get_plugin("another_plugin")
if plugin:
    print(f"插件: {plugin.display_name}")
    print(f"版本: {plugin.version}")
```

---

#### `list_plugins()`

获取所有插件的元数据列表。

**返回**: `list[PluginMetadata]`

**示例**:

```python
plugins = await ctx.metadata.list_plugins()
for plugin in plugins:
    print(f"{plugin.display_name} v{plugin.version} - {plugin.author}")
```

---

#### `get_current_plugin()`

获取当前插件的元数据。

**返回**: `PluginMetadata | None`

**示例**:

```python
current = await ctx.metadata.get_current_plugin()
if current:
    print(f"当前插件: {current.name} v{current.version}")
```

---

#### `get_plugin_config(name=None)`

获取插件配置。

**参数**:
- `name` (`str | None`): 插件名称，None 表示当前插件

**返回**: `dict | None` - 插件配置字典

**注意**: 只能查询当前插件自己的配置

**示例**:

```python
# 获取当前插件配置
config = await ctx.metadata.get_plugin_config()
if config:
    api_key = config.get("api_key")

# 获取其他插件配置会失败并返回 None
other_config = await ctx.metadata.get_plugin_config("other_plugin")
# other_config 为 None，并记录警告日志
```

---

## ProviderClient - Provider 发现客户端

提供 Provider 发现和查询能力。

### 导入

```python
from astrbot_sdk.clients import ProviderClient
```

### 方法

#### `list_all()`

列出所有聊天 Provider。

**返回**: `list[ProviderMeta]`

**示例**:

```python
providers = await ctx.providers.list_all()
for p in providers:
    print(f"{p.id}: {p.model}")
```

---

#### `list_tts()`

列出所有 TTS Provider。

**返回**: `list[ProviderMeta]`

---

#### `list_stt()`

列出所有 STT Provider。

**返回**: `list[ProviderMeta]`

---

#### `list_embedding()`

列出所有 Embedding Provider。

**返回**: `list[ProviderMeta]`

---

#### `list_rerank()`

列出所有 Rerank Provider。

**返回**: `list[ProviderMeta]`

---

#### `get(provider_id)`

获取指定 Provider 的代理。

**参数**:
- `provider_id` (`str`): Provider ID

**返回**: `ProviderProxy | None`

---

#### `get_using_chat(umo=None)`

获取当前使用的聊天 Provider。

**参数**:
- `umo` (`str | None`): 统一消息来源标识

**返回**: `ProviderMeta | None`

---

#### `get_using_tts(umo=None)`

获取当前使用的 TTS Provider。

---

#### `get_using_stt(umo=None)`

获取当前使用的 STT Provider。

---

## ProviderManagerClient - Provider 管理客户端

提供 Provider 的动态管理能力。

### 导入

```python
from astrbot_sdk.clients import ProviderManagerClient
```

### 方法

#### `set_provider(provider_id, provider_type, umo=None)`

设置当前使用的 Provider。

**参数**:
- `provider_id` (`str`): Provider ID
- `provider_type` (`ProviderType | str`): Provider 类型
- `umo` (`str | None`): 统一消息来源标识

---

#### `get_provider_by_id(provider_id)`

通过 ID 获取 Provider 记录。

---

#### `load_provider(provider_config)`

加载 Provider。

---

#### `create_provider(provider_config)`

创建新 Provider。

---

#### `update_provider(origin_provider_id, new_config)`

更新 Provider 配置。

---

#### `delete_provider(provider_id=None, provider_source_id=None)`

删除 Provider。

---

#### `get_insts()`

获取所有已管理的 Provider 实例。

---

#### `watch_changes()`

订阅 Provider 变更事件（流式）。

---

## PersonaManagerClient - 人格管理客户端

提供人格（Persona）的增删改查能力。

### 导入

```python
from astrbot_sdk.clients import PersonaManagerClient
```

### 方法

#### `get_persona(persona_id)`

获取指定人格。

---

#### `get_all_personas()`

获取所有人脸列表。

---

#### `create_persona(params)`

创建新人格。

---

#### `update_persona(persona_id, params)`

更新人格。

---

#### `delete_persona(persona_id)`

删除人格。

---

## ConversationManagerClient - 对话管理客户端

提供对话的创建、切换、更新、删除和查询能力。

### 导入

```python
from astrbot_sdk.clients import ConversationManagerClient
```

### 方法

#### `new_conversation(session, params=None)`

创建新对话。

---

#### `switch_conversation(session, conversation_id)`

切换当前对话。

---

#### `delete_conversation(session, conversation_id=None)`

删除对话。

---

#### `get_conversation(session, conversation_id, create_if_not_exists=False)`

获取对话。

---

#### `get_conversations(session=None, platform_id=None)`

获取对话列表。

---

#### `update_conversation(session, conversation_id=None, params=None)`

更新对话。

---

## KnowledgeBaseManagerClient - 知识库管理客户端

提供知识库的创建、查询和删除能力。

### 导入

```python
from astrbot_sdk.clients import KnowledgeBaseManagerClient
```

### 方法

#### `get_kb(kb_id)`

获取知识库。

---

#### `create_kb(params)`

创建新知识库。

---

#### `delete_kb(kb_id)`

删除知识库。

---

## 使用示例

### 基本对话流程

```python
@on_message()
async def handle_message(event: MessageEvent, ctx: Context):
    reply = await ctx.llm.chat(event.message_content)
    await ctx.platform.send(event.session_id, reply)
```

### 带历史的对话

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

### 使用数据库持久化

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

1. 所有客户端方法都是异步的，需要使用 `await`
2. 远程调用可能失败，建议使用 try-except 处理
3. Memory 适合语义搜索，DB 适合精确匹配
4. 文件操作使用 file service 注册令牌
5. 平台标识使用 UMO 格式：`"platform:instance:session_id"`

---

**版本**: v4.0
**模块**: `astrbot_sdk.clients`
**最后更新**: 2026-03-17
