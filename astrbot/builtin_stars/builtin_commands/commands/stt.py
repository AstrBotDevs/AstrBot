"""Speech-to-text command."""

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult


class STTCommand:
    """Toggle speech-to-text globally."""

    def __init__(self, context: star.Context):
        self.context = context

    async def stt(self, event: AstrMessageEvent):
        config = self.context.get_config(umo=event.unified_msg_origin)
        stt_settings = config.get("provider_stt_settings", {})
        enabled = bool(stt_settings.get("enable", False))

        stt_settings["enable"] = not enabled
        config["provider_stt_settings"] = stt_settings
        config.save_config()

        status = "已开启" if not enabled else "已关闭"
        event.set_result(MessageEventResult().message(f"{status}语音转文本功能。"))
