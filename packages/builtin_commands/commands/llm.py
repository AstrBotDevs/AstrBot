from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageChain


class LLMCommands:
    def __init__(self, context: star.Context):
        self.context = context

    async def llm(self, event: AstrMessageEvent):
        """开启/关闭 LLM"""
        cfg = self.context.get_config(umo=event.unified_msg_origin)
        enable = cfg["provider_settings"].get("enable", True)
        if enable:
            cfg["provider_settings"]["enable"] = False
            status = "关闭"
        else:
            cfg["provider_settings"]["enable"] = True
            status = "开启"
        cfg.save_config()
        await event.send(MessageChain().message(f"{status} LLM 聊天功能。"))
