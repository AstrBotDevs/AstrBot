"""Pre-ack emoji: react before pipeline, unreact after pipeline.

This module is intentionally NOT a pipeline Stage. It runs in
``PipelineScheduler.execute()`` as a simple before/after wrapper so that
it does not interfere with the onion-model stage execution.
"""

import random

from astrbot.core import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent

_SUPPORTED_PLATFORMS = {"telegram", "lark", "discord"}


class PreAckEmoji:
    """Manages the lifecycle of a pre-acknowledgement emoji reaction."""

    def __init__(self, config: dict) -> None:
        self._config = config
        self._reaction_id: str | None = None
        self._platform: str | None = None
        self._auto_remove: bool = True

    async def try_react(self, event: AstrMessageEvent) -> None:
        """Send a reaction emoji if the config and event conditions are met."""
        platform = event.get_platform_name()
        if platform not in _SUPPORTED_PLATFORMS:
            return

        cfg = (
            self._config.get("platform_specific", {})
            .get(platform, {})
            .get("pre_ack_emoji", {})
        ) or {}

        emojis = cfg.get("emojis") or []
        if not (cfg.get("enable", False) and emojis and event.is_at_or_wake_command):
            return

        self._platform = platform
        self._auto_remove = cfg.get("auto_remove", True)

        try:
            self._reaction_id = await event.react(random.choice(emojis))
        except Exception as e:
            logger.warning(f"{platform} 预回应表情发送失败: {e}")

    async def try_unreact(self, event: AstrMessageEvent) -> None:
        """Remove the reaction emoji if auto_remove is enabled."""
        if not (self._auto_remove and self._reaction_id):
            return
        try:
            await event.unreact(self._reaction_id)
        except Exception as e:
            logger.warning(f"{self._platform} 预回应表情撤回失败: {e}")
