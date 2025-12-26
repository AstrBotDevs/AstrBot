"""文本转图片命令"""

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult


class T2ICommand:
    """文本转图片命令类"""

    def __init__(self, context: star.Context):
        self.context = context

    async def t2i(self, event: AstrMessageEvent):
        """开关文本转图片"""
        config = self.context.get_config(umo=event.unified_msg_origin)
        if config["t2i"]:
            config["t2i"] = False
            config.save_config()
            event.set_result(MessageEventResult().message("已关闭文本转图片模式。"))
            return
        config["t2i"] = True
        config.save_config()
        event.set_result(MessageEventResult().message("已开启文本转图片模式。"))
