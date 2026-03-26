"""Typed SDK manager clients for persona, conversation, and knowledge base."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..errors import AstrBotError, ErrorCodes
from ..message.components import (
    BaseMessageComponent,
    component_to_payload_sync,
    payload_to_component,
)
from ..message.session import MessageSession
from ._proxy import CapabilityProxy


class _ManagerModel(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)

    def to_update_payload(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


def _normalize_session(session: str | MessageSession) -> str:
    if isinstance(session, MessageSession):
        return str(session)
    return str(session)


def _require_message_history_session(
    session: MessageSession,
) -> dict[str, str]:
    if not isinstance(session, MessageSession):
        raise TypeError(
            "message_history requires astrbot_sdk.message.session.MessageSession"
        )
    return {
        "platform_id": str(session.platform_id),
        "message_type": str(session.message_type),
        "session_id": str(session.session_id),
    }


def _normalize_message_history_parts(
    parts: list[BaseMessageComponent],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for part in parts:
        if not isinstance(part, BaseMessageComponent):
            raise TypeError(
                "message_history.append requires BaseMessageComponent items in parts"
            )
        normalized.append(component_to_payload_sync(part))
    return normalized


def _normalize_message_history_boundary(value: datetime) -> str:
    if not isinstance(value, datetime):
        raise TypeError("message_history boundary requires datetime")
    normalized = value
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=timezone.utc)
    else:
        normalized = normalized.astimezone(timezone.utc)
    return normalized.isoformat()


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


class MessageHistorySender(_ManagerModel):
    sender_id: str | None = None
    sender_name: str | None = None

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> MessageHistorySender | None:
        if not isinstance(payload, dict):
            return None
        return cls.model_validate(payload)


class MessageHistoryRecord(_ManagerModel):
    id: int
    session: MessageSession
    sender: MessageHistorySender = Field(default_factory=MessageHistorySender)
    parts: list[BaseMessageComponent] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    idempotency_key: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)

        session_payload = normalized.get("session")
        if isinstance(session_payload, dict):
            normalized["session"] = MessageSession(
                platform_id=str(session_payload.get("platform_id", "")),
                message_type=str(session_payload.get("message_type", "")),
                session_id=str(session_payload.get("session_id", "")),
            )

        sender_payload = normalized.get("sender")
        if isinstance(sender_payload, dict):
            normalized["sender"] = MessageHistorySender.model_validate(sender_payload)
        elif sender_payload is None:
            normalized["sender"] = MessageHistorySender()

        parts_payload = normalized.get("parts")
        if isinstance(parts_payload, list):
            normalized["parts"] = [
                payload_to_component(item)
                for item in parts_payload
                if isinstance(item, dict)
            ]

        metadata_payload = normalized.get("metadata")
        if not isinstance(metadata_payload, dict):
            normalized["metadata"] = {}

        return normalized

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> MessageHistoryRecord | None:
        if not isinstance(payload, dict):
            return None
        return cls.model_validate(payload)


class MessageHistoryPage(_ManagerModel):
    records: list[MessageHistoryRecord] = Field(default_factory=list)
    next_cursor: str | None = None
    total: int | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        records_payload = normalized.get("records")
        if isinstance(records_payload, list):
            normalized["records"] = [
                record
                for record in (
                    MessageHistoryRecord.from_payload(item)
                    if isinstance(item, dict)
                    else None
                    for item in records_payload
                )
                if record is not None
            ]
        return normalized

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> MessageHistoryPage | None:
        if not isinstance(payload, dict):
            return None
        return cls.model_validate(payload)


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


class KnowledgeBaseUpdateParams(_ManagerModel):
    kb_name: str | None = None
    embedding_provider_id: str | None = None
    description: str | None = None
    emoji: str | None = None
    rerank_provider_id: str | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    top_k_dense: int | None = None
    top_k_sparse: int | None = None
    top_m_final: int | None = None


class KnowledgeBaseDocumentRecord(_ManagerModel):
    doc_id: str
    kb_id: str
    doc_name: str
    file_type: str
    file_size: int
    file_path: str = ""
    chunk_count: int = 0
    media_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> KnowledgeBaseDocumentRecord | None:
        if not isinstance(payload, dict):
            return None
        return cls.model_validate(payload)


class KnowledgeBaseRetrieveResultItem(_ManagerModel):
    chunk_id: str
    doc_id: str
    kb_id: str
    kb_name: str
    doc_name: str
    chunk_index: int
    content: str
    score: float
    char_count: int

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> KnowledgeBaseRetrieveResultItem | None:
        if not isinstance(payload, dict):
            return None
        return cls.model_validate(payload)


class KnowledgeBaseRetrieveResult(_ManagerModel):
    context_text: str
    results: list[KnowledgeBaseRetrieveResultItem] = Field(default_factory=list)

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> KnowledgeBaseRetrieveResult | None:
        if not isinstance(payload, dict):
            return None
        items = payload.get("results")
        normalized_items = (
            [
                item.model_dump()
                for item in (
                    KnowledgeBaseRetrieveResultItem.from_payload(candidate)
                    if isinstance(candidate, dict)
                    else None
                    for candidate in items
                )
                if item is not None
            ]
            if isinstance(items, list)
            else []
        )
        return cls.model_validate(
            {
                "context_text": str(payload.get("context_text", "")),
                "results": normalized_items,
            }
        )


class KnowledgeBaseDocumentUploadParams(_ManagerModel):
    file_token: str | None = None
    url: str | None = None
    text: str | None = None
    file_name: str | None = None
    file_type: str | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    batch_size: int | None = None
    tasks_limit: int | None = None
    max_retries: int | None = None
    enable_cleaning: bool | None = None
    cleaning_provider_id: str | None = None

    @model_validator(mode="after")
    def _validate_source(self) -> KnowledgeBaseDocumentUploadParams:
        if any(
            isinstance(value, str) and value.strip()
            for value in (self.file_token, self.url, self.text)
        ):
            return self
        raise ValueError(
            "knowledge base document upload requires file_token, url, or text"
        )


class PersonaManagerClient:
    def __init__(self, proxy: CapabilityProxy) -> None:
        self._proxy = proxy

    async def get_persona(self, persona_id: str) -> PersonaRecord:
        try:
            output = await self._proxy.call(
                "persona.get",
                {"persona_id": str(persona_id)},
            )
        except AstrBotError as exc:
            if exc.code == ErrorCodes.INVALID_INPUT:
                raise ValueError(f"persona not found: {persona_id}") from exc
            raise
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

    async def get_current_conversation(
        self,
        session: str | MessageSession,
        *,
        create_if_not_exists: bool = False,
    ) -> ConversationRecord | None:
        output = await self._proxy.call(
            "conversation.get_current",
            {
                "session": _normalize_session(session),
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

    async def unset_persona(
        self,
        session: str | MessageSession,
        conversation_id: str | None = None,
    ) -> None:
        await self._proxy.call(
            "conversation.unset_persona",
            {
                "session": _normalize_session(session),
                "conversation_id": conversation_id,
            },
        )


class MessageHistoryManagerClient:
    def __init__(self, proxy: CapabilityProxy) -> None:
        self._proxy = proxy

    async def list(
        self,
        session: MessageSession,
        *,
        cursor: str | None = None,
        limit: int = 50,
    ) -> MessageHistoryPage:
        output = await self._proxy.call(
            "message_history.list",
            {
                "session": _require_message_history_session(session),
                "cursor": str(cursor) if cursor is not None else None,
                "limit": int(limit),
            },
        )
        page = MessageHistoryPage.from_payload(output.get("page"))
        if page is None:
            raise ValueError("message_history.list returned no page")
        return page

    async def get(
        self,
        session: MessageSession,
        record_id: int,
    ) -> MessageHistoryRecord | None:
        output = await self._proxy.call(
            "message_history.get_by_id",
            {
                "session": _require_message_history_session(session),
                "record_id": int(record_id),
            },
        )
        return MessageHistoryRecord.from_payload(output.get("record"))

    async def get_by_id(
        self,
        session: MessageSession,
        record_id: int,
    ) -> MessageHistoryRecord | None:
        return await self.get(session, record_id)

    async def append(
        self,
        session: MessageSession,
        *,
        parts: list[BaseMessageComponent],
        sender: MessageHistorySender,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> MessageHistoryRecord:
        if isinstance(sender, MessageHistorySender):
            sender_payload = sender.to_payload()
        elif isinstance(sender, dict):
            sender_payload = MessageHistorySender.model_validate(sender).to_payload()
        else:
            raise TypeError(
                "message_history.append requires MessageHistorySender for sender"
            )
        output = await self._proxy.call(
            "message_history.append",
            {
                "session": _require_message_history_session(session),
                "sender": sender_payload,
                "parts": _normalize_message_history_parts(parts),
                "metadata": dict(metadata or {}),
                "idempotency_key": (
                    str(idempotency_key) if idempotency_key is not None else None
                ),
            },
        )
        record = MessageHistoryRecord.from_payload(output.get("record"))
        if record is None:
            raise ValueError("message_history.append returned no record")
        return record

    async def delete_before(
        self,
        session: MessageSession,
        *,
        before: datetime,
    ) -> int:
        output = await self._proxy.call(
            "message_history.delete_before",
            {
                "session": _require_message_history_session(session),
                "before": _normalize_message_history_boundary(before),
            },
        )
        return int(output.get("deleted_count", 0) or 0)

    async def delete_after(
        self,
        session: MessageSession,
        *,
        after: datetime,
    ) -> int:
        output = await self._proxy.call(
            "message_history.delete_after",
            {
                "session": _require_message_history_session(session),
                "after": _normalize_message_history_boundary(after),
            },
        )
        return int(output.get("deleted_count", 0) or 0)

    async def delete_all(self, session: MessageSession) -> int:
        output = await self._proxy.call(
            "message_history.delete_all",
            {"session": _require_message_history_session(session)},
        )
        return int(output.get("deleted_count", 0) or 0)


class KnowledgeBaseManagerClient:
    def __init__(self, proxy: CapabilityProxy) -> None:
        self._proxy = proxy

    async def list_kbs(self) -> list[KnowledgeBaseRecord]:
        output = await self._proxy.call("kb.list", {})
        items = output.get("kbs")
        if not isinstance(items, list):
            return []
        return [
            kb
            for kb in (
                KnowledgeBaseRecord.from_payload(item)
                if isinstance(item, dict)
                else None
                for item in items
            )
            if kb is not None
        ]

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

    async def update_kb(
        self,
        kb_id: str,
        params: KnowledgeBaseUpdateParams,
    ) -> KnowledgeBaseRecord | None:
        output = await self._proxy.call(
            "kb.update",
            {"kb_id": str(kb_id), "kb": params.to_update_payload()},
        )
        return KnowledgeBaseRecord.from_payload(output.get("kb"))

    async def delete_kb(self, kb_id: str) -> bool:
        output = await self._proxy.call("kb.delete", {"kb_id": str(kb_id)})
        return bool(output.get("deleted", False))

    async def retrieve(
        self,
        query: str,
        *,
        kb_ids: list[str] | None = None,
        kb_names: list[str] | None = None,
        top_k_fusion: int | None = None,
        top_m_final: int | None = None,
    ) -> KnowledgeBaseRetrieveResult | None:
        request_payload: dict[str, Any] = {
            "query": str(query),
            "kb_ids": [str(item) for item in (kb_ids or [])],
            "kb_names": [str(item) for item in (kb_names or [])],
        }
        if top_k_fusion is not None:
            request_payload["top_k_fusion"] = int(top_k_fusion)
        if top_m_final is not None:
            request_payload["top_m_final"] = int(top_m_final)
        output = await self._proxy.call(
            "kb.retrieve",
            request_payload,
        )
        return KnowledgeBaseRetrieveResult.from_payload(output.get("result"))

    async def upload_document(
        self,
        kb_id: str,
        params: KnowledgeBaseDocumentUploadParams,
    ) -> KnowledgeBaseDocumentRecord:
        output = await self._proxy.call(
            "kb.document.upload",
            {"kb_id": str(kb_id), "document": params.to_payload()},
        )
        document = KnowledgeBaseDocumentRecord.from_payload(output.get("document"))
        if document is None:
            raise ValueError("kb.document.upload returned no document")
        return document

    async def list_documents(
        self,
        kb_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[KnowledgeBaseDocumentRecord]:
        output = await self._proxy.call(
            "kb.document.list",
            {"kb_id": str(kb_id), "offset": int(offset), "limit": int(limit)},
        )
        items = output.get("documents")
        if not isinstance(items, list):
            return []
        return [
            document
            for document in (
                KnowledgeBaseDocumentRecord.from_payload(item)
                if isinstance(item, dict)
                else None
                for item in items
            )
            if document is not None
        ]

    async def get_document(
        self,
        kb_id: str,
        doc_id: str,
    ) -> KnowledgeBaseDocumentRecord | None:
        output = await self._proxy.call(
            "kb.document.get",
            {"kb_id": str(kb_id), "doc_id": str(doc_id)},
        )
        return KnowledgeBaseDocumentRecord.from_payload(output.get("document"))

    async def delete_document(
        self,
        kb_id: str,
        doc_id: str,
    ) -> bool:
        output = await self._proxy.call(
            "kb.document.delete",
            {"kb_id": str(kb_id), "doc_id": str(doc_id)},
        )
        return bool(output.get("deleted", False))

    async def refresh_document(
        self,
        kb_id: str,
        doc_id: str,
    ) -> KnowledgeBaseDocumentRecord | None:
        output = await self._proxy.call(
            "kb.document.refresh",
            {"kb_id": str(kb_id), "doc_id": str(doc_id)},
        )
        return KnowledgeBaseDocumentRecord.from_payload(output.get("document"))


__all__ = [
    "ConversationCreateParams",
    "ConversationManagerClient",
    "ConversationRecord",
    "ConversationUpdateParams",
    "KnowledgeBaseCreateParams",
    "KnowledgeBaseDocumentRecord",
    "KnowledgeBaseDocumentUploadParams",
    "KnowledgeBaseManagerClient",
    "KnowledgeBaseRecord",
    "KnowledgeBaseRetrieveResult",
    "KnowledgeBaseRetrieveResultItem",
    "KnowledgeBaseUpdateParams",
    "MessageHistoryManagerClient",
    "MessageHistoryPage",
    "MessageHistoryRecord",
    "MessageHistorySender",
    "PersonaCreateParams",
    "PersonaManagerClient",
    "PersonaRecord",
    "PersonaUpdateParams",
]
