# ruff: noqa: E402
from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest


def _install_optional_dependency_stubs() -> None:
    def install(name: str, attrs: dict[str, object]) -> None:
        if name in sys.modules:
            return
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module

    install(
        "faiss",
        {
            "read_index": lambda *args, **kwargs: None,
            "write_index": lambda *args, **kwargs: None,
            "IndexFlatL2": type("IndexFlatL2", (), {}),
            "IndexIDMap": type("IndexIDMap", (), {}),
            "normalize_L2": lambda *args, **kwargs: None,
        },
    )
    install("pypdf", {"PdfReader": type("PdfReader", (), {})})
    install(
        "jieba",
        {
            "cut": lambda text, *args, **kwargs: text.split(),
            "lcut": lambda text, *args, **kwargs: text.split(),
        },
    )
    install("rank_bm25", {"BM25Okapi": type("BM25Okapi", (), {})})
    install(
        "aiocqhttp",
        {
            "CQHttp": type("CQHttp", (), {}),
            "Event": type("Event", (), {}),
        },
    )
    install(
        "aiocqhttp.exceptions",
        {"ActionFailed": type("ActionFailed", (Exception,), {})},
    )


_install_optional_dependency_stubs()

from astrbot_sdk import MessageSession
from astrbot_sdk.clients.managers import (
    ConversationCreateParams,
    ConversationRecord,
    ConversationUpdateParams,
    KnowledgeBaseCreateParams,
    KnowledgeBaseDocumentUploadParams,
    KnowledgeBaseUpdateParams,
    PersonaCreateParams,
    PersonaUpdateParams,
)
from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.testing import MockContext

from astrbot.core.sdk_bridge.capability_bridge import CoreCapabilityBridge


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mock_context_manager_clients_round_trip(tmp_path: Path) -> None:
    ctx = MockContext(plugin_id="sdk-demo")

    assert ctx.persona_manager is ctx.personas
    assert ctx.conversation_manager is ctx.conversations
    assert ctx.kb_manager is ctx.kbs

    persona = await ctx.personas.create_persona(
        PersonaCreateParams(
            persona_id="helper",
            system_prompt="Be helpful",
            begin_dialogs=["user hello", "assistant hello"],
            tools=["tool-a"],
            custom_error_message="fallback",
            sort_order=3,
        )
    )
    assert persona.persona_id == "helper"
    assert persona.tools == ["tool-a"]
    assert (await ctx.personas.get_persona("helper")).system_prompt == "Be helpful"
    updated_persona = await ctx.personas.update_persona(
        "helper",
        PersonaUpdateParams(
            system_prompt="Be precise",
            tools=None,
            custom_error_message=None,
        ),
    )
    assert updated_persona is not None
    assert updated_persona.system_prompt == "Be precise"
    assert updated_persona.tools is None
    assert updated_persona.custom_error_message is None
    assert [item.persona_id for item in await ctx.personas.get_all_personas()] == [
        "helper"
    ]
    await ctx.personas.delete_persona("helper")
    with pytest.raises(Exception):
        await ctx.personas.get_persona("helper")

    session = MessageSession(
        platform_id="demo-platform",
        message_type="private",
        session_id="user-1",
    )
    conversation_a = await ctx.conversations.new_conversation(
        session,
        ConversationCreateParams(
            title="first",
            history=[{"role": "user", "content": "hello"}],
        ),
    )
    conversation_b = await ctx.conversations.new_conversation(
        str(session),
        ConversationCreateParams(
            title="second",
            persona_id="persona-2",
        ),
    )
    await ctx.conversations.switch_conversation(session, conversation_a)
    await ctx.conversations.delete_conversation(session, None)

    assert await ctx.conversations.get_conversation(session, conversation_a) is None
    remaining_conversations = await ctx.conversations.get_conversations(session)
    assert [item.conversation_id for item in remaining_conversations] == [
        conversation_b
    ]

    await ctx.conversations.update_conversation(
        session,
        None,
        ConversationUpdateParams(
            title="second-updated",
            token_usage=42,
            history=[{"role": "assistant", "content": "updated"}],
        ),
    )
    current_conversation = await ctx.conversations.get_conversation(
        session,
        conversation_b,
    )
    assert isinstance(current_conversation, ConversationRecord)
    assert current_conversation.title == "second-updated"
    assert current_conversation.token_usage == 42
    assert current_conversation.history == [{"role": "assistant", "content": "updated"}]

    await ctx.conversations.unset_persona(session, conversation_b)
    current_conversation = await ctx.conversations.get_conversation(
        session,
        conversation_b,
    )
    assert isinstance(current_conversation, ConversationRecord)
    assert current_conversation.persona_id is None

    kb = await ctx.kbs.create_kb(
        KnowledgeBaseCreateParams(
            kb_name="Demo KB",
            embedding_provider_id="mock-embedding-provider",
            top_k_dense=5,
        )
    )
    assert kb.kb_name == "Demo KB"
    assert kb.embedding_provider_id == "mock-embedding-provider"
    listed_kbs = await ctx.kbs.list_kbs()
    assert [item.kb_id for item in listed_kbs] == [kb.kb_id]

    updated_kb = await ctx.kbs.update_kb(
        kb.kb_id,
        KnowledgeBaseUpdateParams(description="Updated KB", top_m_final=3),
    )
    assert updated_kb is not None
    assert updated_kb.description == "Updated KB"
    assert updated_kb.top_m_final == 3

    document_path = tmp_path / "kb-note.txt"
    document_path.write_text("AstrBot SDK knowledge base note", encoding="utf-8")
    document_token = await ctx.files.register_file(str(document_path))
    document = await ctx.kbs.upload_document(
        kb.kb_id,
        KnowledgeBaseDocumentUploadParams(file_token=document_token),
    )
    assert document.kb_id == kb.kb_id
    assert document.doc_name == "kb-note.txt"

    listed_documents = await ctx.kbs.list_documents(kb.kb_id)
    assert [item.doc_id for item in listed_documents] == [document.doc_id]
    assert (await ctx.kbs.get_document(kb.kb_id, document.doc_id)) is not None

    retrieved = await ctx.kbs.retrieve(
        "AstrBot knowledge",
        kb_ids=[kb.kb_id],
        top_m_final=1,
    )
    assert retrieved is not None
    assert [item.doc_id for item in retrieved.results] == [document.doc_id]

    refreshed_document = await ctx.kbs.refresh_document(kb.kb_id, document.doc_id)
    assert refreshed_document is not None
    assert refreshed_document.doc_id == document.doc_id

    assert await ctx.kbs.delete_document(kb.kb_id, document.doc_id) is True
    assert await ctx.kbs.get_document(kb.kb_id, document.doc_id) is None
    assert (await ctx.kbs.get_kb(kb.kb_id)) is not None
    assert await ctx.kbs.delete_kb(kb.kb_id) is True
    assert await ctx.kbs.get_kb(kb.kb_id) is None

    with pytest.raises(Exception):
        KnowledgeBaseCreateParams.model_validate({"kb_name": "Missing embedding"})


@dataclass(slots=True)
class _FakeKBRecord:
    kb_id: str = "kb-1"
    kb_name: str = "Demo KB"
    description: str | None = "desc"
    emoji: str | None = "📚"
    embedding_provider_id: str = "embedding-1"
    rerank_provider_id: str | None = "rerank-1"
    chunk_size: int | None = 512
    chunk_overlap: int | None = 32
    top_k_dense: int | None = 8
    top_k_sparse: int | None = 10
    top_m_final: int | None = 5
    doc_count: int = 2
    chunk_count: int = 8
    created_at: object | None = None
    updated_at: object | None = None


@dataclass(slots=True)
class _FakeKBDocumentRecord:
    doc_id: str = "doc-1"
    kb_id: str = "kb-1"
    doc_name: str = "Guide.txt"
    file_type: str = "txt"
    file_size: int = 17
    file_path: str = ""
    chunk_count: int = 1
    media_count: int = 0
    created_at: object | None = None
    updated_at: object | None = None


class _FakeKBHelper:
    def __init__(self, kb: _FakeKBRecord) -> None:
        self.kb = kb
        self.documents: dict[str, _FakeKBDocumentRecord] = {
            "doc-1": _FakeKBDocumentRecord(kb_id=kb.kb_id)
        }
        self.upload_calls: list[dict[str, object | None]] = []
        self.deleted_document_ids: list[str] = []
        self.refreshed_document_ids: list[str] = []

    async def list_documents(
        self,
        offset: int = 0,
        limit: int = 100,
    ) -> list[_FakeKBDocumentRecord]:
        return list(self.documents.values())[offset : offset + limit]

    async def get_document(self, doc_id: str) -> _FakeKBDocumentRecord | None:
        return self.documents.get(doc_id)

    async def upload_document(self, **kwargs) -> _FakeKBDocumentRecord:
        self.upload_calls.append(dict(kwargs))
        document = _FakeKBDocumentRecord(
            doc_id="doc-uploaded",
            kb_id=self.kb.kb_id,
            doc_name=str(kwargs.get("file_name", "Uploaded.txt")),
            file_type=str(kwargs.get("file_type", "txt")),
            file_size=(
                len(kwargs["file_content"])
                if isinstance(kwargs.get("file_content"), bytes)
                else len("".join(kwargs.get("pre_chunked_text") or []))
            ),
        )
        self.documents[document.doc_id] = document
        self.kb.doc_count = len(self.documents)
        self.kb.chunk_count = sum(item.chunk_count for item in self.documents.values())
        return document

    async def delete_document(self, doc_id: str) -> None:
        self.deleted_document_ids.append(doc_id)
        self.documents.pop(doc_id, None)
        self.kb.doc_count = len(self.documents)
        self.kb.chunk_count = sum(item.chunk_count for item in self.documents.values())

    async def refresh_document(self, doc_id: str) -> None:
        self.refreshed_document_ids.append(doc_id)


class _FakeConversationManager:
    def __init__(self) -> None:
        self.delete_calls: list[tuple[str, str | None]] = []

    async def new_conversation(self, *args, **kwargs) -> str:  # pragma: no cover
        return "conv-created"

    async def switch_conversation(self, *args, **kwargs) -> None:  # pragma: no cover
        return None

    async def delete_conversation(
        self,
        unified_msg_origin: str,
        conversation_id: str | None = None,
    ) -> None:
        self.delete_calls.append((unified_msg_origin, conversation_id))

    async def get_conversation(self, *args, **kwargs):  # pragma: no cover
        return None

    async def get_conversations(
        self, *args, **kwargs
    ) -> list[object]:  # pragma: no cover
        return []

    async def update_conversation(self, *args, **kwargs) -> None:  # pragma: no cover
        return None


class _FakePersonaManager:
    async def get_persona(self, persona_id: str):  # pragma: no cover
        raise ValueError(f"Persona with ID {persona_id} does not exist.")

    async def get_all_personas(self) -> list[object]:  # pragma: no cover
        return []

    async def create_persona(self, **kwargs):  # pragma: no cover
        return None

    async def update_persona(self, **kwargs):  # pragma: no cover
        return None

    async def delete_persona(self, persona_id: str) -> None:  # pragma: no cover
        return None


class _FakeKnowledgeBaseManager:
    def __init__(self) -> None:
        self.deleted_ids: list[str] = []
        self.created_payloads: list[dict[str, object | None]] = []
        self.updated_payloads: list[dict[str, object | None]] = []
        self.retrieve_calls: list[dict[str, object | None]] = []
        self.upload_from_url_calls: list[dict[str, object | None]] = []
        self.helper = _FakeKBHelper(_FakeKBRecord())

    async def get_kb(self, kb_id: str):
        if kb_id != self.helper.kb.kb_id:
            return None
        return self.helper

    async def create_kb(self, **kwargs):
        self.created_payloads.append(dict(kwargs))
        self.helper = _FakeKBHelper(_FakeKBRecord(kb_id="kb-created", kb_name="Created KB"))
        return self.helper

    async def delete_kb(self, kb_id: str) -> bool:
        self.deleted_ids.append(kb_id)
        return kb_id == "kb-1"

    async def list_kbs(self) -> list[_FakeKBRecord]:
        return [self.helper.kb]

    async def update_kb(self, **kwargs):
        self.updated_payloads.append(dict(kwargs))
        kb_name = kwargs.get("kb_name")
        if kb_name is not None:
            self.helper.kb.kb_name = str(kb_name)
        if "description" in kwargs and kwargs["description"] is not None:
            self.helper.kb.description = str(kwargs["description"])
        if "top_m_final" in kwargs and kwargs["top_m_final"] is not None:
            self.helper.kb.top_m_final = int(kwargs["top_m_final"])
        return self.helper

    async def retrieve(
        self,
        *,
        query: str,
        kb_names: list[str],
        top_k_fusion: int = 20,
        top_m_final: int = 5,
    ) -> dict[str, object] | None:
        self.retrieve_calls.append(
            {
                "query": query,
                "kb_names": list(kb_names),
                "top_k_fusion": top_k_fusion,
                "top_m_final": top_m_final,
            }
        )
        if not kb_names:
            return None
        return {
            "context_text": "Mock KB context",
            "results": [
                {
                    "chunk_id": "chunk-1",
                    "doc_id": "doc-1",
                    "kb_id": self.helper.kb.kb_id,
                    "kb_name": self.helper.kb.kb_name,
                    "doc_name": "Guide.txt",
                    "chunk_index": 0,
                    "content": "AstrBot KB guide",
                    "score": 0.9,
                    "char_count": 16,
                }
            ],
        }

    async def upload_from_url(self, **kwargs) -> _FakeKBDocumentRecord:
        self.upload_from_url_calls.append(dict(kwargs))
        document = _FakeKBDocumentRecord(
            doc_id="doc-from-url",
            kb_id=str(kwargs.get("kb_id", self.helper.kb.kb_id)),
            doc_name="from-url.url",
            file_type="url",
        )
        self.helper.documents[document.doc_id] = document
        return document


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bridge_serializes_kb_record_and_preserves_delete_none_semantics() -> (
    None
):
    fake_conversation_manager = _FakeConversationManager()
    fake_kb_manager = _FakeKnowledgeBaseManager()
    bridge = CoreCapabilityBridge(
        star_context=SimpleNamespace(
            persona_manager=_FakePersonaManager(),
            conversation_manager=fake_conversation_manager,
            kb_manager=fake_kb_manager,
        ),
        plugin_bridge=SimpleNamespace(resolve_request_session=lambda _request_id: None),
    )
    assert "persona.get" in {item.name for item in bridge.descriptors()}
    assert "conversation.new" in {item.name for item in bridge.descriptors()}
    assert "kb.get" in {item.name for item in bridge.descriptors()}
    assert "kb.list" in {item.name for item in bridge.descriptors()}
    assert "kb.retrieve" in {item.name for item in bridge.descriptors()}
    assert "kb.document.upload" in {item.name for item in bridge.descriptors()}

    await bridge._conversation_delete(
        "req-1",
        {"session": "demo-platform:private:user-1", "conversation_id": None},
        None,
    )
    assert fake_conversation_manager.delete_calls == [
        ("demo-platform:private:user-1", None)
    ]

    kb_get = await bridge._kb_get("req-2", {"kb_id": "kb-1"}, None)
    assert kb_get["kb"] is not None
    assert kb_get["kb"]["kb_id"] == "kb-1"
    assert kb_get["kb"]["kb_name"] == "Demo KB"
    assert kb_get["kb"]["embedding_provider_id"] == "embedding-1"

    kb_list = await bridge._kb_list("req-2b", {}, None)
    assert [item["kb_id"] for item in kb_list["kbs"]] == ["kb-1"]

    kb_create = await bridge._kb_create(
        "req-3",
        {
            "kb": {
                "kb_name": "Created KB",
                "embedding_provider_id": "embedding-1",
            }
        },
        None,
    )
    assert kb_create["kb"]["kb_id"] == "kb-created"
    assert fake_kb_manager.created_payloads == [
        {
            "kb_name": "Created KB",
            "description": None,
            "emoji": None,
            "embedding_provider_id": "embedding-1",
            "rerank_provider_id": None,
            "chunk_size": None,
            "chunk_overlap": None,
            "top_k_dense": None,
            "top_k_sparse": None,
            "top_m_final": None,
        }
    ]

    kb_update = await bridge._kb_update(
        "req-3b",
        {"kb_id": "kb-created", "kb": {"description": "Updated", "top_m_final": 2}},
        None,
    )
    assert kb_update["kb"] is not None
    assert kb_update["kb"]["description"] == "Updated"
    assert fake_kb_manager.updated_payloads[-1]["top_m_final"] == 2

    kb_delete = await bridge._kb_delete("req-4", {"kb_id": "kb-1"}, None)
    assert kb_delete == {"deleted": True}
    assert fake_kb_manager.deleted_ids == ["kb-1"]

    kb_retrieve = await bridge._kb_retrieve(
        "req-5",
        {"query": "AstrBot", "kb_ids": ["kb-created"], "top_m_final": 1},
        None,
    )
    assert kb_retrieve["result"] is not None
    assert kb_retrieve["result"]["results"][0]["doc_id"] == "doc-1"
    assert fake_kb_manager.retrieve_calls[-1]["kb_names"] == ["Created KB"]

    kb_document_list = await bridge._kb_document_list(
        "req-6",
        {"kb_id": "kb-created"},
        None,
    )
    assert [item["doc_id"] for item in kb_document_list["documents"]] == ["doc-1"]

    kb_document_get = await bridge._kb_document_get(
        "req-7",
        {"kb_id": "kb-created", "doc_id": "doc-1"},
        None,
    )
    assert kb_document_get["document"] is not None
    assert kb_document_get["document"]["doc_name"] == "Guide.txt"

    kb_document_upload = await bridge._kb_document_upload(
        "req-7b",
        {
            "kb_id": "kb-created",
            "document": {"text": "inline knowledge", "file_name": "inline.txt"},
        },
        None,
    )
    assert kb_document_upload["document"] is not None
    assert kb_document_upload["document"]["doc_name"] == "inline.txt"
    assert fake_kb_manager.helper.upload_calls[-1]["pre_chunked_text"] == [
        "inline knowledge"
    ]

    kb_document_refresh = await bridge._kb_document_refresh(
        "req-8",
        {"kb_id": "kb-created", "doc_id": "doc-1"},
        None,
    )
    assert kb_document_refresh["document"] is not None
    assert fake_kb_manager.helper.refreshed_document_ids == ["doc-1"]

    kb_document_delete = await bridge._kb_document_delete(
        "req-9",
        {"kb_id": "kb-created", "doc_id": "doc-1"},
        None,
    )
    assert kb_document_delete == {"deleted": True}
    assert fake_kb_manager.helper.deleted_document_ids == ["doc-1"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bridge_validates_conversation_session_inputs() -> None:
    bridge = CoreCapabilityBridge(
        star_context=SimpleNamespace(
            persona_manager=_FakePersonaManager(),
            conversation_manager=_FakeConversationManager(),
            kb_manager=_FakeKnowledgeBaseManager(),
        ),
        plugin_bridge=SimpleNamespace(resolve_request_session=lambda _request_id: None),
    )

    with pytest.raises(AstrBotError, match="conversation.new requires session"):
        await bridge._conversation_new("req-1", {"session": "   "}, None)

    with pytest.raises(AstrBotError, match="conversation.switch requires session"):
        await bridge._conversation_switch(
            "req-2",
            {"session": "   ", "conversation_id": "conv-1"},
            None,
        )

    with pytest.raises(
        AstrBotError,
        match="conversation.switch requires conversation_id",
    ):
        await bridge._conversation_switch(
            "req-3",
            {"session": "demo-platform:private:user-1", "conversation_id": "   "},
            None,
        )
