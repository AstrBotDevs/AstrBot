from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from astrbot_sdk.errors import AstrBotError

from astrbot.core.sdk_bridge.bridge_base import _get_runtime_file_token_service

from ._host import CapabilityMixinHost


class KnowledgeBaseCapabilityMixin(CapabilityMixinHost):
    def _register_kb_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("kb.list", "List knowledge bases"),
            call_handler=self._kb_list,
        )
        self.register(
            self._builtin_descriptor("kb.get", "Get knowledge base"),
            call_handler=self._kb_get,
        )
        self.register(
            self._builtin_descriptor("kb.create", "Create knowledge base"),
            call_handler=self._kb_create,
        )
        self.register(
            self._builtin_descriptor("kb.update", "Update knowledge base"),
            call_handler=self._kb_update,
        )
        self.register(
            self._builtin_descriptor("kb.delete", "Delete knowledge base"),
            call_handler=self._kb_delete,
        )
        self.register(
            self._builtin_descriptor("kb.retrieve", "Retrieve from knowledge bases"),
            call_handler=self._kb_retrieve,
        )
        self.register(
            self._builtin_descriptor(
                "kb.document.upload", "Upload knowledge base document"
            ),
            call_handler=self._kb_document_upload,
        )
        self.register(
            self._builtin_descriptor(
                "kb.document.list", "List knowledge base documents"
            ),
            call_handler=self._kb_document_list,
        )
        self.register(
            self._builtin_descriptor("kb.document.get", "Get knowledge base document"),
            call_handler=self._kb_document_get,
        )
        self.register(
            self._builtin_descriptor(
                "kb.document.delete",
                "Delete knowledge base document",
            ),
            call_handler=self._kb_document_delete,
        )
        self.register(
            self._builtin_descriptor(
                "kb.document.refresh",
                "Refresh knowledge base document",
            ),
            call_handler=self._kb_document_refresh,
        )

    async def _get_kb_helper(self, kb_id: str):
        return await self._star_context.kb_manager.get_kb(kb_id)

    async def _require_kb_helper(self, kb_id: str):
        kb_id_text = str(kb_id).strip()
        if not kb_id_text:
            raise AstrBotError.invalid_input("kb capability requires kb_id")
        kb_helper = await self._get_kb_helper(kb_id_text)
        if kb_helper is None:
            raise AstrBotError.invalid_input(f"Unknown knowledge base: {kb_id_text}")
        return kb_helper

    @staticmethod
    def _normalize_kb_names(payload: dict[str, Any]) -> list[str]:
        raw_names = payload.get("kb_names")
        if not isinstance(raw_names, list):
            return []
        return [str(item).strip() for item in raw_names if str(item).strip()]

    @staticmethod
    def _normalize_kb_ids(payload: dict[str, Any]) -> list[str]:
        raw_ids = payload.get("kb_ids")
        if not isinstance(raw_ids, list):
            return []
        return [str(item).strip() for item in raw_ids if str(item).strip()]

    async def _resolve_retrieve_kb_names(
        self,
        payload: dict[str, Any],
    ) -> list[str]:
        kb_names = self._normalize_kb_names(payload)
        if kb_names:
            return kb_names
        resolved_names: list[str] = []
        for kb_id in self._normalize_kb_ids(payload):
            kb_helper = await self._get_kb_helper(kb_id)
            if kb_helper is not None and getattr(kb_helper, "kb", None) is not None:
                kb_name = str(getattr(kb_helper.kb, "kb_name", "")).strip()
                if kb_name:
                    resolved_names.append(kb_name)
        return resolved_names

    async def _kb_list(
        self,
        _request_id: str,
        _payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        kbs = await self._star_context.kb_manager.list_kbs()
        return {
            "kbs": [
                payload
                for payload in (self._serialize_kb(kb) for kb in kbs)
                if payload is not None
            ]
        }

    async def _kb_get(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        kb_helper = await self._get_kb_helper(str(payload.get("kb_id", "")))
        return {"kb": self._serialize_kb(kb_helper)}

    async def _kb_create(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        raw_kb = payload.get("kb")
        if not isinstance(raw_kb, dict):
            raise AstrBotError.invalid_input("kb.create requires kb object")
        try:
            kb_helper = await self._star_context.kb_manager.create_kb(
                kb_name=str(raw_kb.get("kb_name", "")),
                description=(
                    str(raw_kb.get("description"))
                    if raw_kb.get("description") is not None
                    else None
                ),
                emoji=(
                    str(raw_kb.get("emoji"))
                    if raw_kb.get("emoji") is not None
                    else None
                ),
                embedding_provider_id=(
                    str(raw_kb.get("embedding_provider_id"))
                    if raw_kb.get("embedding_provider_id") is not None
                    else None
                ),
                rerank_provider_id=(
                    str(raw_kb.get("rerank_provider_id"))
                    if raw_kb.get("rerank_provider_id") is not None
                    else None
                ),
                chunk_size=self._optional_int(raw_kb.get("chunk_size")),
                chunk_overlap=self._optional_int(raw_kb.get("chunk_overlap")),
                top_k_dense=self._optional_int(raw_kb.get("top_k_dense")),
                top_k_sparse=self._optional_int(raw_kb.get("top_k_sparse")),
                top_m_final=self._optional_int(raw_kb.get("top_m_final")),
            )
        except ValueError as exc:
            raise AstrBotError.invalid_input(str(exc)) from exc
        return {"kb": self._serialize_kb(kb_helper)}

    async def _kb_update(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        kb_id = str(payload.get("kb_id", "")).strip()
        raw_kb = payload.get("kb")
        if not isinstance(raw_kb, dict):
            raise AstrBotError.invalid_input("kb.update requires kb object")
        kb_helper = await self._get_kb_helper(kb_id)
        if kb_helper is None:
            return {"kb": None}
        current_kb = getattr(kb_helper, "kb", None)
        kb_name = raw_kb.get("kb_name")
        try:
            updated_helper = await self._star_context.kb_manager.update_kb(
                kb_id=kb_id,
                kb_name=(
                    str(kb_name)
                    if kb_name is not None
                    else str(getattr(current_kb, "kb_name", ""))
                ),
                description=(
                    str(raw_kb.get("description"))
                    if raw_kb.get("description") is not None
                    else None
                )
                if "description" in raw_kb
                else None,
                emoji=(
                    str(raw_kb.get("emoji"))
                    if raw_kb.get("emoji") is not None
                    else None
                )
                if "emoji" in raw_kb
                else None,
                embedding_provider_id=(
                    str(raw_kb.get("embedding_provider_id"))
                    if raw_kb.get("embedding_provider_id") is not None
                    else None
                )
                if "embedding_provider_id" in raw_kb
                else None,
                rerank_provider_id=(
                    str(raw_kb.get("rerank_provider_id"))
                    if raw_kb.get("rerank_provider_id") is not None
                    else None
                )
                if "rerank_provider_id" in raw_kb
                else None,
                chunk_size=(
                    self._optional_int(raw_kb.get("chunk_size"))
                    if "chunk_size" in raw_kb
                    else None
                ),
                chunk_overlap=(
                    self._optional_int(raw_kb.get("chunk_overlap"))
                    if "chunk_overlap" in raw_kb
                    else None
                ),
                top_k_dense=(
                    self._optional_int(raw_kb.get("top_k_dense"))
                    if "top_k_dense" in raw_kb
                    else None
                ),
                top_k_sparse=(
                    self._optional_int(raw_kb.get("top_k_sparse"))
                    if "top_k_sparse" in raw_kb
                    else None
                ),
                top_m_final=(
                    self._optional_int(raw_kb.get("top_m_final"))
                    if "top_m_final" in raw_kb
                    else None
                ),
            )
        except ValueError as exc:
            raise AstrBotError.invalid_input(str(exc)) from exc
        return {"kb": self._serialize_kb(updated_helper)}

    async def _kb_delete(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        deleted = await self._star_context.kb_manager.delete_kb(
            str(payload.get("kb_id", ""))
        )
        return {"deleted": bool(deleted)}

    async def _kb_retrieve(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        query = str(payload.get("query", "")).strip()
        if not query:
            raise AstrBotError.invalid_input("kb.retrieve requires query")
        kb_names = await self._resolve_retrieve_kb_names(payload)
        if not kb_names:
            raise AstrBotError.invalid_input("kb.retrieve requires kb_ids or kb_names")
        result = await self._star_context.kb_manager.retrieve(
            query=query,
            kb_names=kb_names,
            top_k_fusion=self._optional_int(payload.get("top_k_fusion")) or 20,
            top_m_final=self._optional_int(payload.get("top_m_final")) or 5,
        )
        if result is None:
            return {"result": None}
        return {"result": dict(result)}

    async def _kb_document_upload(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        kb_id = str(payload.get("kb_id", "")).strip()
        kb_helper = await self._require_kb_helper(kb_id)
        raw_document = payload.get("document")
        if not isinstance(raw_document, dict):
            raise AstrBotError.invalid_input(
                "kb.document.upload requires document object"
            )

        text_value = raw_document.get("text")
        if isinstance(text_value, str) and text_value.strip():
            file_name = str(raw_document.get("file_name", "")).strip() or "document.txt"
            file_type = (
                str(raw_document.get("file_type", "")).strip()
                or Path(file_name).suffix.lstrip(".")
                or "txt"
            )
            document = await kb_helper.upload_document(
                file_name=file_name,
                file_content=None,
                file_type=file_type,
                chunk_size=self._optional_int(raw_document.get("chunk_size")) or 512,
                chunk_overlap=(
                    self._optional_int(raw_document.get("chunk_overlap")) or 50
                ),
                batch_size=self._optional_int(raw_document.get("batch_size")) or 32,
                tasks_limit=self._optional_int(raw_document.get("tasks_limit")) or 3,
                max_retries=self._optional_int(raw_document.get("max_retries")) or 3,
                pre_chunked_text=[text_value],
            )
            return {"document": self._serialize_kb_document(document)}

        url_value = raw_document.get("url")
        if isinstance(url_value, str) and url_value.strip():
            try:
                document = await self._star_context.kb_manager.upload_from_url(
                    kb_id=kb_id,
                    url=url_value.strip(),
                    chunk_size=self._optional_int(raw_document.get("chunk_size"))
                    or 512,
                    chunk_overlap=(
                        self._optional_int(raw_document.get("chunk_overlap")) or 50
                    ),
                    batch_size=self._optional_int(raw_document.get("batch_size")) or 32,
                    tasks_limit=self._optional_int(raw_document.get("tasks_limit"))
                    or 3,
                    max_retries=self._optional_int(raw_document.get("max_retries"))
                    or 3,
                    enable_cleaning=bool(raw_document.get("enable_cleaning", False)),
                    cleaning_provider_id=(
                        str(raw_document.get("cleaning_provider_id"))
                        if raw_document.get("cleaning_provider_id") is not None
                        else None
                    ),
                )
            except (OSError, ValueError) as exc:
                raise AstrBotError.invalid_input(str(exc)) from exc
            return {"document": self._serialize_kb_document(document)}

        file_token = str(raw_document.get("file_token", "")).strip()
        if not file_token:
            raise AstrBotError.invalid_input(
                "kb.document.upload requires file_token, url, or text"
            )
        try:
            file_path = await _get_runtime_file_token_service().handle_file(file_token)
        except KeyError as exc:
            raise AstrBotError.invalid_input(str(exc)) from exc
        path = Path(file_path)
        if not path.exists():
            raise AstrBotError.invalid_input(f"File does not exist: {file_path}")
        file_name = str(raw_document.get("file_name", "")).strip() or path.name
        file_type = str(
            raw_document.get("file_type", "")
        ).strip() or path.suffix.lstrip(".")
        if not file_type:
            raise AstrBotError.invalid_input(
                "kb.document.upload requires file_type when the file has no suffix"
            )
        file_content = await asyncio.to_thread(path.read_bytes)
        try:
            document = await kb_helper.upload_document(
                file_name=file_name,
                file_content=file_content,
                file_type=file_type,
                chunk_size=self._optional_int(raw_document.get("chunk_size")) or 512,
                chunk_overlap=(
                    self._optional_int(raw_document.get("chunk_overlap")) or 50
                ),
                batch_size=self._optional_int(raw_document.get("batch_size")) or 32,
                tasks_limit=self._optional_int(raw_document.get("tasks_limit")) or 3,
                max_retries=self._optional_int(raw_document.get("max_retries")) or 3,
            )
        except ValueError as exc:
            raise AstrBotError.invalid_input(str(exc)) from exc
        return {"document": self._serialize_kb_document(document)}

    async def _kb_document_list(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        kb_helper = await self._require_kb_helper(str(payload.get("kb_id", "")))
        documents = await kb_helper.list_documents(
            offset=self._optional_int(payload.get("offset")) or 0,
            limit=self._optional_int(payload.get("limit")) or 100,
        )
        return {
            "documents": [
                item
                for item in (
                    self._serialize_kb_document(document) for document in documents
                )
                if item is not None
            ]
        }

    async def _kb_document_get(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        kb_helper = await self._require_kb_helper(str(payload.get("kb_id", "")))
        document = await kb_helper.get_document(str(payload.get("doc_id", "")))
        return {"document": self._serialize_kb_document(document)}

    async def _kb_document_delete(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        kb_helper = await self._require_kb_helper(str(payload.get("kb_id", "")))
        doc_id = str(payload.get("doc_id", "")).strip()
        existing_document = await kb_helper.get_document(doc_id)
        if existing_document is None:
            return {"deleted": False}
        await kb_helper.delete_document(doc_id)
        return {"deleted": True}

    async def _kb_document_refresh(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        kb_helper = await self._require_kb_helper(str(payload.get("kb_id", "")))
        doc_id = str(payload.get("doc_id", "")).strip()
        document = await kb_helper.get_document(doc_id)
        if document is None:
            return {"document": None}
        try:
            await kb_helper.refresh_document(doc_id)
        except ValueError as exc:
            raise AstrBotError.invalid_input(str(exc)) from exc
        refreshed_document = await kb_helper.get_document(doc_id)
        return {"document": self._serialize_kb_document(refreshed_document)}
