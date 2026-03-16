"""Typed SDK manager clients for persona, conversation, and knowledge base."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..message_session import MessageSession
from ._proxy import CapabilityProxy


class _ManagerModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)

    def to_update_payload(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


def _normalize_session(session: str | MessageSession) -> str:
    if isinstance(session, MessageSession):
        return str(session)
    return str(session)


class PersonaRecord(_ManagerModel):
    persona_id: str
    system_prompt: str
    begin_dialogs: list[str] = Field(default_factory=list)
    tools: list[str] | None = None
    skills: list[str] | None = None
    custom_error_message: str | None = None
    folder_id: str | None = None
    sort_order: int = 0
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> PersonaRecord | None:
        if not isinstance(payload, dict):
            return None
        return cls.model_validate(payload)


class PersonaCreateParams(_ManagerModel):
    persona_id: str
    system_prompt: str
    begin_dialogs: list[str] = Field(default_factory=list)
    tools: list[str] | None = None
    skills: list[str] | None = None
    custom_error_message: str | None = None
    folder_id: str | None = None
    sort_order: int = 0


class PersonaUpdateParams(_ManagerModel):
    system_prompt: str | None = None
    begin_dialogs: list[str] | None = None
    tools: list[str] | None = None
    skills: list[str] | None = None
    custom_error_message: str | None = None


class ConversationRecord(_ManagerModel):
    conversation_id: str
    session: str
    platform_id: str
    history: list[dict[str, Any]] = Field(default_factory=list)
    title: str | None = None
    persona_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    token_usage: int | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> ConversationRecord | None:
        if not isinstance(payload, dict):
            return None
        return cls.model_validate(payload)


class ConversationCreateParams(_ManagerModel):
    platform_id: str | None = None
    history: list[dict[str, Any]] | None = None
    title: str | None = None
    persona_id: str | None = None


class ConversationUpdateParams(_ManagerModel):
    history: list[dict[str, Any]] | None = None
    title: str | None = None
    persona_id: str | None = None
    token_usage: int | None = None


class KnowledgeBaseRecord(_ManagerModel):
    kb_id: str
    kb_name: str
    description: str | None = None
    emoji: str | None = None
    embedding_provider_id: str
    rerank_provider_id: str | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    top_k_dense: int | None = None
    top_k_sparse: int | None = None
    top_m_final: int | None = None
    doc_count: int = 0
    chunk_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> KnowledgeBaseRecord | None:
        if not isinstance(payload, dict):
            return None
        return cls.model_validate(payload)


class KnowledgeBaseCreateParams(_ManagerModel):
    kb_name: str
    embedding_provider_id: str
    description: str | None = None
    emoji: str | None = None
    rerank_provider_id: str | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    top_k_dense: int | None = None
    top_k_sparse: int | None = None
    top_m_final: int | None = None


class PersonaManagerClient:
    def __init__(self, proxy: CapabilityProxy) -> None:
        self._proxy = proxy

    async def get_persona(self, persona_id: str) -> PersonaRecord:
        output = await self._proxy.call("persona.get", {"persona_id": str(persona_id)})
        persona = PersonaRecord.from_payload(output.get("persona"))
        if persona is None:
            raise ValueError(f"persona not found: {persona_id}")
        return persona

    async def get_all_personas(self) -> list[PersonaRecord]:
        output = await self._proxy.call("persona.list", {})
        items = output.get("personas")
        if not isinstance(items, list):
            return []
        return [
            persona
            for persona in (
                PersonaRecord.from_payload(item) if isinstance(item, dict) else None
                for item in items
            )
            if persona is not None
        ]

    async def create_persona(self, params: PersonaCreateParams) -> PersonaRecord:
        output = await self._proxy.call(
            "persona.create",
            {"persona": params.to_payload()},
        )
        persona = PersonaRecord.from_payload(output.get("persona"))
        if persona is None:
            raise ValueError("persona.create returned no persona")
        return persona

    async def update_persona(
        self,
        persona_id: str,
        params: PersonaUpdateParams,
    ) -> PersonaRecord | None:
        output = await self._proxy.call(
            "persona.update",
            {"persona_id": str(persona_id), "persona": params.to_update_payload()},
        )
        return PersonaRecord.from_payload(output.get("persona"))

    async def delete_persona(self, persona_id: str) -> None:
        await self._proxy.call("persona.delete", {"persona_id": str(persona_id)})


class ConversationManagerClient:
    def __init__(self, proxy: CapabilityProxy) -> None:
        self._proxy = proxy

    async def new_conversation(
        self,
        session: str | MessageSession,
        params: ConversationCreateParams | None = None,
    ) -> str:
        output = await self._proxy.call(
            "conversation.new",
            {
                "session": _normalize_session(session),
                "conversation": (params.to_payload() if params is not None else {}),
            },
        )
        return str(output.get("conversation_id", ""))

    async def switch_conversation(
        self,
        session: str | MessageSession,
        conversation_id: str,
    ) -> None:
        await self._proxy.call(
            "conversation.switch",
            {
                "session": _normalize_session(session),
                "conversation_id": str(conversation_id),
            },
        )

    async def delete_conversation(
        self,
        session: str | MessageSession,
        conversation_id: str | None = None,
    ) -> None:
        """Delete one conversation for the session.

        When ``conversation_id`` is ``None``, this deletes the current selected
        conversation for the session only. It does not delete all conversations
        under the session.
        """

        await self._proxy.call(
            "conversation.delete",
            {
                "session": _normalize_session(session),
                "conversation_id": conversation_id,
            },
        )

    async def get_conversation(
        self,
        session: str | MessageSession,
        conversation_id: str,
        *,
        create_if_not_exists: bool = False,
    ) -> ConversationRecord | None:
        output = await self._proxy.call(
            "conversation.get",
            {
                "session": _normalize_session(session),
                "conversation_id": str(conversation_id),
                "create_if_not_exists": bool(create_if_not_exists),
            },
        )
        return ConversationRecord.from_payload(output.get("conversation"))

    async def get_conversations(
        self,
        session: str | MessageSession | None = None,
        *,
        platform_id: str | None = None,
    ) -> list[ConversationRecord]:
        output = await self._proxy.call(
            "conversation.list",
            {
                "session": (
                    _normalize_session(session) if session is not None else None
                ),
                "platform_id": platform_id,
            },
        )
        items = output.get("conversations")
        if not isinstance(items, list):
            return []
        return [
            conversation
            for conversation in (
                ConversationRecord.from_payload(item)
                if isinstance(item, dict)
                else None
                for item in items
            )
            if conversation is not None
        ]

    async def update_conversation(
        self,
        session: str | MessageSession,
        conversation_id: str | None = None,
        params: ConversationUpdateParams | None = None,
    ) -> None:
        await self._proxy.call(
            "conversation.update",
            {
                "session": _normalize_session(session),
                "conversation_id": conversation_id,
                "conversation": (
                    params.to_update_payload() if params is not None else {}
                ),
            },
        )


class KnowledgeBaseManagerClient:
    def __init__(self, proxy: CapabilityProxy) -> None:
        self._proxy = proxy

    async def get_kb(self, kb_id: str) -> KnowledgeBaseRecord | None:
        output = await self._proxy.call("kb.get", {"kb_id": str(kb_id)})
        return KnowledgeBaseRecord.from_payload(output.get("kb"))

    async def create_kb(
        self,
        params: KnowledgeBaseCreateParams,
    ) -> KnowledgeBaseRecord:
        output = await self._proxy.call("kb.create", {"kb": params.to_payload()})
        kb = KnowledgeBaseRecord.from_payload(output.get("kb"))
        if kb is None:
            raise ValueError("kb.create returned no knowledge base")
        return kb

    async def delete_kb(self, kb_id: str) -> bool:
        output = await self._proxy.call("kb.delete", {"kb_id": str(kb_id)})
        return bool(output.get("deleted", False))


__all__ = [
    "ConversationCreateParams",
    "ConversationManagerClient",
    "ConversationRecord",
    "ConversationUpdateParams",
    "KnowledgeBaseCreateParams",
    "KnowledgeBaseManagerClient",
    "KnowledgeBaseRecord",
    "PersonaCreateParams",
    "PersonaManagerClient",
    "PersonaRecord",
    "PersonaUpdateParams",
]
