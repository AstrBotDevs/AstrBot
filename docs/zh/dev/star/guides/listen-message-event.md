# 处理消息事件

事件监听器可以收到平台下发的消息内容，可以实现指令、指令组、事件监听等功能。

事件监听器的注册器在 `astrbot.api.event.filter` 下，需要先导入。请务必导入，否则会和 python 的高阶函数 filter 冲突。

```py
from astrbot.api.event import filter, AstrMessageEvent
```

## 消息与事件

AstrBot 接收消息平台下发的消息，并将其封装为 `AstrMessageEvent` 对象，传递给插件进行处理。

![message-event](https://files.astrbot.app/docs/zh/dev/star/guides/message-event.svg)

### 消息事件

`AstrMessageEvent` 是 AstrBot 的消息事件对象，其中存储了消息发送者、消息内容等信息。

### 消息对象

`AstrBotMessage` 是 AstrBot 的消息对象，其中存储了消息平台下发的消息具体内容，`AstrMessageEvent` 对象中包含一个 `message_obj` 属性用于获取该消息对象。

```py{11}
class AstrBotMessage:
    """AstrBot 的消息对象"""

    type: MessageType  # 消息类型
    self_id: str  # 机器人的识别id
    session_id: str  # 会话id。取决于 unique_session 的设置。
    message_id: str  # 消息id
    group: Group | None  # 群组元数据；私聊为 None
    group_id: str = ""  # 群组 id，由 group.group_id 派生；私聊为空字符串
    sender: MessageMember  # 发送者
    message: List[BaseMessageComponent]  # 消息链。比如 [Plain("Hello"), At(qq=123456)]
    message_str: (
        str  # 最直观的纯文本消息字符串，将消息链中的 Plain 消息（文本消息）连接起来
    )
    raw_message: object
    timestamp: int  # 消息时间戳
```

其中，`raw_message` 是消息平台适配器的**原始消息对象**。

`AstrBotMessage.group` 是入站时附带的 `Group`。常见字段：

- `group_id`：群、频道或房间 id
- `group_name`：显示名
- `group_avatar`：头像 URL
- `group_owner`：群主 id
- `group_admins`：管理员 id 列表
- `members`：成员列表；不完整时为 `None`
- `member_count`：平台给出的成员总数，即使成员列表缺失也可以有值

`member_count` 的含义由平台定义。例如 LINE 的计数不含机器人本身，其他平台可能包含。

`await event.get_group()` 会在需要时调用平台 API 补全上述字段，并返回入站 `Group` 的拷贝，不会改写入站对象。成员列表过大或不完整时，`members` 可能为 `None`；此时仍应使用 `member_count`。

### 消息链

![message-chain](https://files.astrbot.app/docs/zh/dev/star/guides/message-chain.svg)

`消息链`描述一个消息的结构，是一个有序列表，列表中每一个元素称为`消息段`。

常见的消息段类型有：

- `Plain`：文本消息段
- `At`：提及消息段
- `Image`：图片消息段
- `Record`：语音消息段
- `Video`：视频消息段
- `File`：文件消息段

大多数消息平台都支持上面的消息段类型。

此外，OneBot v11 平台（QQ 个人号等）还支持以下较为常见的消息段类型：

- `Face`：表情消息段
- `Node`：合并转发消息中的一个节点
- `Nodes`：合并转发消息中的多个节点
- `Poke`：戳一戳消息段

在 AstrBot 中，消息链表示为 `List[BaseMessageComponent]` 类型的列表。

#### QQ 系统表情的模型上下文

对 OneBot v11 与 NapCat 入站的 `Face` 消息段，AstrBot 会在发送给模型的组件上下文中附加可读的 QQ 系统表情语义，例如 `Face(id=111)` 会显示为 `[QQ Face: 可怜 (id: 111)]`。已知系统表情会显示名称；未识别或异常的 ID 会保留 ID 并显示为 `unknown`，不会被猜测或丢弃。

这项补全覆盖当前消息、引用消息、合并转发和群聊上下文，也会传给仅接受文本 prompt 的内置第三方 Agent Runner。它不会修改 `event.message_str`、原始 `Face` 组件或出站消息；插件如需按编号处理表情，仍可直接检查 `Face.id`。

#### 群聊 JSON 卡片

群聊 JSON 卡片会记入群聊上下文，并在主动回复或普通 LLM 请求没有文本 prompt 时作为 `[Shared Card]` 卡片摘要进入模型输入，而不会把原始 JSON 整段塞进 prompt。

## 指令

![message-event-simple-command](https://files.astrbot.app/docs/zh/dev/star/guides/message-event-simple-command.svg)

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import PluginContext, Star


class MyPlugin(Star):
    def __init__(self, context: PluginContext):
        super().__init__(context)

    @filter.command("helloworld")  # from astrbot.api.event.filter import command
    async def helloworld(self, event: AstrMessageEvent):
        """这是 hello world 指令"""
        user_name = event.get_sender_name()
        message_str = event.message_str  # 获取消息的纯文本内容
        yield event.plain_result(f"Hello, {user_name}!")
```

> [!TIP]
> 指令不能带空格，否则 AstrBot 会将其解析到第二个参数。可以使用下面的指令组功能，或者也使用监听器自己解析消息内容。

## 带参指令

![command-with-param](https://files.astrbot.app/docs/zh/dev/star/guides/command-with-param.svg)

AstrBot 会自动帮你解析指令的参数。

```python
@filter.command("add")
async def add(self, event: AstrMessageEvent, a: int, b: int):
    # /add 1 2 -> 结果是: 3
    yield event.plain_result(f"Wow! The answer is {a + b}!")
```

参数由 **Orbit Command Syntax** 解析，并按照函数签名转换为对应类型。Orbit 只在消息命中已注册的完整指令名、指令组或别名后解析参数；完全未知的根指令仍会进入普通插件过滤器或 LLM。

命令 catalog 由插件生命周期按 Pipeline 配置显式拥有，并在插件加载、卸载、重载、启禁以及指令重命名、别名或启用状态修改后原子替换不可变 snapshot。消息处理热路径只读取当前 snapshot，不会重新遍历 handler 或构建索引。

Orbit 不是 shell，也不会执行 shell。它支持确定性的 POSIX quoting 和 escaping 子集：ASCII 空格和 Tab 分隔参数；单引号中的字符都是字面值；双引号支持 `\$`、`` \` ``、`\\`、`\"` 和反斜杠换行；未引用的反斜杠转义下一个字符。相邻片段属于同一个参数，因此 `ab"cd"'ef'` 等价于 `abcdef`，而 `""` 和 `''` 都会产生空参数。

对于 Orbit 成功接受的参数表达式，相同表达式在 POSIX shell 中会产生相同且不依赖环境的 `argv`。Orbit 不执行变量、命令、算术或波浪号展开，不执行字段拆分、glob，也不支持重定向、管道、列表、子 shell、注释或未引用换行。未转义且不在单引号内的 `$` 和反引号会被保守拒绝。

需要把特殊字符作为普通数据传入时，请引用或转义它们：

```text
/session name '$HOME'
/session name "a|b"
/session name \*.txt
/plugin install 'https://example.com?a=1&b=2#readme'
/session name "C:\Users\bot"
/match '^user#[0-9]+$'
```

双引号中的反斜杠只转义上面列出的五类字符，所以 `"C:\Users\bot"` 会保留 Windows 路径中的反斜杠。Unicode 会原样保留，指令匹配区分大小写。

### Orbit 指令设计规范

Orbit 只定义已注册指令头之后的参数语言；唤醒前缀、根指令和子指令属于 AstrBot framing。一个符合 Orbit Command Syntax 的参数表达式必须能被拆成确定的 `argv`，每个 word 恰好对应一个字段，并且相同表达式在 POSIX shell 中产生相同且不依赖环境的结果。它不能依赖环境变量、当前目录、文件、locale、glob 结果或 shell 执行。

插件指令应遵循以下设计约定：

- 根指令使用表示领域或资源的单数英文名，例如 `project`、`persona`。为兼容 Telegram 原生菜单，推荐使用不超过 32 个字符的 ASCII 小写字母、数字和下划线，并以字母开头。
- 指令组使用名词，子指令使用完整、明确且小写的动词，例如 `list`、`show`、`create`、`delete`、`set`、`unset`、`enable` 和 `disable`。复合子指令使用连字符，例如 `create-for`。
- 查询、状态切换和修改操作分别使用显式子指令。状态修改应采用幂等的 `enable`/`disable` 或 `set`/`unset`，不要让同一入口根据当前状态隐式 toggle。
- 长 option 使用 `--kebab-case`；常用 option 可以额外提供一个单字母短名。布尔行为使用 flag，有限选项使用 `Enum` 或 `Literal`，可省略值使用 `T | None` 和默认值 `None`。
- 一个位置参数表达一个概念。可能包含空格的末尾自由文本使用 `GreedyStr`；不要在 handler 中对 `event.message_str` 再做 `split()` 或自行解释引号。
- handler 的类型标注就是参数 schema。只使用受支持的标量、`Enum`、`Literal`、Optional、`GreedyStr` 和 `Annotated[..., option(...)]`；不支持的签名会在插件注册时失败。
- 别名也应遵守同样的命名约束，并只用于真实同义入口。帮助文本和文档应始终使用主名称。
- 为 handler 编写简短、可独立理解的 docstring；Telegram 和 Discord 会用它生成原生指令描述。不满足平台名称约束的入口仍可用于文本消息，但不会注册为对应平台的原生指令。
- 指令 handler 回复后应终止事件传播（`stop_event()`），避免后续阶段继续处理同一条消息。

例如，资源型插件可以使用 `/project list`、`/project show <name>`、`/project create <name> --template <id>` 和 `/project delete <name> --force`。参数中的 `$`、`#`、glob、URL 查询串或 operator 是数据时，由调用者按 Orbit 规则引用；插件收到的是已经完成确定性分词的值，不应再进行 shell 展开。

开发和测试时至少覆盖普通值、空参数、带空格值、Unicode、`--name=value`、`--`、负数、未知 option，以及经过引用的 `$`、`#`、glob 和 URL。未引用的 expansion 或 operator 应产生结构化指令诊断，而不是进入 handler。

### 参数类型与 GreedyStr

第一版支持 `str`、`int`、`float`、`bool`、`Enum`、`Literal[...]` 和 `T | None`（或 `Optional[T]`）。类型标注是转换依据；只有未标注参数才会从默认值推断类型，否则默认为 `str`。Enum 的所有成员值必须统一使用受支持的标量类型，因此字符串、整数、浮点数和布尔值 Enum 都可以绑定；空 Enum、混合值类型或其他值类型会在注册期失败。多类型 Union（例如 `str | int | None`）同样不受支持，插件会在注册 handler 时立即得到包含插件与 handler 名称的错误。

`GreedyStr` 会接收所有剩余位置参数，并用单个空格连接已经完成 quoting/escaping 的字段。它必须是最后一个位置参数；没有默认值时至少需要一个字段，只有显式默认值才允许省略。

```python
from enum import Enum
from typing import Literal

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.event.filter import GreedyStr


class Mode(Enum):
    FAST = "fast"
    SAFE = "safe"


@filter.command("search")
async def search(
    self,
    event: AstrMessageEvent,
    mode: Mode,
    scope: Literal["local", "all"],
    query: GreedyStr,
):
    yield event.plain_result(f"{mode.value}: {scope}: {query}")
```

### 可选项与布尔标志

使用 `typing.Annotated` 和 `filter.option(...)` 可以声明命名可选项。每个可选项可以同时声明长名称和短名称：

```python
from typing import Annotated

from astrbot.api.event import AstrMessageEvent, filter


@filter.command("deploy")
async def deploy(
    self,
    event: AstrMessageEvent,
    target: str,
    replicas: Annotated[int | None, filter.option("--replicas", "-r")] = None,
    force: Annotated[bool, filter.option("--force", "-f")] = False,
):
    # /deploy production --replicas 3 --force
    # /deploy --replicas=3 production -f
    yield event.plain_result(
        f"target={target}, replicas={replicas}, force={force}",
    )
```

- 可选项可以放在位置参数之前或之后，并支持 `--name=value` 形式。
- `bool` 可选项不带值时是 `True`；也可以显式传入 `true/false`、`yes/no` 或 `1/0`，例如 `--force=false`。
- `--` 会终止可选项解析，后面的内容都按位置参数处理。例如 `/deploy -- --force` 会把 `--force` 解析为 `target`，而不是布尔标志。
- 可省略的值可以写成 `T | None` 或 `typing.Optional[T]`，并将默认值设为 `None`；未提供该可选项时，处理函数会收到 `None`。
- 未知或重复 option、缺少 option 值会分别报告错误。未知 option 会建议最接近的已声明名称。
- `-1` 等负数可以直接绑定到数值位置参数。要把 `-x` 传给字符串位置参数，请写成 `-- -x`。

## 指令组

指令组可以帮助你组织指令。

```python
@filter.command_group("math")
def math():
    pass


@math.command("add")
async def add(self, event: AstrMessageEvent, a: int, b: int):
    # /math add 1 2 -> 结果是: 3
    yield event.plain_result(f"结果是: {a + b}")


@math.command("sub")
async def sub(self, event: AstrMessageEvent, a: int, b: int):
    # /math sub 1 2 -> 结果是: -1
    yield event.plain_result(f"结果是: {a - b}")
```

指令组函数内不需要实现任何函数，请直接 `pass` 或者添加函数内注释。指令组的子指令使用 `指令组名.command` 来注册。

当用户没有输入子指令时，会报告不完整指令并列出该组的子指令树。根指令组已识别、但子指令不存在时会报告 `UNKNOWN_SUBCOMMAND`，不会再落入 LLM；只有完全未知的根指令保持 LLM fallback。

![image](https://files.astrbot.app/docs/source/images/plugin/image-1.png)

![image](https://files.astrbot.app/docs/source/images/plugin/898a169ae7ed0478f41c0a7d14cb4d64.png)

![image](https://files.astrbot.app/docs/source/images/plugin/image-2.png)

理论上，指令组可以无限嵌套！

```py
"""
math
├── calc
│   ├── add (a(int),b(int),)
│   ├── sub (a(int),b(int),)
│   ├── help (无参数指令)
"""


@filter.command_group("math")
def math():
    pass


@math.group("calc")  # 请注意，这里是 group，而不是 command_group
def calc():
    pass


@calc.command("add")
async def add(self, event: AstrMessageEvent, a: int, b: int):
    yield event.plain_result(f"结果是: {a + b}")


@calc.command("sub")
async def sub(self, event: AstrMessageEvent, a: int, b: int):
    yield event.plain_result(f"结果是: {a - b}")


@calc.command("help")
async def calc_help(self, event: AstrMessageEvent):
    # /math calc help
    yield event.plain_result("这是一个计算器插件，拥有 add, sub 指令。")
```

## 指令别名

可以为指令或指令组添加不同的别名：

```python
@filter.command("help", alias={"帮助", "helpme"})
async def help(self, event: AstrMessageEvent):
    yield event.plain_result("这是一个计算器插件，拥有 add, sub 指令。")
```

### 直接解析参数

插件可以通过受支持的 `astrbot.api.command` API 在指令 handler 之外复用同一参数语法。`parse_arguments()` 返回只读的 `CommandInvocation`，其中 `words`、fragment 和 Unicode code-point span 均不可变；失败时抛出带结构化 `CommandDiagnostic` 的 `CommandSyntaxError`。

```python
from astrbot.api.command import CommandSyntaxError, parse_arguments

try:
    invocation = parse_arguments(r"""one "two three" C:\Users\bot""")
    argv = invocation.argv
except CommandSyntaxError as exc:
    diagnostic = exc.diagnostic
```

`option` 和 `GreedyStr` 应从 `astrbot.api.event.filter` 导入；插件不要导入内部 catalog、engine 或 handler metadata。

### 事件类型过滤

#### 接收所有

这将接收所有的事件。

```python
@filter.event_message_type(filter.EventMessageType.ALL)
async def on_all_message(self, event: AstrMessageEvent):
    yield event.plain_result("收到了一条消息。")
```

#### 群聊和私聊

```python
@filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
async def on_private_message(self, event: AstrMessageEvent):
    message_str = event.message_str  # 获取消息的纯文本内容
    yield event.plain_result("收到了一条私聊消息。")
```

`EventMessageType` 是一个 `enum.Flag` 类型，当前包含以下值：

- `PRIVATE_MESSAGE`：私聊消息
- `GROUP_MESSAGE`：群聊消息
- `OTHER_MESSAGE`：不属于私聊或群聊的其他消息
- `ALL`：以上所有消息类型

#### 消息平台

```python
@filter.platform_adapter_type(
    filter.PlatformAdapterType.AIOCQHTTP | filter.PlatformAdapterType.QQOFFICIAL
)
async def on_aiocqhttp(self, event: AstrMessageEvent):
    """只接收 AIOCQHTTP 和 QQOFFICIAL 的消息"""
    yield event.plain_result("收到了一条信息")
```

当前版本下，`PlatformAdapterType` 支持以下值：`AIOCQHTTP`、`QQOFFICIAL`、`QQOFFICIAL_WEBHOOK`、`TELEGRAM`、`WECOM`、`WECOM_AI_BOT`、`LARK`、`DINGTALK`、`DISCORD`、`SLACK`、`KOOK`、`VOCECHAT`、`WEIXIN_OFFICIAL_ACCOUNT`、`SATORI`、`MISSKEY`、`LINE`、`MATRIX`、`WEIXIN_OC`、`MATTERMOST`、`WEBCHAT`、`ALL`。

#### 权限与动作

```python
@filter.permission("session.manage")
@filter.command("test")
async def test(self, event: AstrMessageEvent):
    pass
```

`@filter.permission("session.manage")` 会在管道里调用统一授权入口
`AuthorizationService.authorize()`。只有当前会话的 `session_admin` /
`session_owner`，或作用域匹配的 `instance_operator` / Dashboard
`operator` / `root`，才能执行该指令。平台群主/群管理员只影响当前
`(config_id, UMO)`，不会变成全局 operator。

插件自定义动作必须使用自己的命名空间，并再次调用核心授权：

```python
decision = await self.context.authz.authorize(
    event,
    "plugin:example:publish",
    self.context.authz.session_resource(event),
)
if not decision.allowed:
    return
```

不要再使用已删除的 `PermissionType` 或 `@filter.permission_type`。
`event.is_admin()` 恒为 `False`，不能当作授权依据。完整模型见[项目架构](/dev/architecture#统一授权系统)。

### 多个过滤器

支持同时使用多个过滤器，只需要在函数上添加多个装饰器即可。过滤器使用 `AND` 逻辑。也就是说，只有所有的过滤器都通过了，才会执行函数。

```python
@filter.command("helloworld")
@filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
async def helloworld(self, event: AstrMessageEvent):
    yield event.plain_result("你好！")
```

### 事件钩子

> [!TIP]
> 事件钩子不支持与上面的 @filter.command, @filter.command_group, @filter.event_message_type, @filter.platform_adapter_type, @filter.permission 一起使用。

#### Bot 初始化完成时

```python
from astrbot.api.event import filter, AstrMessageEvent


@filter.on_astrbot_loaded()
async def on_astrbot_loaded(self):
    print("AstrBot 初始化完成")
```

#### 平台加载完成时

每加载完成一个消息平台实例，都会触发 `on_platform_loaded` 钩子。该钩子不接收消息事件或平台参数。

```python
from astrbot.api.event import filter


@filter.on_platform_loaded()
async def on_platform_loaded(self):
    print("一个消息平台实例加载完成")
```

#### 插件加载完成时

每加载完成一个插件，都会触发 `on_plugin_loaded` 钩子，并传入该插件的元数据。

```python
from astrbot.api.event import filter


@filter.on_plugin_loaded()
async def on_plugin_loaded(self, metadata):
    print(f"插件 {metadata.name} 加载完成")
```

#### 插件卸载完成时

每卸载完成一个插件，都会触发 `on_plugin_unloaded` 钩子，并传入该插件的元数据。

```python
from astrbot.api.event import filter


@filter.on_plugin_unloaded()
async def on_plugin_unloaded(self, metadata):
    print(f"插件 {metadata.name} 卸载完成")
```

#### 插件处理消息异常时

插件的消息处理函数抛出异常时，会触发 `on_plugin_error` 钩子。它会传入当前事件、插件名、处理函数名、异常对象和格式化后的回溯文本。

```python
from astrbot.api.event import AstrMessageEvent, filter


@filter.on_plugin_error()
async def on_plugin_error(
    self,
    event: AstrMessageEvent,
    plugin_name: str,
    handler_name: str,
    error: Exception,
    traceback_text: str,
):
    print(f"{plugin_name}.{handler_name}: {error}")
    print(traceback_text)
```

如果该钩子调用 `event.stop_event()`，AstrBot 将不再向当前会话发送默认的插件错误提示；插件可以自行记录或转发错误。

#### 等待 LLM 请求时

在 AstrBot 准备调用 LLM 但还未获取会话锁时，会触发 `on_waiting_llm_request` 钩子。

这个钩子适合用于发送"正在等待请求..."等用户反馈提示，亦或是在锁外及时获取LLM请求而不用等到锁被释放。

```python
from astrbot.api.event import filter, AstrMessageEvent


@filter.on_waiting_llm_request()
async def on_waiting_llm(self, event: AstrMessageEvent):
    await event.send(event.plain_result("🤔 正在等待请求...").chain)
```

> 这里不能使用 yield 来发送消息。如需发送，请直接使用 `event.send()` 方法。

#### LLM 请求时

> 这里不能使用 yield 来发送消息。如需发送，请直接使用 `event.send()` 方法。

在 AstrBot 默认的执行流程中，在调用 LLM 前，会触发 `on_llm_request` 钩子。

可以获取到 `ProviderRequest` 对象，可以对其进行修改。

ProviderRequest 对象包含了 LLM 请求的所有信息，包括请求的文本、系统提示等。

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.provider import ProviderRequest


@filter.on_llm_request()
async def my_custom_hook_1(
    self, event: AstrMessageEvent, req: ProviderRequest
):  # 请注意有三个参数
    print(req)  # 打印请求的文本
    req.system_prompt += "自定义 system_prompt"  # 如果有其他替代方法，不建议使用此种方式来追加每轮对话都会改变的提示词，否则会破坏缓存，大大增加价格（约增加 7-20 倍的价格）。
```

> [!WARNING]
> **关于提示词的追加**
>
> `req.system_prompt += ...` 适合追加稳定、长期有效的角色设定或全局规则。不建议把每轮都会变化的内容追加到 `system_prompt`，例如当前时间、好感度、状态栏、短期记忆片段、检索摘要等。这类写法会让系统提示词在每轮请求中变化，容易破坏模型服务端的提示词缓存，显著增加请求成本和首 token 延迟。
>
> 对于每轮都会变化、内容量中小的提示词，可以保留原始 `req.prompt`，再把动态上下文添加到本轮用户输入之前。这样不会让 `system_prompt` 每轮变化，也不会意外覆盖用户的原始消息：
>
> ```python
> @filter.on_llm_request()
> async def add_dynamic_prompt(self, event: AstrMessageEvent, req: ProviderRequest):
>     original_prompt = req.prompt or ""
>     dynamic_context = (
>         "<dynamic_context>\n"
>         "当前时间：2026-05-03 20:00\n"
>         "好感度：72\n"
>         "相关记忆：用户喜欢简洁直接的回答。\n"
>         "</dynamic_context>"
>     )
>     req.prompt = f"{dynamic_context}\n\n{original_prompt}"
> ```
>
> 修改 `req.prompt` 也会改变随后保存到会话历史的用户消息，因此只应放入允许持久化的内容。当前公共插件 SDK 尚未导出可标记为“仅本轮、不保存”的消息内容块；瞬时状态、敏感数据或较大的长期记忆、知识库和外部查询结果应优先注册为 `llm_tool`，让模型按需读取。

#### LLM 请求完成时

在 LLM 请求完成后，会触发 `on_llm_response` 钩子。

可以获取到 `ProviderResponse` 对象，可以对其进行修改。

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.provider import LLMResponse


@filter.on_llm_response()
async def on_llm_resp(
    self, event: AstrMessageEvent, resp: LLMResponse
):  # 请注意有三个参数
    print(resp)
```

> 这里不能使用 yield 来发送消息。如需发送，请直接使用 `event.send()` 方法。

#### Agent 开始运行时

在 Agent 开始运行时，会触发 `on_agent_begin` 钩子。

```python
from astrbot.api.event import filter, AstrMessageEvent


@filter.on_agent_begin()
async def on_agent_begin(self, event: AstrMessageEvent, run_context):
    print("Agent 开始运行")
```

> 这里不能使用 yield 来发送消息。如需发送，请直接使用 `event.send()` 方法。

#### LLM 工具调用前

在 Agent 准备调用 LLM 工具时，会触发 `on_using_llm_tool` 钩子。

可以获取到 `FunctionTool` 对象和工具调用参数。

```python
from astrbot.api import FunctionTool
from astrbot.api.event import filter, AstrMessageEvent


@filter.on_using_llm_tool()
async def on_using_llm_tool(
    self,
    event: AstrMessageEvent,
    tool: FunctionTool,
    tool_args: dict | None,
):
    print(tool.name, tool_args)
```

> 这里不能使用 yield 来发送消息。如需发送，请直接使用 `event.send()` 方法。

#### LLM 工具调用后

在 LLM 工具调用完成后，会触发 `on_llm_tool_respond` 钩子。

可以获取到 `FunctionTool` 对象、工具调用参数和工具调用结果。

```python
from mcp.types import CallToolResult

from astrbot.api import FunctionTool
from astrbot.api.event import filter, AstrMessageEvent


@filter.on_llm_tool_respond()
async def on_llm_tool_respond(
    self,
    event: AstrMessageEvent,
    tool: FunctionTool,
    tool_args: dict | None,
    tool_result: CallToolResult | None,
):
    print(tool.name, tool_args, tool_result)
```

> 这里不能使用 yield 来发送消息。如需发送，请直接使用 `event.send()` 方法。

#### Agent 运行完成时

在 Agent 运行完成后，会触发 `on_agent_done` 钩子。这个钩子会在 `on_llm_response` 之后触发。本质上和 `on_llm_response` 一样。

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.provider import LLMResponse


@filter.on_agent_done()
async def on_agent_done(self, event: AstrMessageEvent, run_context, resp: LLMResponse):
    print(resp)
```

> 这里不能使用 yield 来发送消息。如需发送，请直接使用 `event.send()` 方法。

#### 发送消息前

在发送消息前，会触发 `on_decorating_result` 钩子。

可以在这里实现一些消息的装饰，比如转语音、转图片、加前缀等等

```python
from astrbot.api.event import filter, AstrMessageEvent
import astrbot.api.message_components as Comp


@filter.on_decorating_result()
async def on_decorating_result(self, event: AstrMessageEvent):
    result = event.get_result()
    chain = result.chain
    print(chain)  # 打印消息链
    chain.append(Comp.Plain("!"))  # 在消息链的最后添加一个感叹号
```

> 这里不能使用 yield 来发送消息。这个钩子只是用来装饰 event.get_result().chain 的。如需发送，请直接使用 `event.send()` 方法。

#### 发送消息后

在发送消息给消息平台后，会触发 `after_message_sent` 钩子。

```python
from astrbot.api.event import filter, AstrMessageEvent


@filter.after_message_sent()
async def after_message_sent(self, event: AstrMessageEvent):
    pass
```

> 这里不能使用 yield 来发送消息。如需发送，请直接使用 `event.send()` 方法。

### 优先级

指令、事件监听器、事件钩子可以设置优先级，先于其他指令、监听器、钩子执行。默认优先级是 `0`。

```python
@filter.command("helloworld", priority=1)
async def helloworld(self, event: AstrMessageEvent):
    yield event.plain_result("Hello!")
```

## 控制事件传播

```python{6}
@filter.command("check_ok")
async def check_ok(self, event: AstrMessageEvent):
    ok = self.check()  # 自己的逻辑
    if not ok:
        yield event.plain_result("检查失败")
        event.stop_event()  # 停止事件传播
```

当事件停止传播，后续所有步骤将不会被执行。

假设有一个插件 A，A 终止事件传播之后所有后续操作都不会执行，比如执行其它插件的 handler、请求 LLM。
