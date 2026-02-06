"""NodeStar base class for pipeline nodes."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

from astrbot.core import logger

from .star_base import Star

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent
    from astrbot.core.provider.provider import Provider, STTProvider, TTSProvider


class NodeResult(Enum):
    CONTINUE = "continue"
    STOP = "stop"
    WAIT = "wait"
    SKIP = "skip"


class NodeStar(Star):
    """Star subclass that can be mounted into pipeline chains."""

    def __init__(self, context, config: dict | None = None):
        super().__init__(context, config)
        self.initialized_chain_ids: set[str] = set()

    async def node_initialize(self) -> None:
        pass

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> NodeResult:
        raise NotImplementedError

    def set_node_output(self, event: AstrMessageEvent, output: Any) -> None:
        event.set_node_output(output)

    async def get_node_input(
        self,
        event: AstrMessageEvent,
        *,
        strategy: str = "last",
        names: str | list[str] | None = None,
    ) -> Any:
        return await event.get_node_input(strategy=strategy, names=names)

    def get_chat_provider(self, event: AstrMessageEvent) -> Provider | None:
        from astrbot.core.provider.provider import Provider

        node_config = event.node_config or {}
        if isinstance(node_config, dict):
            node_provider_id = node_config.get("provider_id")
            if isinstance(node_provider_id, str) and node_provider_id:
                prov = self.context.get_provider_by_id(node_provider_id)
                if isinstance(prov, Provider):
                    return prov
                if prov is not None:
                    logger.warning(
                        "node provider_id is not a chat provider: %s",
                        node_provider_id,
                    )

        if event.chain_config is None:
            selected_provider = event.get_extra("selected_provider")
            if isinstance(selected_provider, str) and selected_provider:
                prov = self.context.get_provider_by_id(selected_provider)
                if isinstance(prov, Provider):
                    return prov
                if prov is not None:
                    logger.warning(
                        "selected_provider is not a chat provider: %s",
                        selected_provider,
                    )

        return self.context.get_using_provider(umo=event.unified_msg_origin)

    def get_tts_provider(self, event: AstrMessageEvent) -> TTSProvider | None:
        from astrbot.core.provider.provider import TTSProvider

        node_config = event.node_config or {}
        if isinstance(node_config, dict):
            node_provider_id = str(node_config.get("provider_id") or "").strip()
            if node_provider_id:
                prov = self.context.get_provider_by_id(node_provider_id)
                if isinstance(prov, TTSProvider):
                    return prov
                if prov is not None:
                    logger.warning(
                        "node provider_id is not a TTS provider: %s", node_provider_id
                    )

        return self.context.get_using_tts_provider(umo=event.unified_msg_origin)

    def get_stt_provider(self, event: AstrMessageEvent) -> STTProvider | None:
        from astrbot.core.provider.provider import STTProvider

        node_config = event.node_config or {}
        if isinstance(node_config, dict):
            node_provider_id = str(node_config.get("provider_id") or "").strip()
            if node_provider_id:
                prov = self.context.get_provider_by_id(node_provider_id)
                if isinstance(prov, STTProvider):
                    return prov
                if prov is not None:
                    logger.warning(
                        "node provider_id is not an STT provider: %s", node_provider_id
                    )

        return self.context.get_using_stt_provider(umo=event.unified_msg_origin)

    @staticmethod
    async def collect_stream(event: AstrMessageEvent) -> str | None:
        from astrbot.core.message.components import Plain
        from astrbot.core.message.message_event_result import (
            ResultContentType,
            collect_streaming_result,
        )

        result = event.get_result()
        if not result:
            return None

        if result.result_content_type != ResultContentType.STREAMING_RESULT:
            return None

        if result.async_stream is None:
            return None

        await collect_streaming_result(result)

        parts: list[str] = [
            comp.text for comp in result.chain if isinstance(comp, Plain)
        ]
        return "".join(parts)
