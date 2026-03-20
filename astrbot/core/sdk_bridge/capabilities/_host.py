from __future__ import annotations

from collections.abc import Awaitable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:

    class CapabilityMixinHost:
        MEMORY_SCOPE: str
        _event_streams: dict[str, Any]
        _plugin_bridge: Any
        _star_context: Any
        _memory_backends_by_plugin: dict[str, Any]
        _memory_index_by_plugin: dict[str, dict[str, dict[str, Any]]]
        _memory_dirty_keys_by_plugin: dict[str, set[str]]
        _memory_expires_at_by_plugin: dict[str, dict[str, Any]]

        def register(
            self,
            descriptor: Any,
            *,
            call_handler: Any = None,
            stream_handler: Any = None,
            finalize: Any = None,
            exposed: bool = True,
        ) -> None: ...

        def _builtin_descriptor(
            self,
            name: str,
            description: str,
            *,
            supports_stream: bool = False,
            cancelable: bool = False,
        ) -> Any: ...

        def _resolve_plugin_id(self, request_id: str) -> str: ...

        def _resolve_dispatch_target(
            self,
            request_id: str,
            payload: dict[str, Any],
        ) -> tuple[str, str]: ...

        def _resolve_event_request_context(
            self,
            request_id: str,
            payload: dict[str, Any],
        ) -> Any: ...

        def _resolve_current_group_request_context(
            self,
            request_id: str,
            payload: dict[str, Any],
        ) -> Any: ...

        def _build_core_message_chain(
            self, chain_payload: list[dict[str, Any]]
        ) -> Any: ...

        def _serialize_group(self, group: Any) -> dict[str, Any] | None: ...

        def _require_reserved_plugin(
            self,
            request_id: str,
            capability_name: str,
        ) -> str: ...

        def _get_platform_inst_by_id(self, platform_id: str) -> Any | None: ...

        def _serialize_platform_snapshot(
            self, platform: Any
        ) -> dict[str, Any] | None: ...

        def _serialize_platform_stats(self, stats: Any) -> dict[str, Any] | None: ...

        def _normalize_session_scoped_config(
            self,
            raw_config: Any,
            session_id: str,
        ) -> dict[str, Any]: ...

        def _get_typed_provider(
            self,
            payload: dict[str, Any],
            capability_name: str,
            provider_label: str,
            expected_type: type[Any],
        ) -> Any: ...

        def _provider_embedding_get_embedding(
            self,
            request_id: str,
            payload: dict[str, Any],
            token: Any,
        ) -> Awaitable[dict[str, Any]]: ...

        def _provider_embedding_get_embeddings(
            self,
            request_id: str,
            payload: dict[str, Any],
            token: Any,
        ) -> Awaitable[dict[str, Any]]: ...

        def _reserved_plugin_names(self) -> set[str]: ...

        def _serialize_persona(self, persona: Any) -> dict[str, Any] | None: ...

        def _normalize_persona_dialogs(self, value: Any) -> list[str]: ...

        def _serialize_conversation(
            self, conversation: Any
        ) -> dict[str, Any] | None: ...

        def _normalize_history_items(self, value: Any) -> list[dict[str, Any]]: ...

        def _optional_int(self, value: Any) -> int | None: ...

        def _serialize_kb(self, kb_helper_or_record: Any) -> dict[str, Any] | None: ...

        def _serialize_kb_document(self, document: Any) -> dict[str, Any] | None: ...

else:

    class CapabilityMixinHost:
        # Keep the runtime host empty so it cannot shadow CapabilityRouter methods in
        # CoreCapabilityBridge's MRO. The typed method declarations above are only for
        # static analysis.
        pass
