"""文本转语音命令"""

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.session_overrides import update_overrides


class TTSCommand:
    """文本转语音命令类"""

    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def tts(self, event: AstrMessageEvent) -> None:
        """开关文本转语音(会话级别)"""
        umo = event.unified_msg_origin
        cfg = self.context.get_config(umo=umo)
        new_status = not bool(cfg["provider_tts_settings"]["enable"])
        await update_overrides(umo, {"provider_tts_settings.enable": new_status})
        status_text = "已开启" if new_status else "已关闭"
        event.set_result(
            MessageEventResult().message(f"{status_text}当前会话的文本转语音。")
        )
