"""文本转语音命令"""

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core import t
from astrbot.core.star.session_llm_manager import SessionServiceManager


class TTSCommand:
    """文本转语音命令类"""

    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def tts(self, event: AstrMessageEvent) -> None:
        """开关文本转语音（会话级别）"""
        umo = event.unified_msg_origin
        ses_tts = await SessionServiceManager.is_tts_enabled_for_session(umo)
        cfg = self.context.get_config(umo=umo)
        tts_enable = cfg["provider_tts_settings"]["enable"]

        # 切换状态
        new_status = not ses_tts
        await SessionServiceManager.set_tts_status_for_session(umo, new_status)

        status_text = (
            t("builtin-stars-tts-status-enabled-prefix")
            if new_status
            else t("builtin-stars-tts-status-disabled-prefix")
        )

        if new_status and not tts_enable:
            event.set_result(
                MessageEventResult().message(
                    t(
                        "builtin-stars-tts-enabled-but-global-disabled",
                        status_text=status_text,
                    ),
                ),
            )
        else:
            event.set_result(
                MessageEventResult().message(
                    t(
                        "builtin-stars-tts-toggle-result",
                        status_text=status_text,
                    )
                ),
            )
