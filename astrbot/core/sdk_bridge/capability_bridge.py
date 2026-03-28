from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .bridge_base import CapabilityBridgeBase
from .capabilities import (
    BasicCapabilityMixin,
    ConversationCapabilityMixin,
    KnowledgeBaseCapabilityMixin,
    LLMCapabilityMixin,
    MCPCapabilityMixin,
    MessageHistoryCapabilityMixin,
    PermissionCapabilityMixin,
    PersonaCapabilityMixin,
    PlatformCapabilityMixin,
    ProviderCapabilityMixin,
    SessionCapabilityMixin,
    SkillCapabilityMixin,
    SystemCapabilityMixin,
)

if TYPE_CHECKING:
    from astrbot.core.star.context import Context as StarContext

__all__ = ["CoreCapabilityBridge"]


class CoreCapabilityBridge(
    SystemCapabilityMixin,
    ProviderCapabilityMixin,
    MCPCapabilityMixin,
    PlatformCapabilityMixin,
    PermissionCapabilityMixin,
    KnowledgeBaseCapabilityMixin,
    MessageHistoryCapabilityMixin,
    ConversationCapabilityMixin,
    PersonaCapabilityMixin,
    SessionCapabilityMixin,
    SkillCapabilityMixin,
    LLMCapabilityMixin,
    BasicCapabilityMixin,
    CapabilityBridgeBase,
):
    def __init__(self, *, star_context: StarContext, plugin_bridge) -> None:
        self._star_context = star_context
        self._plugin_bridge = plugin_bridge
        self._event_streams: dict[str, Any] = {}
        self._memory_backends_by_plugin: dict[str, Any] = {}
        self._memory_index_by_plugin: dict[str, dict[str, dict[str, Any]]] = {}
        self._memory_dirty_keys_by_plugin: dict[str, set[str]] = {}
        self._memory_expires_at_by_plugin: dict[str, dict[str, Any]] = {}
        # CapabilityRouter.__init__() registers the built-in capability groups
        # declared by this bridge and its mixins before extended groups are added.
        super().__init__()
        self._register_provider_capabilities()
        self._register_provider_manager_capabilities()
        self._register_mcp_capabilities()
        self._register_platform_manager_capabilities()
        self._register_permission_capabilities()
        self._register_persona_capabilities()
        self._register_conversation_capabilities()
        self._register_message_history_capabilities()
        self._register_kb_capabilities()
        self._register_skill_capabilities()
        self._register_system_capabilities()
        self._register_registry_capabilities()
        self._register_db_capabilities()
        self._register_memory_capabilities()
        self._register_http_capabilities()
        self._register_metadata_capabilities()
