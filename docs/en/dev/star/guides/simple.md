# Minimal Example

The `main.py` file in the plugin template is a minimal plugin instance.

```python
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star
from astrbot.api import logger # Use the logger interface provided by AstrBot

class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    # Decorator to register a command. The command name is "helloworld". Once registered, sending `/helloworld` will trigger this command and respond with `Hello, {user_name}!`
    @filter.command("helloworld")
    async def helloworld(self, event: AstrMessageEvent):
        '''This is a hello world command''' # This is the handler's description, which will be parsed to help users understand the plugin's functionality. Highly recommended to provide.
        user_name = event.get_sender_name()
        message_str = event.message_str # Get the plain text content of the message
        logger.info("Hello world command triggered!")
        yield event.plain_result(f"Hello, {user_name}!") # Send a plain text message

    async def terminate(self):
        '''Optionally implement the terminate function, which will be called when the plugin is uninstalled/disabled.'''
```

Explanation:

- Plugins must inherit from the `Star` class.
- The `Context` class is used for plugin interaction with AstrBot Core, allowing you to call various APIs provided by AstrBot Core.
- Specific handler functions are defined within the plugin class, such as the `helloworld` function here.
- `AstrMessageEvent` is AstrBot's message event object, which stores information about the message sender, message content, etc.
- `AstrBotMessage` is AstrBot's message object, which stores the specific content of messages delivered by the messaging platform. It can be accessed via `event.message_obj`.

> [!TIP]
>
> Handlers must be registered within the plugin class, with the first two parameters being `self` and `event`. If the file becomes too long, you can write services externally and call them from the handler.
>
> The file containing the plugin class must be named `main.py`.

All handler functions must be written within the plugin class. To keep content concise, in subsequent sections, we may omit the plugin class definition.
```

解释如下：

- 插件需要继承 `Star` 类。
- `Context` 类用于插件与 AstrBot Core 交互，可以由此调用 AstrBot Core 提供的各种 API。
- 具体的处理函数 `Handler` 在插件类中定义，如这里的 `helloworld` 函数。
- `AstrMessageEvent` 是 AstrBot 的消息事件对象，存储了消息发送者、消息内容等信息。
- `AstrBotMessage` 是 AstrBot 的消息对象，存储了消息平台下发的消息的具体内容。可以通过 `event.message_obj` 获取。

> [!TIP]
>
> `Handler` 一定需要在插件类中注册，前两个参数必须为 `self` 和 `event`。如果文件行数过长，可以将服务写在外部，然后在 `Handler` 中调用。
>
> 插件类所在的文件名需要命名为 `main.py`。

所有的处理函数都需写在插件类中。为了精简内容，在之后的章节中，我们可能会忽略插件类的定义。
