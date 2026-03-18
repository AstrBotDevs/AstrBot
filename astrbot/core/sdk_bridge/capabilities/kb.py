from __future__ import annotations

from astrbot_sdk.errors import AstrBotError

from ._host import CapabilityMixinHost


class KnowledgeBaseCapabilityMixin(CapabilityMixinHost):
    def _register_kb_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("kb.get", "Get knowledge base"),
            call_handler=self._kb_get,
        )
        self.register(
            self._builtin_descriptor("kb.create", "Create knowledge base"),
            call_handler=self._kb_create,
        )
        self.register(
            self._builtin_descriptor("kb.delete", "Delete knowledge base"),
            call_handler=self._kb_delete,
        )

    async def _kb_get(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        kb_helper = self._star_context.kb_manager.get_kb(str(payload.get("kb_id", "")))
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
            kb_helper = self._star_context.kb_manager.create_kb(
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

    async def _kb_delete(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        deleted = self._star_context.kb_manager.delete_kb(str(payload.get("kb_id", "")))
        return {"deleted": bool(deleted)}
