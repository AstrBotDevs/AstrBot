# 工具与辅助类 API 完整参考

## 概述

本文档介绍 AstrBot SDK 中常用的工具类和辅助类型，包括取消令牌、会话管理、命令组织、参数解析等功能。

**模块路径**:
- `astrbot_sdk.context.CancelToken`
- `astrbot_sdk.message_session.MessageSession`
- `astrbot_sdk.types.GreedyStr`
- `astrbot_sdk.commands`
- `astrbot_sdk.schedule.ScheduleContext`
- `astrbot_sdk.session_waiter`
- `astrbot_sdk.star_tools.StarTools`
- `astrbot_sdk.plugin_kv.PluginKVStoreMixin`

---

## 目录

- [CancelToken - 取消令牌](#canceltoken---取消令牌)
- [MessageSession - 消息会话](#messagesession---消息会话)
- [GreedyStr - 贪婪字符串](#greedystr---贪婪字符串)
- [CommandGroup - 命令组](#commandgroup---命令组)
- [ScheduleContext - 调度上下文](#schedulecontext---调度上下文)
- [SessionController - 会话控制器](#sessioncontroller---会话控制器)
- [session_waiter - 会话等待装饰器](#session_waiter---会话等待装饰器)
- [StarTools - Star 工具类](#startools---star-工具类)
- [PluginKVStoreMixin - KV 存储混入](#pluginkvstoremixin---kv-存储混入)

---

## 导入方式

```python
# 从主模块导入
from astrbot_sdk import (
    CancelToken,
    MessageSession,
    GreedyStr,
    ScheduleContext,
    SessionController,
    session_waiter,
    StarTools,
    PluginKVStoreMixin,
)

# 从子模块导入
from astrbot_sdk.context import CancelToken
from astrbot_sdk.message_session import MessageSession
from astrbot_sdk.types import GreedyStr
from astrbot_sdk.commands import CommandGroup, command_group, print_cmd_tree
from astrbot_sdk.schedule import ScheduleContext
from astrbot_sdk.session_waiter import SessionController, session_waiter
from astrbot_sdk.star_tools import StarTools
from astrbot_sdk.plugin_kv import PluginKVStoreMixin
```

---

## CancelToken - 取消令牌

请求取消令牌，用于协调长时间运行操作的取消。

### 类定义

```python
@dataclass(slots=True)
class CancelToken:
    _cancelled: asyncio.Event
```

### 构造方法

```python
from astrbot_sdk import CancelToken

token = CancelToken()
```

### 实例方法

#### `cancel()`

触发取消信号。

```python
def cancel(self) -> None:
    """触发取消信号。"""
```

**示例**:

```python
token.cancel()
```

---

#### `cancelled` 属性

检查是否已被取消。

```python
@property
def cancelled(self) -> bool:
    """检查是否已被取消。"""
```

**示例**:

```python
if token.cancelled:
    print("操作已取消")
```

---

#### `wait()`

等待取消信号。

```python
async def wait(self) -> None:
    """等待取消信号。"""
```

**示例**:

```python
await token.wait()
```

---

#### `raise_if_cancelled()`

如果已取消则抛出 `CancelledError`。

```python
def raise_if_cancelled(self) -> None:
    """如果已取消则抛出 CancelledError。"""
```

**异常**:
- `asyncio.CancelledError`: 如果令牌已被取消

**示例**:

```python
async def long_operation(ctx: Context):
    for item in large_list:
        ctx.cancel_token.raise_if_cancelled()
        await process(item)
```

---

## MessageSession - 消息会话

统一表示消息会话标识符，格式为 `platform_id:message_type:session_id`。

### 类定义

```python
@dataclass(slots=True)
class MessageSession:
    platform_id: str
    message_type: str
    session_id: str
```

### 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `platform_id` | `str` | 平台实例 ID |
| `message_type` | `str` | 消息类型（`group` 或 `private`） |
| `session_id` | `str` | 会话 ID |

### 类方法

#### `from_str(session)`

从字符串解析会话。

```python
@classmethod
def from_str(cls, session: str) -> MessageSession:
    platform_id, message_type, session_id = str(session).split(":", 2)
    return cls(
        platform_id=platform_id,
        message_type=message_type,
        session_id=session_id,
    )
```

**参数**:
- `session` (`str`): 会话字符串，格式为 `platform_id:message_type:session_id`

**返回**: `MessageSession` 实例

**示例**:

```python
from astrbot_sdk import MessageSession

# 从字符串创建
session = MessageSession.from_str("qq:group:123456")

# 直接创建
session = MessageSession(
    platform_id="qq",
    message_type="group",
    session_id="123456"
)

# 转换为字符串
str(session)  # "qq:group:123456"
```

---

## GreedyStr - 贪婪字符串

用于标记"贪婪字符串"参数，在命令解析时将剩余所有文本作为一个整体参数。

### 类定义

```python
class GreedyStr(str):
    """Consume the remaining command text as one argument."""
```

### 使用场景

当命令参数包含空格时，普通解析会将空格后的内容作为下一个参数，而 `GreedyStr` 会捕获剩余所有文本。

**示例**:

```python
from astrbot_sdk import GreedyStr
from astrbot_sdk.decorators import on_command

@on_command("echo")
async def echo(self, event: MessageEvent, text: GreedyStr):
    # 用户输入: /echo hello world this is a test
    # text = "hello world this is a test"
    await event.reply(text)

@on_command("say")
async def say(self, event: MessageEvent, name: str, message: GreedyStr):
    # 用户输入: /say Alice Hello World
    # name = "Alice"
    # message = "Hello World"
    await event.reply(f"{name} 说: {message}")
```

---

## CommandGroup - 命令组

用于组织具有层级关系的命令，支持命令别名和自动展开。

### 类定义

```python
class CommandGroup:
    def __init__(
        self,
        name: str,
        *,
        aliases: list[str] | None = None,
        description: str | None = None,
        parent: CommandGroup | None = None,
    ) -> None:
```

### 构造方法

```python
from astrbot_sdk import CommandGroup, command_group

# 使用函数创建
admin = command_group("admin", description="管理命令")

# 使用类创建
config = CommandGroup("config", description="配置命令")
```

**参数**:
- `name` (`str`): 组名称
- `aliases` (`list[str] | None`): 别名列表
- `description` (`str | None`): 描述信息
- `parent` (`CommandGroup | None`): 父组

### 实例方法

#### `group(name, *, aliases, description)`

创建子命令组。

```python
def group(
    self,
    name: str,
    *,
    aliases: list[str] | None = None,
    description: str | None = None,
) -> CommandGroup:
```

**示例**:

```python
admin = command_group("admin")
user = admin.group("user", description="用户管理")
config = admin.group("config", description="配置管理")
```

---

#### `command(name, *, aliases, description)`

创建命令装饰器。

```python
def command(
    self,
    name: str,
    *,
    aliases: list[str] | None = None,
    description: str | None = None,
):
```

**返回**: 装饰器函数

**示例**:

```python
admin = command_group("admin")

@admin.command("add", description="添加用户")
async def admin_add_user(self, event: MessageEvent, user_id: str):
    await event.reply(f"添加用户: {user_id}")

@admin.command("remove", aliases=["del"], description="删除用户")
async def admin_remove_user(self, event: MessageEvent, user_id: str):
    await event.reply(f"删除用户: {user_id}")
```

---

#### `path` 属性

获取命令组的完整路径。

```python
@property
def path(self) -> list[str]:
    if self.parent is None:
        return [self.name]
    return [*self.parent.path, self.name]
```

**示例**:

```python
admin = command_group("admin")
user = admin.group("user")

user.path  # ["admin", "user"]
```

---

#### `print_cmd_tree()`

打印命令树结构。

```python
def print_cmd_tree(self) -> str:
    lines: list[str] = []
    self._append_tree_lines(lines, indent=0)
    return "\n".join(lines)
```

**返回**: `str` - 命令树字符串

**示例**:

```python
admin = command_group("admin")

@admin.command("add")
async def admin_add(...): pass

@admin.command("remove")
async def admin_remove(...): pass

print(admin.print_cmd_tree())
# 输出:
# admin
#   - add
#   - remove
```

---

### 函数

#### `command_group(name, *, aliases, description)`

创建命令组实例。

```python
def command_group(
    name: str,
    *,
    aliases: list[str] | None = None,
    description: str | None = None,
) -> CommandGroup:
    return CommandGroup(
        name,
        aliases=aliases,
        description=description,
    )
```

---

#### `print_cmd_tree(group)`

获取命令树字符串。

```python
def print_cmd_tree(group: CommandGroup) -> str:
    return group.print_cmd_tree()
```

**示例**:

```python
from astrbot_sdk import command_group, print_cmd_tree

admin = command_group("admin", description="管理命令")

@admin.command("user")
async def admin_user(...): pass

@admin.command("setting")
async def admin_setting(...): pass

# 获取命令树
tree = print_cmd_tree(admin)
await event.reply(f"```\n{tree}\n```")
```

---

### 使用示例

#### 基本命令组

```python
from astrbot_sdk import Star, command_group
from astrbot_sdk.decorators import on_command
from astrbot_sdk.events import MessageEvent

class MyPlugin(Star):
    # 创建命令组
    admin = command_group("admin", description="管理命令")

    @admin.command("add", description="添加用户")
    async def admin_add(self, event: MessageEvent, user_id: str):
        await event.reply(f"添加用户: {user_id}")

    @admin.command("remove", aliases=["del"], description="删除用户")
    async def admin_remove(self, event: MessageEvent, user_id: str):
        await event.reply(f"删除用户: {user_id}")
```

#### 嵌套命令组

```python
# 创建嵌套结构
admin = command_group("admin")
user = admin.group("user", description="用户管理")
config = admin.group("config", description="配置管理")

@user.command("add")
async def admin_user_add(self, event: MessageEvent, user_id: str):
    await event.reply(f"添加用户: {user_id}")

@user.command("remove")
async def admin_user_remove(self, event: MessageEvent, user_id: str):
    await event.reply(f"删除用户: {user_id}")

@config.command("get")
async def admin_config_get(self, event: MessageEvent, key: str):
    await event.reply(f"获取配置: {key}")

@config.command("set")
async def admin_config_set(self, event: MessageEvent, key: str, value: str):
    await event.reply(f"设置配置: {key} = {value}")
```

#### 使用类组织命令

```python
from astrbot_sdk import Star, CommandGroup

class AdminCommands:
    group = CommandGroup("admin", description="管理命令")

    @group.command("add", description="添加用户")
    async def add_user(self, event, user_id: str):
        await event.reply(f"添加用户: {user_id}")

    @group.command("remove", description="删除用户")
    async def remove_user(self, event, user_id: str):
        await event.reply(f"删除用户: {user_id}")
```

---

## ScheduleContext - 调度上下文

定时任务的上下文信息，包含调度任务的详细信息。

### 类定义

```python
@dataclass(slots=True)
class ScheduleContext:
    schedule_id: str
    plugin_id: str
    handler_id: str
    trigger_kind: str
    cron: str | None = None
    interval_seconds: int | None = None
    scheduled_at: str | None = None
```

### 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `schedule_id` | `str` | 调度任务唯一标识 |
| `plugin_id` | `str` | 所属插件 ID |
| `handler_id` | `str` | 对应 handler 的标识 |
| `trigger_kind` | `str` | 触发类型（`cron` / `interval` / `once`） |
| `cron` | `str \| None` | cron 表达式（仅 cron 类型） |
| `interval_seconds` | `int \| None` | 间隔秒数（仅 interval 类型） |
| `scheduled_at` | `str \| None` | 计划执行时间（仅 once 类型） |

### 使用示例

```python
from astrbot_sdk.decorators import on_schedule
from astrbot_sdk import ScheduleContext

class MyPlugin(Star):
    @on_schedule(cron="0 8 * * *")  # 每天 8:00
    async def morning_greeting(self, ctx: ScheduleContext):
        # ctx.schedule_id: 任务 ID
        # ctx.trigger_kind: "cron"
        # ctx.cron: "0 8 * * *"
        await self.send_message("群号", "早上好！")

    @on_schedule(interval_seconds=3600)  # 每小时
    async def hourly_check(self, ctx: ScheduleContext):
        # ctx.trigger_kind: "interval"
        # ctx.interval_seconds: 3600
        pass
```

---

## SessionController - 会话控制器

控制会话生命周期，支持超时管理、会话保持、历史记录。

### 类定义

```python
@dataclass(slots=True)
class SessionController:
    future: asyncio.Future[Any] = field(default_factory=asyncio.Future)
    current_event: asyncio.Event | None = None
    ts: float | None = None
    timeout: float | None = None
    history_chains: list[list[dict[str, Any]]] = field(default_factory=list)
```

### 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `future` | `asyncio.Future` | 会话结果 Future |
| `current_event` | `asyncio.Event \| None` | 当前事件 |
| `ts` | `float \| None` | 时间戳 |
| `timeout` | `float \| None` | 超时时间（秒） |
| `history_chains` | `list[list[dict]]` | 历史消息链 |

### 实例方法

#### `stop(error)`

停止会话。

```python
def stop(self, error: Exception | None = None) -> None:
    if self.future.done():
        return
    if error is not None:
        self.future.set_exception(error)
    else:
        self.future.set_result(None)
```

**参数**:
- `error` (`Exception | None`): 可选的错误对象

---

#### `keep(timeout, reset_timeout)`

延长会话超时时间。

```python
def keep(self, timeout: float = 0, reset_timeout: bool = False) -> None:
    new_ts = time.time()
    if reset_timeout:
        if timeout <= 0:
            self.stop()
            return
    else:
        assert self.timeout is not None
        assert self.ts is not None
        left_timeout = self.timeout - (new_ts - self.ts)
        timeout = left_timeout + timeout
        if timeout <= 0:
            self.stop()
            return

    if self.current_event and not self.current_event.is_set():
        self.current_event.set()

    current_event = asyncio.Event()
    self.current_event = current_event
    self.ts = new_ts
    self.timeout = timeout
    asyncio.create_task(self._holding(current_event, timeout))
```

**参数**:
- `timeout` (`float`): 延长的超时时间（秒）
- `reset_timeout` (`bool`): 是否重置超时时间

---

#### `get_history_chains()`

获取历史消息链。

```python
def get_history_chains(self) -> list[list[dict[str, Any]]]:
    return list(self.history_chains)
```

**返回**: `list[list[dict]]` - 历史消息链的副本

---

## session_waiter - 会话等待装饰器

将普通 handler 转换为会话式 handler，用于构建多轮对话流程。

### 函数签名

```python
def session_waiter(
    timeout: int = 30,
    *,
    record_history_chains: bool = False,
) -> _SessionWaiterDecorator:
```

### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `timeout` | `int` | `30` | 会话超时时间（秒） |
| `record_history_chains` | `bool` | `False` | 是否记录历史消息链 |

### 使用示例

#### 基本使用

```python
from astrbot_sdk import session_waiter, SessionController
from astrbot_sdk.events import MessageEvent

@session_waiter(timeout=300)
async def interactive_input(self, controller: SessionController, event: MessageEvent):
    await event.reply("请输入用户名:")

    response = await controller.future
    username = response.text

    await event.reply(f"你好, {username}!")
    controller.stop()
```

#### 多轮对话

```python
@session_waiter(timeout=600, record_history_chains=True)
async def survey(self, controller: SessionController, event: MessageEvent):
    # 第一轮：询问姓名
    await event.reply("请输入您的姓名:")
    response1 = await controller.future
    name = response1.text

    # 延长会话时间
    controller.keep(timeout=300)

    # 第二轮：询问年龄
    await event.reply("请输入您的年龄:")
    response2 = await controller.future
    age = response2.text

    # 获取历史消息
    history = controller.get_history_chains()

    await event.reply(f"感谢！姓名: {name}, 年龄: {age}")
    controller.stop()
```

#### 在类方法中使用

```python
class MyPlugin(Star):
    @session_waiter(timeout=300)
    async def interactive(self, controller: SessionController, event: MessageEvent):
        await event.reply("请输入内容:")
        response = await controller.future
        await event.reply(f"收到: {response.text}")
        controller.stop()
```

---

## StarTools - Star 工具类

提供类方法访问运行时上下文能力，只在生命周期、handler 和已注册的 LLM 工具执行期间可用。

### 类定义

```python
class StarTools:
    """Star 工具类，提供类方法访问运行时上下文能力。"""
```

### 类方法

#### `activate_llm_tool(name)`

激活 LLM 工具。

```python
@classmethod
async def activate_llm_tool(cls, name: str) -> bool:
    return await cls._require_context().activate_llm_tool(name)
```

**参数**:
- `name` (`str`): 工具名称

**返回**: `bool` - 是否成功激活

---

#### `deactivate_llm_tool(name)`

停用 LLM 工具。

```python
@classmethod
async def deactivate_llm_tool(cls, name: str) -> bool:
    return await cls._require_context().deactivate_llm_tool(name)
```

**参数**:
- `name` (`str`): 工具名称

**返回**: `bool` - 是否成功停用

---

#### `send_message(session, content)`

发送消息。

```python
@classmethod
async def send_message(
    cls,
    session: str | MessageSession,
    content: (
        str
        | MessageChain
        | Sequence[BaseMessageComponent]
        | Sequence[dict[str, Any]]
    ),
) -> dict[str, Any]:
    return await cls._require_context().send_message(session, content)
```

**参数**:
- `session` (`str | MessageSession`): 目标会话
- `content`: 消息内容

**返回**: `dict[str, Any]` - 发送结果

---

#### `send_message_by_id(type, id, content, *, platform)`

通过 ID 发送消息。

```python
@classmethod
async def send_message_by_id(
    cls,
    type: str,
    id: str,
    content: (
        str
        | MessageChain
        | Sequence[BaseMessageComponent]
        | Sequence[dict[str, Any]]
    ),
    *,
    platform: str,
) -> dict[str, Any]:
    return await cls._require_context().send_message_by_id(
        type,
        id,
        content,
        platform=platform,
    )
```

**参数**:
- `type` (`str`): 消息类型（`group` 或 `private`）
- `id` (`str`): 目标 ID
- `content`: 消息内容
- `platform` (`str`): 平台标识

**返回**: `dict[str, Any]` - 发送结果

---

#### `register_llm_tool(name, parameters_schema, desc, func_obj, *, active)`

注册 LLM 工具。

```python
@classmethod
async def register_llm_tool(
    cls,
    name: str,
    parameters_schema: dict[str, Any],
    desc: str,
    func_obj: Callable[..., Awaitable[Any]] | Callable[..., Any],
    *,
    active: bool = True,
) -> list[str]:
    return await cls._require_context().register_llm_tool(
        name,
        parameters_schema,
        desc,
        func_obj,
        active=active,
    )
```

**参数**:
- `name` (`str`): 工具名称
- `parameters_schema` (`dict[str, Any]`): 参数模式
- `desc` (`str`): 工具描述
- `func_obj`: 工具函数
- `active` (`bool`): 是否激活

**返回**: `list[str]` - 注册的工具名称列表

---

#### `unregister_llm_tool(name)`

注销 LLM 工具。

```python
@classmethod
async def unregister_llm_tool(cls, name: str) -> bool:
    return await cls._require_context().unregister_llm_tool(name)
```

**参数**:
- `name` (`str`): 工具名称

**返回**: `bool` - 是否成功注销

---

### 使用示例

```python
from astrbot_sdk import StarTools
from astrbot_sdk.events import MessageEvent

class MyPlugin(Star):
    async def on_start(self, ctx):
        # 注册 LLM 工具
        await StarTools.register_llm_tool(
            name="my_tool",
            parameters_schema={
                "type": "object",
                "properties": {
                    "text": {"type": "string"}
                }
            },
            desc="我的工具",
            func_obj=self.my_tool_func
        )

    async def my_tool_func(self, text: str) -> str:
        return f"处理结果: {text}"

    @on_command("test")
    async def test(self, event: MessageEvent):
        # 发送消息
        await StarTools.send_message(
            event.session,
            "Hello!"
        )

        # 激活工具
        await StarTools.activate_llm_tool("my_tool")
```

---

## PluginKVStoreMixin - KV 存储混入

插件作用域的 KV 存储助手，基于运行时 db 客户端。

### 类定义

```python
class PluginKVStoreMixin:
    """Plugin-scoped KV helpers backed by the runtime db client."""
```

### 属性

#### `plugin_id`

获取插件 ID。

```python
@property
def plugin_id(self) -> str:
    ctx = self._runtime_context()
    return ctx.plugin_id
```

### 实例方法

#### `put_kv_data(key, value)`

存储键值数据。

```python
async def put_kv_data(self, key: str, value: Any) -> None:
    ctx = self._runtime_context()
    await ctx.db.set(str(key), value)
```

**参数**:
- `key` (`str`): 键名
- `value` (`Any`): 值

---

#### `get_kv_data(key, default)`

获取键值数据。

```python
async def get_kv_data(self, key: str, default: _VT) -> _VT:
    ctx = self._runtime_context()
    value = await ctx.db.get(str(key))
    return default if value is None else value
```

**参数**:
- `key` (`str`): 键名
- `default`: 默认值

**返回**: 存储的值或默认值

---

#### `delete_kv_data(key)`

删除键值数据。

```python
async def delete_kv_data(self, key: str) -> None:
    ctx = self._runtime_context()
    await ctx.db.delete(str(key))
```

**参数**:
- `key` (`str`): 键名

---

### 使用示例

```python
from astrbot_sdk import Star, PluginKVStoreMixin

class MyPlugin(Star, PluginKVStoreMixin):
    async def on_start(self, ctx):
        # 存储数据
        await self.put_kv_data("initialized", True)
        await self.put_kv_data("config", {"key": "value"})

    @on_command("config")
    async def config_command(self, event: MessageEvent, key: str, value: str):
        # 保存配置
        await self.put_kv_data(f"config_{key}", value)
        await event.reply(f"配置已保存: {key} = {value}")

    @on_command("get_config")
    async def get_config(self, event: MessageEvent, key: str):
        # 读取配置
        value = await self.get_kv_data(f"config_{key}", default="未设置")
        await event.reply(f"{key} = {value}")

    @on_command("delete_config")
    async def delete_config(self, event: MessageEvent, key: str):
        # 删除配置
        await self.delete_kv_data(f"config_{key}")
        await event.reply(f"配置已删除: {key}")
```

---

## 相关模块

- **核心类**: `astrbot_sdk.star.Star`, `astrbot_sdk.context.Context`
- **事件处理**: `astrbot_sdk.events.MessageEvent`
- **装饰器**: `astrbot_sdk.decorators`

---

**版本**: v4.0
**最后更新**: 2026-03-17
