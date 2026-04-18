from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import signal
import subprocess
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.llm.agents import AgentSpec
from astrbot_sdk.llm.entities import LLMToolSpec
from astrbot_sdk.protocol.descriptors import (
    CommandTrigger,
    CompositeFilterSpec,
    EventTrigger,
    HandlerDescriptor,
    MessageTrigger,
    PlatformFilterSpec,
    ScheduleTrigger,
)
from astrbot_sdk.runtime._command_matching import command_root_name
from astrbot_sdk.runtime.loader import (
    PluginDiscoveryIssue,
    PluginEnvironmentManager,
    PluginSpec,
    discover_plugins,
    load_plugin_config,
    load_plugin_config_schema,
    save_plugin_config,
)
from astrbot_sdk.runtime.supervisor import WorkerSession

from astrbot.core import astrbot_config, logger
from astrbot.core.agent.mcp_client import MCPClient
from astrbot.core.command_compatibility import (
    CommandRegistration,
    CrossSystemCommandConflict,
    build_cross_system_conflicts,
    collect_legacy_command_registrations,
    collect_sdk_command_registrations,
    match_legacy_command_registrations,
)
from astrbot.core.message.message_event_result import MessageChain, MessageEventResult
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import LLMResponse as CoreLLMResponse
from astrbot.core.provider.entities import ProviderRequest as CoreProviderRequest
from astrbot.core.skills.skill_manager import (
    SkillManager,
)
from astrbot.core.utils.astrbot_path import (
    get_astrbot_data_path,
    get_astrbot_plugin_data_path,
)

from .capability_bridge import CoreCapabilityBridge
from .dispatch_engine import SdkDispatchEngine
from .event_payload import (
    InboundEventSnapshot,
)
from .lifecycle_manager import SdkPluginLifecycleManager
from .mcp_manager import SdkMcpManager
from .registry_manager import SdkRegistryManager
from .request_runtime import SdkRequestRuntime
from .runtime_store import (
    SdkDispatchResult,
    SdkDynamicCommandRoute,
    SdkHandlerRef,
    SdkHttpRoute,
    SdkPluginRecord,
    SdkRuntimeStore,
    _LocalMCPServerRuntime,
    _RequestContext,
    _RequestOverlayState,
)
from .trigger_converter import TriggerConverter, TriggerMatch

SDK_STATE_ENABLED = "enabled"
SDK_STATE_DISABLED = "disabled"
SDK_STATE_RELOADING = "reloading"
SDK_STATE_FAILED = "failed"
SDK_STATE_UNSUPPORTED_PARTIAL = "unsupported_partial"

SKIP_LEGACY_STOPPED = "legacy_stopped"
SKIP_LEGACY_REPLIED = "legacy_replied"
SKIP_SDK_RELOADING = "sdk_reloading"
SKIP_NO_MATCH = "no_match"
SKIP_WORKER_FAILED = "worker_failed"
OVERLAY_TIMEOUT_SECONDS = 300
SDK_SKILL_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
SUPPORTED_SYSTEM_EVENTS = {
    "astrbot_loaded",
    "platform_loaded",
    "after_message_sent",
    "waiting_llm_request",
    "agent_begin",
    "llm_request",
    "llm_response",
    "agent_done",
    "streaming_delta",
    "decorating_result",
    "calling_func_tool",
    "llm_tool_start",
    "llm_tool_end",
    "plugin_error",
    "plugin_loaded",
    "plugin_unloaded",
}
COMMAND_OVERRIDE_WARNING_TYPE = "legacy_sdk_command_override"


class SdkPluginBridge:
    SDK_STATE_ENABLED = SDK_STATE_ENABLED
    SDK_STATE_DISABLED = SDK_STATE_DISABLED
    SDK_STATE_RELOADING = SDK_STATE_RELOADING
    SDK_STATE_FAILED = SDK_STATE_FAILED
    SDK_STATE_UNSUPPORTED_PARTIAL = SDK_STATE_UNSUPPORTED_PARTIAL
    SKIP_LEGACY_STOPPED = SKIP_LEGACY_STOPPED
    SKIP_LEGACY_REPLIED = SKIP_LEGACY_REPLIED
    SKIP_SDK_RELOADING = SKIP_SDK_RELOADING
    SKIP_NO_MATCH = SKIP_NO_MATCH
    SKIP_WORKER_FAILED = SKIP_WORKER_FAILED
    COMMAND_OVERRIDE_WARNING_TYPE = COMMAND_OVERRIDE_WARNING_TYPE
    SDK_SKILL_NAME_RE = SDK_SKILL_NAME_RE

    def __init__(self, star_context) -> None:
        self.star_context = star_context
        self.logger = logger
        self.plugins_dir = Path(get_astrbot_data_path()) / "sdk_plugins"
        self.state_path = Path(get_astrbot_data_path()) / "sdk_plugins_state.json"
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self._started = False
        self._stopping = False
        self._state_overrides = self._load_state_overrides()
        self.env_manager = PluginEnvironmentManager(Path(__file__).resolve().parents[3])
        self._store = SdkRuntimeStore()
        self.capability_bridge = CoreCapabilityBridge(
            star_context=star_context,
            plugin_bridge=self,
        )
        self._records = self._store.records
        self._request_contexts = self._store.request_contexts
        self._request_id_to_token = self._store.request_id_to_token
        self._request_plugin_ids = self._store.request_plugin_ids
        self._request_overlays = self._store.request_overlays
        self._plugin_requests = self._store.plugin_requests
        self._http_routes = self._store.http_routes
        self._session_waiters = self._store.session_waiters
        self._schedule_job_ids = self._store.schedule_job_ids
        self._discovery_issues = self._store.discovery_issues
        self._temporary_mcp_sessions = self._store.temporary_mcp_sessions
        self.request_runtime = SdkRequestRuntime(
            bridge=self,
            store=self._store,
            overlay_timeout_seconds=OVERLAY_TIMEOUT_SECONDS,
        )
        self.dispatch_engine = SdkDispatchEngine(bridge=self)
        self.lifecycle = SdkPluginLifecycleManager(bridge=self)
        self.mcp = SdkMcpManager(bridge=self)
        self.registry = SdkRegistryManager(bridge=self)

    async def start(self) -> None:
        await self.lifecycle.start()

    async def stop(self) -> None:
        await self.lifecycle.stop()

    async def reload_all(self, *, reset_restart_budget: bool = False) -> None:
        await self.lifecycle.reload_all(reset_restart_budget=reset_restart_budget)

    async def reload_plugin(self, plugin_id: str) -> None:
        await self.lifecycle.reload_plugin(plugin_id)

    async def turn_off_plugin(self, plugin_id: str) -> None:
        await self.lifecycle.turn_off_plugin(plugin_id)

    async def turn_on_plugin(self, plugin_id: str) -> None:
        await self.lifecycle.turn_on_plugin(plugin_id)

    def list_plugins(self) -> list[dict[str, Any]]:
        return self.registry.list_plugins()

    def get_plugin_metadata(self, plugin_id: str) -> dict[str, Any] | None:
        return self.registry.get_plugin_metadata(plugin_id)

    def list_plugin_metadata(self) -> list[dict[str, Any]]:
        return self.registry.list_plugin_metadata()

    def get_plugin_config(self, plugin_id: str) -> dict[str, Any] | None:
        record = self._records.get(plugin_id)
        if record is None:
            return None
        return dict(record.config)

    def get_plugin_config_schema(self, plugin_id: str) -> dict[str, Any] | None:
        record = self._records.get(plugin_id)
        if record is None:
            return None
        return dict(record.config_schema)

    def save_plugin_config(
        self,
        plugin_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        record = self._records.get(plugin_id)
        if record is None:
            raise ValueError(f"SDK plugin not found: {plugin_id}")
        normalized = save_plugin_config(
            record.plugin,
            payload,
            schema=record.config_schema,
        )
        record.config = dict(normalized)
        return dict(record.config)

    def get_registered_llm_tools(self, plugin_id: str) -> list[LLMToolSpec]:
        record = self._records.get(plugin_id)
        if record is None:
            return []
        return [item.model_copy(deep=True) for item in record.llm_tools.values()]

    def get_active_llm_tools(self, plugin_id: str) -> list[LLMToolSpec]:
        record = self._records.get(plugin_id)
        if record is None:
            return []
        return [
            item.model_copy(deep=True)
            for name, item in record.llm_tools.items()
            if name in record.active_llm_tools
        ]

    def get_llm_tool(self, plugin_id: str, name: str) -> LLMToolSpec | None:
        record = self._records.get(plugin_id)
        if record is None:
            return None
        spec = record.llm_tools.get(name)
        if spec is None:
            return None
        return spec.model_copy(deep=True)

    def add_llm_tools(self, plugin_id: str, tools: list[LLMToolSpec]) -> list[str]:
        record = self._records.get(plugin_id)
        if record is None:
            return []
        names: list[str] = []
        for spec in tools:
            record.llm_tools[spec.name] = spec.model_copy(deep=True)
            if spec.active:
                record.active_llm_tools.add(spec.name)
            else:
                record.active_llm_tools.discard(spec.name)
            names.append(spec.name)
        return names

    def remove_llm_tool(self, plugin_id: str, name: str) -> bool:
        record = self._records.get(plugin_id)
        if record is None:
            return False
        removed = record.llm_tools.pop(name, None) is not None
        record.active_llm_tools.discard(name)
        return removed

    def activate_llm_tool(self, plugin_id: str, name: str) -> bool:
        record = self._records.get(plugin_id)
        if record is None:
            return False
        spec = record.llm_tools.get(name)
        if spec is None:
            return False
        spec.active = True
        record.active_llm_tools.add(name)
        return True

    def deactivate_llm_tool(self, plugin_id: str, name: str) -> bool:
        record = self._records.get(plugin_id)
        if record is None:
            return False
        spec = record.llm_tools.get(name)
        if spec is None:
            return False
        spec.active = False
        record.active_llm_tools.discard(name)
        return True

    def _local_mcp_record(
        self, plugin_id: str, name: str
    ) -> _LocalMCPServerRuntime | None:
        record = self._records.get(plugin_id)
        if record is None:
            return None
        return record.local_mcp_servers.get(name)

    @staticmethod
    def _serialize_local_mcp_server(
        runtime: _LocalMCPServerRuntime,
    ) -> dict[str, Any]:
        errlogs = list(runtime.errlogs)
        if runtime.client is not None:
            errlogs.extend(str(item) for item in runtime.client.server_errlogs)
        return {
            "name": runtime.name,
            "scope": "local",
            "active": runtime.active,
            "running": runtime.running,
            "config": dict(runtime.config),
            "tools": list(runtime.tools),
            "errlogs": errlogs,
            "last_error": runtime.last_error,
        }

    def get_local_mcp_server(
        self,
        plugin_id: str,
        name: str,
    ) -> dict[str, Any] | None:
        return self.mcp.get_local_mcp_server(plugin_id, name)

    def list_local_mcp_servers(self, plugin_id: str) -> list[dict[str, Any]]:
        return self.mcp.list_local_mcp_servers(plugin_id)

    def get_request_tool_specs(self, plugin_id: str) -> list[LLMToolSpec]:
        record = self._records.get(plugin_id)
        if record is None:
            return []
        specs: dict[str, LLMToolSpec] = {
            item.name: item.model_copy(deep=True)
            for name, item in record.llm_tools.items()
            if name in record.active_llm_tools
        }
        for runtime in record.local_mcp_servers.values():
            if not runtime.active or not runtime.running:
                continue
            for spec in runtime.tool_specs:
                specs.setdefault(spec.name, spec.model_copy(deep=True))
        return list(specs.values())

    def get_registered_agents(self, plugin_id: str) -> list[AgentSpec]:
        record = self._records.get(plugin_id)
        if record is None:
            return []
        return [item.model_copy(deep=True) for item in record.agents.values()]

    def get_registered_agent(self, plugin_id: str, name: str) -> AgentSpec | None:
        record = self._records.get(plugin_id)
        if record is None:
            return None
        spec = record.agents.get(name)
        if spec is None:
            return None
        return spec.model_copy(deep=True)

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
        record = self._records.get(plugin_id)
        if record is None:
            raise AstrBotError.invalid_input(f"Unknown SDK plugin: {plugin_id}")
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise AstrBotError.invalid_input("priority must be an integer")
        command_text = str(command_name).strip()
        if not command_text:
            raise AstrBotError.invalid_input("command_name must not be empty")
        handler_text = str(handler_full_name).strip()
        if not handler_text:
            raise AstrBotError.invalid_input("handler_full_name must not be empty")
        if not handler_text.startswith(f"{plugin_id}:"):
            raise AstrBotError.invalid_input(
                "handler_full_name must belong to the caller plugin"
            )
        if self._find_handler_ref(record, handler_text) is None:
            raise AstrBotError.invalid_input(
                f"Unknown handler_full_name for plugin '{plugin_id}': {handler_text}"
            )
        existing_order = next(
            (
                route.declaration_order
                for route in record.dynamic_command_routes
                if route.command_name == command_text
                and route.use_regex is bool(use_regex)
            ),
            len(record.dynamic_command_routes),
        )
        updated = [
            route
            for route in record.dynamic_command_routes
            if not (
                route.command_name == command_text
                and route.use_regex is bool(use_regex)
            )
        ]
        updated.append(
            SdkDynamicCommandRoute(
                command_name=command_text,
                handler_full_name=handler_text,
                desc=str(desc),
                priority=priority,
                use_regex=bool(use_regex),
                declaration_order=existing_order,
            )
        )
        updated.sort(key=lambda item: item.declaration_order)
        record.dynamic_command_routes = updated

    def register_skill(
        self,
        *,
        plugin_id: str,
        name: str,
        path: str,
        description: str = "",
    ) -> dict[str, str]:
        return self.registry.register_skill(
            plugin_id=plugin_id,
            name=name,
            path=path,
            description=description,
        )

    def unregister_skill(self, *, plugin_id: str, name: str) -> bool:
        return self.registry.unregister_skill(plugin_id=plugin_id, name=name)

    def list_registered_skills(self, plugin_id: str) -> list[dict[str, str]]:
        return self.registry.list_registered_skills(plugin_id)

    def _publish_plugin_skills(self, plugin_id: str) -> None:
        self.registry.publish_plugin_skills_impl(plugin_id)

    async def _clear_plugin_skills(
        self,
        *,
        plugin_id: str,
        record: SdkPluginRecord | Any | None,
        reason: str,
    ) -> None:
        await self.registry.clear_plugin_skills(
            plugin_id=plugin_id,
            record=record,
            reason=reason,
        )

    def register_http_api(
        self,
        *,
        plugin_id: str,
        route: str,
        methods: list[str],
        handler_capability: str,
        description: str,
    ) -> None:
        self.registry.register_http_api(
            plugin_id=plugin_id,
            route=route,
            methods=methods,
            handler_capability=handler_capability,
            description=description,
        )

    def unregister_http_api(
        self,
        *,
        plugin_id: str,
        route: str,
        methods: list[str],
    ) -> None:
        self.registry.unregister_http_api(
            plugin_id=plugin_id,
            route=route,
            methods=methods,
        )

    def list_http_apis(self, plugin_id: str) -> list[dict[str, Any]]:
        return self.registry.list_http_apis(plugin_id)

    def _public_http_path(self, route: str) -> str:
        normalized_route = self._normalize_http_route(route)
        return f"/api/plug{normalized_route}"

    def _public_page_path(self, route: str) -> str:
        normalized_route = self._normalize_http_route(route)
        return f"/plug{normalized_route}"

    @staticmethod
    def _parse_env_bool(value: str | None, default: bool) -> bool:
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}

    def _dashboard_public_base_url(self) -> str:
        return self.registry.dashboard_public_base_url()

    def _public_http_url(self, route: str) -> str:
        return f"{self._dashboard_public_base_url()}{self._public_http_path(route)}"

    def _public_page_url(self, route: str) -> str:
        return f"{self._dashboard_public_base_url()}{self._public_page_path(route)}"

    def _plugin_entry_route(self, plugin_id: str) -> str | None:
        plugin_root = f"/{plugin_id}"
        for entry in self._http_routes.get(plugin_id, []):
            if entry.route == plugin_root:
                return entry.route
        for entry in self._http_routes.get(plugin_id, []):
            if "/api/" not in entry.route:
                return entry.route
        return None

    async def dispatch_http_request(
        self,
        route: str,
        method: str,
    ) -> dict[str, Any] | None:
        return await self.registry.dispatch_http_request(route, method)

    def register_session_waiter(self, *, plugin_id: str, session_key: str) -> None:
        if not session_key:
            raise AstrBotError.invalid_input(
                "session waiter registration requires session_key"
            )
        self._session_waiters.setdefault(plugin_id, set()).add(session_key)

    def unregister_session_waiter(self, *, plugin_id: str, session_key: str) -> None:
        plugin_waiters = self._session_waiters.get(plugin_id)
        if plugin_waiters is None:
            return
        plugin_waiters.discard(session_key)
        if not plugin_waiters:
            self._session_waiters.pop(plugin_id, None)

    async def dispatch_message(self, event: AstrMessageEvent) -> SdkDispatchResult:
        return await self.dispatch_engine.dispatch_message(event)

    def resolve_request_plugin_id(self, request_id: str) -> str:
        return self.request_runtime.resolve_request_plugin_id(request_id)

    def resolve_request_session(self, request_id: str) -> _RequestContext | None:
        return self.request_runtime.resolve_request_session(request_id)

    def get_request_context_by_token(
        self, dispatch_token: str
    ) -> _RequestContext | None:
        return self.request_runtime.get_request_context_by_token(dispatch_token)

    def _bind_dispatch_token(
        self, event: AstrMessageEvent, dispatch_token: str
    ) -> None:
        self.request_runtime.bind_dispatch_token(event, dispatch_token)

    def _get_dispatch_token(self, event: AstrMessageEvent) -> str | None:
        return self.request_runtime.get_dispatch_token(event)

    def _schedule_overlay_cleanup(
        self, dispatch_token: str
    ) -> asyncio.Task[None] | None:
        return self.request_runtime.schedule_overlay_cleanup(dispatch_token)

    def _ensure_request_overlay(
        self,
        dispatch_token: str,
        *,
        should_call_llm: bool,
    ) -> _RequestOverlayState:
        return self.request_runtime.ensure_request_overlay(
            dispatch_token,
            should_call_llm=should_call_llm,
        )

    def _track_request_scope(
        self,
        *,
        dispatch_token: str,
        request_id: str,
        plugin_id: str,
    ) -> None:
        self.request_runtime.track_request_scope(
            dispatch_token=dispatch_token,
            request_id=request_id,
            plugin_id=plugin_id,
        )

    def _close_request_overlay(self, dispatch_token: str) -> None:
        self.request_runtime.close_request_overlay(dispatch_token)

    def close_request_overlay_for_event(self, event: AstrMessageEvent) -> None:
        self.request_runtime.close_request_overlay_for_event(event)

    def get_request_overlay_by_token(
        self, dispatch_token: str
    ) -> _RequestOverlayState | None:
        return self.request_runtime.get_request_overlay_by_token(dispatch_token)

    def get_request_overlay_by_request_id(
        self, request_id: str
    ) -> _RequestOverlayState | None:
        return self.request_runtime.get_request_overlay_by_request_id(request_id)

    def request_llm_for_request(self, request_id: str) -> bool:
        return self.request_runtime.request_llm_for_request(request_id)

    def get_effective_should_call_llm(self, event: AstrMessageEvent) -> bool:
        return self.request_runtime.get_effective_should_call_llm(event)

    def get_should_call_llm_for_request(self, request_id: str) -> bool | None:
        return self.request_runtime.get_should_call_llm_for_request(request_id)

    def _set_overlay_stop_state(
        self,
        overlay: _RequestOverlayState,
        *,
        stopped: bool,
    ) -> None:
        self.request_runtime.set_overlay_stop_state(overlay, stopped=stopped)

    def _set_result_from_object(
        self,
        overlay: _RequestOverlayState,
        result: MessageEventResult | None,
    ) -> None:
        self.request_runtime.set_result_from_object(overlay, result)

    def _bind_result_object(
        self,
        overlay: _RequestOverlayState,
        result: MessageEventResult | None,
    ) -> None:
        self.request_runtime.bind_result_object(overlay, result)

    def _set_result_payload_on_overlay(
        self,
        overlay: _RequestOverlayState,
        result_payload: dict[str, Any] | None,
    ) -> None:
        self.request_runtime.set_result_payload_on_overlay(overlay, result_payload)

    def _sync_overlay_payload_from_result_object(
        self,
        overlay: _RequestOverlayState,
    ) -> None:
        self.request_runtime.sync_overlay_payload_from_result_object(overlay)

    def _get_effective_result_for_token(
        self,
        dispatch_token: str,
    ) -> MessageEventResult | None:
        return self.request_runtime.get_effective_result_for_token(dispatch_token)

    def _set_result_for_dispatch_token(
        self,
        dispatch_token: str,
        result: MessageEventResult | None,
    ) -> None:
        self.request_runtime.set_result_for_dispatch_token(dispatch_token, result)

    def _clear_result_for_dispatch_token(self, dispatch_token: str) -> None:
        self.request_runtime.clear_result_for_dispatch_token(dispatch_token)

    def _stop_event_for_dispatch_token(self, dispatch_token: str) -> None:
        self.request_runtime.stop_event_for_dispatch_token(dispatch_token)

    def _continue_event_for_dispatch_token(self, dispatch_token: str) -> None:
        self.request_runtime.continue_event_for_dispatch_token(dispatch_token)

    def _is_stopped_for_dispatch_token(self, dispatch_token: str) -> bool:
        return self.request_runtime.is_stopped_for_dispatch_token(dispatch_token)

    def set_result_for_request(
        self,
        request_id: str,
        result_payload: dict[str, Any] | None,
    ) -> bool:
        return self.request_runtime.set_result_for_request(request_id, result_payload)

    def clear_result_for_request(self, request_id: str) -> bool:
        return self.request_runtime.clear_result_for_request(request_id)

    def get_result_payload_for_request(self, request_id: str) -> dict[str, Any] | None:
        return self.request_runtime.get_result_payload_for_request(request_id)

    def set_handler_whitelist_for_request(
        self,
        request_id: str,
        plugin_names: set[str] | None,
    ) -> bool:
        return self.request_runtime.set_handler_whitelist_for_request(
            request_id,
            plugin_names,
        )

    def get_handler_whitelist_for_request(self, request_id: str) -> set[str] | None:
        return self.request_runtime.get_handler_whitelist_for_request(request_id)

    def _get_handler_whitelist_for_event(
        self, event: AstrMessageEvent
    ) -> set[str] | None:
        return self.request_runtime.get_handler_whitelist_for_event(event)

    @staticmethod
    def _build_core_message_chain_from_payload(
        chain_payload: list[dict[str, Any]],
    ) -> MessageChain:
        return SdkRequestRuntime.build_core_message_chain_from_payload(chain_payload)

    @classmethod
    def _build_core_result_from_chain_payload(
        cls,
        chain_payload: list[dict[str, Any]],
    ) -> MessageEventResult:
        return SdkRequestRuntime.build_core_result_from_chain_payload(chain_payload)

    @staticmethod
    def _legacy_result_to_sdk_payload(
        result: MessageEventResult | None,
    ) -> dict[str, Any] | None:
        return SdkRequestRuntime.legacy_result_to_sdk_payload(result)

    @staticmethod
    def _components_to_sdk_payload(
        components: list[Any] | tuple[Any, ...] | None,
    ) -> list[dict[str, Any]]:
        return SdkRequestRuntime.components_to_sdk_payload(components)

    def _persist_sdk_local_extras_from_handler(
        self,
        overlay: _RequestOverlayState,
        payload: Any,
        *,
        plugin_id: str,
        handler_id: str,
    ) -> None:
        self.request_runtime.persist_sdk_local_extras_from_handler(
            overlay,
            payload,
            plugin_id=plugin_id,
            handler_id=handler_id,
        )

    @staticmethod
    def _sanitize_host_extras(event: AstrMessageEvent) -> dict[str, Any]:
        return SdkRequestRuntime.sanitize_host_extras(event)

    @staticmethod
    def _set_sdk_origin_plugin_id(
        event: AstrMessageEvent,
        plugin_id: str,
    ) -> None:
        SdkRequestRuntime.set_sdk_origin_plugin_id(event, plugin_id)

    def _get_or_build_inbound_snapshot(
        self,
        event: AstrMessageEvent,
        overlay: _RequestOverlayState | None,
    ) -> InboundEventSnapshot:
        return self.request_runtime.get_or_build_inbound_snapshot(event, overlay)

    def build_sdk_event_payload(
        self,
        event: AstrMessageEvent,
        *,
        dispatch_token: str,
        plugin_id: str,
        request_id: str,
        overlay: _RequestOverlayState | None,
        raw_updates: dict[str, Any] | None = None,
        field_updates: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.request_runtime.build_sdk_event_payload(
            event,
            dispatch_token=dispatch_token,
            plugin_id=plugin_id,
            request_id=request_id,
            overlay=overlay,
            raw_updates=raw_updates,
            field_updates=field_updates,
        )

    @staticmethod
    def _core_provider_request_to_sdk_payload(
        request: CoreProviderRequest,
    ) -> dict[str, Any]:
        return SdkRequestRuntime.core_provider_request_to_sdk_payload(request)

    @staticmethod
    def _apply_sdk_provider_request_payload(
        request: CoreProviderRequest,
        payload: dict[str, Any],
    ) -> None:
        SdkRequestRuntime.apply_sdk_provider_request_payload(request, payload)

    @staticmethod
    def _core_llm_response_to_sdk_payload(
        response: CoreLLMResponse,
    ) -> dict[str, Any]:
        return SdkRequestRuntime.core_llm_response_to_sdk_payload(response)

    @classmethod
    def _apply_sdk_result_payload(
        cls,
        result: MessageEventResult,
        payload: dict[str, Any],
    ) -> MessageEventResult:
        return SdkRequestRuntime.apply_sdk_result_payload(result, payload)

    def get_effective_result(
        self, event: AstrMessageEvent
    ) -> MessageEventResult | None:
        return self.request_runtime.get_effective_result(event)

    def before_platform_send(self, dispatch_token: str) -> None:
        self.request_runtime.before_platform_send(dispatch_token)

    def mark_platform_send(self, dispatch_token: str) -> str:
        return self.request_runtime.mark_platform_send(dispatch_token)

    def get_or_bind_dispatch_token(self, event: AstrMessageEvent) -> str:
        return self.request_runtime.get_or_bind_dispatch_token(event)

    def get_plugin_session(self, plugin_id: str) -> WorkerSession | None:
        record = self._records.get(plugin_id)
        return None if record is None else record.session

    @staticmethod
    def _legacy_has_replied(event: AstrMessageEvent) -> bool:
        # 委托给统一的 event_has_send_operation 方法,
        # 该方法已包含对新版 API → 兼容 API → 直接读字段的完整适配逻辑
        return SdkRequestRuntime.event_has_send_operation(event)

    def _match_handlers(self, event: AstrMessageEvent) -> list[TriggerMatch]:
        matches: list[TriggerMatch] = []
        normalized_platform = self._normalize_platform_name(event.get_platform_name())
        for record in self._records.values():
            if record.state in {SDK_STATE_DISABLED, SDK_STATE_FAILED}:
                continue
            if not self._record_supports_platform(record, normalized_platform):
                continue
            for handler in record.handlers:
                match = TriggerConverter.match_handler(
                    plugin_id=record.plugin_id,
                    descriptor=handler.descriptor,
                    event=event,
                    load_order=record.load_order,
                    declaration_order=handler.declaration_order,
                )
                if match is not None:
                    matches.append(match)
            dynamic_base_order = len(record.handlers)
            for route in getattr(record, "dynamic_command_routes", []):
                match = self._match_dynamic_command_route(
                    record=record,
                    route=route,
                    event=event,
                    declaration_order=dynamic_base_order + route.declaration_order,
                )
                if match is not None:
                    matches.append(match)
        matches.sort(key=TriggerConverter.sort_key)
        return matches

    def list_cross_system_command_conflicts(
        self,
    ) -> list[CrossSystemCommandConflict]:
        return build_cross_system_conflicts(
            collect_legacy_command_registrations(),
            self._collect_sdk_command_registrations(),
        )

    def has_active_sdk_command_handlers(self) -> bool:
        if not self._records:
            return False
        for record in self._snapshot_records():
            if record.state in {
                SDK_STATE_DISABLED,
                SDK_STATE_FAILED,
                SDK_STATE_RELOADING,
            }:
                continue
            if any(
                isinstance(handler.descriptor.trigger, CommandTrigger)
                for handler in record.handlers
            ):
                return True
            if any(
                not route.use_regex
                for route in getattr(record, "dynamic_command_routes", [])
            ):
                return True
        return False

    def refresh_command_compatibility_issues(self) -> None:
        conflicts = self.list_cross_system_command_conflicts()
        conflict_map: dict[str, list[CrossSystemCommandConflict]] = {}
        for conflict in conflicts:
            conflict_map.setdefault(conflict.sdk.plugin_name, []).append(conflict)

        for record in self._snapshot_records():
            record.issues = [
                issue
                for issue in record.issues
                if issue.get("warning_type") != self.COMMAND_OVERRIDE_WARNING_TYPE
            ]
            record_conflicts = conflict_map.get(record.plugin_id, [])
            if record_conflicts:
                for issue in self._build_command_compatibility_issues(
                    record.plugin_id,
                    record_conflicts,
                ):
                    record.issues.append(issue)
                logger.warning(
                    "SDK plugin command overrides legacy handlers: plugin=%s commands=%s",
                    record.plugin_id,
                    ", ".join(
                        sorted({conflict.command_name for conflict in record_conflicts})
                    ),
                )

    def detect_legacy_command_conflict(
        self,
        event: AstrMessageEvent,
        legacy_handlers: list[Any],
    ) -> CrossSystemCommandConflict | None:
        if not legacy_handlers or not self.has_active_sdk_command_handlers():
            return None
        sdk_matches = self._match_handlers(event)
        if not sdk_matches:
            return None
        legacy_registrations = match_legacy_command_registrations(
            legacy_handlers,
            event.get_message_str(),
        )
        if not legacy_registrations:
            return None
        sdk_registrations = self._matched_sdk_command_registrations(sdk_matches)
        if not sdk_registrations:
            return None
        conflicts = build_cross_system_conflicts(
            legacy_registrations,
            sdk_registrations,
        )
        if not conflicts:
            return None
        conflicts.sort(
            key=lambda item: (
                item.command_name,
                item.legacy.plugin_name,
                item.sdk.plugin_name,
                item.sdk.handler_full_name,
            )
        )
        return conflicts[0]

    def format_legacy_command_conflict_message(
        self,
        conflict: CrossSystemCommandConflict,
    ) -> str:
        legacy_name = conflict.legacy.plugin_display_name or conflict.legacy.plugin_name
        sdk_name = conflict.sdk.plugin_display_name or conflict.sdk.plugin_name
        if conflict.legacy.command_name == conflict.sdk.command_name:
            command_detail = f"`/{conflict.legacy.command_name}`"
        else:
            command_detail = (
                f"`/{conflict.legacy.command_name}` 与 `/{conflict.sdk.command_name}`"
            )
        return (
            "检测到旧插件与 SDK 插件存在命令冲突，当前不兼容："
            f"{command_detail} 分别来自 {legacy_name} 和 {sdk_name}。"
            "请停用、卸载或重命名其中一个插件后再使用。"
        )

    def _collect_sdk_command_registrations(self) -> list[Any]:
        registrations: list[Any] = []
        for record in self._snapshot_records_sorted():
            if record.state in {
                SDK_STATE_DISABLED,
                SDK_STATE_FAILED,
                SDK_STATE_RELOADING,
            }:
                continue
            registrations.extend(self._sdk_record_command_registrations(record))
        return registrations

    def _sdk_record_command_registrations(self, record: SdkPluginRecord) -> list[Any]:
        registrations: list[Any] = []
        plugin_display_name = str(
            record.plugin.manifest_data.get("display_name") or record.plugin_id
        )
        for handler in record.handlers:
            registrations.extend(
                collect_sdk_command_registrations(
                    plugin_name=record.plugin_id,
                    plugin_display_name=plugin_display_name,
                    handler_full_name=handler.descriptor.id,
                    descriptor=handler.descriptor,
                )
            )
        for route in getattr(record, "dynamic_command_routes", []):
            descriptor = self._build_dynamic_route_descriptor(record, route)
            if descriptor is None:
                continue
            registrations.extend(
                collect_sdk_command_registrations(
                    plugin_name=record.plugin_id,
                    plugin_display_name=plugin_display_name,
                    handler_full_name=descriptor.id,
                    descriptor=descriptor,
                )
            )
        return registrations

    def _matched_sdk_command_registrations(
        self,
        matches: list[TriggerMatch],
    ) -> list[CommandRegistration]:
        registrations: list[CommandRegistration] = []
        for match in matches:
            if not match.matched_command_name:
                continue
            record = self._records.get(match.plugin_id)
            if record is None:
                continue
            descriptor = self._descriptor_from_match(record, match)
            if descriptor is None:
                continue
            registrations.append(
                CommandRegistration(
                    runtime_kind="sdk",
                    plugin_name=record.plugin_id,
                    plugin_display_name=str(
                        record.plugin.manifest_data.get("display_name")
                        or record.plugin_id
                    ),
                    handler_full_name=descriptor.id,
                    command_name=match.matched_command_name,
                )
            )
        return registrations

    def _descriptor_from_match(
        self,
        record: SdkPluginRecord,
        match: TriggerMatch,
    ) -> HandlerDescriptor | None:
        for handler in record.handlers:
            if (
                handler.descriptor.id == match.handler_id
                and handler.declaration_order == match.declaration_order
            ):
                return handler.descriptor

        dynamic_order = match.declaration_order - len(record.handlers)
        if dynamic_order < 0:
            return None
        for route in getattr(record, "dynamic_command_routes", []):
            if route.declaration_order != dynamic_order:
                continue
            return self._build_dynamic_route_descriptor(record, route)
        return None

    def _build_command_compatibility_issues(
        self,
        plugin_id: str,
        conflicts: list[CrossSystemCommandConflict],
    ) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        for conflict in conflicts:
            legacy_name = (
                conflict.legacy.plugin_display_name or conflict.legacy.plugin_name
            )
            if conflict.legacy.command_name == conflict.sdk.command_name:
                conflict_detail = f"Command '/{conflict.legacy.command_name}'"
            else:
                conflict_detail = (
                    f"Commands '/{conflict.legacy.command_name}' and "
                    f"'/{conflict.sdk.command_name}'"
                )
            issues.append(
                {
                    "severity": "warning",
                    "phase": "compatibility",
                    "plugin_id": plugin_id,
                    "message": "SDK plugin command overrides a legacy plugin command",
                    "details": (
                        f"{conflict_detail} are registered by both systems. "
                        f"The SDK plugin overrides legacy plugin '{legacy_name}' at runtime."
                    ),
                    "warning_type": self.COMMAND_OVERRIDE_WARNING_TYPE,
                    "command_name": conflict.command_name,
                    "legacy_command_name": conflict.legacy.command_name,
                    "sdk_command_name": conflict.sdk.command_name,
                    "legacy_plugin_name": conflict.legacy.plugin_name,
                    "legacy_plugin_display_name": conflict.legacy.plugin_display_name,
                    "legacy_handler_full_name": conflict.legacy.handler_full_name,
                    "sdk_handler_full_name": conflict.sdk.handler_full_name,
                }
            )
        return issues

    @staticmethod
    def _descriptor_root_candidates(descriptor: HandlerDescriptor) -> list[str]:
        trigger = descriptor.trigger
        if not isinstance(trigger, CommandTrigger):
            return []
        candidates: list[str] = []
        route = descriptor.command_route
        if route is not None and route.group_path:
            root_name = str(route.group_path[0]).strip()
            if root_name:
                candidates.append(root_name)
        for name in [trigger.command, *trigger.aliases]:
            normalized = str(name).strip()
            if " " not in normalized:
                continue
            root_name = normalized.split()[0].strip()
            if root_name:
                candidates.append(root_name)
        return list(dict.fromkeys(candidates))

    @classmethod
    def _descriptor_help_entry(
        cls,
        descriptor: HandlerDescriptor,
    ) -> tuple[str, str | None] | None:
        trigger = descriptor.trigger
        if not isinstance(trigger, CommandTrigger):
            return None
        route = descriptor.command_route
        display_command = (
            str(route.display_command).strip()
            if route is not None and str(route.display_command).strip()
            else str(trigger.command).strip()
        )
        if not display_command:
            return None
        return display_command, cls._descriptor_description(descriptor)

    def _resolve_group_root_fallback(
        self,
        event: AstrMessageEvent,
    ) -> dict[str, str] | None:
        root_name = command_root_name(event.get_message_str())
        if not root_name:
            return None
        normalized_platform = self._normalize_platform_name(event.get_platform_name())
        for record in self._snapshot_records_sorted():
            if record.state in {
                SDK_STATE_DISABLED,
                SDK_STATE_FAILED,
                SDK_STATE_RELOADING,
            }:
                continue
            if not self._record_supports_platform(record, normalized_platform):
                continue
            help_text = self._build_group_root_help(record, event, root_name)
            if help_text is None:
                continue
            return {"plugin_id": record.plugin_id, "help_text": help_text}
        return None

    def _resolve_command_permission_denied(
        self,
        event: AstrMessageEvent,
    ) -> dict[str, str] | None:
        text = event.get_message_str().strip()
        if not text:
            return None
        normalized_platform = self._normalize_platform_name(event.get_platform_name())
        for record in sorted(self._records.values(), key=lambda item: item.load_order):
            if record.state in {
                SDK_STATE_DISABLED,
                SDK_STATE_FAILED,
                SDK_STATE_RELOADING,
            }:
                continue
            if not self._record_supports_platform(record, normalized_platform):
                continue
            for handler in record.handlers:
                descriptor = handler.descriptor
                if not self._descriptor_requires_admin(descriptor):
                    continue
                if not TriggerConverter._match_filters(descriptor, event):
                    continue
                if not self._descriptor_matches_command_text(descriptor, text):
                    continue
                help_entry = self._descriptor_help_entry(descriptor)
                display_command = (
                    help_entry[0]
                    if help_entry is not None
                    else str(getattr(descriptor.trigger, "command", "")).strip()
                )
                if not display_command:
                    continue
                return {
                    "plugin_id": record.plugin_id,
                    "message": (f"权限不足：`/{display_command}` 需要管理员权限。"),
                }
        return None

    def _has_command_trigger_match(self, matches: list[TriggerMatch]) -> bool:
        for match in matches:
            record = self._records.get(match.plugin_id)
            if record is None:
                continue
            handler_ref = self._find_handler_ref(record, match.handler_id)
            if handler_ref is not None and isinstance(
                handler_ref.descriptor.trigger, CommandTrigger
            ):
                return True
        return False

    def _build_group_root_help(
        self,
        record: SdkPluginRecord,
        event: AstrMessageEvent,
        root_name: str,
    ) -> str | None:
        entries: list[tuple[str, str | None]] = []
        seen_commands: set[str] = set()
        for handler in record.handlers:
            descriptor = handler.descriptor
            if root_name not in self._descriptor_root_candidates(descriptor):
                continue
            if not TriggerConverter._match_filters(descriptor, event):
                continue
            if not self._descriptor_is_visible_to_event(descriptor, event):
                continue
            help_entry = self._descriptor_help_entry(descriptor)
            if help_entry is None:
                continue
            command_name, description = help_entry
            if command_name in seen_commands:
                continue
            seen_commands.add(command_name)
            entries.append((command_name, description))
        if not entries:
            return None
        lines = [f"{root_name}命令："]
        for command_name, description in entries:
            line = f"- /{command_name}"
            if description:
                line += f": {description}"
            lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def _descriptor_requires_admin(descriptor: HandlerDescriptor) -> bool:
        required_role = descriptor.permissions.required_role
        if required_role is None and descriptor.permissions.require_admin:
            required_role = "admin"
        return required_role == "admin"

    @classmethod
    def _descriptor_is_visible_to_event(
        cls,
        descriptor: HandlerDescriptor,
        event: AstrMessageEvent,
    ) -> bool:
        if cls._descriptor_requires_admin(descriptor) and not event.is_admin():
            return False
        return True

    @staticmethod
    def _descriptor_matches_command_text(
        descriptor: HandlerDescriptor,
        text: str,
    ) -> bool:
        trigger = descriptor.trigger
        if not isinstance(trigger, CommandTrigger):
            return False
        for command_name in [trigger.command, *trigger.aliases]:
            if not command_name:
                continue
            if TriggerConverter._match_command_name(text, command_name) is not None:
                return True
        return False

    def _match_dynamic_command_route(
        self,
        *,
        record: SdkPluginRecord,
        route: SdkDynamicCommandRoute,
        event: AstrMessageEvent,
        declaration_order: int,
    ) -> TriggerMatch | None:
        # 复用 _build_dynamic_route_descriptor 构建描述符，避免重复内联逻辑
        descriptor = self._build_dynamic_route_descriptor(record, route)
        if descriptor is None:
            return None
        return TriggerConverter.match_handler(
            plugin_id=record.plugin_id,
            descriptor=descriptor,
            event=event,
            load_order=record.load_order,
            declaration_order=declaration_order,
        )

    @staticmethod
    def _find_handler_ref(
        record: SdkPluginRecord,
        handler_full_name: str,
    ) -> SdkHandlerRef | None:
        for handler in record.handlers:
            if handler.descriptor.id == handler_full_name:
                return handler
        return None

    async def dispatch_system_event(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        await self.dispatch_engine.dispatch_system_event(event_type, payload)

    async def dispatch_message_event(
        self,
        event_type: str,
        event: AstrMessageEvent,
        payload: dict[str, Any] | None = None,
        *,
        provider_request: CoreProviderRequest | None = None,
        llm_response: CoreLLMResponse | None = None,
        event_result: MessageEventResult | None = None,
    ) -> None:
        await self.dispatch_engine.dispatch_message_event(
            event_type,
            event,
            payload,
            provider_request=provider_request,
            llm_response=llm_response,
            event_result=event_result,
        )

    def _match_event_handlers(
        self,
        event_type: str,
        *,
        allowed_plugins: set[str] | None = None,
        platform_name: str = "",
    ) -> list[tuple[SdkPluginRecord, HandlerDescriptor]]:
        matches: list[tuple[int, int, int, SdkPluginRecord, HandlerDescriptor]] = []
        for record in self._snapshot_records():
            if record.state in {
                SDK_STATE_DISABLED,
                SDK_STATE_FAILED,
                SDK_STATE_RELOADING,
            }:
                continue
            if allowed_plugins is not None and record.plugin_id not in allowed_plugins:
                continue
            if not self._record_supports_platform(record, platform_name):
                continue
            for handler in record.handlers:
                trigger = handler.descriptor.trigger
                if not isinstance(trigger, EventTrigger):
                    continue
                if trigger.event_type != event_type:
                    continue
                if not self._descriptor_supports_platform(
                    handler.descriptor,
                    platform_name,
                ):
                    continue
                matches.append(
                    (
                        -handler.descriptor.priority,
                        record.load_order,
                        handler.declaration_order,
                        record,
                        handler.descriptor,
                    )
                )
        matches.sort(key=lambda item: (item[0], item[1], item[2]))
        return [(record, descriptor) for _, _, _, record, descriptor in matches]

    @staticmethod
    def _descriptor_event_types(descriptor: HandlerDescriptor) -> list[str]:
        trigger = descriptor.trigger
        if isinstance(trigger, EventTrigger):
            return [trigger.event_type]
        return []

    @staticmethod
    def _descriptor_group_path(descriptor: HandlerDescriptor) -> list[str]:
        route = getattr(descriptor, "command_route", None)
        if route is None:
            return []
        return list(route.group_path)

    @staticmethod
    def _descriptor_description(descriptor: HandlerDescriptor) -> str | None:
        description = str(descriptor.description or "").strip()
        if description:
            return description
        trigger = descriptor.trigger
        if isinstance(trigger, CommandTrigger):
            command_description = str(trigger.description or "").strip()
            if command_description:
                return command_description
        return None

    def _descriptor_metadata(
        self,
        *,
        plugin_id: str,
        descriptor: HandlerDescriptor,
    ) -> dict[str, Any]:
        return {
            "plugin_name": plugin_id,
            "handler_full_name": descriptor.id,
            "trigger_type": getattr(descriptor.trigger, "type", ""),
            "description": self._descriptor_description(descriptor),
            "event_types": self._descriptor_event_types(descriptor),
            "enabled": True,
            "group_path": self._descriptor_group_path(descriptor),
            "priority": descriptor.priority,
            "kind": descriptor.kind,
            "require_admin": descriptor.permissions.require_admin,
            "required_role": descriptor.permissions.required_role,
        }

    def get_handlers_by_event_type(self, event_type: str) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for record in self._snapshot_records_sorted():
            if record.state in {
                SDK_STATE_DISABLED,
                SDK_STATE_FAILED,
                SDK_STATE_RELOADING,
            }:
                continue
            for handler in record.handlers:
                trigger = handler.descriptor.trigger
                if (
                    isinstance(trigger, EventTrigger)
                    and trigger.event_type == event_type
                ):
                    entries.append(
                        self._descriptor_metadata(
                            plugin_id=record.plugin_id,
                            descriptor=handler.descriptor,
                        )
                    )
            if event_type == "message":
                for route in getattr(record, "dynamic_command_routes", []):
                    descriptor = self._build_dynamic_route_descriptor(record, route)
                    if descriptor is None:
                        continue
                    entries.append(
                        self._descriptor_metadata(
                            plugin_id=record.plugin_id,
                            descriptor=descriptor,
                        )
                    )
        return entries

    def list_native_command_candidates(
        self,
        platform_name: str,
    ) -> list[dict[str, Any]]:
        """Expose SDK commands that can be surfaced in native platform menus.

        Native platform command menus are top-level and single-token, so grouped
        SDK commands are exported as their root command (for example ``gf`` for
        ``gf chat`` / ``gf affection``).
        """
        normalized_platform = str(platform_name).strip().lower()
        if not normalized_platform:
            return []

        entries: list[dict[str, Any]] = []
        seen_names: set[str] = set()

        for record in self._snapshot_records_sorted():
            if record.state in {
                SDK_STATE_DISABLED,
                SDK_STATE_FAILED,
                SDK_STATE_RELOADING,
            }:
                continue
            if not self._record_supports_platform(record, normalized_platform):
                continue

            for handler in record.handlers:
                for entry in self._descriptor_native_command_candidates(
                    handler.descriptor,
                    platform_name=normalized_platform,
                ):
                    name = str(entry.get("name", "")).strip().lower()
                    if not name or name in seen_names:
                        continue
                    seen_names.add(name)
                    entries.append(entry)

            for route in getattr(record, "dynamic_command_routes", []):
                descriptor = self._build_dynamic_route_descriptor(record, route)
                if descriptor is None:
                    continue
                for entry in self._descriptor_native_command_candidates(
                    descriptor,
                    platform_name=normalized_platform,
                ):
                    name = str(entry.get("name", "")).strip().lower()
                    if not name or name in seen_names:
                        continue
                    seen_names.add(name)
                    entries.append(entry)

        return entries

    def get_handler_by_full_name(self, full_name: str) -> dict[str, Any] | None:
        for record in self._snapshot_records():
            for handler in record.handlers:
                if handler.descriptor.id == full_name:
                    return self._descriptor_metadata(
                        plugin_id=record.plugin_id,
                        descriptor=handler.descriptor,
                    )
        return None

    def list_dashboard_commands(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for record in self._snapshot_records_sorted():
            items.extend(self._build_dashboard_command_items(record))
        items.sort(key=lambda item: str(item.get("effective_command", "")).lower())
        return items

    def list_dashboard_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for record in self._snapshot_records_sorted():
            display_name = str(
                record.plugin.manifest_data.get("display_name") or record.plugin_id
            )
            plugin_enabled = record.state not in {
                SDK_STATE_DISABLED,
                SDK_STATE_FAILED,
                SDK_STATE_RELOADING,
            }
            for spec in sorted(record.llm_tools.values(), key=lambda item: item.name):
                tools.append(
                    {
                        "tool_key": (f"sdk:{record.plugin_id}:{spec.name}"),
                        "name": spec.name,
                        "description": spec.description,
                        "parameters": dict(spec.parameters_schema),
                        "active": bool(spec.active) and plugin_enabled,
                        "origin": "sdk_plugin",
                        "origin_name": display_name,
                        "runtime_kind": "sdk",
                        "plugin_id": record.plugin_id,
                    }
                )
        return tools

    def _build_dashboard_command_items(
        self,
        record: SdkPluginRecord,
    ) -> list[dict[str, Any]]:
        flat_commands: list[dict[str, Any]] = []
        for handler in record.handlers:
            entry = self._build_dashboard_command_entry(
                record=record,
                descriptor=handler.descriptor,
            )
            if entry is not None:
                flat_commands.append(entry)
        for route in getattr(record, "dynamic_command_routes", []):
            descriptor = self._build_dynamic_route_descriptor(record, route)
            if descriptor is None:
                continue
            entry = self._build_dashboard_command_entry(
                record=record,
                descriptor=descriptor,
                route=route,
            )
            if entry is not None:
                flat_commands.append(entry)

        groups: dict[str, dict[str, Any]] = {}
        root_items: list[dict[str, Any]] = []
        for entry in flat_commands:
            parent_signature = str(entry.get("parent_signature", "")).strip()
            if not parent_signature:
                root_items.append(entry)
                continue
            group_key = self._dashboard_group_key(record.plugin_id, parent_signature)
            group = groups.get(group_key)
            if group is None:
                group = {
                    "command_key": group_key,
                    "handler_full_name": group_key,
                    "handler_name": parent_signature.split()[-1] or record.plugin_id,
                    "plugin": record.plugin_id,
                    "plugin_display_name": str(
                        record.plugin.manifest_data.get("display_name")
                        or record.plugin_id
                    ),
                    "module_path": str(record.plugin.plugin_dir),
                    "description": entry.pop("_group_help", "") or "",
                    "type": "group",
                    "parent_signature": "",
                    "parent_group_handler": "",
                    "original_command": parent_signature,
                    "current_fragment": parent_signature.split()[-1]
                    if parent_signature
                    else "",
                    "effective_command": parent_signature,
                    "aliases": [],
                    "permission": "everyone",
                    "enabled": bool(entry.get("enabled", False)),
                    "is_group": True,
                    "has_conflict": False,
                    "reserved": False,
                    "runtime_kind": "sdk",
                    "supports_toggle": False,
                    "supports_rename": False,
                    "supports_permission": False,
                    "sub_commands": [],
                }
                groups[group_key] = group
                root_items.append(group)
            elif not group.get("description") and entry.get("_group_help"):
                group["description"] = entry["_group_help"]

            if entry.get("permission") == "admin":
                group["permission"] = "admin"
            group["enabled"] = bool(group["enabled"]) or bool(
                entry.get("enabled", False)
            )
            entry["parent_group_handler"] = group["handler_full_name"]
            entry.pop("_group_help", None)
            group["sub_commands"].append(entry)

        for group in groups.values():
            group["sub_commands"].sort(
                key=lambda item: str(item.get("effective_command", "")).lower()
            )
        for item in root_items:
            item.pop("_group_help", None)
        return root_items

    def _build_dashboard_command_entry(
        self,
        *,
        record: SdkPluginRecord,
        descriptor: HandlerDescriptor,
        route: SdkDynamicCommandRoute | None = None,
    ) -> dict[str, Any] | None:
        trigger = descriptor.trigger
        if not isinstance(trigger, CommandTrigger):
            return None

        route_meta = descriptor.command_route
        effective_command = (
            str(route_meta.display_command).strip()
            if route_meta is not None and str(route_meta.display_command).strip()
            else str(trigger.command).strip()
        )
        parent_signature = ""
        group_help = ""
        if route_meta is not None and route_meta.group_path:
            parent_signature = " ".join(
                str(item).strip() for item in route_meta.group_path if str(item).strip()
            ).strip()
            group_help = str(route_meta.group_help or "").strip()

        current_fragment = effective_command
        if parent_signature and effective_command.startswith(f"{parent_signature} "):
            current_fragment = effective_command[len(parent_signature) + 1 :].strip()

        enabled = record.state not in {
            SDK_STATE_DISABLED,
            SDK_STATE_FAILED,
            SDK_STATE_RELOADING,
        }
        return {
            "command_key": self._dashboard_command_key(
                plugin_id=record.plugin_id,
                handler_full_name=descriptor.id,
                route=route,
            ),
            "handler_full_name": descriptor.id,
            "handler_name": descriptor.id.rsplit(".", 1)[-1],
            "plugin": record.plugin_id,
            "plugin_display_name": str(
                record.plugin.manifest_data.get("display_name") or record.plugin_id
            ),
            "module_path": descriptor.id.rsplit(".", 1)[0],
            "description": self._descriptor_description(descriptor) or "",
            "type": "sub_command" if parent_signature else "command",
            "parent_signature": parent_signature,
            "parent_group_handler": "",
            "original_command": effective_command,
            "current_fragment": current_fragment,
            "effective_command": effective_command,
            "aliases": list(trigger.aliases),
            "permission": (
                "admin" if descriptor.permissions.require_admin else "everyone"
            ),
            "enabled": enabled,
            "is_group": False,
            "has_conflict": False,
            "reserved": False,
            "runtime_kind": "sdk",
            "supports_toggle": False,
            "supports_rename": False,
            "supports_permission": False,
            "sub_commands": [],
            "_group_help": group_help,
        }

    @staticmethod
    def _dashboard_command_key(
        *,
        plugin_id: str,
        handler_full_name: str,
        route: SdkDynamicCommandRoute | None,
    ) -> str:
        if route is None:
            return f"sdk:command:{plugin_id}:{handler_full_name}"
        route_kind = "regex" if route.use_regex else "command"
        return f"sdk:route:{plugin_id}:{handler_full_name}:{route_kind}:{route.command_name}"

    @staticmethod
    def _dashboard_group_key(plugin_id: str, parent_signature: str) -> str:
        return f"sdk:group:{plugin_id}:{parent_signature}"

    def _build_dynamic_route_descriptor(
        self,
        record: SdkPluginRecord,
        route: SdkDynamicCommandRoute,
    ) -> HandlerDescriptor | None:
        handler_ref = self._find_handler_ref(record, route.handler_full_name)
        if handler_ref is None:
            return None
        descriptor = handler_ref.descriptor.model_copy(deep=True)
        descriptor.priority = route.priority
        if route.use_regex:
            descriptor.trigger = MessageTrigger(regex=route.command_name)
        else:
            descriptor.trigger = CommandTrigger(
                command=route.command_name,
                description=route.desc or None,
            )
        return descriptor

    @staticmethod
    def _normalize_platform_name(value: Any) -> str:
        return str(value or "").strip().lower()

    @classmethod
    def _normalized_platform_names(cls, values: Any) -> set[str]:
        if not isinstance(values, list):
            return set()
        return {
            cls._normalize_platform_name(item)
            for item in values
            if cls._normalize_platform_name(item)
        }

    @classmethod
    def _manifest_supported_platforms(cls, manifest_data: Any) -> set[str]:
        if not isinstance(manifest_data, dict):
            return set()
        return cls._normalized_platform_names(manifest_data.get("support_platforms"))

    def plugin_supports_platform(self, plugin_id: str, platform_name: str) -> bool:
        normalized_platform = self._normalize_platform_name(platform_name)
        if not normalized_platform:
            return True
        record = self._records.get(str(plugin_id))
        if record is None:
            return True
        return self._record_supports_platform(record, normalized_platform)

    @staticmethod
    def _record_supports_platform(
        record: SdkPluginRecord,
        platform_name: str,
    ) -> bool:
        normalized_platform = SdkPluginBridge._normalize_platform_name(platform_name)
        if not normalized_platform:
            return True
        plugin = getattr(record, "plugin", None)
        manifest_data = getattr(plugin, "manifest_data", None)
        normalized = SdkPluginBridge._manifest_supported_platforms(manifest_data)
        if not normalized:
            return True
        return normalized_platform in normalized

    @staticmethod
    def _local_mcp_tool_name(server_name: str, tool_name: str) -> str:
        return f"mcp.{server_name}.{tool_name}"

    @staticmethod
    def _local_mcp_tool_ref(server_name: str, tool_name: str) -> str:
        return json.dumps(
            {"server_name": server_name, "tool_name": tool_name},
            ensure_ascii=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _plugin_data_dir(plugin_id: str) -> Path:
        return Path(get_astrbot_plugin_data_path()) / plugin_id

    @classmethod
    def _plugin_mcp_lease_dir(cls, plugin_id: str) -> Path:
        return cls._plugin_data_dir(plugin_id) / ".mcp_leases"

    def acknowledges_global_mcp_risk(self, plugin_id: str) -> bool:
        record = self._records.get(plugin_id)
        return bool(record and record.acknowledge_global_mcp_risk)

    def _load_local_mcp_configs(self, plugin: PluginSpec) -> dict[str, dict[str, Any]]:
        config_path = plugin.plugin_dir / "mcp.json"
        if not config_path.exists():
            return {}
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(
                "Failed to read SDK plugin mcp.json %s: %s", config_path, exc
            )
            return {}
        if not isinstance(payload, dict):
            logger.warning("Ignoring invalid SDK plugin mcp.json root: %s", config_path)
            return {}
        servers = payload.get("mcpServers")
        if not isinstance(servers, dict):
            logger.warning(
                "Ignoring SDK plugin mcp.json without mcpServers: %s", config_path
            )
            return {}
        return {
            str(name): dict(config)
            for name, config in servers.items()
            if str(name).strip() and isinstance(config, dict)
        }

    @classmethod
    def _build_local_mcp_tool_specs(
        cls,
        server_name: str,
        client: MCPClient,
    ) -> list[LLMToolSpec]:
        specs: list[LLMToolSpec] = []
        for tool in client.tools:
            raw_tool_name = str(getattr(tool, "name", "")).strip()
            if not raw_tool_name:
                continue
            parameters_schema = getattr(tool, "inputSchema", None)
            if not isinstance(parameters_schema, dict):
                parameters_schema = {"type": "object", "properties": {}}
            specs.append(
                LLMToolSpec.create(
                    name=cls._local_mcp_tool_name(server_name, raw_tool_name),
                    description=str(getattr(tool, "description", "") or ""),
                    parameters_schema=dict(parameters_schema),
                    handler_ref=cls._local_mcp_tool_ref(server_name, raw_tool_name),
                    handler_capability="internal.mcp.local.execute",
                    active=True,
                )
            )
        return specs

    @staticmethod
    def _mcp_call_result_to_text(result: Any) -> str | None:
        content_items = getattr(result, "content", None)
        if not isinstance(content_items, list):
            return None
        chunks: list[str] = []
        for item in content_items:
            text = getattr(item, "text", None)
            if isinstance(text, str):
                chunks.append(text)
                continue
            model_dump = getattr(item, "model_dump", None)
            if callable(model_dump):
                chunks.append(json.dumps(model_dump(), ensure_ascii=False))
                continue
            if item is not None:
                chunks.append(str(item))
        return "\n".join(part for part in chunks if part).strip() or None

    async def _cleanup_mcp_client(self, client: MCPClient | None) -> None:
        if client is None:
            return
        with contextlib.suppress(Exception):
            await client.cleanup()

    def _write_local_mcp_lease(
        self,
        *,
        plugin_id: str,
        server_name: str,
        pid: int,
    ) -> Path:
        lease_dir = self._plugin_mcp_lease_dir(plugin_id)
        lease_dir.mkdir(parents=True, exist_ok=True)
        lease_path = lease_dir / f"{server_name}.json"
        lease_path.write_text(
            json.dumps(
                {
                    "pid": int(pid),
                    "plugin_id": plugin_id,
                    "server_name": server_name,
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        return lease_path

    @staticmethod
    def _remove_local_mcp_lease(runtime: _LocalMCPServerRuntime) -> None:
        lease_path = runtime.lease_path
        runtime.lease_path = None
        if lease_path is None:
            return
        with contextlib.suppress(OSError):
            lease_path.unlink()

    def _terminate_stale_mcp_pid(self, pid: int) -> None:
        if pid <= 0:
            return
        if os.name == "nt":
            # Windows 没有 SIGTERM，os.kill 在 Windows 上行为不稳定；
            # 使用 taskkill /T /F 可以递归终止整个进程树，更可靠
            creation_flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
            completed = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
                creationflags=creation_flags,
            )
            combined_output = " ".join(
                item.strip()
                for item in (completed.stdout, completed.stderr)
                if isinstance(item, str) and item.strip()
            ).lower()
            # 进程已不存在（"not found"）也视为成功终止，避免误报
            if completed.returncode == 0 or "not found" in combined_output:
                return
            logger.warning(
                "Failed to terminate stale MCP pid %s on Windows: rc=%s output=%s",
                pid,
                completed.returncode,
                combined_output or "<empty>",
            )
            return
        # 非 Windows 平台使用 SIGTERM，简洁且可移植
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except PermissionError:
            logger.warning("Permission denied while terminating stale MCP pid %s", pid)
            return
        except OSError as exc:
            logger.warning("Failed to terminate stale MCP pid %s: %s", pid, exc)

    def _sweep_stale_mcp_leases(self) -> None:
        plugin_data_root = Path(get_astrbot_plugin_data_path())
        if not plugin_data_root.exists():
            return
        for lease_path in plugin_data_root.glob("*/.mcp_leases/*.json"):
            try:
                payload = json.loads(lease_path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            pid = payload.get("pid")
            if pid is not None:
                with contextlib.suppress(TypeError, ValueError):
                    self._terminate_stale_mcp_pid(int(pid))
            with contextlib.suppress(OSError):
                lease_path.unlink()

    async def _connect_local_mcp_server(
        self,
        *,
        plugin_id: str,
        runtime: _LocalMCPServerRuntime,
        timeout: float,
    ) -> None:
        await self.mcp.connect_local_mcp_server(
            plugin_id=plugin_id,
            runtime=runtime,
            timeout=timeout,
        )

    async def _initialize_local_mcp_servers(self, record: SdkPluginRecord) -> None:
        await self.mcp.initialize_local_mcp_servers(record)

    async def _shutdown_local_mcp_runtime(
        self,
        runtime: _LocalMCPServerRuntime,
    ) -> None:
        await self.mcp.shutdown_local_mcp_runtime(runtime)

    async def _shutdown_local_mcp_servers(self, record: SdkPluginRecord) -> None:
        await self.mcp.shutdown_local_mcp_servers(record)

    async def enable_local_mcp_server(
        self,
        plugin_id: str,
        name: str,
        *,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        return await self.mcp.enable_local_mcp_server(
            plugin_id,
            name,
            timeout=timeout,
        )

    async def disable_local_mcp_server(
        self,
        plugin_id: str,
        name: str,
    ) -> dict[str, Any]:
        return await self.mcp.disable_local_mcp_server(plugin_id, name)

    async def wait_for_local_mcp_server(
        self,
        plugin_id: str,
        name: str,
        *,
        timeout: float,
    ) -> dict[str, Any]:
        return await self.mcp.wait_for_local_mcp_server(
            plugin_id,
            name,
            timeout=timeout,
        )

    async def open_temporary_mcp_session(
        self,
        plugin_id: str,
        *,
        name: str,
        config: dict[str, Any],
        timeout: float,
    ) -> tuple[str, list[str]]:
        return await self.mcp.open_temporary_mcp_session(
            plugin_id,
            name=name,
            config=config,
            timeout=timeout,
        )

    async def close_temporary_mcp_session(
        self,
        plugin_id: str,
        session_id: str,
    ) -> None:
        await self.mcp.close_temporary_mcp_session(plugin_id, session_id)

    async def _close_temporary_mcp_sessions(self, plugin_id: str) -> None:
        await self.mcp.close_temporary_mcp_sessions(plugin_id)

    def get_temporary_mcp_session_tools(
        self,
        plugin_id: str,
        session_id: str,
    ) -> list[str]:
        return self.mcp.get_temporary_mcp_session_tools(plugin_id, session_id)

    async def call_temporary_mcp_tool(
        self,
        plugin_id: str,
        *,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.mcp.call_temporary_mcp_tool(
            plugin_id,
            session_id=session_id,
            tool_name=tool_name,
            arguments=arguments,
        )

    async def execute_local_mcp_tool(
        self,
        plugin_id: str,
        *,
        server_name: str,
        tool_name: str,
        tool_args: dict[str, Any],
        timeout_seconds: int = 60,
    ) -> dict[str, Any]:
        return await self.mcp.execute_local_mcp_tool(
            plugin_id,
            server_name=server_name,
            tool_name=tool_name,
            tool_args=tool_args,
            timeout_seconds=timeout_seconds,
        )

    @classmethod
    def _descriptor_native_command_candidates(
        cls,
        descriptor: HandlerDescriptor,
        *,
        platform_name: str,
    ) -> list[dict[str, Any]]:
        trigger = descriptor.trigger
        if not isinstance(trigger, CommandTrigger):
            return []
        if not cls._descriptor_supports_platform(descriptor, platform_name):
            return []

        names = [trigger.command, *trigger.aliases]
        route = descriptor.command_route
        root_candidates: list[str] = []

        if route is not None and route.group_path:
            root_candidates.append(str(route.group_path[0]).strip())

        for name in names:
            normalized = str(name).strip()
            if " " not in normalized:
                continue
            root_candidates.append(normalized.split()[0].strip())

        if root_candidates:
            description = (
                str(route.group_help).strip()
                if route is not None and route.group_help
                else str(trigger.description or "").strip()
            )
            root_name = next((item for item in root_candidates if item), "")
            if not description and root_name:
                description = f"Command group: {root_name}"
            unique_roots = [
                item
                for item in dict.fromkeys(root_candidates)
                if isinstance(item, str) and item.strip()
            ]
            return [
                {
                    "name": item.strip(),
                    "description": description,
                    "is_group": True,
                }
                for item in unique_roots
            ]

        description = str(trigger.description or "").strip()
        if not description and trigger.command.strip():
            description = f"Command: {trigger.command.strip()}"
        unique_names = [
            item for item in dict.fromkeys(str(name).strip() for name in names) if item
        ]
        return [
            {
                "name": item,
                "description": description,
                "is_group": False,
            }
            for item in unique_names
        ]

    @classmethod
    def _descriptor_supports_platform(
        cls,
        descriptor: HandlerDescriptor,
        platform_name: str,
    ) -> bool:
        normalized_platform = cls._normalize_platform_name(platform_name)
        if not normalized_platform:
            return True
        trigger_platforms = getattr(descriptor.trigger, "platforms", [])
        if isinstance(trigger_platforms, list):
            normalized = cls._normalized_platform_names(trigger_platforms)
            if normalized and normalized_platform not in normalized:
                return False
        for filter_spec in descriptor.filters:
            if not cls._filter_supports_platform(filter_spec, normalized_platform):
                return False
        return True

    @classmethod
    def _filter_supports_platform(cls, filter_spec, platform_name: str) -> bool:
        if isinstance(filter_spec, PlatformFilterSpec):
            normalized = {
                str(item).strip().lower()
                for item in filter_spec.platforms
                if str(item).strip()
            }
            return not normalized or platform_name in normalized
        if isinstance(filter_spec, CompositeFilterSpec):
            platform_children = [
                child
                for child in filter_spec.children
                if isinstance(child, PlatformFilterSpec | CompositeFilterSpec)
            ]
            if not platform_children:
                return True
            results = [
                cls._filter_supports_platform(child, platform_name)
                for child in platform_children
            ]
            if filter_spec.kind == "and":
                return all(results)
            return any(results)
        return True

    async def _load_or_reload_plugin(
        self,
        plugin: PluginSpec,
        *,
        load_order: int,
        reset_restart_budget: bool,
    ) -> None:
        current = self._records.get(plugin.name)
        if current is not None:
            current.state = SDK_STATE_RELOADING
            await self._cancel_plugin_requests(plugin.name)
            await self._teardown_plugin(plugin.name)

        disabled = bool(
            self._state_overrides.get(plugin.name, {}).get("disabled", False)
        )
        config_schema = load_plugin_config_schema(plugin)
        local_mcp_configs = self._load_local_mcp_configs(plugin)
        local_mcp_servers: dict[str, _LocalMCPServerRuntime] = {}
        for server_name, server_config in local_mcp_configs.items():
            local_mcp_servers[server_name] = _LocalMCPServerRuntime(
                name=server_name,
                config=dict(server_config),
                active=bool(server_config.get("active", True)),
            )

        record = SdkPluginRecord(
            plugin=plugin,
            load_order=load_order,
            state=SDK_STATE_DISABLED if disabled else SDK_STATE_ENABLED,
            unsupported_features=[],
            config_schema=config_schema,
            config=load_plugin_config(plugin, schema=config_schema),
            handlers=[],
            llm_tools={},
            active_llm_tools=set(),
            agents={},
            restart_attempted=False
            if reset_restart_budget
            else (current.restart_attempted if current is not None else False),
            issues=[dict(item) for item in self._discovery_issues.get(plugin.name, [])],
            local_mcp_servers=local_mcp_servers,
        )
        self._records[plugin.name] = record
        self._publish_plugin_skills(plugin.name)
        if disabled:
            self._persist_state_overrides()
            return

        try:

            def _schedule_closed(plugin_id: str = plugin.name) -> None:
                asyncio.create_task(self._handle_worker_closed(plugin_id))

            session = WorkerSession(
                plugin=plugin,
                repo_root=Path(__file__).resolve().parents[3],
                env_manager=self.env_manager,
                capability_router=self.capability_bridge,
                on_closed=_schedule_closed,
            )
            await session.start()
            session.start_close_watch()
            record.session = session
            remote_metadata = (
                dict(session.peer.remote_metadata)
                if session.peer is not None
                and isinstance(session.peer.remote_metadata, dict)
                else {}
            )
            record.acknowledge_global_mcp_risk = bool(
                remote_metadata.get("acknowledge_global_mcp_risk", False)
            )
            unsupported_features: set[str] = set()
            for index, descriptor in enumerate(session.handlers):
                if (
                    isinstance(descriptor.trigger, EventTrigger)
                    and descriptor.trigger.event_type not in SUPPORTED_SYSTEM_EVENTS
                ):
                    unsupported_features.add("event_trigger")
                record.handlers.append(
                    SdkHandlerRef(
                        descriptor=descriptor,
                        declaration_order=index,
                    )
                )
            for item in session.llm_tools:
                if not isinstance(item, dict):
                    continue
                plugin_name = str(item.get("plugin_id") or plugin.name)
                if plugin_name != plugin.name:
                    continue
                normalized = dict(item)
                normalized.pop("plugin_id", None)
                spec = LLMToolSpec.from_payload(normalized)
                record.llm_tools[spec.name] = spec
                if spec.active:
                    record.active_llm_tools.add(spec.name)
            for item in session.agents:
                if not isinstance(item, dict):
                    continue
                plugin_name = str(item.get("plugin_id") or plugin.name)
                if plugin_name != plugin.name:
                    continue
                normalized = dict(item)
                normalized.pop("plugin_id", None)
                spec = AgentSpec.from_payload(normalized)
                record.agents[spec.name] = spec
            await self._register_schedule_handlers(record)
            await self._initialize_local_mcp_servers(record)
            record.issues.extend(issue.to_payload() for issue in session.issues)
            record.unsupported_features = sorted(unsupported_features)
            record.state = (
                SDK_STATE_UNSUPPORTED_PARTIAL
                if record.unsupported_features
                else SDK_STATE_ENABLED
            )
            record.failure_reason = ""
            registered_http_apis = self.list_http_apis(plugin.name)
            if registered_http_apis:
                api_base_url = self._public_http_url(f"/{plugin.name}")
                entry_route = self._plugin_entry_route(plugin.name)
                if entry_route is not None:
                    logger.info(
                        "SDK plugin HTTP routes ready: plugin=%s total=%s page=%s api_base=%s",
                        plugin.name,
                        len(registered_http_apis),
                        self._public_page_url(entry_route),
                        api_base_url,
                    )
                else:
                    logger.info(
                        "SDK plugin HTTP routes ready: plugin=%s total=%s api_base=%s",
                        plugin.name,
                        len(registered_http_apis),
                        api_base_url,
                    )
        except Exception as exc:
            record.session = None
            record.state = SDK_STATE_FAILED
            record.failure_reason = str(exc)
            record.issues.append(
                PluginDiscoveryIssue(
                    severity="error",
                    phase="load",
                    plugin_id=plugin.name,
                    message="插件 worker 启动失败",
                    details=str(exc),
                ).to_payload()
            )
            logger.warning("Failed to start SDK plugin %s: %s", plugin.name, exc)
        finally:
            self._persist_state_overrides()

    async def _teardown_plugin(self, plugin_id: str) -> None:
        record = self._records.get(plugin_id)
        self._http_routes.pop(plugin_id, None)
        self._session_waiters.pop(plugin_id, None)
        await self._unregister_schedule_jobs(plugin_id)
        await self._close_temporary_mcp_sessions(plugin_id)
        await self._clear_plugin_skills(
            plugin_id=plugin_id,
            record=record,
            reason="teardown",
        )
        if record is None or record.session is None:
            if record is not None:
                await self._shutdown_local_mcp_servers(record)
            return
        try:
            await self._shutdown_local_mcp_servers(record)
            await record.session.stop()
        finally:
            record.session = None

    async def _register_schedule_handlers(self, record: SdkPluginRecord) -> None:
        cron_manager = getattr(self.star_context, "cron_manager", None)
        if cron_manager is None:
            return
        for handler in record.handlers:
            trigger = handler.descriptor.trigger
            if not isinstance(trigger, ScheduleTrigger):
                continue
            schedule_key = f"{record.plugin_id}:{handler.handler_id}"
            job_ref: dict[str, Any] = {"job": None}
            job = await cron_manager.add_basic_job(
                name=trigger.name or schedule_key,
                cron_expression=trigger.cron,
                interval_seconds=trigger.interval_seconds,
                handler=self._build_schedule_runner(
                    plugin_id=record.plugin_id,
                    handler_id=handler.handler_id,
                    trigger=trigger,
                    job_ref=job_ref,
                ),
                description=handler.descriptor.description
                or f"SDK schedule handler {handler.handler_id}",
                timezone=trigger.timezone,
                enabled=True,
                persistent=False,
            )
            job_ref["job"] = job
            self._schedule_job_ids.setdefault(record.plugin_id, set()).add(job.job_id)

    async def _unregister_schedule_jobs(self, plugin_id: str) -> None:
        cron_manager = getattr(self.star_context, "cron_manager", None)
        if cron_manager is None:
            return
        for job_id in list(self._schedule_job_ids.pop(plugin_id, set())):
            try:
                await cron_manager.delete_job(job_id)
            except Exception:
                logger.debug("Failed to remove SDK schedule job {}", job_id)

    def _build_schedule_runner(
        self,
        *,
        plugin_id: str,
        handler_id: str,
        trigger: ScheduleTrigger,
        job_ref: dict[str, Any] | None = None,
    ):
        async def _run(**_scheduler_payload: Any) -> None:
            # CronJobManager stores scheduler metadata such as interval_seconds in the
            # job payload and replays that payload into basic handlers. SDK schedule
            # handlers do not consume those transport-level kwargs, so the bridge
            # must swallow them here and only forward the synthesized schedule event.
            invoke_kwargs = {
                "plugin_id": plugin_id,
                "handler_id": handler_id,
                "trigger": trigger,
            }
            job = (job_ref or {}).get("job")
            if job is not None:
                invoke_kwargs["job"] = job
            await self._invoke_schedule_handler(
                **invoke_kwargs,
            )

        return _run

    def _set_discovery_issues(self, issues: list[PluginDiscoveryIssue]) -> None:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for issue in issues:
            grouped.setdefault(issue.plugin_id, []).append(issue.to_payload())
        self._discovery_issues = grouped

    # TODO: 平台适配器目前仍用 legacy 的 @register_platform_adapter，不走 SDK 协议。
    # 长期来看可以把平台适配器也纳入 SDK 的 capability 体系，实现完全统一的插件/平台注册机制。
    # 但是目前先保持现状，等平台适配器的 SDK 能力稳定后再做迁移，以避免不必要的重复开发和潜在风险。
    async def _refresh_native_platform_commands(
        self, platforms: set[str] | None = None
    ) -> None:
        platform_manager = getattr(self.star_context, "platform_manager", None)
        if platform_manager is None:
            return
        refresh_commands = getattr(platform_manager, "refresh_native_commands", None)
        if not callable(refresh_commands):
            return
        refresh_commands_async = cast(
            Callable[..., Awaitable[Any]],
            refresh_commands,
        )
        try:
            await refresh_commands_async(platforms=platforms)
        except Exception as exc:
            logger.warning("Failed to refresh native platform commands: %s", exc)

    async def _invoke_schedule_handler(
        self,
        *,
        plugin_id: str,
        handler_id: str,
        trigger: ScheduleTrigger,
        job: Any | None = None,
    ) -> None:
        record = self._records.get(plugin_id)
        if (
            record is None
            or record.session is None
            or record.state
            in {SDK_STATE_DISABLED, SDK_STATE_FAILED, SDK_STATE_RELOADING}
        ):
            return
        dispatch_token = uuid.uuid4().hex
        request_id = f"sdk_schedule_{plugin_id}_{uuid.uuid4().hex}"
        self._ensure_request_overlay(dispatch_token, should_call_llm=False)
        self._request_contexts[dispatch_token] = _RequestContext(
            plugin_id=plugin_id,
            request_id=request_id,
            dispatch_token=dispatch_token,
            dispatch_state=None,
        )
        self._track_request_scope(
            dispatch_token=dispatch_token,
            request_id=request_id,
            plugin_id=plugin_id,
        )
        payload = self._build_schedule_payload(
            plugin_id=plugin_id,
            handler_id=handler_id,
            trigger=trigger,
            job=job,
        )
        try:
            await record.session.invoke_handler(
                handler_id,
                payload,
                request_id=request_id,
                args={},
            )
        except Exception as exc:
            logger.warning(
                "SDK schedule handler failed: plugin=%s handler=%s error=%s",
                plugin_id,
                handler_id,
                exc,
            )
        finally:
            # 无论调度 handler 成功与否，都要关闭 overlay，
            # 防止已结束的调度任务一直占用 overlay 槽位导致内存泄漏
            self._close_request_overlay(dispatch_token)

    @staticmethod
    def _build_schedule_payload(
        *,
        plugin_id: str,
        handler_id: str,
        trigger: ScheduleTrigger,
        job: Any | None = None,
    ) -> dict[str, Any]:
        scheduled_at = datetime.now(timezone.utc).isoformat()
        job_name = str(getattr(job, "name", "")).strip() or f"{plugin_id}:{handler_id}"
        job_id = str(getattr(job, "job_id", "")).strip() or None
        description = getattr(job, "description", None)
        if description is not None:
            description = str(description).strip() or None
        job_type = str(getattr(job, "job_type", "")).strip() or "basic"
        timezone_name = getattr(job, "timezone", None)
        if isinstance(timezone_name, str):
            timezone_name = timezone_name.strip() or None
        else:
            timezone_name = None
        if timezone_name is None:
            timezone_name = trigger.timezone
        return {
            "type": "schedule",
            "event_type": "schedule",
            "text": "",
            "session_id": "",
            "platform": "",
            "platform_id": "",
            "message_type": "other",
            "sender_name": "",
            "self_id": "",
            "raw": {"event_type": "schedule"},
            "schedule": {
                "schedule_id": f"{plugin_id}:{handler_id}",
                "job_id": job_id,
                "plugin_id": plugin_id,
                "handler_id": handler_id,
                "name": job_name,
                "description": description,
                "job_type": job_type,
                "trigger_kind": "cron" if trigger.cron is not None else "interval",
                "cron": trigger.cron,
                "interval_seconds": trigger.interval_seconds,
                "timezone": timezone_name,
                "scheduled_at": scheduled_at,
            },
        }

    async def _cancel_plugin_requests(self, plugin_id: str) -> None:
        requests = list(self._plugin_requests.get(plugin_id, {}).values())
        for inflight in requests:
            request_context = self._request_contexts.get(inflight.dispatch_token)
            if request_context is not None:
                request_context.cancelled = True
            self._close_request_overlay(inflight.dispatch_token)
            record = self._records.get(plugin_id)
            if (
                record is not None
                and record.session is not None
                and record.session.peer is not None
                and not inflight.task.done()
            ):
                try:
                    await record.session.cancel(inflight.request_id)
                except Exception:
                    logger.debug(
                        "Failed to forward SDK cancel for %s", inflight.request_id
                    )
                inflight.task.cancel()
            else:
                inflight.logical_cancelled = True
        self._plugin_requests.pop(plugin_id, None)

    async def _handle_worker_closed(self, plugin_id: str) -> None:
        await self.lifecycle.handle_worker_closed(plugin_id)

    def _record_to_dashboard_item(self, record: SdkPluginRecord) -> dict[str, Any]:
        manifest = record.plugin.manifest_data
        support_platforms = manifest.get("support_platforms")
        installed_at = None
        try:
            installed_at = datetime.fromtimestamp(
                record.plugin.plugin_dir.stat().st_mtime,
                timezone.utc,
            ).isoformat()
        except OSError:
            installed_at = None
        handlers = [
            self._handler_to_dashboard_item(handler) for handler in record.handlers
        ]
        return {
            "name": record.plugin_id,
            "repo": str(manifest.get("repo") or ""),
            "author": str(manifest.get("author") or ""),
            "desc": str(manifest.get("desc") or manifest.get("description") or ""),
            "version": str(manifest.get("version") or "0.0.0"),
            "reserved": False,
            "activated": record.state not in {SDK_STATE_DISABLED, SDK_STATE_FAILED},
            "online_vesion": "",
            "handlers": handlers,
            "display_name": str(manifest.get("display_name") or record.plugin_id),
            "logo": None,
            "support_platforms": [
                str(item) for item in support_platforms if isinstance(item, str)
            ]
            if isinstance(support_platforms, list)
            else [],
            "astrbot_version": (
                str(manifest.get("astrbot_version"))
                if manifest.get("astrbot_version") is not None
                else ""
            ),
            "installed_at": installed_at,
            "runtime_kind": "sdk",
            "source_kind": "local_dir",
            "managed_by": "sdk_bridge",
            "state": record.state,
            "trigger_summary": [item["cmd"] for item in handlers],
            "unsupported_features": list(record.unsupported_features),
            "failure_reason": record.failure_reason,
            "issues": [dict(item) for item in record.issues],
        }

    def _failed_issue_to_dashboard_item(
        self,
        plugin_id: str,
        issues: list[dict[str, Any]],
    ) -> dict[str, Any]:
        issue = issues[0] if issues else {}
        failure_reason = str(issue.get("details") or issue.get("message") or "")
        return {
            "name": plugin_id,
            "repo": "",
            "author": "",
            "desc": str(issue.get("message", "")),
            "version": "0.0.0",
            "reserved": False,
            "activated": False,
            "online_vesion": "",
            "handlers": [],
            "display_name": plugin_id,
            "logo": None,
            "support_platforms": [],
            "astrbot_version": "",
            "installed_at": None,
            "runtime_kind": "sdk",
            "source_kind": "local_dir",
            "managed_by": "sdk_bridge",
            "state": SDK_STATE_FAILED,
            "trigger_summary": [],
            "unsupported_features": [],
            "failure_reason": failure_reason,
            "issues": [dict(item) for item in issues],
        }

    def _handler_to_dashboard_item(self, handler: SdkHandlerRef) -> dict[str, Any]:
        trigger = handler.descriptor.trigger
        description = self._descriptor_description(handler.descriptor)
        if not description and isinstance(trigger, CommandTrigger):
            description = f"Command: {trigger.command}"
        if not description:
            description = "无描述"
        if isinstance(trigger, CommandTrigger):
            event_type = "SDKCommandEvent"
            event_type_h = "SDK 指令触发"
        elif isinstance(trigger, MessageTrigger):
            event_type = "SDKMessageEvent"
            event_type_h = "SDK 消息触发"
        elif isinstance(trigger, EventTrigger):
            event_type = "SDKEventTrigger"
            event_type_h = "SDK 事件触发"
        elif isinstance(trigger, ScheduleTrigger):
            event_type = "SDKScheduleEvent"
            event_type_h = "SDK 定时触发"
        else:
            event_type = "SDKHandler"
            event_type_h = "SDK 行为触发"

        base = {
            "event_type": event_type,
            "event_type_h": event_type_h,
            "handler_full_name": handler.handler_id,
            "desc": description,
            "handler_name": handler.handler_name,
            "has_admin": handler.descriptor.permissions.require_admin,
        }
        if isinstance(trigger, CommandTrigger):
            return {**base, "type": "指令", "cmd": trigger.command}
        if isinstance(trigger, MessageTrigger):
            if trigger.regex:
                return {**base, "type": "正则匹配", "cmd": trigger.regex}
            if trigger.keywords:
                return {**base, "type": "关键词", "cmd": ", ".join(trigger.keywords)}
            return {**base, "type": "消息", "cmd": "任意消息"}
        if isinstance(trigger, EventTrigger):
            return {**base, "type": "事件", "cmd": trigger.event_type}
        if isinstance(trigger, ScheduleTrigger):
            return {
                **base,
                "type": "定时",
                "cmd": trigger.cron or str(trigger.interval_seconds),
            }
        return {**base, "type": "未知", "cmd": "未知"}

    def _load_state_overrides(self) -> dict[str, dict[str, Any]]:
        if not self.state_path.exists():
            return {}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        plugins = data.get("plugins")
        return dict(plugins) if isinstance(plugins, dict) else {}

    def _persist_state_overrides(self) -> None:
        self.state_path.write_text(
            json.dumps(
                {"plugins": self._state_overrides}, ensure_ascii=False, indent=2
            ),
            encoding="utf-8",
        )

    def _set_disabled_override(self, plugin_id: str, *, disabled: bool) -> None:
        plugin_state = dict(self._state_overrides.get(plugin_id, {}))
        if disabled:
            plugin_state["disabled"] = True
            self._state_overrides[plugin_id] = plugin_state
        else:
            plugin_state.pop("disabled", None)
            if plugin_state:
                self._state_overrides[plugin_id] = plugin_state
            else:
                self._state_overrides.pop(plugin_id, None)
        self._persist_state_overrides()

    def _discover_plugins(self):
        return discover_plugins(self.plugins_dir)

    def _snapshot_records(self) -> list[SdkPluginRecord]:
        """Preserve compatibility for callers that replace ``bridge._records``."""
        if self._records is self._store.records:
            return self._store.snapshot_records()
        return list(self._records.values())

    def _snapshot_records_sorted(self) -> list[SdkPluginRecord]:
        """Mirror store ordering even when tests inject a plain record mapping."""
        if self._records is self._store.records:
            return self._store.snapshot_records_sorted()
        return sorted(self._records.values(), key=lambda item: item.load_order)

    @staticmethod
    def _make_mcp_client() -> MCPClient:
        return MCPClient()

    @staticmethod
    def _make_skill_manager() -> SkillManager:
        return SkillManager()

    @staticmethod
    def _get_dashboard_config():
        return astrbot_config

    @staticmethod
    def _normalize_http_route(route: str) -> str:
        route_text = str(route).strip()
        if not route_text:
            raise AstrBotError.invalid_input("http route must not be empty")
        if not route_text.startswith("/"):
            route_text = f"/{route_text}"
        return route_text

    @staticmethod
    def _normalize_http_methods(methods: list[str]) -> tuple[str, ...]:
        normalized = tuple(
            sorted({str(method).upper() for method in methods if method})
        )
        if not normalized:
            raise AstrBotError.invalid_input("http methods must not be empty")
        return normalized

    def _ensure_http_route_available(
        self,
        *,
        plugin_id: str,
        route: str,
        methods: tuple[str, ...],
    ) -> None:
        for legacy_route, _view_handler, legacy_methods, _desc in getattr(
            self.star_context, "registered_web_apis", []
        ):
            if route != legacy_route:
                continue
            if set(methods) & {str(method).upper() for method in legacy_methods}:
                raise AstrBotError.invalid_input(
                    f"HTTP route conflict with legacy plugin route: {route}"
                )
        for owner, entries in self._http_routes.items():
            for entry in entries:
                if (
                    owner == plugin_id
                    and entry.route == route
                    and entry.methods == methods
                ):
                    continue
                if entry.route != route:
                    continue
                if set(entry.methods) & set(methods):
                    raise AstrBotError.invalid_input(
                        f"HTTP route conflict with SDK plugin route: {route}"
                    )

    def _resolve_http_route(
        self,
        route: str,
        method: str,
    ) -> tuple[SdkPluginRecord, SdkHttpRoute] | None:
        normalized_route = self._normalize_http_route(route)
        normalized_method = str(method).upper()
        for record in sorted(self._records.values(), key=lambda item: item.load_order):
            for entry in self._http_routes.get(record.plugin_id, []):
                if (
                    entry.route == normalized_route
                    and normalized_method in entry.methods
                ):
                    return record, entry
        return None

    def _match_waiter_plugins(self, session_key: str) -> list[SdkPluginRecord]:
        matches: list[SdkPluginRecord] = []
        for record in sorted(self._records.values(), key=lambda item: item.load_order):
            if session_key in self._session_waiters.get(record.plugin_id, set()):
                matches.append(record)
        return matches

    async def _dispatch_waiter_event(
        self,
        event: AstrMessageEvent,
        records: list[SdkPluginRecord],
    ) -> SdkDispatchResult:
        return await self.dispatch_engine.dispatch_waiter_event(event, records)
