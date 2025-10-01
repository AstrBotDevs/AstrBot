"""文本转语音命令"""

import astrbot.api.star as star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.star.session_llm_manager import SessionServiceManager


class TTSCommand:
    """文本转语音命令类"""

    def __init__(self, context: star.Context):
        self.context = context

    async def tts(self, event: AstrMessageEvent):
        """开关文本转语音（会话级别）"""
        umo = event.unified_msg_origin
        ses_tts = SessionServiceManager.is_tts_enabled_for_session(umo)
        cfg = self.context.get_config(umo=umo)
        tts_enable = cfg["provider_tts_settings"]["enable"]

        # 切换状态
        new_status = not ses_tts
        SessionServiceManager.set_tts_status_for_session(umo, new_status)

        status_text = "已开启" if new_status else "已关闭"

        if new_status and not tts_enable:
            event.set_result(
                MessageEventResult().message(
                    f"{status_text}当前会话的文本转语音。但 TTS 功能在配置中未启用，请前往 WebUI 开启。"
                )
            )
        else:
            event.set_result(
                MessageEventResult().message(f"{status_text}当前会话的文本转语音。")
            )
