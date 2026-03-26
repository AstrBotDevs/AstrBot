import random

from astrbot.core import logger
from astrbot.core.platform import AstrMessageEvent


class PreAckEmojiManager:
    """预回应表情管理器。

    在 pipeline 执行前贴表情，执行后根据配置撤回。
    运行在洋葱模型外层，不参与 stage 调度。
    """

    SUPPORTED_PLATFORMS = ("telegram", "lark", "discord")

    def __init__(self, config: dict) -> None:
        self.config = config

    def _get_cfg(self, platform: str) -> dict:
        return (
            self.config.get("platform_specific", {})
            .get(platform, {})
            .get("pre_ack_emoji", {})
        ) or {}

    async def add_emoji(self, event: AstrMessageEvent) -> str | None:
        """贴表情。返回所选 emoji，或 None（未贴）。"""
        platform = event.get_platform_name()
        if platform not in self.SUPPORTED_PLATFORMS:
            return None

        cfg = self._get_cfg(platform)
        emojis = cfg.get("emojis") or []

        if not cfg.get("enable", False) or not emojis or not event.is_at_or_wake_command:
            return None

        emoji = random.choice(emojis)
        try:
            await event.react(emoji)
            return emoji
        except Exception as e:
            logger.warning(f"{platform} 预回应表情发送失败: {e}")
            return None

    async def remove_emoji(self, event: AstrMessageEvent, emoji: str | None) -> None:
        """根据配置撤回表情。"""
        if emoji is None:
            return

        platform = event.get_platform_name()
        cfg = self._get_cfg(platform)

        if not cfg.get("auto_remove", True):
            return

        try:
            await event.remove_react(emoji)
        except Exception as e:
            logger.warning(f"{platform} 预回应表情撤回失败: {e}")
