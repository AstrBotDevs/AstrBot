"""Adapter exposing the built-in knowledge base through the public contract."""

from typing import TYPE_CHECKING

from astrbot.api.knowledge_base import (
    BaseKnowledgeBaseBackend,
    KnowledgeBaseHit,
    KnowledgeBaseInfo,
    KnowledgeBaseQuery,
    KnowledgeBaseRef,
    KnowledgeBaseResponse,
)

if TYPE_CHECKING:
    from .kb_mgr import KnowledgeBaseManager


class BuiltinKnowledgeBaseBackend(BaseKnowledgeBaseBackend):
    """Adapt the existing AstrBot knowledge base implementation."""

    def __init__(self, manager: "KnowledgeBaseManager") -> None:
        """Initialize the built-in backend adapter.

        Args:
            manager: Existing knowledge base manager.
        """
        self.manager = manager

    @property
    def backend_id(self) -> str:
        """Return the reserved built-in backend identifier."""
        return "builtin"

    @property
    def display_name(self) -> str:
        """Return the built-in backend display name."""
        return "AstrBot Built-in Knowledge Base"

    async def list_knowledge_bases(
        self,
        *,
        umo: str | None = None,
    ) -> list[KnowledgeBaseInfo]:
        """List built-in knowledge bases.

        Args:
            umo: Optional unified message origin. The built-in backend does not
                currently apply session-specific access filtering.

        Returns:
            Built-in knowledge base descriptors.
        """
        records = await self.manager.list_kbs()
        return [
            KnowledgeBaseInfo(
                ref=KnowledgeBaseRef(
                    backend_id=self.backend_id,
                    knowledge_base_id=record.kb_id,
                ),
                name=record.kb_name,
                description=record.description,
                metadata={
                    "emoji": record.emoji,
                    "doc_count": record.doc_count,
                    "chunk_count": record.chunk_count,
                },
            )
            for record in records
        ]

    async def retrieve(
        self,
        knowledge_base_ids: list[str],
        request: KnowledgeBaseQuery,
    ) -> KnowledgeBaseResponse:
        """Retrieve from built-in knowledge bases.

        Args:
            knowledge_base_ids: Built-in knowledge base identifiers.
            request: Standardized retrieval request.

        Returns:
            Standardized built-in retrieval results and warnings.
        """
        kb_names = []
        warnings = []
        for kb_id in knowledge_base_ids:
            helper = await self.manager.get_kb(kb_id)
            if helper is None:
                warnings.append(f"Built-in knowledge base '{kb_id}' was not found.")
                continue
            kb_names.append(helper.kb.kb_name)

        if not kb_names:
            return KnowledgeBaseResponse(hits=[], warnings=warnings)

        result = await self.manager.retrieve(
            query=request.query,
            kb_names=kb_names,
            top_m_final=request.top_k,
        )
        if not result:
            return KnowledgeBaseResponse(hits=[], warnings=warnings)

        hits = []
        for rank, item in enumerate(result.get("results", []), start=1):
            hits.append(
                KnowledgeBaseHit(
                    content=item["content"],
                    source=item.get("doc_name")
                    or item.get("kb_name")
                    or self.display_name,
                    rank=rank,
                    score=item.get("score"),
                    document_id=item.get("doc_id"),
                    chunk_id=item.get("chunk_id"),
                    metadata={
                        "backend_id": self.backend_id,
                        "knowledge_base_id": item.get("kb_id"),
                        "knowledge_base_name": item.get("kb_name"),
                        "chunk_index": item.get("chunk_index", 0),
                        "char_count": item.get("char_count", 0),
                    },
                )
            )

        return KnowledgeBaseResponse(hits=hits, warnings=warnings)
