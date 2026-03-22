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
- [MessageHistoryManagerClient - 消息历史管理客户端](#messagehistorymanagerclient---消息历史管理客户端)
- [KnowledgeBaseManagerClient - 知识库管理客户端](#knowledgebasemanagerclient---知识库管理客户端)
- [RegistryClient - Handler 注册表客户端](#registryclient---handler-注册表客户端)
- [SkillClient - 技能注册客户端](#skillclient---技能注册客户端)
- [SessionPluginManager - 会话插件管理器](#sessionpluginmanager---会话插件管理器)
- [SessionServiceManager - 会话服务管理器](#sessionservicemanager---会话服务管理器)

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

提供 AI 记忆的存储和检索能力，支持语义搜索。与 DBClient 和 MessageHistoryManagerClient 不同，
MemoryClient 主要用于可检索的 AI 上下文，而不是精确保存原始消息记录。

### 导入

```python
from astrbot_sdk.clients import MemoryClient
```

### 方法

#### `search(query, *, mode="auto", limit=None, min_score=None, provider_id=None)`

搜索记忆项。默认会在存在 embedding provider 时执行 hybrid 检索，
否则退化为关键词检索。

**参数**:
- `query` (`str`): 搜索查询文本（自然语言）
- `mode` (`Literal["auto", "keyword", "vector", "hybrid"]`): 搜索模式
- `limit` (`int | None`): 最大返回条数
- `min_score` (`float | None`): 最低分数阈值
- `provider_id` (`str | None`): 指定 embedding provider

**返回**: `list[dict]` - 匹配的记忆项列表。每项至少包含 `key`、`value`、`score`、`match_type`

**示例**:

```python
# 搜索用户偏好
results = await ctx.memory.search("用户喜欢什么颜色", mode="hybrid", limit=5)
for item in results:
    print(item["key"], item["score"], item["match_type"])

# 强制使用关键词检索
keyword_hits = await ctx.memory.search("blue", mode="keyword", min_score=0.9)

# 使用当前激活的 embedding provider 执行向量检索
vector_hits = await ctx.memory.search("之前讨论过什么技术话题", mode="vector")
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

# 显式指定检索文本
await ctx.memory.save(
    "profile:alice",
    {
        "name": "Alice",
        "city": "Shanghai",
        "embedding_text": "Alice 喜欢蓝色、海边和摄影",
    },
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
if 'indexed_items' in stats:
    print(f"已建立索引: {stats['indexed_items']}")
if 'embedded_items' in stats:
    print(f"已向量化: {stats['embedded_items']}")
if 'dirty_items' in stats:
    print(f"待重建索引: {stats['dirty_items']}")
```

---

## DBClient - KV 数据库客户端

提供键值存储能力，用于持久化插件数据。数据永久保存直到显式删除，且运行时会自动对 key 做插件级命名空间隔离。

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

返回的 key 是当前插件视角的原始 key，不包含运行时内部命名空间前缀。

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

事件中的 `key` 也是当前插件视角的原始 key。

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
- `route` (`str`): API 路由路径。当前实现会拦截包含 `..` 的路径和部分明显非法输入；建议使用以 `/` 开头、没有重复斜杠的规范化路径
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
- `methods` (`list[str] | None`): HTTP 方法列表，`None` 表示移除当前插件在该 route 下注册的全部方法

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

# 获取其他插件配置会抛 PermissionError
await ctx.metadata.get_plugin_config("other_plugin")
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
仅 `reserved/system` 插件可用。普通插件调用这些方法会收到 `provider.manager.* is restricted to reserved/system plugins` 错误；普通插件应优先使用 `ProviderClient` 进行只读查询。

### 导入

```python
from astrbot_sdk.clients import ProviderManagerClient
```

### 方法

#### `set_provider(provider_id, provider_type, umo=None)`

设置当前全局生效的 Provider。
`umo` 只会出现在变更事件中，不会让 Provider 选择按会话隔离。

**参数**:
- `provider_id` (`str`): Provider ID
- `provider_type` (`ProviderType | str`): Provider 类型
- `umo` (`str | None`): 统一消息来源标识

**示例**:

```python
from astrbot_sdk.llm.entities import ProviderType

await ctx.provider_manager.set_provider(
    "my_provider",
    ProviderType.CHAT_COMPLETION,
    umo=event.session_id,
)
```

---

#### `get_provider_by_id(provider_id)`

通过 ID 获取 Provider 记录。

---

#### `load_provider(provider_config)`

加载 Provider。

---

#### `create_provider(provider_config)`

创建新 Provider。

`provider_config` 至少应包含 `id`、`type` 和 `provider_type`。例如：

```python
record = await ctx.provider_manager.create_provider(
    {
        "id": "my_provider",
        "type": "openai",
        "provider_type": "chat_completion",
        "model": "gpt-4",
    }
)
```

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

当人格不存在时会抛出 `ValueError`，而不是返回 `None`。

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

#### `get_current_conversation(session, create_if_not_exists=False)`

获取当前 session 正在使用的对话记录。

这个方法适合“跟随 AstrBot 原生当前会话状态”的插件，例如：
- 给当前会话切换 persona
- 判断当前主聊天是否已经在某个 persona 下
- 在 `waiting_llm_request` / `llm_request` hook 中对当前对话做增强

---

#### `get_conversations(session=None, platform_id=None)`

获取对话列表。

---

#### `update_conversation(session, conversation_id=None, params=None)`

更新对话。

---

## MessageHistoryManagerClient - 消息历史管理客户端

按 `MessageSession` 精确保存原始消息组件、发送者和元数据。适合审计、回溯、分页读取和按时间清理。
如果要做语义召回或向量检索，请继续使用 `MemoryClient`。

### 导入

```python
from astrbot_sdk.clients import (
    MessageHistoryManagerClient,
    MessageHistoryPage,
    MessageHistoryRecord,
    MessageHistorySender,
)
from astrbot_sdk.message.session import MessageSession
from astrbot_sdk.message.components import Plain
```

### 方法

#### `list(session, *, cursor=None, limit=50)`

分页列出某个会话的消息历史。

**参数**:
- `session` (`MessageSession`): 目标会话，必须是 `MessageSession`
- `cursor` (`str | None`): 分页游标，建议直接使用上一页返回的 `next_cursor`
- `limit` (`int`): 返回条数，默认 `50`

**返回**: `MessageHistoryPage` - 包含 `records`、`next_cursor`、`total`

**示例**:

```python
session = MessageSession(
    platform_id=event.platform_id,
    message_type=event.message_type,
    session_id=event.session_id,
)
page = await ctx.message_history.list(session, limit=20)
for record in page.records:
    print(record.id, record.sender.sender_name, record.parts)
```

---

#### `get(session, record_id)` / `get_by_id(session, record_id)`

按记录 ID 读取单条消息历史。

**参数**:
- `session` (`MessageSession`): 目标会话
- `record_id` (`int`): 记录 ID

**返回**: `MessageHistoryRecord | None`

**示例**:

```python
session = MessageSession(
    platform_id=event.platform_id,
    message_type=event.message_type,
    session_id=event.session_id,
)
record = await ctx.message_history.get(session, 1)
same_record = await ctx.message_history.get_by_id(session, 1)
```

---

#### `append(session, *, parts, sender, metadata=None, idempotency_key=None)`

追加一条消息历史记录。

**参数**:
- `session` (`MessageSession`): 目标会话
- `parts` (`list[BaseMessageComponent]`): 原始消息组件列表
- `sender` (`MessageHistorySender`): 发送者信息，也可传可验证为该模型的 `dict`
- `metadata` (`dict[str, Any] | None`): 附加元数据
- `idempotency_key` (`str | None`): 幂等键；相同 key 会返回现有记录而不是重复写入

**返回**: `MessageHistoryRecord`

**示例**:

```python
session = MessageSession(
    platform_id=event.platform_id,
    message_type=event.message_type,
    session_id=event.session_id,
)
record = await ctx.message_history.append(
    session,
    parts=[Plain(event.message_content, convert=False)],
    sender=MessageHistorySender(
        sender_id=event.sender_id,
        sender_name=event.sender_name,
    ),
    metadata={"source": "handler"},
    idempotency_key="incoming:demo-user:hello",
)
print(record.created_at, record.idempotency_key)
```

---

#### `delete_before(session, *, before)` / `delete_after(session, *, after)`

按时间边界删除某个会话内的消息历史。

**参数**:
- `session` (`MessageSession`): 目标会话
- `before` / `after` (`datetime`): 时间边界，建议使用带时区的 `datetime`

**返回**: `int` - 删除的记录数

**示例**:

```python
from datetime import datetime, timezone

deleted = await ctx.message_history.delete_before(
    session,
    before=datetime(2026, 3, 22, tzinfo=timezone.utc),
)
```

---

#### `delete_all(session)`

删除某个会话的全部消息历史。

**参数**:
- `session` (`MessageSession`): 目标会话

**返回**: `int` - 删除的记录数

**示例**:

```python
deleted = await ctx.message_history.delete_all(session)
print(f"deleted={deleted}")
```

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

参数 `kb_id` 是知识库的唯一 ID，不是 `kb_name`。

---

#### `create_kb(params)`

创建新知识库。
返回的 `KnowledgeBaseRecord` 中包含运行时生成的 `kb_id`，后续更新、删除和文档操作都应使用这个 `kb_id`。

---

#### `delete_kb(kb_id)`

删除知识库。

---

## RegistryClient - Handler 注册表客户端

handler 注册表查询与白名单管理客户端，用于查询 handler 信息并管理 handler 白名单。

### 导入

```python
from astrbot_sdk.clients import RegistryClient, HandlerMetadata
```

### 方法

#### `get_handlers_by_event_type(event_type)`

获取指定事件类型的所有 handler。

**参数**:
- `event_type` (`str`): 事件类型

**返回**: `list[HandlerMetadata]`

**示例**:

```python
handlers = await ctx.registry.get_handlers_by_event_type("message")
for h in handlers:
    print(f"{h.handler_full_name}: {h.description}")
```

---

#### `get_handler_by_full_name(full_name)`

通过完整名称获取 handler 元数据。

**参数**:
- `full_name` (`str`): handler 完整名称（格式：`plugin_name.handler_name`）

**返回**: `HandlerMetadata | None`

**示例**:

```python
handler = await ctx.registry.get_handler_by_full_name("my_plugin.on_message")
if handler:
    print(f"触发类型: {handler.trigger_type}")
    print(f"优先级: {handler.priority}")
    print(f"需要管理员: {handler.require_admin}")
```

---

#### `set_handler_whitelist(plugin_names)`

设置 handler 白名单。

**参数**:
- `plugin_names` (`list[str] | set[str] | None`): 插件名称列表，None 表示清除白名单

**返回**: `list[str] | None` - 实际设置的白名单

**示例**:

```python
# 设置白名单
await ctx.registry.set_handler_whitelist(["plugin_a", "plugin_b"])

# 清空白名单
await ctx.registry.set_handler_whitelist(None)
```

---

#### `get_handler_whitelist()`

获取当前 handler 白名单。

**返回**: `list[str] | None`

**示例**:

```python
whitelist = await ctx.registry.get_handler_whitelist()
if whitelist:
    print(f"当前白名单: {whitelist}")
```

---

#### `clear_handler_whitelist()`

清除 handler 白名单。

**示例**:

```python
await ctx.registry.clear_handler_whitelist()
```

---

## SkillClient - 技能注册客户端

技能注册客户端，用于注册和管理技能。

### 导入

```python
from astrbot_sdk.clients import SkillClient, SkillRegistration
```

### 方法

#### `register(*, name, path, description="")`

注册一个技能。

**参数**:
- `name` (`str`): 技能名称
- `path` (`str`): 技能路径
- `description` (`str`): 技能描述

**返回**: `SkillRegistration`

**示例**:

```python
skill = await ctx.skills.register(
    name="my_skill",
    path="/path/to/skill",
    description="我的技能描述"
)
print(f"技能已注册: {skill.name}")
```

---

#### `unregister(name)`

注销技能。

**参数**:
- `name` (`str`): 技能名称

**返回**: `bool` - 是否成功注销

**示例**:

```python
removed = await ctx.skills.unregister("my_skill")
if removed:
    print("技能已注销")
```

---

#### `list()`

列出当前已注册的技能。

**返回**: `list[SkillRegistration]`

**示例**:

```python
skills = await ctx.skills.list()
for skill in skills:
    print(f"{skill.name}: {skill.skill_dir}")
```

---

## SessionPluginManager - 会话插件管理器

会话级别的插件状态管理器，用于检查和过滤会话相关的插件状态。

### 导入

```python
from astrbot_sdk.clients import SessionPluginManager
```

### 方法

#### `is_plugin_enabled_for_session(session, plugin_name)`

检查插件在指定会话是否启用。

**参数**:
- `session` (`str | MessageSession | MessageEvent`): 会话标识
- `plugin_name` (`str`): 插件名称

**返回**: `bool`

**示例**:

```python
enabled = await ctx.session_plugins.is_plugin_enabled_for_session(
    session=event,
    plugin_name="my_plugin"
)
if not enabled:
    await event.reply("该插件在此会话已禁用")
```

---

#### `filter_handlers_by_session(session, handlers)`

根据会话过滤 handler 列表。

**参数**:
- `session` (`str | MessageSession | MessageEvent`): 会话标识
- `handlers` (`list[HandlerMetadata]`): handler 列表

**返回**: `list[HandlerMetadata]` - 过滤后的 handler 列表

**示例**:

```python
handlers = await ctx.registry.get_handlers_by_event_type("message")
filtered = await ctx.session_plugins.filter_handlers_by_session(
    session=event,
    handlers=handlers
)
print(f"可用 handler 数量: {len(filtered)}")
```

---

## SessionServiceManager - 会话服务管理器

会话级别的 LLM/TTS 服务状态管理器。

### 导入

```python
from astrbot_sdk.clients import SessionServiceManager
```

### 方法

#### `is_llm_enabled_for_session(session)`

检查 LLM 服务在指定会话是否启用。

**参数**:
- `session` (`str | MessageSession | MessageEvent`): 会话标识

**返回**: `bool`

**示例**:

```python
if await ctx.session_services.is_llm_enabled_for_session(event):
    reply = await ctx.llm.chat(prompt)
```

---

#### `set_llm_status_for_session(session, enabled)`

设置会话的 LLM 服务状态。

**参数**:
- `session` (`str | MessageSession | MessageEvent`): 会话标识
- `enabled` (`bool`): 是否启用

**示例**:

```python
await ctx.session_services.set_llm_status_for_session(event, enabled=False)
await event.reply("LLM 已在此会话禁用")
```

---

#### `should_process_llm_request(event_or_session)`

检查是否应处理 LLM 请求（等同于 `is_llm_enabled_for_session`）。

**参数**:
- `event_or_session` (`str | MessageSession | MessageEvent`): 会话标识

**返回**: `bool`

**示例**:

```python
if await ctx.session_services.should_process_llm_request(event):
    reply = await ctx.llm.chat(prompt)
```

---

#### `is_tts_enabled_for_session(session)`

检查 TTS 服务在指定会话是否启用。

**参数**:
- `session` (`str | MessageSession | MessageEvent`): 会话标识

**返回**: `bool`

---

#### `set_tts_status_for_session(session, enabled)`

设置会话的 TTS 服务状态。

**参数**:
- `session` (`str | MessageSession | MessageEvent`): 会话标识
- `enabled` (`bool`): 是否启用

**示例**:

```python
await ctx.session_services.set_tts_status_for_session(event, enabled=True)
await event.reply("TTS 已在此会话启用")
```

---

#### `should_process_tts_request(event_or_session)`

检查是否应处理 TTS 请求（等同于 `is_tts_enabled_for_session`）。

**参数**:
- `event_or_session` (`str | MessageSession | MessageEvent`): 会话标识

**返回**: `bool`

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

如果你需要保留原始消息组件、发送者和按时间清理能力，应优先使用 `ctx.message_history`。

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
3. Memory 适合语义搜索，DB 适合结构化 KV，MessageHistory 适合精确保存原始消息记录
4. DB key 在运行时按插件隔离；`list()` 和 `watch()` 返回插件本地 key 视图
5. `HTTPClient.register_api()` 当前会拦截 `..` 等明显非法路径，但仍建议插件自行使用规范化 route；`unregister_api(route)` 默认移除该 route 下全部方法
6. 文件操作使用 file service 注册令牌
7. 平台标识使用 UMO 格式：`"platform:instance:session_id"`

---

**版本**: v4.0
**模块**: `astrbot_sdk.clients`
**最后更新**: 2026-03-22
