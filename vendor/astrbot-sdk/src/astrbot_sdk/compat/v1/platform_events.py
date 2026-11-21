"""Legacy per-platform event shims and the raw bot escape hatch.

Old plugins isinstance-check platform event classes (mostly
AiocqhttpMessageEvent) and call raw OneBot actions through ``event.bot``.
In the isolated legacy Runner the real core classes cannot exist, so this
module provides honest subclasses of the compat AstrMessageEvent facade
(chosen by the event's platform metadata) plus a bot proxy that forwards
raw actions to the Host adapter over the platform.raw capability.

This surface exists only for legacy compatibility; the new SDK public API
deliberately has no equivalent.
"""

from __future__ import annotations

from typing import Any

from ...events import MessageEvent
from .event import AstrMessageEvent

#: Capability used by the legacy bot proxy. Granted to isolated legacy
#: plugins only; new SDK plugins cannot declare it.
PLATFORM_RAW_CAPABILITY = "platform.raw"


class LegacyBotApiProxy:
    """OneBot-style ``bot.api`` object forwarding call_action to the Host."""

    def __init__(self, context: Any, platform_id: str, platform_type: str) -> None:
        """Initialize the proxy.

        Args:
            context: Legacy facade context used to reach the Host.
            platform_id: Host platform instance ID to address.
            platform_type: Platform metadata name of the instance.
        """
        self._context = context
        self._platform_id = platform_id
        self._platform_type = platform_type

    @classmethod
    def from_event(cls, event: MessageEvent, context: Any) -> LegacyBotApiProxy:
        """Build a proxy bound to the platform of one event."""
        return cls(context, event.umo.platform_id, event.platform_type)

    async def call_action(self, action: str, **params: Any) -> Any:
        """Forward one raw platform action to the Host-side adapter.

        Args:
            action: Raw action name (e.g. set_group_ban).
            **params: Action parameters, JSON-serializable.

        Returns:
            Decoded adapter result.
        """
        return await self._context._ctx._invoke_capability(
            PLATFORM_RAW_CAPABILITY,
            "call_action",
            {
                "platform_id": self._platform_id,
                "platform": self._platform_type,
                "action": action,
                "params": params,
            },
        )


class LegacyBotProxy:
    """Dynamic bot client mirroring aiocqhttp's CQHttp method surface."""

    def __init__(self, context: Any, platform_id: str, platform_type: str) -> None:
        """Initialize the proxy.

        Args:
            context: Legacy facade context used to reach the Host.
            platform_id: Host platform instance ID to address.
            platform_type: Platform metadata name of the instance.
        """
        self._context = context
        self._platform_id = platform_id
        self.api = LegacyBotApiProxy(context, platform_id, platform_type)

    @property
    def platform(self) -> Any:
        """Adapter facade for this bot (mirrors botClient.set_platform).

        In-process, the raw bot client carries the live platform adapter, and
        legacy plugins read bot.platform.config from it. Resolve the matching
        snapshot-backed facade; None when the instance is gone.
        """
        manager = getattr(self._context, "platform_manager", None)
        for inst in getattr(manager, "platform_insts", None) or ():
            try:
                if inst.meta().id == self._platform_id:
                    return inst
            except Exception:  # a broken entry must not break attribute reads
                continue
        return None

    @classmethod
    def from_event(cls, event: MessageEvent, context: Any) -> LegacyBotProxy:
        """Build a proxy bound to the platform of one event."""
        return cls(context, event.umo.platform_id, event.platform_type)

    def __getattr__(self, name: str) -> Any:
        # Mirror CQHttp: unknown attributes become async kwargs-only raw
        # action methods (bot.get_group_member_list(group_id=...)).
        if name.startswith("_"):
            raise AttributeError(name)

        async def method(**kwargs: Any) -> Any:
            return await self.api.call_action(name, **kwargs)

        return method


class AiocqhttpMessageEvent(AstrMessageEvent):
    """Legacy aiocqhttp event facade exposing the raw OneBot client."""

    @property
    def bot(self) -> LegacyBotProxy:
        return LegacyBotProxy.from_event(self._event, self._context)

    @classmethod
    async def send_message(cls, *args: Any, **kwargs: Any) -> None:
        # Present so legacy plugins can monkeypatch the class-level send
        # hook like they do in-process. The real implementation needs the
        # live OneBot connection, which only exists in the Host.
        from .errors import IsolationUnsupportedError

        raise IsolationUnsupportedError(
            "AiocqhttpMessageEvent.send_message is unavailable in isolated "
            "legacy mode; plugins needing it must run in-process."
        )


class QQOfficialMessageEvent(AstrMessageEvent):
    """Legacy QQ official API event facade."""

    @property
    def bot(self) -> LegacyBotProxy:
        return LegacyBotProxy.from_event(self._event, self._context)


class QQOfficialWebhookMessageEvent(QQOfficialMessageEvent):
    """Legacy QQ official webhook event facade."""


class TelegramPlatformEvent(AstrMessageEvent):
    """Legacy telegram event facade."""

    @property
    def bot(self) -> LegacyBotProxy:
        return LegacyBotProxy.from_event(self._event, self._context)


class LarkMessageEvent(AstrMessageEvent):
    """Legacy lark event facade."""

    @property
    def bot(self) -> LegacyBotProxy:
        return LegacyBotProxy.from_event(self._event, self._context)


class DiscordPlatformEvent(AstrMessageEvent):
    """Legacy discord event facade."""

    @property
    def bot(self) -> LegacyBotProxy:
        return LegacyBotProxy.from_event(self._event, self._context)


class DingtalkMessageEvent(AstrMessageEvent):
    """Legacy dingtalk event facade."""

    @property
    def bot(self) -> LegacyBotProxy:
        return LegacyBotProxy.from_event(self._event, self._context)


class SlackMessageEvent(AstrMessageEvent):
    """Legacy slack event facade."""

    @property
    def bot(self) -> LegacyBotProxy:
        return LegacyBotProxy.from_event(self._event, self._context)


class WebChatMessageEvent(AstrMessageEvent):
    """Legacy webchat event facade."""

    @property
    def bot(self) -> LegacyBotProxy:
        return LegacyBotProxy.from_event(self._event, self._context)


#: Event class chosen by the event's platform name so isinstance checks in
#: legacy plugins stay honest. Unknown platforms fall back to the base
#: facade (isinstance against a specific platform class returns False).
_PLATFORM_EVENT_CLASSES: dict[str, type[AstrMessageEvent]] = {
    "aiocqhttp": AiocqhttpMessageEvent,
    "qqofficial": QQOfficialMessageEvent,
    "qqofficial_webhook": QQOfficialWebhookMessageEvent,
    "telegram": TelegramPlatformEvent,
    "lark": LarkMessageEvent,
    "discord": DiscordPlatformEvent,
    "dingtalk": DingtalkMessageEvent,
    "slack": SlackMessageEvent,
    "webchat": WebChatMessageEvent,
}


def build_legacy_event(event: MessageEvent, context: Any) -> AstrMessageEvent:
    """Wrap one SDK event in the platform-shaped legacy facade.

    Args:
        event: Immutable SDK message event.
        context: Legacy compat context of the owning plugin.

    Returns:
        Platform-specific facade when the platform is known, else the base
        AstrMessageEvent facade.
    """
    cls = _PLATFORM_EVENT_CLASSES.get(event.platform_type, AstrMessageEvent)
    return cls(event, context)


# ---------------------------------------------------------------------------
# Import-only shells
#
# Classes below exist so ``from astrbot.core.platform.sources... import X``
# keeps working in legacy plugins. Adapter classes are only ever used for
# isinstance against platform_insts, which isolated plugins cannot access,
# and community adapters (wechatpadpro, gewechat) are not Host platforms, so
# plain shells are honest here.
# ---------------------------------------------------------------------------


class AiocqhttpAdapter:
    """Import shell for the core aiocqhttp adapter."""


class QQOfficialPlatformAdapter:
    """Import shell for the core QQ official adapter."""


class LarkPlatformAdapter:
    """Import shell for the core lark adapter."""


class DiscordPlatformAdapter:
    """Import shell for the core discord adapter."""


class WeChatPadProMessageEvent(AstrMessageEvent):
    """Import shell for the community wechatpadpro event."""


class WeChatPadProAdapter:
    """Import shell for the community wechatpadpro adapter."""


class GewechatPlatformEvent(AstrMessageEvent):
    """Import shell for the community gewechat event."""


class SimpleGewechatClient:
    """Import shell for the community gewechat client."""


class _UnavailableWebchatQueueMgr:
    """webchat_queue_mgr is a live Host singleton; unavailable when isolated."""

    def __getattr__(self, name: str) -> Any:
        raise RuntimeError(
            "webchat_queue_mgr is a Host-internal singleton and is not "
            "available to isolated legacy plugins",
        )


webchat_queue_mgr = _UnavailableWebchatQueueMgr()
