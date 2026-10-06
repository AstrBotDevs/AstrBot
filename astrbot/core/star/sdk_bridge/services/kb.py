from __future__ import annotations

from typing import TYPE_CHECKING, Any

from astrbot_sdk.errors import InvalidRequest, NotFound

if TYPE_CHECKING:
    from astrbot.core.star.context import Context


def _serialize_kb(kb: Any) -> dict[str, Any]:
    """Serialize one KnowledgeBase row to a JSON-safe dict."""
    return {
        "kb_id": kb.kb_id,
        "kb_name": kb.kb_name,
        "description": kb.description,
        "emoji": kb.emoji,
        "embedding_provider_id": kb.embedding_provider_id,
        "rerank_provider_id": kb.rerank_provider_id,
        "chunk_size": kb.chunk_size,
        "chunk_overlap": kb.chunk_overlap,
        "top_k_dense": kb.top_k_dense,
        "top_k_sparse": kb.top_k_sparse,
        "top_m_final": kb.top_m_final,
        "doc_count": kb.doc_count,
        "chunk_count": kb.chunk_count,
    }


class KnowledgeBaseService:
    """Knowledge-base access for isolated legacy plugins.

    Method calls on the legacy ``context.kb_manager`` are forwarded here;
    retrieval results are already JSON-safe on the Host. Only granted to
    legacy plugins; new SDK plugins cannot declare it.
    """

    capability_id = "kb.manage"

    def __init__(self, context: Context) -> None:
        """Initialize the service.

        Args:
            context: AstrBot star context used for KB manager access.
        """
        self._context = context

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Serve one kb operation."""
        manager = self._context.kb_manager
        if operation == "list_kbs":
            return {"kbs": [_serialize_kb(kb) for kb in await manager.list_kbs()]}
        if operation == "get_kb_by_name":
            helper = await manager.get_kb_by_name(str(payload.get("kb_name") or ""))
            return {"kb": _serialize_kb(helper.kb) if helper else None}
        if operation == "get_kb":
            helper = await manager.get_kb(str(payload.get("kb_id") or ""))
            return {"kb": _serialize_kb(helper.kb) if helper else None}
        if operation == "create_kb":
            return {"kb": _serialize_kb(await self._create_kb(payload))}
        if operation == "delete_kb":
            kb_id = str(payload.get("kb_id") or "")
            if not kb_id:
                raise InvalidRequest("delete_kb requires kb_id")
            return {"deleted": await manager.delete_kb(kb_id)}
        if operation == "retrieve":
            return {"result": await self._retrieve(payload)}
        raise NotFound(f"unknown kb operation: {operation}")

    async def _create_kb(self, payload: dict[str, Any]) -> Any:
        kb_name = str(payload.get("kb_name") or "")
        embedding_provider_id = payload.get("embedding_provider_id")
        if not kb_name or not embedding_provider_id:
            raise InvalidRequest(
                "create_kb requires kb_name and embedding_provider_id",
            )
        optional = {
            key: payload[key]
            for key in (
                "description",
                "emoji",
                "rerank_provider_id",
                "chunk_size",
                "chunk_overlap",
                "top_k_dense",
                "top_k_sparse",
                "top_m_final",
            )
            if payload.get(key) is not None
        }
        helper = await self._context.kb_manager.create_kb(
            kb_name,
            embedding_provider_id=str(embedding_provider_id),
            **optional,
        )
        return helper.kb

    async def _retrieve(self, payload: dict[str, Any]) -> Any:
        query = str(payload.get("query") or "")
        kb_names = payload.get("kb_names")
        if not query or not isinstance(kb_names, list):
            raise InvalidRequest("retrieve requires query and a kb_names list")
        return await self._context.kb_manager.retrieve(
            query=query,
            kb_names=[str(name) for name in kb_names],
            top_k_fusion=int(payload.get("top_k_fusion") or 20),
            top_m_final=int(payload.get("top_m_final") or 5),
        )
