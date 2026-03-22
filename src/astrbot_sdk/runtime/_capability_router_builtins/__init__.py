from __future__ import annotations

from .bridge_base import CapabilityRouterBridgeBase
from .capabilities import (
    ConversationCapabilityMixin,
    DBCapabilityMixin,
    HttpCapabilityMixin,
    KnowledgeBaseCapabilityMixin,
    LLMCapabilityMixin,
    MemoryCapabilityMixin,
    MessageHistoryCapabilityMixin,
    MetadataCapabilityMixin,
    PersonaCapabilityMixin,
    PlatformCapabilityMixin,
    ProviderCapabilityMixin,
    SessionCapabilityMixin,
    SkillCapabilityMixin,
    SystemCapabilityMixin,
)


class BuiltinCapabilityRouterMixin(
    LLMCapabilityMixin,
    MemoryCapabilityMixin,
    DBCapabilityMixin,
    PlatformCapabilityMixin,
    HttpCapabilityMixin,
    MetadataCapabilityMixin,
    ProviderCapabilityMixin,
    SessionCapabilityMixin,
    SkillCapabilityMixin,
    PersonaCapabilityMixin,
    ConversationCapabilityMixin,
    MessageHistoryCapabilityMixin,
    KnowledgeBaseCapabilityMixin,
    SystemCapabilityMixin,
    CapabilityRouterBridgeBase,
):
    def _register_builtin_capabilities(self) -> None:
        self._register_llm_capabilities()
        self._register_memory_capabilities()
        self._register_db_capabilities()
        self._register_platform_capabilities()
        self._register_http_capabilities()
        self._register_metadata_capabilities()
        self._register_provider_capabilities()
        self._register_agent_tool_capabilities()
        self._register_session_capabilities()
        self._register_skill_capabilities()
        self._register_persona_capabilities()
        self._register_conversation_capabilities()
        self._register_message_history_capabilities()
        self._register_kb_capabilities()
        self._register_provider_manager_capabilities()
        self._register_platform_manager_capabilities()
        self._register_system_capabilities()


__all__ = ["BuiltinCapabilityRouterMixin"]
