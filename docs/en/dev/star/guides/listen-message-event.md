
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
    '''AstrBot's message object'''
    type: MessageType  # Message type
    self_id: str  # Bot's identification ID
    session_id: str  # Session ID. Depends on the unique_session setting.
    message_id: str  # Message ID
    group_id: str = "" # Group ID, empty if it's a private chat
    sender: MessageMember  # Sender
    message: List[BaseMessageComponent]  # Message chain. For example: [Plain("Hello"), At(qq=123456)]
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

## Commands

![message-event-simple-command](https://files.astrbot.app/docs/en/dev/star/guides/message-event-simple-command.svg)

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star

class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("helloworld") # from astrbot.api.event.filter import command
    async def helloworld(self, event: AstrMessageEvent):
        '''This is a hello world command'''
        user_name = event.get_sender_name()
        message_str = event.message_str # Get the plain text content of the message
        yield event.plain_result(f"Hello, {user_name}!")
```

> [!TIP]
> Commands cannot contain spaces, otherwise AstrBot will parse them as a second parameter. You can use the command group feature below, or use a listener to parse the message content yourself.

## Commands with Parameters

![command-with-param](https://files.astrbot.app/docs/en/dev/star/guides/command-with-param.svg)

AstrBot will automatically parse command parameters for you.

```python
@filter.command("add")
def add(self, event: AstrMessageEvent, a: int, b: int):
    # /add 1 2 -> Result is: 3
    yield event.plain_result(f"Wow! The answer is {a + b}!")
```

## Command Groups

Command groups help you organize commands.

```python
@filter.command_group("math")
def math(self):
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

When a user doesn't input a subcommand, an error will be reported and the tree structure of the command group will be rendered.

![image](https://files.astrbot.app/docs/source/images/plugin/image-1.png)

![image](https://files.astrbot.app/docs/source/images/plugin/898a169ae7ed0478f41c0a7d14cb4d64.png)

![image](https://files.astrbot.app/docs/source/images/plugin/image-2.png)

Theoretically, command groups can be nested infinitely!

```py
'''
math
├── calc
│   ├── add (a(int),b(int),)
│   ├── sub (a(int),b(int),)
│   ├── help (command with no parameters)
'''

@filter.command_group("math")
def math():
    pass

@math.group("calc") # Note: this is group, not command_group
def calc():
    pass

@calc.command("add")
async def add(self, event: AstrMessageEvent, a: int, b: int):
    yield event.plain_result(f"Result is: {a + b}")

@calc.command("sub")
async def sub(self, event: AstrMessageEvent, a: int, b: int):
    yield event.plain_result(f"Result is: {a - b}")

@calc.command("help")
def calc_help(self, event: AstrMessageEvent):
    # /math calc help
    yield event.plain_result("This is a calculator plugin with add and sub commands.")
```

## Command Aliases

> Available after v3.4.28

You can add different aliases for commands or command groups:

```python
@filter.command("help", alias={'帮助', 'helpme'})
def help(self, event: AstrMessageEvent):
    yield event.plain_result("This is a calculator plugin with add and sub commands.")
```

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
    message_str = event.message_str # Get the plain text content of the message
    yield event.plain_result("Received a private message.")
```

`EventMessageType` is an `Enum` type that contains all event types. Current event types are `PRIVATE_MESSAGE` and `GROUP_MESSAGE`.

#### Messaging Platform

```python
@filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP | filter.PlatformAdapterType.QQOFFICIAL)
async def on_aiocqhttp(self, event: AstrMessageEvent):
    '''Only receive messages from AIOCQHTTP and QQOFFICIAL'''
    yield event.plain_result("Received a message")
```

In the current version, `PlatformAdapterType` includes `AIOCQHTTP`, `QQOFFICIAL`, `GEWECHAT`, and `ALL`.

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

> Available after v3.4.34

```python
from astrbot.api.event import filter, AstrMessageEvent

@filter.on_astrbot_loaded()
async def on_astrbot_loaded(self):
    print("AstrBot initialization complete")

```

#### On LLM Request

In AstrBot's default execution flow, the `on_llm_request` hook is triggered before calling the LLM.

You can obtain the `ProviderRequest` object and modify it.

The ProviderRequest object contains all information about the LLM request, including the request text, system prompt, etc.

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.provider import ProviderRequest

@filter.on_llm_request()
async def my_custom_hook_1(self, event: AstrMessageEvent, req: ProviderRequest): # Note there are three parameters
    print(req) # Print the request text
    req.system_prompt += "Custom system_prompt"

```

> You cannot use yield to send messages here. If you need to send, please use the `event.send()` method directly.

#### On LLM Response Complete

After the LLM request completes, the `on_llm_response` hook is triggered.

You can obtain the `ProviderResponse` object and modify it.

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.provider import LLMResponse

@filter.on_llm_response()
async def on_llm_resp(self, event: AstrMessageEvent, resp: LLMResponse): # Note there are three parameters
    print(resp)
```

> You cannot use yield to send messages here. If you need to send, please use the `event.send()` method directly.

#### Before Sending Message

Before sending a message, the `on_decorating_result` hook is triggered.

You can implement some message decoration here, such as converting to voice, converting to image, adding prefixes, etc.

```python
from astrbot.api.event import filter, AstrMessageEvent

@filter.on_decorating_result()
async def on_decorating_result(self, event: AstrMessageEvent):
    result = event.get_result()
    chain = result.chain
    print(chain) # Print the message chain
    chain.append(Plain("!")) # Add an exclamation mark at the end of the message chain
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
    ok = self.check() # Your own logic
    if not ok:
        yield event.plain_result("Check failed")
        event.stop_event() # Stop event propagation
```

When event propagation is stopped, all subsequent steps will not be executed.

Assuming there's a plugin A, after A terminates event propagation, all subsequent operations will not be executed, such as executing other plugins' handlers or requesting the LLM.
