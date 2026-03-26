from __future__ import annotations

import math
import uuid
from pathlib import Path
from typing import Any

from ....errors import AstrBotError
from ..bridge_base import CapabilityRouterBridgeBase


def _term_set(text: str) -> set[str]:
    normalized = " ".join(str(text).strip().casefold().split())
    compact = normalized.replace(" ", "")
    if not normalized:
        return set()
    terms = {item for item in normalized.split(" ") if item}
    if compact:
        terms.add(compact)
        if len(compact) > 1:
            terms.update(
                compact[index : index + 2] for index in range(len(compact) - 1)
            )
    return terms


class KnowledgeBaseCapabilityMixin(CapabilityRouterBridgeBase):
    def _kb_documents(self, kb_id: str) -> dict[str, dict[str, Any]]:
        return self._kb_document_store.setdefault(kb_id, {})

    def _refresh_mock_kb_stats(self, kb_id: str) -> None:
        kb = self._kb_store.get(kb_id)
        if not isinstance(kb, dict):
            return
        documents = self._kb_documents(kb_id)
        kb["doc_count"] = len(documents)
        kb["chunk_count"] = sum(
            int(document.get("chunk_count", 0) or 0) for document in documents.values()
        )
        kb["updated_at"] = self._now_iso()

    def _resolve_mock_kb_ids(self, payload: dict[str, Any]) -> list[str]:
        kb_ids = [
            str(item).strip() for item in payload.get("kb_ids", []) if str(item).strip()
        ]
        if kb_ids:
            return [kb_id for kb_id in kb_ids if kb_id in self._kb_store]

        kb_names = [
            str(item).strip()
            for item in payload.get("kb_names", [])
            if str(item).strip()
        ]
        if not kb_names:
            return []
        name_set = set(kb_names)
        return [
            kb_id
            for kb_id, kb in self._kb_store.items()
            if str(kb.get("kb_name", "")).strip() in name_set
        ]

    @staticmethod
    def _score_mock_document(query: str, content: str) -> float:
        query_terms = _term_set(query)
        content_terms = _term_set(content)
        if not query_terms or not content_terms:
            return 0.0
        overlap = len(query_terms & content_terms)
        if overlap <= 0:
            return 0.0
        score = overlap / len(query_terms)
        if query.strip().casefold() in str(content).casefold():
            score += 0.25
        return min(score, 1.0)

    @staticmethod
    def _build_mock_context_text(results: list[dict[str, Any]]) -> str:
        lines = ["以下是相关的知识库内容,请参考这些信息回答用户的问题:\n"]
        for index, item in enumerate(results, start=1):
            lines.append(f"【知识 {index}】")
            lines.append(f"来源: {item['kb_name']} / {item['doc_name']}")
            lines.append(f"内容: {item['content']}")
            lines.append(f"相关度: {float(item['score']):.2f}")
            lines.append("")
        return "\n".join(lines)

    async def _kb_list(
        self,
        _request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        return {
            "kbs": [
                dict(record)
                for record in sorted(
                    self._kb_store.values(),
                    key=lambda item: str(item.get("created_at", "")),
                )
            ]
        }

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
        self._kb_document_store[kb_id] = {}
        return {"kb": dict(record)}

    async def _kb_update(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        kb_id = str(payload.get("kb_id", "")).strip()
        raw_kb = payload.get("kb")
        if not isinstance(raw_kb, dict):
            raise AstrBotError.invalid_input("kb.update requires kb object")
        record = self._kb_store.get(kb_id)
        if not isinstance(record, dict):
            return {"kb": None}

        for field_name in (
            "kb_name",
            "description",
            "emoji",
            "embedding_provider_id",
            "rerank_provider_id",
        ):
            if field_name in raw_kb:
                value = raw_kb.get(field_name)
                record[field_name] = str(value) if value is not None else None
        for field_name in (
            "chunk_size",
            "chunk_overlap",
            "top_k_dense",
            "top_k_sparse",
            "top_m_final",
        ):
            if field_name in raw_kb:
                record[field_name] = self._optional_int(raw_kb.get(field_name))
        record["updated_at"] = self._now_iso()
        return {"kb": dict(record)}

    async def _kb_delete(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        kb_id = str(payload.get("kb_id", "")).strip()
        documents = self._kb_document_store.pop(kb_id, {})
        for document in documents.values():
            doc_id = str(document.get("doc_id", "")).strip()
            if doc_id:
                self._kb_document_content_store.pop(doc_id, None)
        deleted = self._kb_store.pop(kb_id, None) is not None
        return {"deleted": deleted}

    async def _kb_retrieve(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        query = str(payload.get("query", "")).strip()
        if not query:
            raise AstrBotError.invalid_input("kb.retrieve requires query")
        kb_ids = self._resolve_mock_kb_ids(payload)
        if not kb_ids:
            raise AstrBotError.invalid_input("kb.retrieve requires kb_ids or kb_names")

        top_m_final = self._optional_int(payload.get("top_m_final")) or 5
        results: list[dict[str, Any]] = []
        for kb_id in kb_ids:
            kb = self._kb_store.get(kb_id)
            if not isinstance(kb, dict):
                continue
            for document in self._kb_documents(kb_id).values():
                doc_id = str(document.get("doc_id", "")).strip()
                if not doc_id:
                    continue
                content = self._kb_document_content_store.get(doc_id, "")
                score = self._score_mock_document(query, content)
                if score <= 0:
                    continue
                results.append(
                    {
                        "chunk_id": f"{doc_id}:0",
                        "doc_id": doc_id,
                        "kb_id": kb_id,
                        "kb_name": str(kb.get("kb_name", "")),
                        "doc_name": str(document.get("doc_name", "")),
                        "chunk_index": 0,
                        "content": content,
                        "score": score,
                        "char_count": len(content),
                    }
                )
        results.sort(key=lambda item: float(item["score"]), reverse=True)
        results = results[:top_m_final]
        if not results:
            return {"result": None}
        return {
            "result": {
                "context_text": self._build_mock_context_text(results),
                "results": results,
            }
        }

    async def _kb_document_upload(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        kb_id = str(payload.get("kb_id", "")).strip()
        kb = self._kb_store.get(kb_id)
        if not isinstance(kb, dict):
            raise AstrBotError.invalid_input(f"Unknown knowledge base: {kb_id}")
        raw_document = payload.get("document")
        if not isinstance(raw_document, dict):
            raise AstrBotError.invalid_input(
                "kb.document.upload requires document object"
            )

        file_name = str(raw_document.get("file_name", "")).strip()
        file_type = str(raw_document.get("file_type", "")).strip()
        file_path = ""
        content_text = ""
        file_size = 0

        text_value = raw_document.get("text")
        url_value = raw_document.get("url")
        file_token = str(raw_document.get("file_token", "")).strip()

        if isinstance(text_value, str) and text_value.strip():
            content_text = text_value
            if not file_name:
                file_name = "document.txt"
            if not file_type:
                file_type = "txt"
            file_size = len(content_text.encode("utf-8"))
        elif isinstance(url_value, str) and url_value.strip():
            url_text = url_value.strip()
            content_text = f"Imported from {url_text}"
            if not file_name:
                file_name = (
                    Path(url_text.split("?", maxsplit=1)[0]).name or "document.url"
                )
            if not file_type:
                suffix = Path(file_name).suffix.lstrip(".")
                file_type = suffix or "url"
            file_path = url_text
            file_size = len(content_text.encode("utf-8"))
        elif file_token:
            file_path = self._file_token_store.pop(file_token, "")
            if not file_path:
                raise AstrBotError.invalid_input(f"Unknown file token: {file_token}")
            path = Path(file_path)
            if not path.exists():
                raise AstrBotError.invalid_input(f"File does not exist: {file_path}")
            raw_bytes = path.read_bytes()
            content_text = raw_bytes.decode("utf-8", errors="ignore")
            if not file_name:
                file_name = path.name
            if not file_type:
                file_type = path.suffix.lstrip(".")
            if not file_type:
                raise AstrBotError.invalid_input(
                    "kb.document.upload requires file_type when the file has no suffix"
                )
            file_size = len(raw_bytes)
        else:
            raise AstrBotError.invalid_input(
                "kb.document.upload requires file_token, url, or text"
            )

        chunk_size = self._optional_int(raw_document.get("chunk_size"))
        if chunk_size is None or chunk_size <= 0:
            chunk_size = self._optional_int(kb.get("chunk_size")) or 512
        chunk_count = max(1, math.ceil(max(len(content_text), 1) / chunk_size))
        doc_id = uuid.uuid4().hex
        now = self._now_iso()
        document = {
            "doc_id": doc_id,
            "kb_id": kb_id,
            "doc_name": file_name,
            "file_type": file_type,
            "file_size": file_size,
            "file_path": file_path,
            "chunk_count": chunk_count,
            "media_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        self._kb_documents(kb_id)[doc_id] = document
        self._kb_document_content_store[doc_id] = content_text
        self._refresh_mock_kb_stats(kb_id)
        return {"document": dict(document)}

    async def _kb_document_list(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        kb_id = str(payload.get("kb_id", "")).strip()
        offset = max(self._optional_int(payload.get("offset")) or 0, 0)
        limit = max(self._optional_int(payload.get("limit")) or 100, 0)
        documents = list(self._kb_documents(kb_id).values())
        documents.sort(key=lambda item: str(item.get("created_at", "")))
        return {
            "documents": [dict(item) for item in documents[offset : offset + limit]]
        }

    async def _kb_document_get(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        kb_id = str(payload.get("kb_id", "")).strip()
        doc_id = str(payload.get("doc_id", "")).strip()
        document = self._kb_documents(kb_id).get(doc_id)
        return {"document": dict(document) if isinstance(document, dict) else None}

    async def _kb_document_delete(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        kb_id = str(payload.get("kb_id", "")).strip()
        doc_id = str(payload.get("doc_id", "")).strip()
        deleted = self._kb_documents(kb_id).pop(doc_id, None) is not None
        if deleted:
            self._kb_document_content_store.pop(doc_id, None)
            self._refresh_mock_kb_stats(kb_id)
        return {"deleted": deleted}

    async def _kb_document_refresh(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        kb_id = str(payload.get("kb_id", "")).strip()
        doc_id = str(payload.get("doc_id", "")).strip()
        document = self._kb_documents(kb_id).get(doc_id)
        if not isinstance(document, dict):
            return {"document": None}
        kb = self._kb_store.get(kb_id, {})
        chunk_size = self._optional_int(kb.get("chunk_size")) or 512
        content_text = self._kb_document_content_store.get(doc_id, "")
        document["chunk_count"] = max(
            1, math.ceil(max(len(content_text), 1) / chunk_size)
        )
        document["updated_at"] = self._now_iso()
        self._refresh_mock_kb_stats(kb_id)
        return {"document": dict(document)}

    def _register_kb_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("kb.list", "列出知识库"),
            call_handler=self._kb_list,
        )
        self.register(
            self._builtin_descriptor("kb.get", "获取知识库"),
            call_handler=self._kb_get,
        )
        self.register(
            self._builtin_descriptor("kb.create", "创建知识库"),
            call_handler=self._kb_create,
        )
        self.register(
            self._builtin_descriptor("kb.update", "更新知识库"),
            call_handler=self._kb_update,
        )
        self.register(
            self._builtin_descriptor("kb.delete", "删除知识库"),
            call_handler=self._kb_delete,
        )
        self.register(
            self._builtin_descriptor("kb.retrieve", "检索知识库"),
            call_handler=self._kb_retrieve,
        )
        self.register(
            self._builtin_descriptor("kb.document.upload", "上传知识库文档"),
            call_handler=self._kb_document_upload,
        )
        self.register(
            self._builtin_descriptor("kb.document.list", "列出知识库文档"),
            call_handler=self._kb_document_list,
        )
        self.register(
            self._builtin_descriptor("kb.document.get", "获取知识库文档"),
            call_handler=self._kb_document_get,
        )
        self.register(
            self._builtin_descriptor("kb.document.delete", "删除知识库文档"),
            call_handler=self._kb_document_delete,
        )
        self.register(
            self._builtin_descriptor("kb.document.refresh", "刷新知识库文档"),
            call_handler=self._kb_document_refresh,
        )
