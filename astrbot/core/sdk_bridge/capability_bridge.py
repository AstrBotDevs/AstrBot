from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .bridge_base import CapabilityBridgeBase
from .capabilities import (
    BasicCapabilityMixin,
    ConversationCapabilityMixin,
    KnowledgeBaseCapabilityMixin,
    LLMCapabilityMixin,
    PersonaCapabilityMixin,
    PlatformCapabilityMixin,
    ProviderCapabilityMixin,
    SessionCapabilityMixin,
    SystemCapabilityMixin,
)

if TYPE_CHECKING:
    from astrbot.core.star.context import Context as StarContext


class CoreCapabilityBridge(
    SystemCapabilityMixin,
    ProviderCapabilityMixin,
    PlatformCapabilityMixin,
    KnowledgeBaseCapabilityMixin,
    ConversationCapabilityMixin,
    PersonaCapabilityMixin,
    SessionCapabilityMixin,
    LLMCapabilityMixin,
    BasicCapabilityMixin,
    CapabilityBridgeBase,
):
    def __init__(self, *, star_context: StarContext, plugin_bridge) -> None:
        self._star_context = star_context
        self._plugin_bridge = plugin_bridge
        self._event_streams: dict[str, Any] = {}
        # CapabilityRouter.__init__() registers the built-in capability groups
        # declared by this bridge and its mixins before extended groups are added.
        super().__init__()
        self._register_provider_capabilities()
        self._register_provider_manager_capabilities()
        self._register_platform_manager_capabilities()
        self._register_persona_capabilities()
        self._register_conversation_capabilities()
        self._register_kb_capabilities()
        self._register_system_capabilities()
        self._register_registry_capabilities()
