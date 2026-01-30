"""Text-to-speech command."""

from astrbot.api import sp, star
from astrbot.api.event import AstrMessageEvent, MessageEventResult


class TTSCommand:
    """Toggle text-to-speech for the current session."""

    def __init__(self, context: star.Context):
        self.context = context

    async def tts(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        session_config = await sp.session_get(
            umo,
            "session_service_config",
            default={},
        )
        session_config = session_config or {}
        current = session_config.get("tts_enabled")
        if current is None:
            current = True

        new_status = not current
        session_config["tts_enabled"] = new_status
        await sp.session_put(umo, "session_service_config", session_config)

        status_text = "已开启" if new_status else "已关闭"
        cfg = self.context.get_config(umo=umo)
        if new_status and not cfg.get("provider_tts_settings", {}).get("enable", False):
            event.set_result(
                MessageEventResult().message(
                    f"{status_text}当前会话的文本转语音。但 TTS 功能在配置中未启用，请前往 WebUI 开启。",
                ),
            )
            return

        event.set_result(
            MessageEventResult().message(f"{status_text}当前会话的文本转语音。"),
        )
