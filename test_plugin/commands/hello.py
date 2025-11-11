from astrbot_sdk.api.components.command import CommandComponent
from astrbot_sdk.api.event import AstrMessageEvent, filter
from astrbot_sdk.api.star.context import Context


class HelloCommand(CommandComponent):
    def __init__(self, context: Context):
        self.context = context

    @filter.command("hello")
    async def hello(self, event: AstrMessageEvent):
        yield event.plain_result("Hello, Astrbot!")
