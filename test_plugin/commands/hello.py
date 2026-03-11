from astrbot_sdk.api.components.command import CommandComponent
from astrbot_sdk.api.event import AstrMessageEvent, filter
from astrbot_sdk.api.star.context import Context
from loguru import logger


class HelloCommand(CommandComponent):
    def __init__(self, context: Context):
        self.context = context

    @filter.command("hello")
    async def hello(self, event: AstrMessageEvent):
        ret = await self.context.conversation_manager.new_conversation("hello")
        logger.info(f"New conversation created: {ret}")
        yield event.plain_result(f"Hello, Astrbot! Created conversation ID: {ret}")
        yield event.plain_result("Hello, Astrbot!")
        yield event.plain_result("Hello again, Astrbot!")
        yield event.plain_result("Goodbye, Astrbot!")
