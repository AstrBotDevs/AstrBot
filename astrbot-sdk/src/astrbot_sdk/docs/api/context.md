# Context 类 - 插件运行时上下文完整参考

## 概述

`Context` 是插件运行时的核心上下文对象，每个 handler 调用都会创建一个新的 Context 实例。Context 组合了所有 capability 客户端，提供统一的访问接口。

**模块路径**: `astrbot_sdk.context.Context`

---

## 类定义

```python
@dataclass(slots=True)
class Context:
    # 基本属性
    peer: Any                          # 协议对等端
    plugin_id: str                     # 插件 ID
    logger: PluginLogger               # 日志器
    cancel_token: CancelToken          # 取消令牌

    # 能力客户端
    llm: LLMClient                    # LLM 客户端
    memory: MemoryClient              # 记忆客户端
    db: DBClient                      # 数据库客户端
    files: FileServiceClient          # 文件服务客户端
    platform: PlatformClient          # 平台客户端
    providers: ProviderClient         # Provider 客户端
    provider_manager: ProviderManagerClient  # Provider 管理客户端
    personas: PersonaManagerClient    # 人格管理客户端
    conversations: ConversationManagerClient  # 对话管理客户端
    kbs: KnowledgeBaseManagerClient   # 知识库管理客户端
    http: HTTPClient                  # HTTP 客户端
    metadata: MetadataClient          # 元数据客户端

    # 系统工具
    _llm_tool_manager: LLMToolManager
    _source_event_payload: dict[str, Any]

    # 别名
    persona_manager = personas
    conversation_manager = conversations
    kb_manager = kbs
```

---

## 导入方式

```python
# 从主模块导入（推荐）
from astrbot_sdk import Context

# 从子模块导入
from astrbot_sdk.context import Context

# 常用配套导入
from astrbot_sdk import MessageEvent  # 消息事件
from astrbot_sdk.decorators import on_command, on_message  # 装饰器
from astrbot_sdk.clients.llm import ChatMessage  # 聊天消息（用于历史记录）
```

---

## 基本属性

### `peer`

协议对等端，用于底层通信。

```python
# 类型: Any
# 说明: 内部使用，用于与 Core 通信
```

### `plugin_id`

当前插件的唯一标识符。

```python
# 类型: str
# 说明: 插件的名称，对应 plugin.yaml 中的 name 字段

ctx.logger.info(f"当前插件: {ctx.plugin_id}")
```

### `logger`

绑定了插件 ID 的日志器。

```python
# 类型: PluginLogger
# 说明: 自动添加 plugin_id 上下文

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

### `cancel_token`

取消令牌，用于长时间运行的任务中检查是否需要取消。

```python
# 类型: CancelToken

# 检查是否取消
ctx.cancel_token.raise_if_cancelled()

# 触发取消
ctx.cancel_token.cancel()

# 等待取消信号
await ctx.cancel_token.wait()

# 检查状态
if ctx.cancel_token.cancelled:
    print("操作已取消")
```

**使用场景**:

```python
async def long_operation(ctx: Context):
    for item in large_list:
        # 检查是否取消
        ctx.cancel_token.raise_if_cancelled()

        await process(item)
```

---

## 能力客户端

### 1. LLM 客户端 (ctx.llm)

提供 AI 对话能力。

```python
# 类型: LLMClient
```

#### 方法

##### `chat()`

简单对话。

```python
reply = await ctx.llm.chat("你好，介绍一下自己")

# 带系统提示
reply = await ctx.llm.chat(
    "翻译成英文",
    system="你是一个专业翻译助手"
)

# 带对话历史
from astrbot_sdk.clients.llm import ChatMessage

history = [
    ChatMessage(role="user", content="我叫小明"),
    ChatMessage(role="assistant", content="你好小明！"),
]
reply = await ctx.llm.chat("你记得我吗？", history=history)
```

##### `chat_raw()`

获取完整响应对象。

```python
response = await ctx.llm.chat_raw("写一首诗", temperature=0.8)
print(f"生成文本: {response.text}")
print(f"Token 使用: {response.usage}")
print(f"结束原因: {response.finish_reason}")
```

##### `stream_chat()`

流式对话。

```python
async for chunk in ctx.llm.stream_chat("讲一个故事"):
    print(chunk, end="", flush=True)
```

---

### 2. Memory 客户端 (ctx.memory)

提供语义搜索的记忆存储能力。

```python
# 类型: MemoryClient
```

#### 方法

##### `search()`

语义搜索。

```python
results = await ctx.memory.search("用户喜欢什么颜色")
for item in results:
    print(item["key"], item["content"])
```

##### `save()`

保存记忆。

```python
# 保存用户偏好
await ctx.memory.save("user_pref", {"theme": "dark", "lang": "zh"})

# 使用关键字参数
await ctx.memory.save("note", None, content="重要笔记", tags=["work"])
```

##### `get()`

获取记忆。

```python
pref = await ctx.memory.get("user_pref")
if pref:
    print(f"用户偏好主题: {pref.get('theme')}")
```

##### `save_with_ttl()`

保存带过期时间的记忆。

```python
# 保存临时会话状态，1小时后过期
await ctx.memory.save_with_ttl(
    "session_temp",
    {"state": "waiting"},
    ttl_seconds=3600
)
```

##### `delete()`

删除记忆。

```python
await ctx.memory.delete("old_note")
```

---

### 3. DB 客户端 (ctx.db)

提供键值存储能力，数据永久保存。

```python
# 类型: DBClient
```

#### 方法

##### `get() / set()`

基本读写。

```python
# 读取
data = await ctx.db.get("user_settings")
if data:
    print(data["theme"])

# 写入
await ctx.db.set("user_settings", {"theme": "dark", "lang": "zh"})
await ctx.db.set("greeted", True)
```

##### `delete()`

删除数据。

```python
await ctx.db.delete("user_settings")
```

##### `list()`

列出键。

```python
keys = await ctx.db.list("user_")
# ["user_settings", "user_profile", "user_history"]
```

##### `get_many() / set_many()`

批量操作。

```python
# 批量读取
values = await ctx.db.get_many(["user:1", "user:2"])

# 批量写入
await ctx.db.set_many({
    "user:1": {"name": "Alice"},
    "user:2": {"name": "Bob"}
})
```

##### `watch()`

监听变更事件。

```python
async for event in ctx.db.watch("user:"):
    print(f"{event['op']}: {event['key']}")
```

---

### 4. Files 客户端 (ctx.files)

提供文件令牌注册与解析能力。

```python
# 类型: FileServiceClient
```

#### 方法

##### `register_file()`

注册文件并获取令牌。

```python
token = await ctx.files.register_file("/path/to/file.jpg", timeout=3600)
```

##### `handle_file()`

通过令牌解析文件路径。

```python
path = await ctx.files.handle_file(token)
```

---

### 5. Platform 客户端 (ctx.platform)

提供向聊天平台发送消息和获取信息的能力。

```python
# 类型: PlatformClient
```

#### 方法

##### `send()`

发送文本消息。

```python
await ctx.platform.send("qq:group:123456", "大家好！")

# 使用 MessageSession
from astrbot_sdk.message_session import MessageSession

session = MessageSession(
    platform_id="qq",
    message_type="group",
    session_id="123456"
)
await ctx.platform.send(session, "你好！")
```

##### `send_image()`

发送图片。

```python
await ctx.platform.send_image(
    event.session_id,
    "https://example.com/image.png"
)
```

##### `send_chain()`

发送消息链。

```python
from astrbot_sdk.message_components import Plain, Image

chain = [Plain("文字"), Image(url="https://example.com/img.jpg")]
await ctx.platform.send_chain(event.session_id, chain)
```

##### `send_by_id()`

通过 ID 发送。

```python
await ctx.platform.send_by_id(
    platform_id="qq",
    session_id="user123",
    content="Hello",
    message_type="private"
)
```

##### `get_members()`

获取群组成员。

```python
members = await ctx.platform.get_members("qq:group:123456")
for member in members:
    print(f"{member['nickname']} ({member['user_id']})")
```

---

### 6. Providers 客户端 (ctx.providers)

提供 Provider 发现和查询能力。

```python
# 类型: ProviderClient
```

#### 方法

##### `list_all()`

列出所有 Provider。

```python
providers = await ctx.providers.list_all()
for p in providers:
    print(f"{p.id}: {p.model}")
```

##### `get_using_chat()`

获取当前使用的聊天 Provider。

```python
provider = await ctx.providers.get_using_chat()
if provider:
    print(f"当前使用: {provider.id}")
```

##### `list_tts() / list_stt() / list_embedding() / list_rerank()`

列出特定类型的 Provider。

```python
tts_providers = await ctx.providers.list_tts()
stt_providers = await ctx.providers.list_stt()
```

---

### 7. Provider Manager 客户端 (ctx.provider_manager)

提供 Provider 的动态管理能力。

```python
# 类型: ProviderManagerClient
```

#### 方法

##### `set_provider()`

设置当前使用的 Provider。

```python
from astrbot_sdk.llm.entities import ProviderType

await ctx.provider_manager.set_provider(
    "my_provider",
    ProviderType.TEXT_TO_TEXT,
    umo=event.session_id
)
```

##### `get_provider_by_id()`

获取 Provider 记录。

```python
record = await ctx.provider_manager.get_provider_by_id("my_provider")
```

##### `create_provider() / update_provider() / delete_provider()`

管理 Provider。

```python
# 创建
record = await ctx.provider_manager.create_provider({
    "id": "my_provider",
    "type": "openai",
    "model": "gpt-4"
})

# 更新
record = await ctx.provider_manager.update_provider(
    "my_provider",
    {"model": "gpt-4-turbo"}
)

# 删除
await ctx.provider_manager.delete_provider(provider_id="my_provider")
```

##### `watch_changes()`

监听 Provider 变更事件。

```python
async for event in ctx.provider_manager.watch_changes():
    print(f"Provider {event.provider_id} 变更")
```

---

### 8. Personas 客户端 (ctx.personas / ctx.persona_manager)

提供人格管理能力。

```python
# 类型: PersonaManagerClient
```

#### 方法

##### `get_persona() / get_all_personas()`

获取人格。

```python
# 获取单个人格
persona = await ctx.personas.get_persona("assistant")

# 获取所有人格
personas = await ctx.personas.get_all_personas()
```

##### `create_persona() / update_persona() / delete_persona()`

管理人格。

```python
from astrbot_sdk.clients import PersonaCreateParams

# 创建
persona = await ctx.personas.create_persona(PersonaCreateParams(
    persona_id="assistant",
    system_prompt="你是一个有用的助手。",
    begin_dialogs=["你好，有什么可以帮助你的？"]
))

# 更新
updated = await ctx.personas.update_persona(
    "assistant",
    PersonaUpdateParams(system_prompt="你是一个专业的编程助手。")
)

# 删除
await ctx.personas.delete_persona("old_persona")
```

---

### 9. Conversations 客户端 (ctx.conversations / ctx.conversation_manager)

提供对话管理能力。

```python
# 类型: ConversationManagerClient
```

#### 方法

##### `new_conversation()`

创建新对话。

```python
from astrbot_sdk.clients import ConversationCreateParams

conv_id = await ctx.conversations.new_conversation(
    event.session_id,
    ConversationCreateParams(
        title="新对话",
        persona_id="assistant"
    )
)
```

##### `switch_conversation()`

切换当前对话。

```python
await ctx.conversations.switch_conversation(
    event.session_id,
    "conv_123"
)
```

##### `delete_conversation()`

删除对话。

```python
# 删除指定对话
await ctx.conversations.delete_conversation(
    event.session_id,
    "conv_123"
)

# 删除当前对话
await ctx.conversations.delete_conversation(event.session_id)
```

##### `get_conversation() / get_conversations()`

获取对话。

```python
# 获取单个对话
conv = await ctx.conversations.get_conversation(
    event.session_id,
    "conv_123",
    create_if_not_exists=True
)

# 获取对话列表
convs = await ctx.conversations.get_conversations(event.session_id)
```

##### `update_conversation()`

更新对话。

```python
from astrbot_sdk.clients import ConversationUpdateParams

await ctx.conversations.update_conversation(
    event.session_id,
    "conv_123",
    ConversationUpdateParams(title="新标题")
)
```

---

### 10. Knowledge Bases 客户端 (ctx.kbs / ctx.kb_manager)

提供知识库管理能力。

```python
# 类型: KnowledgeBaseManagerClient
```

#### 方法

##### `get_kb()`

获取知识库。

```python
kb = await ctx.kbs.get_kb("my_kb")
if kb:
    print(f"知识库: {kb.kb_name}")
    print(f"文档数: {kb.doc_count}")
```

##### `create_kb()`

创建知识库。

```python
from astrbot_sdk.clients import KnowledgeBaseCreateParams

kb = await ctx.kbs.create_kb(KnowledgeBaseCreateParams(
    kb_name="技术文档",
    embedding_provider_id="openai_embedding",
    description="存储技术文档",
    emoji="📚"
))
```

##### `delete_kb()`

删除知识库。

```python
deleted = await ctx.kbs.delete_kb("my_kb")
if deleted:
    print("知识库已删除")
```

---

### 11. HTTP 客户端 (ctx.http)

提供 Web API 注册能力。

```python
# 类型: HTTPClient
```

#### 方法

##### `register_api()`

注册 API 端点。

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
    methods=["GET", "POST"],
    description="我的 API"
)
```

##### `unregister_api()`

注销 API。

```python
await ctx.http.unregister_api("/my-api")
```

##### `list_apis()`

列出当前插件注册的所有 API。

```python
apis = await ctx.http.list_apis()
for api in apis:
    print(f"{api['route']}: {api['methods']}")
```

---

### 12. Metadata 客户端 (ctx.metadata)

提供插件元数据查询能力。

```python
# 类型: MetadataClient
```

#### 方法

##### `get_plugin()`

获取指定插件信息。

```python
plugin = await ctx.metadata.get_plugin("another_plugin")
if plugin:
    print(f"插件: {plugin.display_name}")
    print(f"版本: {plugin.version}")
    print(f"作者: {plugin.author}")
```

##### `list_plugins()`

列出所有插件。

```python
plugins = await ctx.metadata.list_plugins()
for plugin in plugins:
    print(f"{plugin.display_name} v{plugin.version} - {plugin.author}")
```

##### `get_current_plugin()`

获取当前插件信息。

```python
current = await ctx.metadata.get_current_plugin()
if current:
    print(f"当前插件: {current.name} v{current.version}")
```

##### `get_plugin_config()`

获取插件配置。

```python
config = await ctx.metadata.get_plugin_config()
if config:
    api_key = config.get("api_key")
```

**注意**: 只能查询当前插件自己的配置

---

### 13. Session Plugins 客户端 (ctx.session_plugins)

提供会话级别的插件状态管理能力。

```python
# 类型: SessionPluginManager
```

#### 方法

##### `is_plugin_enabled_for_session()`

检查插件是否对指定会话启用。

```python
enabled = await ctx.session_plugins.is_plugin_enabled_for_session(
    event,  # 可以是 event, session 字符串, 或 MessageSession
    "my_plugin"
)
```

##### `filter_handlers_by_session()`

过滤会话启用的处理器。

```python
from astrbot_sdk.clients.registry import HandlerMetadata

enabled_handlers = await ctx.session_plugins.filter_handlers_by_session(
    event,
    all_handlers
)
```

---

### 14. Session Services 客户端 (ctx.session_services)

提供会话级别的 LLM/TTS 服务状态管理能力。

```python
# 类型: SessionServiceManager
```

#### 方法

##### `is_llm_enabled_for_session()`

检查 LLM 是否对指定会话启用。

```python
enabled = await ctx.session_services.is_llm_enabled_for_session(event)
if not enabled:
    await event.reply("LLM 服务已禁用")
```

##### `set_llm_status_for_session()`

设置 LLM 服务状态。

```python
# 启用 LLM
await ctx.session_services.set_llm_status_for_session(event, True)

# 禁用 LLM
await ctx.session_services.set_llm_status_for_session(event, False)
```

##### `should_process_llm_request()`

判断是否应该处理 LLM 请求。

```python
if await ctx.session_services.should_process_llm_request(event):
    response = await ctx.llm.chat("...")
```

---

## 系统工具方法

### `get_data_dir()`

获取插件数据目录路径。

```python
data_dir = await ctx.get_data_dir()
print(f"数据目录: {data_dir}")
```

**返回**: `Path` - 数据目录的 Path 对象

---

### `text_to_image()`

将文本渲染为图片。

```python
url = await ctx.text_to_image("Hello World", return_url=True)
```

**参数**:
- `text`: 要渲染的文本
- `return_url`: 是否返回 URL（False 则返回本地路径）

**返回**: `str` - 图片 URL 或路径

---

### `html_render()`

渲染 HTML 模板。

```python
url = await ctx.html_render(
    tmpl="<h1>{{ title }}</h1>",
    data={"title": "标题"}
)
```

**参数**:
- `tmpl`: HTML 模板内容
- `data`: 模板数据
- `return_url`: 是否返回 URL
- `options`: 渲染选项

**返回**: `str` - 渲染结果 URL 或路径

---

### `send_message()`

向会话发送消息。

```python
await ctx.send_message(event.session_id, "消息内容")
```

**参数**:
- `session`: 会话标识
- `content`: 消息内容（支持多种格式）

---

### `send_message_by_id()`

通过 ID 向平台发送消息。

```python
await ctx.send_message_by_id(
    type="private",
    id="user123",
    content="Hello",
    platform="qq"
)
```

---

### `register_task()`

注册后台任务。

```python
async def background_work():
    while True:
        await asyncio.sleep(60)
        ctx.logger.info("每分钟执行一次")

task = await ctx.register_task(background_work(), "定时任务")
```

**参数**:
- `task`: 可等待对象
- `desc`: 任务描述

**返回**: `asyncio.Task` - 任务对象

**注意**: 任务失败会自动记录日志，不会影响插件主流程

---

## LLM Tool 管理方法

### `get_llm_tool_manager()`

获取 LLM Tool 管理器。

```python
manager = ctx.get_llm_tool_manager()
```

---

### `add_llm_tools()`

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

---

### `activate_llm_tool() / deactivate_llm_tool()`

激活/停用 LLM 工具。

```python
await ctx.activate_llm_tool("my_tool")
await ctx.deactivate_llm_tool("my_tool")
```

---

### `register_llm_tool()`

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

---

### `unregister_llm_tool()`

取消注册 LLM 工具。

```python
await ctx.unregister_llm_tool("my_tool")
```

---

## 高级方法

### `tool_loop_agent()`

执行 Agent 工具循环。

**签名**:
```python
async def tool_loop_agent(
    self,
    request: ProviderRequest | None = None,
    **kwargs: Any
) -> LLMResponse
```

**参数**:
- `request`: ProviderRequest 对象，包含请求配置
- `**kwargs`: 额外的请求参数，会自动合并到 request

**返回**: `LLMResponse` - 包含工具调用结果的完整响应

**示例**:

```python
from astrbot_sdk.llm.entities import ProviderRequest

response = await ctx.tool_loop_agent(
    request=ProviderRequest(
        prompt="搜索天气",
        system_prompt="你是一个助手"
    )
)
print(response.text)
```

---

### `register_commands()`

注册命令（仅在 `astrbot_loaded` 或 `platform_loaded` 事件中可用）。

**签名**:
```python
async def register_commands(
    self,
    command_name: str,
    handler_full_name: str,
    *,
    desc: str = "",
    priority: int = 0,
    use_regex: bool = False,
    ignore_prefix: bool = False,
) -> None
```

**参数**:
- `command_name`: 命令名称
- `handler_full_name`: 处理函数的完整名称（如 `module.handler_name`）
- `desc`: 命令描述
- `priority`: 优先级
- `use_regex`: 是否使用正则匹配
- `ignore_prefix`: 是否忽略前缀（SDK 中不支持）

**异常**:
- `AstrBotError`: 如果在非加载事件中调用或设置 `ignore_prefix=True`

**示例**:

```python
@on_event("astrbot_loaded")
async def on_load(self, event, ctx: Context):
    await ctx.register_commands(
        command_name="my_cmd",
        handler_full_name="my_module.handle_cmd",
        desc="我的命令",
        priority=10
    )
```

---

### `get_platform()`

获取指定类型的平台兼容层实例。

**签名**:
```python
async def get_platform(self, platform_type: str) -> PlatformCompatFacade | None
```

**参数**:
- `platform_type`: 平台类型（如 "qq", "telegram"）

**返回**: `PlatformCompatFacade | None` - 平台兼容层实例

**示例**:

```python
platform = await ctx.get_platform("qq")
if platform:
    await platform.send_by_session("session_id", "消息")
```

---

### `get_platform_inst()`

获取指定 ID 的平台兼容层实例。

**签名**:
```python
async def get_platform_inst(self, platform_id: str) -> PlatformCompatFacade | None
```

**参数**:
- `platform_id`: 平台实例 ID

**返回**: `PlatformCompatFacade | None` - 平台兼容层实例

---

## PlatformCompatFacade

平台兼容层类，提供安全的平台元信息和主动发送能力。

### 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `id` | `str` | 平台实例 ID |
| `name` | `str` | 平台名称 |
| `type` | `str` | 平台类型 |
| `status` | `PlatformStatus` | 平台状态 |
| `errors` | `list[PlatformError]` | 错误列表 |
| `last_error` | `PlatformError \| None` | 最近错误 |
| `unified_webhook` | `bool` | 是否统一 webhook |

### 方法

#### `send()`

发送消息。

```python
await platform.send("session_id", "消息内容")
```

#### `send_by_session()`

通过会话发送消息。

```python
await platform.send_by_session("platform:private:123", "消息")
```

#### `send_by_id()`

通过 ID 发送消息。

```python
await platform.send_by_id("user123", "消息", message_type="private")
```

#### `refresh()`

刷新平台状态。

```python
await platform.refresh()
```

#### `clear_errors()`

清除平台错误。

```python
await platform.clear_errors()
```

#### `get_stats()`

获取平台统计信息。

```python
stats = await platform.get_stats()
```

---

## 使用示例

### 1. 基本对话流程

```python
from astrbot_sdk.decorators import on_message

@on_message()
async def handle_message(event: MessageEvent, ctx: Context):
    reply = await ctx.llm.chat(event.message_content)
    await ctx.platform.send(event.session_id, reply)
```

---

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

---

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

### 4. 注册 Web API

```python
from astrbot_sdk.decorators import provide_capability

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

1. **跨进程通信**: Context 通过 capability 协议与核心通信，所有方法调用都是异步的

2. **插件隔离**: 每个插件有独立的 Context 实例，数据和配置是隔离的

3. **取消处理**: 长时间运行的操作应定期检查 `ctx.cancel_token.raise_if_cancelled()`

4. **错误处理**: 所有远程调用都可能失败，建议使用 try-except 处理

5. **Memory vs DB**:
   - Memory: 语义搜索，适合 AI 上下文
   - DB: 精确匹配，适合结构化数据

6. **文件操作**: 使用 `ctx.files` 注册文件令牌，不要直接传递本地路径

7. **平台标识**: 使用 UMO（统一消息来源标识）格式：`"platform:instance:session_id"`

8. **配置访问**: `get_plugin_config()` 只支持查询当前插件自己的配置

---

## 相关模块

- **LLM 客户端**: `astrbot_sdk.clients.llm.LLMClient`
- **Memory 客户端**: `astrbot_sdk.clients.memory.MemoryClient`
- **DB 客户端**: `astrbot_sdk.clients.db.DBClient`
- **Platform 客户端**: `astrbot_sdk.clients.platform.PlatformClient`
- **日志器**: `astrbot_sdk._plugin_logger.PluginLogger`
- **取消令牌**: `astrbot_sdk.context.CancelToken`

---

**版本**: v4.0
**模块**: `astrbot_sdk.context.Context`
**最后更新**: 2026-03-17
