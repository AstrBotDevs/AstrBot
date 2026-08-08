# Handling Message Events

Event listeners can receive message content delivered by the platform and implement features such as commands, command groups, and event listening.

Event listener decorators are located in `astrbot.api.event.filter` and must be imported first. Please make sure to import it, otherwise it will conflict with Python's built-in `filter` higher-order function.

```py
from astrbot.api.event import filter, AstrMessageEvent
```

## Messages and Events

AstrBot receives messages delivered by messaging platforms and encapsulates them as `AstrMessageEvent` objects, which are then passed to plugins for processing.

![message-event](https://files.astrbot.app/docs/en/dev/star/guides/message-event.svg)

### Message Events

`AstrMessageEvent` is AstrBot's message event object, which stores information about the message sender, message content, etc.

### Message Object

`AstrBotMessage` is AstrBot's message object, which stores the specific content of messages delivered by the messaging platform. The `AstrMessageEvent` object contains a `message_obj` attribute to retrieve this message object.

```py{11}
class AstrBotMessage:
    """AstrBot's message object"""

    type: MessageType  # Message type
    self_id: str  # Bot's identification ID
    session_id: str  # Session ID. Depends on the unique_session setting.
    message_id: str  # Message ID
    group_id: str = ""  # Group ID, empty if it's a private chat
    sender: MessageMember  # Sender
    message: List[
        BaseMessageComponent
    ]  # Message chain. For example: [Plain("Hello"), At(qq=123456)]
    message_str: str  # The most straightforward plain text message string, concatenating Plain messages (text messages) from the message chain
    raw_message: object
    timestamp: int  # Message timestamp
```

Here, `raw_message` is the **raw message object** from the messaging platform adapter.

### Message Chain

![message-chain](https://files.astrbot.app/docs/en/dev/star/guides/message-chain.svg)

A `message chain` describes the structure of a message. It's an ordered list where each element is called a `message segment`.

Common message segment types include:

- `Plain`: Text message segment
- `At`: Mention message segment
- `Image`: Image message segment
- `Record`: Audio message segment
- `Video`: Video message segment
- `File`: File message segment

Most messaging platforms support the above message segment types.

Additionally, the OneBot v11 platform (QQ personal accounts, etc.) also supports the following common message segment types:

- `Face`: Emoji message segment
- `Node`: A node in a forward message
- `Nodes`: Multiple nodes in a forward message
- `Poke`: Poke message segment

In AstrBot, message chains are represented as lists of type `List[BaseMessageComponent]`.

#### QQ system-face model context

For inbound `Face` segments from OneBot v11 and NapCat, AstrBot adds readable QQ system-face semantics to the component context sent to the model. For example, `Face(id=111)` is rendered as `[QQ Face: 可怜 (id: 111)]`. Known system faces include their names; unknown or malformed IDs retain the ID and are rendered as `unknown` rather than guessed or discarded.

This enrichment covers the current message, quoted messages, forwarded messages, and group-chat context, and is also passed to built-in third-party Agent Runners that accept text prompts only. It does not modify `event.message_str`, the original `Face` component, or outbound messages. Plugins that need ID-based handling can continue to inspect `Face.id` directly.

## Commands

![message-event-simple-command](https://files.astrbot.app/docs/en/dev/star/guides/message-event-simple-command.svg)

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import PluginContext, Star


class MyPlugin(Star):
    def __init__(self, context: PluginContext):
        super().__init__(context)

    @filter.command("helloworld")  # from astrbot.api.event.filter import command
    async def helloworld(self, event: AstrMessageEvent):
        """This is a hello world command"""
        user_name = event.get_sender_name()
        message_str = event.message_str  # Get the plain text content of the message
        yield event.plain_result(f"Hello, {user_name}!")
```

> [!TIP]
> Commands cannot contain spaces, otherwise AstrBot will parse them as a second parameter. You can use the command group feature below, or use a listener to parse the message content yourself.

## Commands with Parameters

![command-with-param](https://files.astrbot.app/docs/en/dev/star/guides/command-with-param.svg)

AstrBot will automatically parse command parameters for you.

```python
@filter.command("add")
async def add(self, event: AstrMessageEvent, a: int, b: int):
    # /add 1 2 -> Result is: 3
    yield event.plain_result(f"Wow! The answer is {a + b}!")
```

Arguments are parsed by **Orbit Command Syntax** and converted according to the function signature. Orbit parses arguments only after the message matches a complete registered command, command group, or alias. A completely unknown root command still reaches ordinary plugin filters or the LLM.

The plugin lifecycle explicitly owns one command catalog per Pipeline configuration. Plugin load, unload, reload, enablement changes, command rename, alias changes, and command enablement atomically replace its immutable snapshot. The message hot path only reads the current snapshot and never walks handlers or rebuilds the index.

Orbit is not a shell and never executes a shell. It supports a deterministic subset of POSIX quoting and escaping: ASCII spaces and tabs separate arguments; everything inside single quotes is literal; double quotes recognize `\$`, `` \` ``, `\\`, `\"`, and backslash-newline; an unquoted backslash escapes the next character. Adjacent fragments form one argument, so `ab"cd"'ef'` is `abcdef`, while `""` and `''` each produce an empty argument.

Every argument expression accepted by Orbit produces the same environment-independent `argv` in a POSIX shell. Orbit performs no parameter, command, arithmetic, or tilde expansion; field splitting or globbing; redirection, pipelines, lists, subshells, comments, or unquoted command separators. An unescaped `$` or backtick outside single quotes is conservatively rejected.

Quote or escape special characters when they are data:

```text
/session name '$HOME'
/session name "a|b"
/session name \*.txt
/plugin install 'https://example.com?a=1&b=2#readme'
/session name "C:\Users\bot"
/match '^user#[0-9]+$'
```

A backslash inside double quotes only escapes the five character classes listed above, so `"C:\Users\bot"` preserves the backslashes in a Windows path. Unicode is preserved without normalization, and command matching is case-sensitive.

### Orbit Command Design Specification

Orbit defines the argument language after a registered command header. The wake prefix, root command, and subcommands are AstrBot framing. An argument expression conforms to Orbit Command Syntax when it produces a deterministic `argv`, with exactly one field per word, and the same expression produces the same environment-independent result in a POSIX shell. It cannot depend on environment variables, the working directory, files, locale, glob results, or shell execution.

Plugin commands should follow these conventions:

- Use a singular English noun for the root command, such as `project` or `persona`. For Telegram native-menu compatibility, prefer at most 32 ASCII lowercase letters, digits, and underscores, starting with a letter.
- Use nouns for groups and complete, explicit lowercase verbs for subcommands, such as `list`, `show`, `create`, `delete`, `set`, `unset`, `enable`, and `disable`. Use hyphens in compound subcommands, such as `create-for`.
- Give queries, state transitions, and mutations explicit subcommands. State changes should use idempotent `enable`/`disable` or `set`/`unset` operations rather than one entry that implicitly toggles based on current state.
- Write long options as `--kebab-case`; a frequently used option may also have one single-letter short name. Use flags for Boolean behavior, `Enum` or `Literal` for closed choices, and `T | None` with a `None` default for an omissible value.
- Let each positional represent one concept. Use `GreedyStr` for trailing free text that may contain spaces. Do not split `event.message_str` again or implement another quoting layer inside the handler.
- Treat handler annotations as the parameter schema. Use only supported scalars, `Enum`, `Literal`, Optional, `GreedyStr`, and `Annotated[..., option(...)]`; an unsupported signature fails when the plugin registers.
- Apply the same naming constraints to aliases and reserve them for genuine synonymous entries. Help text and documentation should use the primary name.
- Give each handler a short, self-contained docstring; Telegram and Discord use it for native command descriptions. An entry outside a platform's naming constraints can still work in text messages but is not registered as that platform's native command.

For example, a resource-oriented plugin can expose `/project list`, `/project show <name>`, `/project create <name> --template <id>`, and `/project delete <name> --force`. When `$`, `#`, globs, URL query strings, or operators are data, the caller quotes them according to Orbit rules. The plugin receives the deterministically tokenized value and must not perform shell expansion.

At minimum, development tests should cover ordinary values, empty arguments, values with spaces, Unicode, `--name=value`, `--`, negative numbers, unknown options, and quoted `$`, `#`, globs, and URLs. An unquoted expansion or operator should produce a structured command diagnostic and never enter the handler.

### Parameter Types and GreedyStr

The first version supports `str`, `int`, `float`, `bool`, `Enum`, `Literal[...]`, and `T | None` (or `Optional[T]`). An annotation is the source of truth for conversion. Only an unannotated parameter infers its type from its default; otherwise it defaults to `str`. Every member of an Enum must use one supported scalar value type, so string-, integer-, float-, and Boolean-valued Enums bind correctly. Empty Enums, mixed value types, and other value types fail during registration. Multi-type unions such as `str | int | None` are also unsupported and fail with the plugin and handler name.

`GreedyStr` consumes all remaining positional fields and joins their already quoted/escaped values with one space. It must be the last positional parameter. A required `GreedyStr` needs at least one field; omission is allowed only when it has an explicit default.

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

### Options and Boolean Flags

Use `typing.Annotated` with `filter.option(...)` to declare named options. An option can have both a long and a short name:

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

- Options may appear before or after positional arguments and support the `--name=value` form.
- A `bool` option without a value becomes `True`. You can also pass `true/false`, `yes/no`, or `1/0` explicitly, such as `--force=false`.
- `--` stops option parsing, so every following token is treated as a positional argument. For example, `/deploy -- --force` parses `--force` as `target`, not as a Boolean flag.
- An omissible value can use `T | None` or `typing.Optional[T]` with a default of `None`. The handler receives `None` when that option is absent.
- Unknown options, duplicate options, and missing option values produce distinct errors. An unknown option suggests the closest declared name.
- Negative numbers such as `-1` bind directly to numeric positionals. Use `-- -x` to pass `-x` to a string positional.

## Command Groups

Command groups help you organize commands.

```python
@filter.command_group("math")
def math():
    pass


@math.command("add")
async def add(self, event: AstrMessageEvent, a: int, b: int):
    # /math add 1 2 -> Result is: 3
    yield event.plain_result(f"Result is: {a + b}")


@math.command("sub")
async def sub(self, event: AstrMessageEvent, a: int, b: int):
    # /math sub 1 2 -> Result is: -1
    yield event.plain_result(f"Result is: {a - b}")
```

The command group function doesn't need to implement any logic; just use `pass` directly or add comments within the function. Subcommands of the command group are registered using `command_group_name.command`.

When a user omits the subcommand, AstrBot reports an incomplete command and lists the group's subcommand tree. A recognized root group with an unknown child reports `UNKNOWN_SUBCOMMAND` instead of falling back to the LLM. Only a completely unknown root keeps the LLM fallback.

![image](https://files.astrbot.app/docs/source/images/plugin/image-1.png)

![image](https://files.astrbot.app/docs/source/images/plugin/898a169ae7ed0478f41c0a7d14cb4d64.png)

![image](https://files.astrbot.app/docs/source/images/plugin/image-2.png)

Theoretically, command groups can be nested infinitely!

```py
"""
math
├── calc
│   ├── add (a(int),b(int),)
│   ├── sub (a(int),b(int),)
│   ├── help (command with no parameters)
"""


@filter.command_group("math")
def math():
    pass


@math.group("calc")  # Note: this is group, not command_group
def calc():
    pass


@calc.command("add")
async def add(self, event: AstrMessageEvent, a: int, b: int):
    yield event.plain_result(f"Result is: {a + b}")


@calc.command("sub")
async def sub(self, event: AstrMessageEvent, a: int, b: int):
    yield event.plain_result(f"Result is: {a - b}")


@calc.command("help")
async def calc_help(self, event: AstrMessageEvent):
    # /math calc help
    yield event.plain_result("This is a calculator plugin with add and sub commands.")
```

## Command Aliases

You can add different aliases for commands or command groups:

```python
@filter.command("help", alias={"帮助", "helpme"})
async def help(self, event: AstrMessageEvent):
    yield event.plain_result("This is a calculator plugin with add and sub commands.")
```

### Direct Argument Parsing

Plugins can reuse the same argument syntax outside a command handler through the supported `astrbot.api.command` API. `parse_arguments()` returns a read-only `CommandInvocation`; its words, fragments, and Unicode code-point spans are immutable. A failure raises `CommandSyntaxError` with a structured `CommandDiagnostic`.

```python
from astrbot.api.command import CommandSyntaxError, parse_arguments

try:
    invocation = parse_arguments(r"""one "two three" C:\Users\bot""")
    argv = invocation.argv
except CommandSyntaxError as exc:
    diagnostic = exc.diagnostic
```

Import `option` and `GreedyStr` from `astrbot.api.event.filter`. Plugins must not import the internal catalog, engine, or handler metadata.

### Event Type Filtering

#### Receive All

This will receive all events.

```python
@filter.event_message_type(filter.EventMessageType.ALL)
async def on_all_message(self, event: AstrMessageEvent):
    yield event.plain_result("Received a message.")
```

#### Group Chat and Private Chat

```python
@filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
async def on_private_message(self, event: AstrMessageEvent):
    message_str = event.message_str  # Get the plain text content of the message
    yield event.plain_result("Received a private message.")
```

`EventMessageType` is an `enum.Flag` with the following values:

- `PRIVATE_MESSAGE`: Private-chat messages
- `GROUP_MESSAGE`: Group-chat messages
- `OTHER_MESSAGE`: Messages that are neither private nor group messages
- `ALL`: All of the message types above

#### Messaging Platform

```python
@filter.platform_adapter_type(
    filter.PlatformAdapterType.AIOCQHTTP | filter.PlatformAdapterType.QQOFFICIAL
)
async def on_aiocqhttp(self, event: AstrMessageEvent):
    """Only receive messages from AIOCQHTTP and QQOFFICIAL"""
    yield event.plain_result("Received a message")
```

In the current version, `PlatformAdapterType` supports the following values: `AIOCQHTTP`, `QQOFFICIAL`, `QQOFFICIAL_WEBHOOK`, `TELEGRAM`, `WECOM`, `WECOM_AI_BOT`, `LARK`, `DINGTALK`, `DISCORD`, `SLACK`, `KOOK`, `VOCECHAT`, `WEIXIN_OFFICIAL_ACCOUNT`, `SATORI`, `MISSKEY`, `LINE`, `MATRIX`, `WEIXIN_OC`, `MATTERMOST`, `WEBCHAT`, `ALL`.

#### Admin Commands

```python
@filter.permission_type(filter.PermissionType.ADMIN)
@filter.command("test")
async def test(self, event: AstrMessageEvent):
    pass
```

Only admins can use the `test` command.

### Multiple Filters

Multiple filters can be used simultaneously by adding multiple decorators to a function. Filters use `AND` logic, meaning the function will only execute if all filters pass.

```python
@filter.command("helloworld")
@filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
async def helloworld(self, event: AstrMessageEvent):
    yield event.plain_result("Hello!")
```

### Event Hooks

> [!TIP]
> Event hooks do not support being used together with @filter.command, @filter.command_group, @filter.event_message_type, @filter.platform_adapter_type, or @filter.permission_type.

#### On Bot Initialization Complete

```python
from astrbot.api.event import filter, AstrMessageEvent


@filter.on_astrbot_loaded()
async def on_astrbot_loaded(self):
    print("AstrBot initialization complete")
```

#### On Platform Loaded

The `on_platform_loaded` hook runs after each messaging-platform instance finishes loading. It does not receive a message event or platform argument.

```python
from astrbot.api.event import filter


@filter.on_platform_loaded()
async def on_platform_loaded(self):
    print("A messaging-platform instance has loaded")
```

#### On Plugin Loaded

The `on_plugin_loaded` hook runs after each plugin finishes loading and receives that plugin's metadata.

```python
from astrbot.api.event import filter


@filter.on_plugin_loaded()
async def on_plugin_loaded(self, metadata):
    print(f"Plugin {metadata.name} has loaded")
```

#### On Plugin Unloaded

The `on_plugin_unloaded` hook runs after each plugin finishes unloading and receives that plugin's metadata.

```python
from astrbot.api.event import filter


@filter.on_plugin_unloaded()
async def on_plugin_unloaded(self, metadata):
    print(f"Plugin {metadata.name} has unloaded")
```

#### On Plugin Message-Handler Error

The `on_plugin_error` hook runs when a plugin message handler raises an exception. It receives the current event, plugin name, handler name, exception object, and formatted traceback text.

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

If this hook calls `event.stop_event()`, AstrBot does not send its default plugin-error message to the current session. The plugin can log or forward the error itself instead.

#### On Waiting for LLM Request

This hook is triggered when AstrBot is preparing to call the LLM but has not yet acquired the session lock.

It is suitable for sending feedback such as "Waiting for request..." to the user, or for obtaining the LLM request outside the lock without waiting for it to be released.

```python
from astrbot.api.event import filter, AstrMessageEvent


@filter.on_waiting_llm_request()
async def on_waiting_llm(self, event: AstrMessageEvent):
    await event.send(event.plain_result("🤔 Waiting for request...").chain)
```

> You cannot use yield to send messages here. If you need to send, please use the `event.send()` method directly.

#### On LLM Request

In AstrBot's default execution flow, the `on_llm_request` hook is triggered before calling the LLM.

You can obtain the `ProviderRequest` object and modify it.

The ProviderRequest object contains all information about the LLM request, including the request text, system prompt, etc.

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.provider import ProviderRequest


@filter.on_llm_request()
async def my_custom_hook_1(
    self, event: AstrMessageEvent, req: ProviderRequest
):  # Note there are three parameters
    print(req)  # Print the request text
    req.system_prompt += "Custom system_prompt"  # If there is another suitable approach, avoid using this to append prompts that change every round. It can break prompt caching and greatly increase cost (7 - 20x).
```

> [!WARNING]
> **About appending prompts**
>
> `req.system_prompt += ...` is suitable for stable, long-lived role settings or global rules. Do not append content that changes every round to `system_prompt`, such as the current time, affinity score, status panel, short-term memory snippets, or retrieval summaries. Doing so makes the system prompt different for each request, which can break provider-side prompt caching and significantly increase both cost and time to first token.
>
> For small or medium-sized dynamic prompts that change every round, preserve the original `req.prompt` and prepend the dynamic context to the current user input. This keeps `system_prompt` stable and avoids accidentally discarding the user's original message:
>
> ```python
> @filter.on_llm_request()
> async def add_dynamic_prompt(self, event: AstrMessageEvent, req: ProviderRequest):
>     original_prompt = req.prompt or ""
>     dynamic_context = (
>         "<dynamic_context>\n"
>         "Current time: 2026-05-03 20:00\n"
>         "Affinity: 72\n"
>         "Relevant memory: The user prefers concise and direct answers.\n"
>         "</dynamic_context>"
>     )
>     req.prompt = f"{dynamic_context}\n\n{original_prompt}"
> ```
>
> Changing `req.prompt` also changes the user message later saved in conversation history, so add only content that may be persisted. The public plugin SDK does not currently export a message-content part that can be marked as request-only and excluded from history. Prefer an `llm_tool` for transient state, sensitive data, or large long-term-memory, knowledge-base, and external-query results so the model reads them only when needed.

> You cannot use yield to send messages here. If you need to send, please use the `event.send()` method directly.

#### On LLM Response Complete

After the LLM request completes, the `on_llm_response` hook is triggered.

You can obtain the `ProviderResponse` object and modify it.

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.provider import LLMResponse


@filter.on_llm_response()
async def on_llm_resp(
    self, event: AstrMessageEvent, resp: LLMResponse
):  # Note there are three parameters
    print(resp)
```

> You cannot use yield to send messages here. If you need to send, please use the `event.send()` method directly.

#### On Agent Begin

When the Agent starts running, the `on_agent_begin` hook is triggered.

```python
from astrbot.api.event import filter, AstrMessageEvent


@filter.on_agent_begin()
async def on_agent_begin(
    self, event: AstrMessageEvent, run_context
):  # Note there are three parameters
    print("Agent started")
```

> You cannot use yield to send messages here. If you need to send, please use the `event.send()` method directly.

#### Before LLM Tool Call

When the Agent is about to call an LLM tool, the `on_using_llm_tool` hook is triggered.

You can obtain the `FunctionTool` object and tool call arguments.

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

> You cannot use yield to send messages here. If you need to send, please use the `event.send()` method directly.

#### After LLM Tool Call

After the LLM tool call completes, the `on_llm_tool_respond` hook is triggered.

You can obtain the `FunctionTool` object, tool call arguments, and tool call result.

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

> You cannot use yield to send messages here. If you need to send, please use the `event.send()` method directly.

#### On Agent Done

After the Agent finishes running, the `on_agent_done` hook is triggered. This hook is triggered after `on_llm_response`.

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.provider import LLMResponse


@filter.on_agent_done()
async def on_agent_done(
    self, event: AstrMessageEvent, run_context, resp: LLMResponse
):  # Note there are four parameters
    print(resp)
```

> You cannot use yield to send messages here. If you need to send, please use the `event.send()` method directly.

#### Before Sending Message

Before sending a message, the `on_decorating_result` hook is triggered.

You can implement some message decoration here, such as converting to voice, converting to image, adding prefixes, etc.

```python
from astrbot.api.event import filter, AstrMessageEvent
import astrbot.api.message_components as Comp


@filter.on_decorating_result()
async def on_decorating_result(self, event: AstrMessageEvent):
    result = event.get_result()
    chain = result.chain
    print(chain)  # Print the message chain
    chain.append(
        Comp.Plain("!")
    )  # Add an exclamation mark at the end of the message chain
```

> You cannot use yield to send messages here. This hook is only for decorating event.get_result().chain. If you need to send, please use the `event.send()` method directly.

#### After Message Sent

After a message is sent to the messaging platform, the `after_message_sent` hook is triggered.

```python
from astrbot.api.event import filter, AstrMessageEvent


@filter.after_message_sent()
async def after_message_sent(self, event: AstrMessageEvent):
    pass
```

> You cannot use yield to send messages here. If you need to send, please use the `event.send()` method directly.

### Priority

Commands, event listeners, and event hooks can have priority set to execute before other commands, listeners, or hooks. The default priority is `0`.

```python
@filter.command("helloworld", priority=1)
async def helloworld(self, event: AstrMessageEvent):
    yield event.plain_result("Hello!")
```

## Controlling Event Propagation

```python{6}
@filter.command("check_ok")
async def check_ok(self, event: AstrMessageEvent):
    ok = self.check()  # Your own logic
    if not ok:
        yield event.plain_result("Check failed")
        event.stop_event()  # Stop event propagation
```

When event propagation is stopped, all subsequent steps will not be executed.

Assuming there's a plugin A, after A terminates event propagation, all subsequent operations will not be executed, such as executing other plugins' handlers or requesting the LLM.
