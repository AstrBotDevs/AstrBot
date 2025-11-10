from astrbot.api.v1.components.listener import ListenerComponent
from astrbot.api.v1.event import AstrMessageEvent, filter
from astrbot.api.v1.context import Context


class EchoListener(ListenerComponent):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.platform_adapter_type(filter.PlatformAdapterType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        yield event.plain_result("Hello, Astrbot!")
