from __future__ import annotations

import uuid
from typing import Any

from ....errors import AstrBotError
from ..bridge_base import CapabilityRouterBridgeBase


class KnowledgeBaseCapabilityMixin(CapabilityRouterBridgeBase):
    async def _kb_get(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        kb_id = str(payload.get("kb_id", "")).strip()
        record = self._kb_store.get(kb_id)
        return {"kb": dict(record) if isinstance(record, dict) else None}

    async def _kb_create(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        raw_kb = payload.get("kb")
        if not isinstance(raw_kb, dict):
            raise AstrBotError.invalid_input("kb.create requires kb object")
        embedding_provider_id = str(raw_kb.get("embedding_provider_id", "")).strip()
        if not embedding_provider_id:
            raise AstrBotError.invalid_input("kb.create requires embedding_provider_id")
        kb_id = uuid.uuid4().hex
        now = self._now_iso()
        record = {
            "kb_id": kb_id,
            "kb_name": str(raw_kb.get("kb_name", "")),
            "description": (
                str(raw_kb.get("description"))
                if raw_kb.get("description") is not None
                else None
            ),
            "emoji": (
                str(raw_kb.get("emoji")) if raw_kb.get("emoji") is not None else None
            ),
            "embedding_provider_id": embedding_provider_id,
            "rerank_provider_id": (
                str(raw_kb.get("rerank_provider_id"))
                if raw_kb.get("rerank_provider_id") is not None
                else None
            ),
            "chunk_size": self._optional_int(raw_kb.get("chunk_size")),
            "chunk_overlap": self._optional_int(raw_kb.get("chunk_overlap")),
            "top_k_dense": self._optional_int(raw_kb.get("top_k_dense")),
            "top_k_sparse": self._optional_int(raw_kb.get("top_k_sparse")),
            "top_m_final": self._optional_int(raw_kb.get("top_m_final")),
            "doc_count": 0,
            "chunk_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        self._kb_store[kb_id] = record
        return {"kb": dict(record)}

    async def _kb_delete(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        kb_id = str(payload.get("kb_id", "")).strip()
        deleted = self._kb_store.pop(kb_id, None) is not None
        return {"deleted": deleted}

    def _register_kb_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("kb.get", "获取知识库"),
            call_handler=self._kb_get,
        )
        self.register(
            self._builtin_descriptor("kb.create", "创建知识库"),
            call_handler=self._kb_create,
        )
        self.register(
            self._builtin_descriptor("kb.delete", "删除知识库"),
            call_handler=self._kb_delete,
        )
