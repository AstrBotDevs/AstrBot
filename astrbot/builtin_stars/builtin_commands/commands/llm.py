from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.core import t


class LLMCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def llm(self, event: AstrMessageEvent) -> None:
        """开启/关闭 LLM"""
        cfg = self.context.get_config(umo=event.unified_msg_origin)
        enable = cfg["provider_settings"].get("enable", True)
        if enable:
            cfg["provider_settings"]["enable"] = False
            status = t("builtin-stars-llm-status-disabled")
        else:
            cfg["provider_settings"]["enable"] = True
            status = t("builtin-stars-llm-status-enabled")
        cfg.save_config()
        await event.send(
            MessageChain().message(t("builtin-stars-llm-toggle-result", status=status))
        )
