"""Legacy kb_manager facade forwarding to the Host knowledge-base service.

Method calls on the legacy ``context.kb_manager`` cross the kb capability;
returned knowledge bases are plain namespaces mirroring the core model
fields. Document-level helper operations are not RPC-able yet and raise a
loud isolation error.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from .errors import IsolationUnsupportedError


class KbHelperFacade:
    """Legacy KBHelper facade exposing the knowledge-base record."""

    def __init__(self, kb: dict[str, Any]) -> None:
        """Build the facade from a serialized knowledge-base dict."""
        self.kb = SimpleNamespace(**kb)

    @property
    def kb_id(self) -> str:
        """Return the knowledge-base ID."""
        return self.kb.kb_id

    def _unsupported(self, method: str) -> None:
        raise IsolationUnsupportedError(
            f"kb helper {method} is unavailable in isolated legacy mode; "
            "use context.kb_manager operations instead."
        )

    async def upload_document(self, *args: Any, **kwargs: Any) -> Any:
        """Document uploads are not RPC-able yet."""
        self._unsupported("upload_document")

    async def list_documents(self, *args: Any, **kwargs: Any) -> Any:
        """Document listing is not RPC-able yet."""
        self._unsupported("list_documents")

    async def get_document(self, *args: Any, **kwargs: Any) -> Any:
        """Document reads are not RPC-able yet."""
        self._unsupported("get_document")

    async def delete_document(self, *args: Any, **kwargs: Any) -> Any:
        """Document deletes are not RPC-able yet."""
        self._unsupported("delete_document")


class KbManagerFacade:
    """Legacy kb_manager facade over the kb capability."""

    def __init__(self, facade_context: Any) -> None:
        """Initialize the facade.

        Args:
            facade_context: Legacy Context facade used to reach the Host.
        """
        self._facade_context = facade_context

    async def _call(self, operation: str, payload: dict[str, Any]) -> Any:
        return await self._facade_context._ctx._invoke_capability(
            "kb.manage",
            operation,
            payload,
        )

    async def list_kbs(self) -> list:
        """List all knowledge bases as attribute namespaces."""
        result = await self._call("list_kbs", {})
        return [SimpleNamespace(**item) for item in (result or {}).get("kbs") or []]

    async def get_kb_by_name(self, kb_name: str) -> KbHelperFacade | None:
        """Return the helper facade for one knowledge base, or None."""
        result = await self._call("get_kb_by_name", {"kb_name": kb_name})
        kb = (result or {}).get("kb")
        return KbHelperFacade(kb) if kb else None

    async def get_kb(self, kb_id: str) -> KbHelperFacade | None:
        """Return the helper facade for one knowledge-base ID, or None."""
        result = await self._call("get_kb", {"kb_id": kb_id})
        kb = (result or {}).get("kb")
        return KbHelperFacade(kb) if kb else None

    async def create_kb(
        self,
        kb_name: str,
        *,
        embedding_provider_id: str,
        **optional: Any,
    ) -> KbHelperFacade:
        """Create one knowledge base on the Host."""
        result = await self._call(
            "create_kb",
            {
                "kb_name": kb_name,
                "embedding_provider_id": embedding_provider_id,
                **optional,
            },
        )
        return KbHelperFacade(dict((result or {}).get("kb") or {}))

    async def delete_kb(self, kb_id: str) -> bool:
        """Delete one knowledge base on the Host."""
        result = await self._call("delete_kb", {"kb_id": kb_id})
        return bool((result or {}).get("deleted"))

    async def retrieve(
        self,
        query: str,
        kb_names: list[str],
        top_k_fusion: int = 20,
        top_m_final: int = 5,
    ) -> Any:
        """Run one retrieval query across the named knowledge bases."""
        result = await self._call(
            "retrieve",
            {
                "query": query,
                "kb_names": list(kb_names),
                "top_k_fusion": top_k_fusion,
                "top_m_final": top_m_final,
            },
        )
        return (result or {}).get("result")

    async def update_kb(self, *args: Any, **kwargs: Any) -> Any:
        """KB metadata updates are not RPC-able yet."""
        raise IsolationUnsupportedError(
            "kb_manager.update_kb is unavailable in isolated legacy mode."
        )
