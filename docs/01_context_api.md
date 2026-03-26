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
- [Permission 客户端 (ctx.permission)](#permission-客户端)
- [Permission 管理客户端 (ctx.permission_manager)](#permission-管理客户端)
- [Provider 客户端 (ctx.providers)](#provider-客户端)
- [Provider 管理客户端 (ctx.provider_manager)](#provider-管理客户端)
- [Personas 客户端 (ctx.personas / ctx.persona_manager)](#personas-客户端)
- [Conversations 客户端 (ctx.conversations / ctx.conversation_manager)](#conversations-客户端)
- [Knowledge Base 客户端 (ctx.kbs / ctx.kb_manager)](#knowledge-base-客户端)
- [Message History 客户端 (ctx.message_history / ctx.message_history_manager)](#message-history-客户端)
- [HTTP 客户端 (ctx.http)](#http-客户端)
- [MCP 客户端 (ctx.mcp / ctx.mcp_manager)](#mcp-客户端)
- [Metadata 客户端 (ctx.metadata)](#metadata-客户端)
- [Registry 客户端 (ctx.registry)](#registry-客户端)
- [Skills 客户端 (ctx.skills)](#skills-客户端)
- [Session 管理客户端 (ctx.session_plugins / ctx.session_services)](#session-管理客户端)
- [LLM Tool 管理方法](#llm-tool-管理方法)
- [系统工具方法](#系统工具方法)
- [高级上下文方法](#高级上下文方法)

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
    request_id: str | None             # 当前请求作用域 ID（如有）
```

### 客户端属性

```python
ctx.llm: LLMClient                    # LLM 能力客户端
ctx.memory: MemoryClient              # 记忆能力客户端
ctx.db: DBClient                      # 数据库客户端
ctx.files: FileServiceClient          # 文件服务客户端
ctx.platform: PlatformClient          # 平台客户端
ctx.permission: PermissionClient      # 权限只读客户端
ctx.providers: ProviderClient         # Provider 客户端
ctx.provider_manager: ProviderManagerClient  # Provider 管理客户端
ctx.permission_manager: PermissionManagerClient  # 权限管理客户端
ctx.personas: PersonaManagerClient    # 人格管理客户端
ctx.conversations: ConversationManagerClient  # 对话管理客户端
ctx.kbs: KnowledgeBaseManagerClient   # 知识库管理客户端
ctx.message_history: MessageHistoryManagerClient  # 消息历史管理客户端
ctx.message_history_manager: MessageHistoryManagerClient  # ctx.message_history 的别名
ctx.http: HTTPClient                  # HTTP 客户端
ctx.mcp: MCPManagerClient             # MCP 管理客户端
ctx.mcp_manager: MCPManagerClient     # ctx.mcp 的别名
ctx.metadata: MetadataClient          # 元数据客户端
ctx.registry: RegistryClient          # 能力注册客户端
ctx.skills: SkillClient               # 技能客户端
ctx.session_plugins: SessionPluginManager  # 会话插件管理器
ctx.session_services: SessionServiceManager  # 会话服务管理器
ctx.persona_manager: PersonaManagerClient   # ctx.personas 的别名
ctx.conversation_manager: ConversationManagerClient  # ctx.conversations 的别名
ctx.kb_manager: KnowledgeBaseManagerClient  # ctx.kbs 的别名
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

```
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

搜索记忆项。默认在有 embedding provider 时执行 hybrid 检索。

```python
results = await ctx.memory.search("用户喜欢什么颜色", mode="hybrid", limit=5)
for item in results:
    print(item["key"], item["score"], item["match_type"])
```

### save()

保存记忆项。

```python
# 保存用户偏好
await ctx.memory.save("user_pref", {"theme": "dark", "lang": "zh"})

# 使用关键字参数
await ctx.memory.save("note", None, content="重要笔记", tags=["work"])

# 显式指定检索文本
await ctx.memory.save(
    "profile:alice",
    {"name": "Alice", "embedding_text": "Alice 喜欢蓝色和海边"},
)
```

### get()

精确获取单个记忆项。

```python
pref = await ctx.memory.get("user_pref")
if pref:
    print(f"用户偏好主题: {pref.get('theme')}")
```

### list_keys()

列出某个精确 namespace 下的 key。返回顺序按大小写不敏感排序，若大小写折叠后相同则再按原始 key 排序。

```python
keys = await ctx.memory.list_keys(namespace="users/alice")
print(keys)  # ["Alpha", "apple", "beta"]
```

### exists()

检查某个 key 是否存在于精确 namespace 中。

```python
exists = await ctx.memory.exists("user_pref", namespace="users/alice")
print(exists)  # True / False
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

### clear_namespace()

清理某个 namespace 下的记忆。默认只清理当前 namespace；传 `include_descendants=True` 时会递归清理子 namespace，返回值包含整个作用域内被删除的记录总数。

```python
deleted = await ctx.memory.clear_namespace(namespace="users/alice")
deleted_recursive = await ctx.memory.clear_namespace(
    namespace="users/alice",
    include_descendants=True,
)
print(deleted, deleted_recursive)
```

### count()

统计某个 namespace 下的记忆数量。默认只统计当前 namespace；传 `include_descendants=True` 时会包含子 namespace。

```python
count = await ctx.memory.count(namespace="users/alice")
recursive_count = await ctx.memory.count(
    namespace="users/alice",
    include_descendants=True,
)
print(count, recursive_count)
```

### stats()

查看记忆索引状态。

```python
stats = await ctx.memory.stats()
print(stats["total_items"], stats.get("embedded_items"), stats.get("dirty_items"))
```

---

## Database 客户端

`ctx.db` 是插件作用域的 KV 存储。运行时会自动为 key 加上当前插件命名空间前缀，
因此不同插件即使使用同名 key 也不会互相覆盖；`list()` 和 `watch()` 返回的仍是插件视角的原始 key。

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

当前 AstrBot Core bridge 里，这个能力仍处于 MVP 限制状态：
调用 `ctx.db.watch()` 会返回显式错误 `db.watch is unsupported in AstrBot SDK MVP`，
因此现在应优先使用 `ctx.db.get()` / `ctx.db.list()` 轮询，而不是依赖流式订阅。

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

## Permission 客户端

`ctx.permission` 提供与 Core 当前权限模型对齐的只读能力。v1 正式角色只有 `member` 和 `admin` 两级；`session_id` 参数当前仅保留给未来扩展，不会改变判定结果。

### check()

查询某个用户当前会被视为 `admin` 还是 `member`。

```python
result = await ctx.permission.check("user-123")
print(result.is_admin, result.role)

# session_id 在 v1 中只作为保留参数
same_result = await ctx.permission.check(
    "user-123",
    session_id=event.session_id,
)
```

### get_admins()

读取当前 `admins_id` 配置中的管理员列表。

```python
admins = await ctx.permission.get_admins()
print(admins)
```

---

## Permission 管理客户端

`ctx.permission_manager` 仅 `reserved/system` 插件可用，并且要求当前调用绑定到一个真实消息事件，且该事件发送者本身是 admin。普通插件会收到 `permission.manager.* is restricted to reserved/system plugins` 错误；非管理员事件会收到显式权限错误。

### add_admin() / remove_admin()

返回值表示本次调用是否真的修改了管理员列表：
- 已存在再 `add_admin()` 返回 `False`
- 不存在再 `remove_admin()` 返回 `False`

```python
changed = await ctx.permission_manager.add_admin("user-456")
removed = await ctx.permission_manager.remove_admin("user-456")
print(changed, removed)
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

## Provider 管理客户端

仅 `reserved/system` 插件可用。普通插件调用 `ctx.provider_manager` 的方法会收到 `provider.manager.* is restricted to reserved/system plugins` 错误；普通插件应使用只读的 `ctx.providers` 查询当前 Provider 状态。

### set_provider()

切换当前全局生效的 Provider。
`umo` 仅作为变更事件中的来源标识，不会把 Provider 绑定到单个会话。

```python
from astrbot_sdk.llm.entities import ProviderType

await ctx.provider_manager.set_provider(
    provider_id="openai_chat",
    provider_type=ProviderType.CHAT_COMPLETION,
    umo=event.session_id,
)
```

### create_provider() / update_provider() / delete_provider()

动态创建、更新和删除 Provider 实例。

```python
record = await ctx.provider_manager.create_provider(
    {
        "id": "custom_chat",
        "type": "openai",
        "provider_type": "chat_completion",
        "model": "gpt-4.1",
    }
)

updated = await ctx.provider_manager.update_provider(
    "custom_chat",
    {"model": "gpt-4.1-mini"},
)

await ctx.provider_manager.delete_provider("custom_chat")
```

### watch_changes()

监听 Provider 变更事件。

```python
async for change in ctx.provider_manager.watch_changes():
    print(f"{change.provider_id}: {change.provider_type} @ {change.umo}")
```

如果你只是想声明式地监听 Provider 切换，而不是手动拉一个监听流，
可以优先使用 `@on_provider_change(...)` 装饰器，让运行时自动订阅和清理。
注意当前底层仍依赖 `provider.manager.watch_changes`，因此这条装饰器在现阶段也应视为
`reserved/system` 插件能力：

```python
from astrbot_sdk import Star, on_provider_change


class ProviderWatcher(Star):
    @on_provider_change(provider_types=["embedding"])
    async def handle_change(self, provider_id: str, provider_type, umo: str | None):
        print(provider_id, provider_type, umo)
```

---

## Personas 客户端

`ctx.personas` 与 `ctx.persona_manager` 指向同一个人格管理客户端。

### get_persona() / get_all_personas()

查询单个人格或获取所有人格。

```python
persona = await ctx.personas.get_persona("assistant")
all_personas = await ctx.personas.get_all_personas()
```

### create_persona() / update_persona() / delete_persona()

创建、更新或删除人格。

```python
from astrbot_sdk.clients import PersonaCreateParams, PersonaUpdateParams

created = await ctx.personas.create_persona(
    PersonaCreateParams(
        persona_id="assistant",
        system_prompt="你是一个有用的助手。",
    )
)

updated = await ctx.personas.update_persona(
    "assistant",
    PersonaUpdateParams(system_prompt="你是一个专业的编程助手。"),
)

await ctx.personas.delete_persona("assistant")
```

---

## Conversations 客户端

`ctx.conversations` 与 `ctx.conversation_manager` 指向同一个对话管理客户端。

### new_conversation()

为指定会话创建新对话。

```python
from astrbot_sdk.clients import ConversationCreateParams

conv_id = await ctx.conversations.new_conversation(
    event.session_id,
    ConversationCreateParams(title="新对话"),
)
```

### get_current_conversation() / get_conversations()

获取当前对话或会话内的全部对话。

```python
current = await ctx.conversations.get_current_conversation(
    event.session_id,
    create_if_not_exists=True,
)
all_conversations = await ctx.conversations.get_conversations(event.session_id)
```

### switch_conversation() / update_conversation() / delete_conversation()

切换、更新或删除对话。

```python
from astrbot_sdk.clients import ConversationUpdateParams

await ctx.conversations.switch_conversation(event.session_id, "conv_123")
await ctx.conversations.update_conversation(
    event.session_id,
    "conv_123",
    ConversationUpdateParams(title="新标题"),
)
await ctx.conversations.delete_conversation(event.session_id, "conv_123")
```

---

## Knowledge Base 客户端

`ctx.kbs` 与 `ctx.kb_manager` 指向同一个知识库管理客户端。

### list_kbs() / get_kb()

列出所有知识库或获取单个知识库。

```python
kbs = await ctx.kbs.list_kbs()
kb = await ctx.kbs.get_kb("kb_123")
```

### create_kb() / update_kb() / delete_kb()

创建、更新或删除知识库。

```python
from astrbot_sdk import KnowledgeBaseCreateParams, KnowledgeBaseUpdateParams

kb = await ctx.kbs.create_kb(
    KnowledgeBaseCreateParams(
        kb_name="tech_docs",
        embedding_provider_id="openai_embedding",
        description="技术文档",
    )
)

kb = await ctx.kbs.update_kb(
    kb.kb_id,
    KnowledgeBaseUpdateParams(description="更新后的描述"),
)
deleted = await ctx.kbs.delete_kb(kb.kb_id)
```

### retrieve()

从知识库中检索相关片段。

```python
result = await ctx.kbs.retrieve(
    "如何初始化 Context",
    kb_names=["tech_docs"],
    top_m_final=3,
)
if result:
    for item in result.results:
        print(item.content)
```

---

## Message History 客户端

`ctx.message_history` 用于按 `MessageSession` 精确保存原始消息组件、发送者和元数据，
`ctx.message_history_manager` 是它的别名。它适合消息审计、分页回看和按时间清理；
如果你要做语义检索，仍应使用 `ctx.memory`。

### append()

追加一条消息历史记录。

```python
from astrbot_sdk import MessageHistorySender, MessageSession, Plain

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
    metadata={"source": "message_handler"},
    idempotency_key="incoming:demo-user:hello",
)
print(record.id, record.created_at)
```

### list()

分页读取某个会话的消息历史。
分页时建议直接复用上一页返回的 `next_cursor`，不要自行构造游标值。

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

### get() / get_by_id()

按记录 ID 读取单条历史。

```python
session = MessageSession(
    platform_id=event.platform_id,
    message_type=event.message_type,
    session_id=event.session_id,
)
record = await ctx.message_history.get(session, 1)
same_record = await ctx.message_history.get_by_id(session, 1)
```

### delete_before() / delete_after() / delete_all()

按时间或按会话清理消息历史。
当前实现要求传入带时区的 `datetime`，例如 `timezone.utc`。

```python
from datetime import datetime, timezone

session = MessageSession(
    platform_id=event.platform_id,
    message_type=event.message_type,
    session_id=event.session_id,
)
deleted = await ctx.message_history.delete_before(
    session,
    before=datetime(2026, 3, 22, tzinfo=timezone.utc),
)
await ctx.message_history.delete_all(session)
```

---

## HTTP 客户端

`ctx.http.register_api()` 当前会拦截包含 `..` 的路径和部分明显非法输入，但校验并非完全严格。
文档示例建议统一使用以 `/` 开头、没有重复斜杠的规范化路径。`ctx.http.unregister_api(route)`
在不传 `methods` 时会移除当前插件在该路由下注册的全部方法。

如果路由和 handler 在插件定义阶段就固定了，优先考虑使用
`@http_api(...) + @provide_capability(...)` 的声明式写法。它会在插件启动时自动注册，
插件卸载时自动清理；`ctx.http.register_api()` 更适合运行时动态增删路由。

### register_api()

注册 Web API 端点。

```python
from astrbot_sdk import Context, Star, provide_capability


class HttpPlugin(Star):
    @provide_capability(
        name="my_plugin.http_handler",
        description="处理 HTTP 请求",
    )
    async def handle_http_request(self, request_id: str, payload: dict, cancel_token):
        return {"status": 200, "body": {"result": "ok"}}

    async def setup_api(self, ctx: Context) -> None:
        await ctx.http.register_api(
            route="/my-api",
            handler=self.handle_http_request,
            methods=["GET", "POST"],
        )
```

对应的声明式写法：

```python
from astrbot_sdk import Star, http_api, provide_capability


class HttpPlugin(Star):
    @http_api(route="/my-api", methods=["GET", "POST"], description="我的 API")
    @provide_capability(
        "my_plugin.http_handler",
        description="处理 HTTP 请求",
    )
    async def handle_http_request(self, request_id: str, payload: dict, cancel_token):
        return {"status": 200, "body": {"result": "ok"}}
```

`register_api()` 二选一支持：
- 直接传 `handler_capability="my_plugin.http_handler"`
- 传已经用 `@provide_capability(...)` 标记过的 `handler=...`

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

## MCP 客户端

`ctx.mcp` 与 `ctx.mcp_manager` 指向同一个 MCP 管理客户端。它既支持管理本地 MCP 服务，
也支持注册全局 MCP 服务和临时打开 MCP session。

如果 MCP 服务定义在插件类上且生命周期固定，可以优先用 `@mcp_server(...)` 声明；
若 `scope="global"`，还必须同时显式标注 `@acknowledge_global_mcp_risk`。

### list_servers() / get_server() / enable_server() / disable_server()

管理本地 MCP 服务。

```python
servers = await ctx.mcp.list_servers()
server = await ctx.mcp.get_server("local-devtools")

if server and not server.active:
    await ctx.mcp.enable_server(server.name)
```

### wait_until_ready()

等待某个本地 MCP 服务可用。

```python
ready = await ctx.mcp.wait_until_ready("local-devtools", timeout=10)
print(ready.name, ready.running)
```

### session()

临时打开 MCP session，并在退出 `async with` 时自动关闭。

```python
async with ctx.mcp.session(
    name="local-devtools",
    config={"mock_tools": ["inspect"]},
    timeout=10,
) as session:
    tools = await session.list_tools()
    result = await session.call_tool("inspect", {"target": "project"})
```

### register_global_server() / list_global_servers() / unregister_global_server()

管理全局 MCP 服务。

```python
server = await ctx.mcp.register_global_server(
    "shared-inspector",
    {"mock_tools": ["inspect"]},
    timeout=10,
)
print(server.name, server.scope)

global_servers = await ctx.mcp.list_global_servers()
await ctx.mcp.unregister_global_server("shared-inspector")
```

对应的声明式写法：

```python
from astrbot_sdk import Star, acknowledge_global_mcp_risk, mcp_server


@acknowledge_global_mcp_risk
@mcp_server(
    name="shared-inspector",
    scope="global",
    config={"mock_tools": ["inspect"]},
    timeout=10,
)
class MCPPlugin(Star):
    pass
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

## Registry 客户端

handler 注册表查询与白名单管理客户端，用于查询 handler 信息并管理 handler 白名单。

### get_handlers_by_event_type()

获取指定事件类型的所有 handler。

```python
handlers = await ctx.registry.get_handlers_by_event_type("message")
for h in handlers:
    print(f"{h.handler_full_name}: {h.description}")
```

### get_handler_by_full_name()

通过完整名称获取 handler 元数据。

```python
handler = await ctx.registry.get_handler_by_full_name("my_plugin.on_message")
if handler:
    print(f"触发类型: {handler.trigger_type}")
    print(f"优先级: {handler.priority}")
```

### set_handler_whitelist() / get_handler_whitelist()

管理 handler 白名单。

```python
# 设置白名单
await ctx.registry.set_handler_whitelist(["plugin_a", "plugin_b"])

# 获取当前白名单
whitelist = await ctx.registry.get_handler_whitelist()

# 清空白名单
await ctx.registry.clear_handler_whitelist()
```

---

## Skills 客户端

技能注册客户端，用于注册和管理技能。

如果技能声明在插件类定义里就是固定的，优先用 `@register_skill(...)` 声明式注册；
`ctx.skills.register()` 或 `ctx.register_skill()` 更适合运行时动态增删。

### register()

注册一个技能。

```python
skill = await ctx.skills.register(
    name="my_skill",
    path="/path/to/skill",
    description="我的技能描述"
)
print(f"技能已注册: {skill.name}")
```

对应的声明式写法：

```python
from astrbot_sdk import Star, register_skill


@register_skill(name="my_skill", path="skills/demo.py", description="我的技能描述")
class MyPlugin(Star):
    pass
```

### unregister()

注销技能。

```python
removed = await ctx.skills.unregister("my_skill")
if removed:
    print("技能已注销")
```

### list()

列出当前已注册的技能。

```python
skills = await ctx.skills.list()
for skill in skills:
    print(f"{skill.name}: {skill.skill_dir}")
```

---

## Session 管理客户端

### SessionPluginManager (ctx.session_plugins)

会话级别的插件状态管理器。

#### is_plugin_enabled_for_session()

检查插件在指定会话是否启用。

```python
enabled = await ctx.session_plugins.is_plugin_enabled_for_session(
    session=event,
    plugin_name="my_plugin"
)
```

#### filter_handlers_by_session()

根据会话过滤 handler。

```python
handlers = await ctx.registry.get_handlers_by_event_type("message")
filtered = await ctx.session_plugins.filter_handlers_by_session(
    session=event,
    handlers=handlers
)
```

### SessionServiceManager (ctx.session_services)

会话级别的 LLM/TTS 服务状态管理器。

#### LLM 状态管理

```python
# 检查 LLM 是否启用
enabled = await ctx.session_services.is_llm_enabled_for_session(event)

# 设置 LLM 状态
await ctx.session_services.set_llm_status_for_session(event, enabled=False)

# 检查是否应处理 LLM 请求
if await ctx.session_services.should_process_llm_request(event):
    reply = await ctx.llm.chat(prompt)
```

#### TTS 状态管理

```python
# 检查 TTS 是否启用
enabled = await ctx.session_services.is_tts_enabled_for_session(event)

# 设置 TTS 状态
await ctx.session_services.set_tts_status_for_session(event, enabled=True)

# 检查是否应处理 TTS 请求
if await ctx.session_services.should_process_tts_request(event):
    await handle_tts(text)
```

---

## LLM Tool 管理方法

如果工具在插件代码中是静态定义的，优先用 `@register_llm_tool(...)` 装饰器；
它会在插件装载时自动注册。这个装饰器应标在插件类方法上，让运行时能扫描到；
`ctx.register_llm_tool()` 更适合运行时按条件动态创建工具。

### get_llm_tool_manager()

获取底层 `LLMToolManager`。

```python
manager = ctx.get_llm_tool_manager()
```

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

对应的声明式写法：

```python
from astrbot_sdk import Star
from astrbot_sdk.decorators import register_llm_tool


class MyPlugin(Star):
    @register_llm_tool(name="search_weather", description="搜索天气信息")
    async def search_weather(self, location: str) -> str:
        return f"{location} 今天晴天"
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

### unregister_llm_tool()

取消注册一个动态 LLM 工具。

```python
await ctx.unregister_llm_tool("my_tool")
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

如果这是插件生命周期内常驻的后台任务，而不是某个 handler 临时派生出来的 follow-up work，
优先考虑 `@background_task(...)` 装饰器。它会在插件启动时自动启动，停用时自动取消：

```python
from astrbot_sdk import Context, Star, background_task


class MyPlugin(Star):
    @background_task(description="同步缓存")
    async def sync_cache(self, ctx: Context) -> None:
        while True:
            await asyncio.sleep(60)
            ctx.logger.info("sync once")
```

`ctx.register_task()` 更适合在 handler 内部启动一个应当脱离当前请求继续运行的异步任务。

### register_skill() / unregister_skill()

`Context` 也提供了对 `ctx.skills.register()` / `ctx.skills.unregister()` 的薄封装。

```python
registration = await ctx.register_skill(
    name="my_skill",
    path="skills/demo.py",
    description="动态注册技能",
)

removed = await ctx.unregister_skill("my_skill")
print(registration.name, removed)
```

---

## 高级上下文方法

### tool_loop_agent()

运行一次带工具循环的 Agent 请求，返回完整 `LLMResponse`。

```python
from astrbot_sdk.llm.entities import ProviderRequest

response = await ctx.tool_loop_agent(
    request=ProviderRequest(
        prompt="帮我先搜索再总结",
        system_prompt="你是一个严谨的助手",
    )
)
print(response.text)
```

### register_commands()

只允许在 `astrbot_loaded` 或 `platform_loaded` 事件中动态注册命令。
`ignore_prefix=True` 在当前 SDK 运行时中不支持。

```python
from astrbot_sdk import Context, Star
from astrbot_sdk.decorators import on_event


class MyPlugin(Star):
    @on_event("astrbot_loaded")
    async def on_loaded(self, event, ctx: Context):
        await ctx.register_commands(
            command_name="status",
            handler_full_name="my_plugin.status_handler",
            desc="查看状态",
            priority=10,
        )
```

### list_platforms() / get_platform() / get_platform_inst()

读取平台兼容层对象，便于主动下行消息和查看平台状态。

```python
for platform in await ctx.list_platforms():
    print(platform.id, platform.type, platform.status)

qq = await ctx.get_platform("qq")
inst = await ctx.get_platform_inst("qq-main")
```

兼容层对象常用方法：
- `await platform.send("session_id", "消息")`
- `await platform.send_by_id("user123", "消息", message_type="private")`
- `await platform.refresh()`
- `await platform.clear_errors()`
- `stats = await platform.get_stats()`

---

## 常见使用模式

### 1. 基本对话流程

```python
from astrbot_sdk import Context, MessageEvent, Star
from astrbot_sdk.decorators import on_message


class MyPlugin(Star):
    @on_message()
    async def handle_message(self, event: MessageEvent, ctx: Context):
        reply = await ctx.llm.chat(event.message_content)
        await ctx.platform.send(event.session_id, reply)
```

### 2. 带历史的对话

```python
from astrbot_sdk import Context, MessageEvent, Star
from astrbot_sdk.clients.llm import ChatMessage
from astrbot_sdk.decorators import on_message


class MyPlugin(Star):
    @on_message()
    async def handle_message(self, event: MessageEvent, ctx: Context):
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

如果你需要保留原始消息组件、发送者信息、分页读取或按时间清理，请改用
`ctx.message_history`，不要把消息链序列化后再手工塞进 `ctx.memory`。

### 3. 使用数据库持久化

```python
from astrbot_sdk import Context, MessageEvent, Star
from astrbot_sdk.decorators import on_message


class MyPlugin(Star):
    @on_message()
    async def handle_message(self, event: MessageEvent, ctx: Context):
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

5. **Memory vs DB vs MessageHistory**：
   - Memory: 语义搜索，适合 AI 上下文
   - DB: 精确匹配，适合结构化数据
   - MessageHistory: 精确保存原始消息组件、发送者和元数据

6. **声明式优先**：固定的 HTTP 路由、LLM Tool、技能注册、Provider 变更监听、插件级后台任务、MCP 服务，优先考虑对应装饰器；需要运行时动态增删时再使用 `Context` 方法。

7. **文件操作**：使用 `ctx.files` 注册文件令牌，不要直接传递本地路径

8. **平台标识**：使用 UMO（统一消息来源标识）格式：`"platform:instance:session_id"`

9. **MCP 全局服务**：全局 MCP 服务会影响整个运行时，使用声明式 `@mcp_server(scope="global")` 时必须同时显式确认风险。
