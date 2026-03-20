from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

from ...protocol.descriptors import CapabilityDescriptor


class CapabilityRouterHost:
    memory_store: dict[str, dict[str, Any]]
    _memory_backends: dict[str, Any]
    _memory_index: dict[str, dict[str, Any]]
    _memory_dirty_keys: set[str]
    _memory_expires_at: dict[str, datetime | None]
    db_store: dict[str, Any]
    sent_messages: list[dict[str, Any]]
    event_actions: list[dict[str, Any]]
    http_api_store: list[dict[str, Any]]
    _event_streams: dict[str, dict[str, Any]]
    _plugins: dict[str, Any]
    _request_overlays: dict[str, dict[str, Any]]
    _provider_catalog: dict[str, list[dict[str, Any]]]
    _provider_configs: dict[str, dict[str, Any]]
    _active_provider_ids: dict[str, str | None]
    _provider_change_subscriptions: dict[str, asyncio.Queue[dict[str, Any]]]
    _system_data_root: Path
    _session_waiters: dict[str, set[str]]
    _session_plugin_configs: dict[str, dict[str, Any]]
    _session_service_configs: dict[str, dict[str, Any]]
    _db_watch_subscriptions: dict[str, tuple[str | None, asyncio.Queue[dict[str, Any]]]]
    _dynamic_command_routes: dict[str, list[dict[str, Any]]]
    _file_token_store: dict[str, str]
    _platform_instances: list[dict[str, Any]]
    _persona_store: dict[str, dict[str, Any]]
    _conversation_store: dict[str, dict[str, Any]]
    _session_current_conversation_ids: dict[str, str]
    _kb_store: dict[str, dict[str, Any]]

    def register(
        self,
        descriptor: CapabilityDescriptor,
        *,
        call_handler=None,
        stream_handler=None,
        finalize=None,
        exposed: bool = True,
    ) -> None:
        raise NotImplementedError

    def _emit_db_change(self, *, op: str, key: str, value: Any | None) -> None:
        raise NotImplementedError

    @staticmethod
    def _require_caller_plugin_id(capability_name: str) -> str:
        raise NotImplementedError

    @staticmethod
    def _validated_plugin_id(plugin_id: str, *, capability_name: str) -> str:
        raise NotImplementedError

    def _plugin_data_dir(self, plugin_id: str, *, capability_name: str) -> Path:
        raise NotImplementedError

    def register_dynamic_command_route(
        self,
        *,
        plugin_id: str,
        command_name: str,
        handler_full_name: str,
        desc: str = "",
        priority: int = 0,
        use_regex: bool = False,
    ) -> None:
        raise NotImplementedError

    def get_platform_instances(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def _register_agent_tool_capabilities(self) -> None:
        raise NotImplementedError

    def _provider_entry(
        self,
        payload: dict[str, Any],
        capability_name: str,
        expected_kind: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def _provider_embedding_get_embedding(
        self, request_id: str, payload: dict[str, Any], token
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def _provider_embedding_get_embeddings(
        self, request_id: str, payload: dict[str, Any], token
    ) -> dict[str, Any]:
        raise NotImplementedError
