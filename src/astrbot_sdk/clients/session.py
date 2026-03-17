"""Session-scoped SDK managers."""

from __future__ import annotations

from typing import Any

from ..events import MessageEvent
from ..message_session import MessageSession
from ._proxy import CapabilityProxy
from .registry import HandlerMetadata


def _normalize_session(session: str | MessageSession | MessageEvent) -> str:
    if isinstance(session, MessageEvent):
        return str(session.unified_msg_origin)
    if isinstance(session, MessageSession):
        return str(session)
    return str(session)


def _handler_to_payload(handler: HandlerMetadata) -> dict[str, Any]:
    return {
        "plugin_name": handler.plugin_name,
        "handler_full_name": handler.handler_full_name,
        "trigger_type": handler.trigger_type,
        "event_types": list(handler.event_types),
        "enabled": handler.enabled,
        "group_path": list(handler.group_path),
    }


class SessionPluginManager:
    """Session-scoped plugin status manager."""

    def __init__(self, proxy: CapabilityProxy) -> None:
        self._proxy = proxy

    async def is_plugin_enabled_for_session(
        self,
        session: str | MessageSession | MessageEvent,
        plugin_name: str,
    ) -> bool:
        output = await self._proxy.call(
            "session.plugin.is_enabled",
            {
                "session": _normalize_session(session),
                "plugin_name": str(plugin_name),
            },
        )
        return bool(output.get("enabled", False))

    async def filter_handlers_by_session(
        self,
        session: str | MessageSession | MessageEvent,
        handlers: list[HandlerMetadata],
    ) -> list[HandlerMetadata]:
        output = await self._proxy.call(
            "session.plugin.filter_handlers",
            {
                "session": _normalize_session(session),
                "handlers": [_handler_to_payload(handler) for handler in handlers],
            },
        )
        items = output.get("handlers")
        if not isinstance(items, list):
            return []
        return [
            HandlerMetadata.from_dict(item) for item in items if isinstance(item, dict)
        ]


class SessionServiceManager:
    """Session-scoped LLM/TTS service status manager."""

    def __init__(self, proxy: CapabilityProxy) -> None:
        self._proxy = proxy

    async def is_llm_enabled_for_session(
        self,
        session: str | MessageSession | MessageEvent,
    ) -> bool:
        output = await self._proxy.call(
            "session.service.is_llm_enabled",
            {"session": _normalize_session(session)},
        )
        return bool(output.get("enabled", False))

    async def set_llm_status_for_session(
        self,
        session: str | MessageSession | MessageEvent,
        enabled: bool,
    ) -> None:
        await self._proxy.call(
            "session.service.set_llm_status",
            {"session": _normalize_session(session), "enabled": bool(enabled)},
        )

    async def should_process_llm_request(
        self,
        event_or_session: str | MessageSession | MessageEvent,
    ) -> bool:
        return await self.is_llm_enabled_for_session(event_or_session)

    async def is_tts_enabled_for_session(
        self,
        session: str | MessageSession | MessageEvent,
    ) -> bool:
        output = await self._proxy.call(
            "session.service.is_tts_enabled",
            {"session": _normalize_session(session)},
        )
        return bool(output.get("enabled", False))

    async def set_tts_status_for_session(
        self,
        session: str | MessageSession | MessageEvent,
        enabled: bool,
    ) -> None:
        await self._proxy.call(
            "session.service.set_tts_status",
            {"session": _normalize_session(session), "enabled": bool(enabled)},
        )

    async def should_process_tts_request(
        self,
        event_or_session: str | MessageSession | MessageEvent,
    ) -> bool:
        return await self.is_tts_enabled_for_session(event_or_session)


__all__ = ["SessionPluginManager", "SessionServiceManager"]
