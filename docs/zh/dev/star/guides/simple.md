# 最小实例

插件模版中的 `main.py` 是一个最小的插件实例。

```python
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger # 使用 astrbot 提供的 logger 接口

class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    # 注册指令的装饰器。指令名为 helloworld。注册成功后，发送 `/helloworld` 就会触发这个指令，并回复 `你好, {user_name}!`
    @filter.command("helloworld")
    async def helloworld(self, event: AstrMessageEvent):
        '''这是一个 hello world 指令''' # 这是 handler 的描述，将会被解析方便用户了解插件内容。非常建议填写。
        user_name = event.get_sender_name()
        message_str = event.message_str # 获取消息的纯文本内容
        logger.info("触发hello world指令!")
        yield event.plain_result(f"Hello, {user_name}!") # 发送一条纯文本消息

    async def terminate(self):
        '''可选择实现 terminate 函数，当插件被卸载/停用时会调用。'''
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
