"""Text-to-image command."""

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult


class T2ICommand:
    """Toggle text-to-image output."""

    def __init__(self, context: star.Context):
        self.context = context

    async def t2i(self, event: AstrMessageEvent):
        config = self.context.get_config(umo=event.unified_msg_origin)
        enabled = bool(config.get("t2i", False))
        config["t2i"] = not enabled
        config.save_config()

        status = "已开启" if not enabled else "已关闭"
        event.set_result(MessageEventResult().message(f"{status}文本转图片模式。"))
