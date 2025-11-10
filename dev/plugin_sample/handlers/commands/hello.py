from astrbot.api.v1.components.command import CommandComponent
from astrbot.api.v1.event import AstrMessageEvent, filter
from astrbot.api.v1.context import Context


class HelloCommand(CommandComponent):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("hello")
    async def hello(self, event: AstrMessageEvent):
        yield event.plain_result("Hello, Astrbot!")
