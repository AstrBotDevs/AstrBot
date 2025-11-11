from astrbot_sdk.api.components.command import CommandComponent
from astrbot_sdk.api.event import AstrMessageEvent, filter
from astrbot_sdk.api.star.context import Context


class HelloCommand(CommandComponent):
    def __init__(self, context: Context):
        self.context = context

    @filter.command("hello")
    async def hello(self, event: AstrMessageEvent):
        ret = await self.context.conversation_manager.new_conversation("hello")
        print(f"New conversation created: {ret}")
        yield event.plain_result("Hello, Astrbot!")
