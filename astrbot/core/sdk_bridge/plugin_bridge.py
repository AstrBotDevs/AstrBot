from __future__ import annotations

import asyncio
import contextlib
import copy
import json
import os
import re
import signal
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.llm.agents import AgentSpec
from astrbot_sdk.llm.entities import LLMToolSpec
from astrbot_sdk.message.components import component_to_payload_sync
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
from quart import request as quart_request

from astrbot.core import logger
from astrbot.core.agent.mcp_client import MCPClient
from astrbot.core.message.message_event_result import MessageChain, MessageEventResult
from astrbot.core.message.message_types import sdk_message_type
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import LLMResponse as CoreLLMResponse
from astrbot.core.provider.entities import ProviderRequest as CoreProviderRequest
from astrbot.core.skills.skill_manager import (
    SkillManager,
    _parse_frontmatter_description,
)
from astrbot.core.utils.astrbot_path import (
    get_astrbot_data_path,
    get_astrbot_plugin_data_path,
)

from .bridge_base import _build_message_chain_from_payload
from .capability_bridge import CoreCapabilityBridge
from .event_payload import (
    InboundEventSnapshot,
    build_inbound_event_snapshot,
    extract_sdk_handler_result,
    normalize_sdk_local_extras,
    sanitize_sdk_extras,
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


@dataclass(slots=True)
class SdkHandlerRef:
    descriptor: HandlerDescriptor
    declaration_order: int

    @property
    def handler_id(self) -> str:
        return self.descriptor.id

    @property
    def handler_name(self) -> str:
        return self.descriptor.id.rsplit(".", 1)[-1]


@dataclass(slots=True)
class SdkDispatchResult:
    matched_handlers: list[dict[str, str]] = field(default_factory=list)
    executed_handlers: list[dict[str, str]] = field(default_factory=list)
    sent_message: bool = False
    stopped: bool = False
    skipped_reason: str | None = None


@dataclass(slots=True)
class _DispatchState:
    event: AstrMessageEvent
    sent_message: bool = False
    stopped: bool = False


@dataclass(slots=True)
class _RequestContext:
    plugin_id: str
    request_id: str
    dispatch_token: str
    dispatch_state: _DispatchState | None
    cancelled: bool = False

    @property
    def has_event(self) -> bool:
        return self.dispatch_state is not None

    @property
    def event(self) -> AstrMessageEvent:
        if self.dispatch_state is None:
            raise AstrBotError.invalid_input(
                "The current SDK request is not bound to a message event"
            )
        return self.dispatch_state.event


@dataclass(slots=True)
class _InFlightRequest:
    request_id: str
    dispatch_token: str
    task: asyncio.Task[dict[str, Any]]
    logical_cancelled: bool = False


@dataclass(slots=True)
class _LocalMCPServerRuntime:
    name: str
    config: dict[str, Any]
    active: bool
    running: bool = False
    client: MCPClient | None = None
    tools: list[str] = field(default_factory=list)
    tool_specs: list[LLMToolSpec] = field(default_factory=list)
    errlogs: list[str] = field(default_factory=list)
    last_error: str | None = None
    ready_event: asyncio.Event = field(default_factory=asyncio.Event)
    connect_task: asyncio.Task[None] | None = None
    lease_path: Path | None = None


@dataclass(slots=True)
class _TemporaryMCPSessionRuntime:
    plugin_id: str
    name: str
    client: MCPClient
    tools: list[str]


@dataclass(slots=True)
class _RequestOverlayState:
    dispatch_token: str
    should_call_llm: bool
    requested_llm: bool = False
    sdk_local_extras: dict[str, Any] = field(default_factory=dict)
    inbound_snapshot: InboundEventSnapshot | None = None
    result_payload: dict[str, Any] | None = None
    result_object: MessageEventResult | None = None
    result_is_set: bool = False
    result_stopped: bool = False
    handler_whitelist: set[str] | None = None
    request_scope_ids: set[str] = field(default_factory=set)
    closed: bool = False
    cleanup_task: asyncio.Task[None] | None = None


@dataclass(slots=True)
class _EventResultBinding:
    bridge: SdkPluginBridge
    dispatch_token: str

    def is_active(self) -> bool:
        return self.bridge.get_request_overlay_by_token(self.dispatch_token) is not None

    def has_result_state(self) -> bool:
        overlay = self.bridge.get_request_overlay_by_token(self.dispatch_token)
        return bool(overlay is not None and overlay.result_is_set)

    def get_result(self) -> MessageEventResult | None:
        return self.bridge._get_effective_result_for_token(self.dispatch_token)

    def set_result(self, result: MessageEventResult) -> None:
        self.bridge._set_result_for_dispatch_token(self.dispatch_token, result)

    def clear_result(self) -> None:
        self.bridge._clear_result_for_dispatch_token(self.dispatch_token)

    def stop_event(self) -> None:
        self.bridge._stop_event_for_dispatch_token(self.dispatch_token)

    def continue_event(self) -> None:
        self.bridge._continue_event_for_dispatch_token(self.dispatch_token)

    def is_stopped(self) -> bool:
        return self.bridge._is_stopped_for_dispatch_token(self.dispatch_token)


@dataclass(slots=True)
class SdkPluginRecord:
    plugin: PluginSpec
    load_order: int
    state: str
    unsupported_features: list[str]
    config_schema: dict[str, Any]
    config: dict[str, Any]
    handlers: list[SdkHandlerRef]
    llm_tools: dict[str, LLMToolSpec] = field(default_factory=dict)
    active_llm_tools: set[str] = field(default_factory=set)
    agents: dict[str, AgentSpec] = field(default_factory=dict)
    skills: dict[str, SdkRegisteredSkill] = field(default_factory=dict)
    dynamic_command_routes: list[SdkDynamicCommandRoute] = field(default_factory=list)
    session: WorkerSession | None = None
    restart_attempted: bool = False
    failure_reason: str = ""
    issues: list[dict[str, Any]] = field(default_factory=list)
    local_mcp_servers: dict[str, _LocalMCPServerRuntime] = field(default_factory=dict)
    acknowledge_global_mcp_risk: bool = False

    @property
    def plugin_id(self) -> str:
        return self.plugin.name


@dataclass(slots=True)
class SdkHttpRoute:
    plugin_id: str
    route: str
    methods: tuple[str, ...]
    handler_capability: str
    description: str


@dataclass(slots=True)
class SdkRegisteredSkill:
    name: str
    description: str
    skill_dir: Path
    skill_md_path: Path

    def to_registry_payload(self) -> dict[str, str]:
        return {
            "name": self.name,
            "description": self.description,
            "path": str(self.skill_md_path),
            "skill_dir": str(self.skill_dir),
        }


@dataclass(slots=True)
class SdkDynamicCommandRoute:
    command_name: str
    handler_full_name: str
    desc: str
    priority: int
    use_regex: bool
    declaration_order: int


class SdkPluginBridge:
    def __init__(self, star_context) -> None:
        self.star_context = star_context
        self.plugins_dir = Path(get_astrbot_data_path()) / "sdk_plugins"
        self.state_path = Path(get_astrbot_data_path()) / "sdk_plugins_state.json"
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self._started = False
        self._stopping = False
        self._state_overrides = self._load_state_overrides()
        self.env_manager = PluginEnvironmentManager(Path(__file__).resolve().parents[3])
        self.capability_bridge = CoreCapabilityBridge(
            star_context=star_context,
            plugin_bridge=self,
        )
        self._records: dict[str, SdkPluginRecord] = {}
        self._request_contexts: dict[str, _RequestContext] = {}
        self._request_id_to_token: dict[str, str] = {}
        self._request_plugin_ids: dict[str, str] = {}
        self._request_overlays: dict[str, _RequestOverlayState] = {}
        self._plugin_requests: dict[str, dict[str, _InFlightRequest]] = {}
        self._http_routes: dict[str, list[SdkHttpRoute]] = {}
        self._session_waiters: dict[str, set[str]] = {}
        self._schedule_job_ids: dict[str, set[str]] = {}
        self._discovery_issues: dict[str, list[dict[str, Any]]] = {}
        self._temporary_mcp_sessions: dict[str, _TemporaryMCPSessionRuntime] = {}

    async def start(self) -> None:
        if self._started:
            return
        self._sweep_stale_mcp_leases()
        await self.reload_all(reset_restart_budget=True)
        self._started = True

    async def stop(self) -> None:
        if not self._started and not self._records:
            return
        self._stopping = True
        for plugin_id in list(self._records.keys()):
            await self._cancel_plugin_requests(plugin_id)
            await self._close_temporary_mcp_sessions(plugin_id)
        for record in list(self._records.values()):
            await self._shutdown_local_mcp_servers(record)
            if record.session is not None:
                await record.session.stop()
                record.session = None
        self._records.clear()
        self._request_contexts.clear()
        self._request_id_to_token.clear()
        self._request_plugin_ids.clear()
        for overlay in list(self._request_overlays.values()):
            if overlay.cleanup_task is not None:
                overlay.cleanup_task.cancel()
        self._request_overlays.clear()
        self._plugin_requests.clear()
        self._http_routes.clear()
        self._session_waiters.clear()
        self._schedule_job_ids.clear()
        self._temporary_mcp_sessions.clear()
        self._started = False
        self._stopping = False

    async def reload_all(self, *, reset_restart_budget: bool = False) -> None:
        discovered = discover_plugins(self.plugins_dir)
        self._set_discovery_issues(discovered.issues)
        self.env_manager.plan(discovered.plugins)
        known = {plugin.name for plugin in discovered.plugins}
        SkillManager().prune_sdk_plugin_skills(known)
        for plugin_id in list(self._records.keys()):
            if plugin_id not in known:
                await self._teardown_plugin(plugin_id)
                self._records.pop(plugin_id, None)
        for load_order, plugin in enumerate(discovered.plugins):
            await self._load_or_reload_plugin(
                plugin,
                load_order=load_order,
                reset_restart_budget=reset_restart_budget,
            )
        await self._refresh_native_platform_commands({"telegram"})

    async def reload_plugin(self, plugin_id: str) -> None:
        discovered = discover_plugins(self.plugins_dir)
        self._set_discovery_issues(discovered.issues)
        self.env_manager.plan(discovered.plugins)
        for load_order, plugin in enumerate(discovered.plugins):
            if plugin.name != plugin_id:
                continue
            await self._load_or_reload_plugin(
                plugin,
                load_order=load_order,
                reset_restart_budget=True,
            )
            await self._refresh_native_platform_commands({"telegram"})
            return
        raise ValueError(f"SDK plugin not found: {plugin_id}")

    async def turn_off_plugin(self, plugin_id: str) -> None:
        record = self._records.get(plugin_id)
        if record is None:
            raise ValueError(f"SDK plugin not found: {plugin_id}")
        record.state = SDK_STATE_DISABLED
        await self._cancel_plugin_requests(plugin_id)
        await self._teardown_plugin(plugin_id)
        record.failure_reason = ""
        self._set_disabled_override(plugin_id, disabled=True)
        await self._refresh_native_platform_commands({"telegram"})

    async def turn_on_plugin(self, plugin_id: str) -> None:
        discovered = discover_plugins(self.plugins_dir)
        self._set_discovery_issues(discovered.issues)
        self.env_manager.plan(discovered.plugins)
        for load_order, plugin in enumerate(discovered.plugins):
            if plugin.name != plugin_id:
                continue
            self._set_disabled_override(plugin_id, disabled=False)
            await self._load_or_reload_plugin(
                plugin,
                load_order=load_order,
                reset_restart_budget=True,
            )
            await self._refresh_native_platform_commands({"telegram"})
            return
        raise ValueError(f"SDK plugin not found: {plugin_id}")

    def list_plugins(self) -> list[dict[str, Any]]:
        records = sorted(self._records.values(), key=lambda item: item.load_order)
        items = [self._record_to_dashboard_item(record) for record in records]
        for plugin_id, issues in sorted(self._discovery_issues.items()):
            if plugin_id in self._records:
                continue
            items.append(self._failed_issue_to_dashboard_item(plugin_id, issues))
        return items

    def get_plugin_metadata(self, plugin_id: str) -> dict[str, Any] | None:
        record = self._records.get(plugin_id)
        if record is not None:
            manifest = record.plugin.manifest_data
            support_platforms = manifest.get("support_platforms")
            return {
                "name": plugin_id,
                "display_name": str(manifest.get("display_name") or plugin_id),
                "description": str(
                    manifest.get("desc") or manifest.get("description") or ""
                ),
                "author": str(manifest.get("author") or ""),
                "version": str(manifest.get("version") or "0.0.0"),
                "enabled": record.state not in {SDK_STATE_DISABLED, SDK_STATE_FAILED},
                "support_platforms": [
                    str(item) for item in support_platforms if isinstance(item, str)
                ]
                if isinstance(support_platforms, list)
                else [],
                "astrbot_version": (
                    str(manifest.get("astrbot_version"))
                    if manifest.get("astrbot_version") is not None
                    else None
                ),
                "runtime_kind": "sdk",
                "issues": [dict(item) for item in record.issues],
            }
        for plugin in self.star_context.get_all_stars():
            if plugin.name == plugin_id:
                return {
                    "name": plugin.name,
                    "display_name": plugin.display_name,
                    "description": plugin.desc,
                    "author": plugin.author,
                    "version": plugin.version,
                    "enabled": plugin.activated,
                    "support_platforms": list(plugin.support_platforms),
                    "astrbot_version": plugin.astrbot_version,
                    "runtime_kind": "legacy",
                }
        if plugin_id in self._discovery_issues:
            issue = self._discovery_issues[plugin_id][0]
            return {
                "name": plugin_id,
                "display_name": plugin_id,
                "description": str(issue.get("message", "")),
                "author": "",
                "version": "0.0.0",
                "enabled": False,
                "support_platforms": [],
                "astrbot_version": None,
                "runtime_kind": "sdk",
                "issues": [dict(item) for item in self._discovery_issues[plugin_id]],
            }
        return None

    def list_plugin_metadata(self) -> list[dict[str, Any]]:
        metadata = []
        for plugin in self.star_context.get_all_stars():
            metadata.append(
                {
                    "name": plugin.name,
                    "display_name": plugin.display_name,
                    "description": plugin.desc,
                    "author": plugin.author,
                    "version": plugin.version,
                    "enabled": plugin.activated,
                    "support_platforms": list(plugin.support_platforms),
                    "astrbot_version": plugin.astrbot_version,
                    "runtime_kind": "legacy",
                }
            )
        for plugin_id in sorted(self._records.keys()):
            plugin_metadata = self.get_plugin_metadata(plugin_id)
            if plugin_metadata is not None:
                metadata.append(plugin_metadata)
        for plugin_id in sorted(self._discovery_issues.keys()):
            if plugin_id in self._records:
                continue
            plugin_metadata = self.get_plugin_metadata(plugin_id)
            if plugin_metadata is not None:
                metadata.append(plugin_metadata)
        return metadata

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
        runtime = self._local_mcp_record(plugin_id, name)
        if runtime is None:
            return None
        return self._serialize_local_mcp_server(runtime)

    def list_local_mcp_servers(self, plugin_id: str) -> list[dict[str, Any]]:
        record = self._records.get(plugin_id)
        if record is None:
            return []
        return [
            self._serialize_local_mcp_server(runtime)
            for runtime in sorted(
                record.local_mcp_servers.values(),
                key=lambda item: item.name,
            )
        ]

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
        record = self._records.get(plugin_id)
        if record is None:
            raise AstrBotError.invalid_input(f"Unknown SDK plugin: {plugin_id}")

        skill_name = str(name).strip()
        if not skill_name or not SDK_SKILL_NAME_RE.fullmatch(skill_name):
            raise AstrBotError.invalid_input(
                "skill.register requires a name matching [A-Za-z0-9._-]+"
            )

        path_text = str(path).strip()
        if not path_text:
            raise AstrBotError.invalid_input("skill.register requires path")

        plugin_root = record.plugin.plugin_dir.resolve()
        requested_path = Path(path_text)
        resolved_path = (
            requested_path.resolve()
            if requested_path.is_absolute()
            else (plugin_root / requested_path).resolve()
        )

        skill_dir = resolved_path if resolved_path.is_dir() else resolved_path.parent
        skill_md_path = (
            resolved_path / "SKILL.md" if resolved_path.is_dir() else resolved_path
        )
        if skill_md_path.name != "SKILL.md" or not skill_md_path.is_file():
            raise AstrBotError.invalid_input(
                "skill.register path must point to a skill directory containing SKILL.md or to SKILL.md itself"
            )
        if not skill_dir.is_dir():
            raise AstrBotError.invalid_input(
                "skill.register resolved skill_dir is not a directory"
            )
        if not skill_md_path.is_relative_to(plugin_root):
            raise AstrBotError.invalid_input(
                "skill.register path must stay inside the plugin directory"
            )

        normalized_description = str(description).strip()
        if not normalized_description:
            try:
                normalized_description = _parse_frontmatter_description(
                    skill_md_path.read_text(encoding="utf-8")
                )
            except Exception:
                normalized_description = ""

        record.skills[skill_name] = SdkRegisteredSkill(
            name=skill_name,
            description=normalized_description,
            skill_dir=skill_dir,
            skill_md_path=skill_md_path,
        )
        self._publish_plugin_skills(plugin_id)
        return {
            "name": skill_name,
            "description": normalized_description,
            "path": str(skill_md_path),
            "skill_dir": str(skill_dir),
        }

    def unregister_skill(self, *, plugin_id: str, name: str) -> bool:
        record = self._records.get(plugin_id)
        if record is None:
            raise AstrBotError.invalid_input(f"Unknown SDK plugin: {plugin_id}")
        removed = record.skills.pop(str(name).strip(), None) is not None
        if removed:
            self._publish_plugin_skills(plugin_id)
        return removed

    def list_registered_skills(self, plugin_id: str) -> list[dict[str, str]]:
        record = self._records.get(plugin_id)
        if record is None:
            return []
        return [
            record.skills[name].to_registry_payload()
            for name in sorted(record.skills.keys())
        ]

    def _publish_plugin_skills(self, plugin_id: str) -> None:
        record = self._records.get(plugin_id)
        manager = SkillManager()
        if record is None or not record.skills:
            manager.remove_sdk_plugin_skills(plugin_id)
            return
        manager.replace_sdk_plugin_skills(
            plugin_id,
            [skill.to_registry_payload() for skill in record.skills.values()],
        )

    async def _clear_plugin_skills(
        self,
        *,
        plugin_id: str,
        record: SdkPluginRecord | Any | None,
        reason: str,
    ) -> None:
        if record is None or not getattr(record, "skills", None):
            return
        record.skills.clear()
        self._publish_plugin_skills(plugin_id)
        try:
            from astrbot.core.computer.computer_client import (
                sync_skills_to_active_sandboxes,
            )

            # Keep sandbox-visible skills aligned with the bridge registry so a
            # stopped plugin cannot continue exposing dead skill entries.
            await sync_skills_to_active_sandboxes()
        except Exception as exc:
            logger.warning(
                "Failed to sync skills after SDK plugin %s %s: %s",
                plugin_id,
                reason,
                exc,
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
        normalized_route = self._normalize_http_route(route)
        normalized_methods = self._normalize_http_methods(methods)
        if not handler_capability:
            raise AstrBotError.invalid_input(
                "http.register_api requires handler_capability"
            )
        self._ensure_http_route_available(
            plugin_id=plugin_id,
            route=normalized_route,
            methods=normalized_methods,
        )
        route_entry = SdkHttpRoute(
            plugin_id=plugin_id,
            route=normalized_route,
            methods=normalized_methods,
            handler_capability=handler_capability,
            description=description,
        )
        plugin_routes = [
            entry
            for entry in self._http_routes.get(plugin_id, [])
            if not (
                entry.route == normalized_route and entry.methods == normalized_methods
            )
        ]
        plugin_routes.append(route_entry)
        self._http_routes[plugin_id] = plugin_routes

    def unregister_http_api(
        self,
        *,
        plugin_id: str,
        route: str,
        methods: list[str],
    ) -> None:
        normalized_route = self._normalize_http_route(route)
        normalized_methods = {method.upper() for method in methods if method}
        updated: list[SdkHttpRoute] = []
        for entry in self._http_routes.get(plugin_id, []):
            if entry.route != normalized_route:
                updated.append(entry)
                continue
            if not normalized_methods:
                # Plugins do not have a separate "delete route" capability, so an
                # empty method list means "remove every method registered on route".
                continue
            remaining = tuple(
                method for method in entry.methods if method not in normalized_methods
            )
            if remaining:
                updated.append(
                    SdkHttpRoute(
                        plugin_id=entry.plugin_id,
                        route=entry.route,
                        methods=remaining,
                        handler_capability=entry.handler_capability,
                        description=entry.description,
                    )
                )
        if updated:
            self._http_routes[plugin_id] = updated
        else:
            self._http_routes.pop(plugin_id, None)

    def list_http_apis(self, plugin_id: str) -> list[dict[str, Any]]:
        return [
            {
                "route": entry.route,
                "methods": list(entry.methods),
                "handler_capability": entry.handler_capability,
                "description": entry.description,
            }
            for entry in self._http_routes.get(plugin_id, [])
        ]

    async def dispatch_http_request(
        self,
        route: str,
        method: str,
    ) -> dict[str, Any] | None:
        resolved = self._resolve_http_route(route, method)
        if resolved is None:
            return None
        record, route_entry = resolved
        if record.session is None:
            raise AstrBotError.invalid_input("SDK HTTP route worker is unavailable")
        text_body = await quart_request.get_data(as_text=True)
        payload = {
            "method": method.upper(),
            "route": route_entry.route,
            "path": quart_request.path,
            "query": quart_request.args.to_dict(flat=False),
            "headers": dict(quart_request.headers),
            "json_body": await quart_request.get_json(silent=True),
            "text_body": text_body,
        }
        output = await record.session.invoke_capability(
            route_entry.handler_capability,
            payload,
            request_id=f"sdk_http_{record.plugin_id}_{uuid.uuid4().hex}",
        )
        if not isinstance(output, dict):
            raise AstrBotError.invalid_input("SDK HTTP handler must return an object")
        return output

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
        result = SdkDispatchResult()
        if event.is_stopped():
            result.skipped_reason = SKIP_LEGACY_STOPPED
            return result
        if self._legacy_has_replied(event):
            result.skipped_reason = SKIP_LEGACY_REPLIED
            return result

        waiter_plugins = self._match_waiter_plugins(event.unified_msg_origin)
        if waiter_plugins:
            return await self._dispatch_waiter_event(event, waiter_plugins)

        dispatch_token = self._get_dispatch_token(event) or uuid.uuid4().hex
        self._bind_dispatch_token(event, dispatch_token)
        overlay = self._ensure_request_overlay(
            dispatch_token,
            should_call_llm=not bool(getattr(event, "call_llm", False)),
        )
        matches = self._match_handlers(event)
        permission_denied = self._resolve_command_permission_denied(event)
        if permission_denied is not None and not self._has_command_trigger_match(
            matches
        ):
            dispatch_state = _DispatchState(event=event)
            request_context = self._request_contexts.get(dispatch_token)
            if request_context is None:
                request_context = _RequestContext(
                    plugin_id=permission_denied["plugin_id"],
                    request_id="",
                    dispatch_token=dispatch_token,
                    dispatch_state=dispatch_state,
                )
                self._request_contexts[dispatch_token] = request_context
            else:
                request_context.plugin_id = permission_denied["plugin_id"]
                request_context.dispatch_state = dispatch_state
            self._set_sdk_origin_plugin_id(event, permission_denied["plugin_id"])
            event.set_result(MessageEventResult().message(permission_denied["message"]))
            event.stop_event()
            event.should_call_llm(True)
            overlay.should_call_llm = False
            result.stopped = True
            return result
        group_fallback = self._resolve_group_root_fallback(event)
        if group_fallback is not None and not self._has_command_trigger_match(matches):
            dispatch_state = _DispatchState(event=event)
            request_context = self._request_contexts.get(dispatch_token)
            if request_context is None:
                request_context = _RequestContext(
                    plugin_id=group_fallback["plugin_id"],
                    request_id="",
                    dispatch_token=dispatch_token,
                    dispatch_state=dispatch_state,
                )
                self._request_contexts[dispatch_token] = request_context
            else:
                request_context.plugin_id = group_fallback["plugin_id"]
                request_context.dispatch_state = dispatch_state
            self._set_sdk_origin_plugin_id(event, group_fallback["plugin_id"])
            event.set_result(MessageEventResult().message(group_fallback["help_text"]))
            event.stop_event()
            event.should_call_llm(True)
            overlay.should_call_llm = False
            result.stopped = True
            return result
        if not matches:
            result.skipped_reason = SKIP_NO_MATCH
            return result
        result.matched_handlers = [
            {"plugin_id": match.plugin_id, "handler_id": match.handler_id}
            for match in matches
        ]

        dispatch_state = _DispatchState(event=event)
        request_context = self._request_contexts.get(dispatch_token)
        if request_context is None:
            request_context = _RequestContext(
                plugin_id="",
                request_id="",
                dispatch_token=dispatch_token,
                dispatch_state=dispatch_state,
            )
            self._request_contexts[dispatch_token] = request_context
        else:
            request_context.dispatch_state = dispatch_state
        skipped_reason = None
        for match in matches:
            whitelist = (
                None
                if overlay.handler_whitelist is None
                else set(overlay.handler_whitelist)
            )
            if whitelist is not None and match.plugin_id not in whitelist:
                continue
            record = self._records.get(match.plugin_id)
            if record is None:
                continue
            if record.state == SDK_STATE_RELOADING:
                skipped_reason = skipped_reason or SKIP_SDK_RELOADING
                continue
            if (
                record.state in {SDK_STATE_FAILED, SDK_STATE_DISABLED}
                or record.session is None
            ):
                skipped_reason = skipped_reason or SKIP_WORKER_FAILED
                continue

            request_id = f"sdk_{record.plugin_id}_{uuid.uuid4().hex}"
            request_context.plugin_id = record.plugin_id
            request_context.request_id = request_id
            request_context.cancelled = False
            self._set_sdk_origin_plugin_id(event, record.plugin_id)
            setattr(event, "_sdk_last_request_id", request_id)
            payload = self._build_sdk_event_payload(
                event,
                dispatch_token=dispatch_token,
                plugin_id=record.plugin_id,
                request_id=request_id,
                overlay=overlay,
            )
            task = asyncio.create_task(
                record.session.invoke_handler(
                    match.handler_id,
                    payload,
                    request_id=request_id,
                    args=match.args,
                )
            )
            self._track_request_scope(
                dispatch_token=dispatch_token,
                request_id=request_id,
                plugin_id=record.plugin_id,
            )
            self._plugin_requests.setdefault(record.plugin_id, {})[request_id] = (
                _InFlightRequest(
                    request_id=request_id,
                    dispatch_token=dispatch_token,
                    task=task,
                )
            )

            try:
                output = await task
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "SDK handler failed: plugin=%s handler=%s error=%s",
                    record.plugin_id,
                    match.handler_id,
                    exc,
                )
                skipped_reason = skipped_reason or SKIP_WORKER_FAILED
                output = {}
            finally:
                inflight = self._plugin_requests.get(record.plugin_id, {}).pop(
                    request_id,
                    None,
                )

            if inflight is not None and inflight.logical_cancelled:
                continue

            handler_result = extract_sdk_handler_result(
                output if isinstance(output, dict) else {}
            )
            if isinstance(output, dict) and "sdk_local_extras" in output:
                self._persist_sdk_local_extras_from_handler(
                    overlay,
                    output.get("sdk_local_extras"),
                    plugin_id=record.plugin_id,
                    handler_id=match.handler_id,
                )
            result.executed_handlers.append(
                {"plugin_id": record.plugin_id, "handler_id": match.handler_id}
            )
            dispatch_state.sent_message = (
                dispatch_state.sent_message or handler_result["sent_message"]
            )
            dispatch_state.stopped = dispatch_state.stopped or handler_result["stop"]
            if handler_result["call_llm"]:
                overlay.requested_llm = True
                overlay.should_call_llm = True
            if handler_result["sent_message"] or handler_result["stop"]:
                overlay.should_call_llm = False
            if handler_result["stop"]:
                break

        result.sent_message = dispatch_state.sent_message
        result.stopped = dispatch_state.stopped
        if not result.executed_handlers:
            result.skipped_reason = skipped_reason or SKIP_NO_MATCH
        if result.sent_message:
            event._has_send_oper = True
            overlay.should_call_llm = False
            event.should_call_llm(True)
        if result.stopped:
            event.stop_event()
            overlay.should_call_llm = False
            event.should_call_llm(True)
        return result

    def resolve_request_plugin_id(self, request_id: str) -> str:
        plugin_id = self._request_plugin_ids.get(request_id)
        if plugin_id is not None:
            return plugin_id
        token = self._request_id_to_token.get(request_id)
        if token is not None and token in self._request_contexts:
            return self._request_contexts[token].plugin_id
        raise AstrBotError.invalid_input(f"Unknown SDK request id: {request_id}")

    def resolve_request_session(self, request_id: str) -> _RequestContext | None:
        token = self._request_id_to_token.get(request_id)
        if token is None:
            return None
        return self._request_contexts.get(token)

    def get_request_context_by_token(
        self, dispatch_token: str
    ) -> _RequestContext | None:
        return self._request_contexts.get(dispatch_token)

    def _bind_dispatch_token(
        self, event: AstrMessageEvent, dispatch_token: str
    ) -> None:
        setattr(event, "_sdk_dispatch_token", dispatch_token)
        setattr(
            event,
            "_sdk_result_binding",
            _EventResultBinding(bridge=self, dispatch_token=dispatch_token),
        )

    def _get_dispatch_token(self, event: AstrMessageEvent) -> str | None:
        token = getattr(event, "_sdk_dispatch_token", None)
        return str(token) if token else None

    def _schedule_overlay_cleanup(
        self, dispatch_token: str
    ) -> asyncio.Task[None] | None:
        async def _cleanup_later() -> None:
            try:
                await asyncio.sleep(OVERLAY_TIMEOUT_SECONDS)
            except asyncio.CancelledError:
                return
            self._close_request_overlay(dispatch_token)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None
        return loop.create_task(_cleanup_later())

    def _ensure_request_overlay(
        self,
        dispatch_token: str,
        *,
        should_call_llm: bool,
    ) -> _RequestOverlayState:
        overlay = self._request_overlays.get(dispatch_token)
        if overlay is not None:
            if overlay.closed:
                overlay.closed = False
            if overlay.cleanup_task is None or overlay.cleanup_task.done():
                overlay.cleanup_task = self._schedule_overlay_cleanup(dispatch_token)
            return overlay
        overlay = _RequestOverlayState(
            dispatch_token=dispatch_token,
            should_call_llm=should_call_llm,
            cleanup_task=self._schedule_overlay_cleanup(dispatch_token),
        )
        self._request_overlays[dispatch_token] = overlay
        return overlay

    def _track_request_scope(
        self,
        *,
        dispatch_token: str,
        request_id: str,
        plugin_id: str,
    ) -> None:
        # request-scoped system.event.* calls may outlive the original handler RPC
        # when plugin code moves follow-up work into background tasks.
        self._request_id_to_token[request_id] = dispatch_token
        self._request_plugin_ids[request_id] = plugin_id
        overlay = self._request_overlays.get(dispatch_token)
        if overlay is not None:
            overlay.request_scope_ids.add(request_id)

    def _close_request_overlay(self, dispatch_token: str) -> None:
        request_context = self._request_contexts.get(dispatch_token)
        bound_event = None
        dispatch_state = (
            getattr(request_context, "dispatch_state", None)
            if request_context is not None
            else None
        )
        if dispatch_state is not None:
            bound_event = dispatch_state.event
            bound_event._result = self._get_effective_result_for_token(dispatch_token)
            bound_event.call_llm = not self.get_effective_should_call_llm(bound_event)
            if hasattr(bound_event, "_sdk_result_binding"):
                delattr(bound_event, "_sdk_result_binding")
        overlay = self._request_overlays.pop(dispatch_token, None)
        if overlay is not None:
            overlay.closed = True
            if overlay.cleanup_task is not None:
                overlay.cleanup_task.cancel()
            for request_id in overlay.request_scope_ids:
                self._request_id_to_token.pop(request_id, None)
                self._request_plugin_ids.pop(request_id, None)
        request_context = self._request_contexts.pop(dispatch_token, None)
        if request_context is not None:
            request_context.cancelled = True

    def close_request_overlay_for_event(self, event: AstrMessageEvent) -> None:
        dispatch_token = self._get_dispatch_token(event)
        if not dispatch_token:
            return
        self._close_request_overlay(dispatch_token)

    def get_request_overlay_by_token(
        self, dispatch_token: str
    ) -> _RequestOverlayState | None:
        overlay = self._request_overlays.get(dispatch_token)
        if overlay is None or overlay.closed:
            return None
        return overlay

    def get_request_overlay_by_request_id(
        self, request_id: str
    ) -> _RequestOverlayState | None:
        token = self._request_id_to_token.get(request_id)
        if not token:
            return None
        return self.get_request_overlay_by_token(token)

    def request_llm_for_request(self, request_id: str) -> bool:
        overlay = self.get_request_overlay_by_request_id(request_id)
        if overlay is None:
            return False
        overlay.requested_llm = True
        if not overlay.result_stopped:
            overlay.should_call_llm = True
        return True

    def get_effective_should_call_llm(self, event: AstrMessageEvent) -> bool:
        dispatch_token = self._get_dispatch_token(event)
        if dispatch_token:
            overlay = self.get_request_overlay_by_token(dispatch_token)
            if overlay is not None:
                return overlay.should_call_llm
        return not bool(getattr(event, "call_llm", False))

    def get_should_call_llm_for_request(self, request_id: str) -> bool | None:
        overlay = self.get_request_overlay_by_request_id(request_id)
        if overlay is None:
            return None
        return overlay.should_call_llm

    def _set_overlay_stop_state(
        self,
        overlay: _RequestOverlayState,
        *,
        stopped: bool,
    ) -> None:
        overlay.result_stopped = stopped
        if stopped:
            overlay.should_call_llm = False

    def _set_result_from_object(
        self,
        overlay: _RequestOverlayState,
        result: MessageEventResult | None,
    ) -> None:
        overlay.result_object = result
        overlay.result_is_set = True
        self._set_overlay_stop_state(
            overlay,
            stopped=bool(result is not None and result.is_stopped()),
        )
        self._sync_overlay_payload_from_result_object(overlay)

    def _bind_result_object(
        self,
        overlay: _RequestOverlayState,
        result: MessageEventResult | None,
    ) -> None:
        overlay.result_object = result
        overlay.result_is_set = True
        self._set_overlay_stop_state(
            overlay,
            stopped=bool(result is not None and result.is_stopped()),
        )

    def _set_result_payload_on_overlay(
        self,
        overlay: _RequestOverlayState,
        result_payload: dict[str, Any] | None,
    ) -> None:
        if result_payload is None:
            overlay.result_payload = None
            overlay.result_object = None
            overlay.result_is_set = True
            self._set_overlay_stop_state(overlay, stopped=False)
            return
        normalized_payload = json.loads(json.dumps(result_payload))
        overlay.result_payload = normalized_payload
        chain_payload = normalized_payload.get("chain")
        overlay.result_object = (
            self._build_core_result_from_chain_payload(chain_payload)
            if isinstance(chain_payload, list)
            else None
        )
        overlay.result_is_set = True
        self._set_overlay_stop_state(overlay, stopped=False)

    def _sync_overlay_payload_from_result_object(
        self,
        overlay: _RequestOverlayState,
    ) -> None:
        overlay.result_payload = self._legacy_result_to_sdk_payload(
            overlay.result_object
        )
        self._set_overlay_stop_state(
            overlay,
            stopped=bool(
                overlay.result_object is not None and overlay.result_object.is_stopped()
            ),
        )

    def _get_effective_result_for_token(
        self,
        dispatch_token: str,
    ) -> MessageEventResult | None:
        overlay = self.get_request_overlay_by_token(dispatch_token)
        if overlay is None or not overlay.result_is_set:
            request_context = self._request_contexts.get(dispatch_token)
            if (
                request_context is not None
                and request_context.dispatch_state is not None
            ):
                return request_context.dispatch_state.event._result
            return None
        if overlay.result_object is None and overlay.result_payload is not None:
            chain_payload = overlay.result_payload.get("chain")
            if isinstance(chain_payload, list):
                overlay.result_object = self._build_core_result_from_chain_payload(
                    chain_payload
                )
        if overlay.result_object is None:
            if overlay.result_stopped:
                stopped_result = MessageEventResult()
                stopped_result.stop_event()
                overlay.result_object = stopped_result
            else:
                return None
        if overlay.result_stopped and not overlay.result_object.is_stopped():
            overlay.result_object.stop_event()
        elif not overlay.result_stopped and overlay.result_object.is_stopped():
            overlay.result_object.continue_event()
        return overlay.result_object

    def _set_result_for_dispatch_token(
        self,
        dispatch_token: str,
        result: MessageEventResult | None,
    ) -> None:
        overlay = self.get_request_overlay_by_token(dispatch_token)
        if overlay is None:
            return
        self._set_result_from_object(overlay, result)

    def _clear_result_for_dispatch_token(self, dispatch_token: str) -> None:
        overlay = self.get_request_overlay_by_token(dispatch_token)
        if overlay is None:
            return
        overlay.result_payload = None
        overlay.result_object = None
        overlay.result_is_set = True
        self._set_overlay_stop_state(overlay, stopped=False)

    def _stop_event_for_dispatch_token(self, dispatch_token: str) -> None:
        overlay = self.get_request_overlay_by_token(dispatch_token)
        if overlay is None:
            return
        self._set_overlay_stop_state(overlay, stopped=True)
        overlay.result_is_set = True
        if overlay.result_object is not None and not overlay.result_object.is_stopped():
            overlay.result_object.stop_event()

    def _continue_event_for_dispatch_token(self, dispatch_token: str) -> None:
        overlay = self.get_request_overlay_by_token(dispatch_token)
        if overlay is None:
            return
        overlay.result_is_set = True
        self._set_overlay_stop_state(overlay, stopped=False)
        if overlay.result_object is not None and overlay.result_object.is_stopped():
            overlay.result_object.continue_event()

    def _is_stopped_for_dispatch_token(self, dispatch_token: str) -> bool:
        overlay = self.get_request_overlay_by_token(dispatch_token)
        if overlay is not None and overlay.result_is_set:
            return overlay.result_stopped
        request_context = self._request_contexts.get(dispatch_token)
        if request_context is not None and request_context.dispatch_state is not None:
            result = request_context.dispatch_state.event._result
            return bool(result is not None and result.is_stopped())
        return False

    def set_result_for_request(
        self,
        request_id: str,
        result_payload: dict[str, Any] | None,
    ) -> bool:
        overlay = self.get_request_overlay_by_request_id(request_id)
        if overlay is None:
            return False
        self._set_result_payload_on_overlay(overlay, result_payload)
        return True

    def clear_result_for_request(self, request_id: str) -> bool:
        overlay = self.get_request_overlay_by_request_id(request_id)
        if overlay is None:
            return False
        overlay.result_payload = None
        overlay.result_object = None
        overlay.result_is_set = True
        self._set_overlay_stop_state(overlay, stopped=False)
        return True

    def get_result_payload_for_request(self, request_id: str) -> dict[str, Any] | None:
        overlay = self.get_request_overlay_by_request_id(request_id)
        request_context = self.resolve_request_session(request_id)
        request_context_has_event = False
        if request_context is not None:
            has_event = getattr(request_context, "has_event", None)
            request_context_has_event = (
                bool(has_event)
                if has_event is not None
                else hasattr(request_context, "event")
            )
        if overlay is not None and overlay.result_is_set:
            if overlay.result_object is not None:
                self._sync_overlay_payload_from_result_object(overlay)
            return (
                copy.deepcopy(overlay.result_payload)
                if overlay.result_payload is not None
                else None
            )
        if request_context is None or not request_context_has_event:
            return None
        return self._legacy_result_to_sdk_payload(request_context.event.get_result())

    def set_handler_whitelist_for_request(
        self,
        request_id: str,
        plugin_names: set[str] | None,
    ) -> bool:
        overlay = self.get_request_overlay_by_request_id(request_id)
        if overlay is None:
            return False
        overlay.handler_whitelist = None if plugin_names is None else set(plugin_names)
        return True

    def get_handler_whitelist_for_request(self, request_id: str) -> set[str] | None:
        overlay = self.get_request_overlay_by_request_id(request_id)
        if overlay is None:
            return None
        return (
            None
            if overlay.handler_whitelist is None
            else set(overlay.handler_whitelist)
        )

    def _get_handler_whitelist_for_event(
        self, event: AstrMessageEvent
    ) -> set[str] | None:
        dispatch_token = self._get_dispatch_token(event)
        if not dispatch_token:
            return None
        overlay = self.get_request_overlay_by_token(dispatch_token)
        if overlay is None:
            return None
        return (
            None
            if overlay.handler_whitelist is None
            else set(overlay.handler_whitelist)
        )

    @staticmethod
    def _build_core_message_chain_from_payload(
        chain_payload: list[dict[str, Any]],
    ) -> MessageChain:
        return _build_message_chain_from_payload(chain_payload)

    @classmethod
    def _build_core_result_from_chain_payload(
        cls,
        chain_payload: list[dict[str, Any]],
    ) -> MessageEventResult:
        chain = cls._build_core_message_chain_from_payload(chain_payload)
        result = MessageEventResult()
        # Core stages currently treat result.chain as a MessageChain-like object and
        # call get_plain_text()/mutate nested components on it directly.
        setattr(result, "chain", chain)
        result.use_t2i_ = chain.use_t2i_
        result.type = chain.type
        return result

    @staticmethod
    def _legacy_result_to_sdk_payload(
        result: MessageEventResult | None,
    ) -> dict[str, Any] | None:
        if result is None:
            return None
        chain = (
            result.chain.chain
            if isinstance(result.chain, MessageChain)
            else result.chain
        )
        return {
            "type": "chain" if chain else "empty",
            "chain": SdkPluginBridge._components_to_sdk_payload(chain),
        }

    @staticmethod
    def _components_to_sdk_payload(
        components: list[Any] | tuple[Any, ...] | None,
    ) -> list[dict[str, Any]]:
        return [
            component_to_payload_sync(component) for component in (components or [])
        ]

    @classmethod
    def _persist_sdk_local_extras_from_handler(
        cls,
        overlay: _RequestOverlayState,
        payload: Any,
        *,
        plugin_id: str,
        handler_id: str,
    ) -> None:
        if payload is None:
            overlay.sdk_local_extras = {}
            return
        if not isinstance(payload, dict):
            logger.warning(
                "SDK event handler returned invalid sdk_local_extras: plugin=%s handler=%s payload_type=%s",
                plugin_id,
                handler_id,
                type(payload).__name__,
            )
            return
        normalized, dropped_keys = normalize_sdk_local_extras(payload)
        overlay.sdk_local_extras = normalized
        for key in dropped_keys:
            value = payload.get(key)
            logger.warning(
                "Dropped sdk_local_extras entry during SDK bridge serialization: "
                "plugin=%s handler=%s key=%s value_type=%s reason=%s "
                "recommended_fix=%s",
                plugin_id,
                handler_id,
                key,
                type(value).__name__,
                "sdk_local_extras only preserves JSON-serializable values across "
                "handler and lifecycle boundaries",
                "store plain dict/list/scalar payloads, or serialize framework "
                "objects such as message components before calling set_extra()",
            )

    @staticmethod
    def _sanitize_host_extras(event: AstrMessageEvent) -> dict[str, Any]:
        extras = event.get_extra()
        if not isinstance(extras, dict) or not extras:
            return {}
        return sanitize_sdk_extras(extras)

    @staticmethod
    def _set_sdk_origin_plugin_id(
        event: AstrMessageEvent,
        plugin_id: str,
    ) -> None:
        setter = getattr(event, "set_extra", None)
        if callable(setter):
            setter("_sdk_origin_plugin_id", plugin_id)
            return
        setattr(event, "_sdk_origin_plugin_id", plugin_id)

    def _get_or_build_inbound_snapshot(
        self,
        event: AstrMessageEvent,
        overlay: _RequestOverlayState | None,
    ) -> InboundEventSnapshot:
        if overlay is not None and overlay.inbound_snapshot is not None:
            return overlay.inbound_snapshot
        snapshot = build_inbound_event_snapshot(event)
        if overlay is not None:
            overlay.inbound_snapshot = snapshot
        return snapshot

    def _build_sdk_event_payload(
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
        snapshot = self._get_or_build_inbound_snapshot(event, overlay)
        sdk_local_extras = dict(overlay.sdk_local_extras) if overlay is not None else {}
        return snapshot.to_payload(
            dispatch_token=dispatch_token,
            plugin_id=plugin_id,
            request_id=request_id,
            host_extras=self._sanitize_host_extras(event),
            sdk_local_extras=sdk_local_extras,
            raw_updates=raw_updates,
            field_updates=field_updates,
        )

    @staticmethod
    def _core_provider_request_to_sdk_payload(
        request: CoreProviderRequest,
    ) -> dict[str, Any]:
        tool_calls_result: list[dict[str, Any]] = []
        raw_results = request.tool_calls_result
        if raw_results is not None:
            if not isinstance(raw_results, list):
                raw_results = [raw_results]
            for item in raw_results:
                if not getattr(item, "tool_calls_result", None):
                    continue
                tool_name_by_id: dict[str, str] = {}
                tool_calls_info = getattr(item, "tool_calls_info", None)
                raw_tool_calls = getattr(tool_calls_info, "tool_calls", None)
                if isinstance(raw_tool_calls, list):
                    for tool_call in raw_tool_calls:
                        if isinstance(tool_call, dict):
                            tool_call_id = tool_call.get("id")
                            function_payload = tool_call.get("function")
                            if isinstance(function_payload, dict):
                                tool_name = function_payload.get("name")
                            else:
                                tool_name = None
                        else:
                            tool_call_id = getattr(tool_call, "id", None)
                            function_payload = getattr(tool_call, "function", None)
                            tool_name = getattr(function_payload, "name", None)
                        if tool_call_id is None or tool_name is None:
                            continue
                        tool_name_by_id[str(tool_call_id)] = str(tool_name)
                for tool_result in item.tool_calls_result:
                    tool_name = ""
                    tool_call_id = getattr(tool_result, "tool_call_id", None)
                    content = getattr(tool_result, "content", "")
                    success = True
                    if tool_call_id is not None:
                        tool_name = tool_name_by_id.get(str(tool_call_id), "")
                    tool_calls_result.append(
                        {
                            "tool_call_id": str(tool_call_id)
                            if tool_call_id is not None
                            else None,
                            "tool_name": tool_name,
                            "content": str(content or ""),
                            "success": bool(success),
                        }
                    )
        return {
            "prompt": request.prompt,
            "system_prompt": request.system_prompt or None,
            "session_id": request.session_id or None,
            "contexts": copy.deepcopy(request.contexts or []),
            "image_urls": list(request.image_urls or []),
            "tool_calls_result": tool_calls_result,
            "model": request.model,
        }

    @staticmethod
    def _apply_sdk_provider_request_payload(
        request: CoreProviderRequest,
        payload: dict[str, Any],
    ) -> None:
        prompt = payload.get("prompt")
        request.prompt = None if prompt is None else str(prompt)
        system_prompt = payload.get("system_prompt")
        request.system_prompt = "" if system_prompt is None else str(system_prompt)
        session_id = payload.get("session_id")
        request.session_id = None if session_id is None else str(session_id)

        contexts = payload.get("contexts")
        if isinstance(contexts, list):
            request.contexts = copy.deepcopy(contexts)

        image_urls = payload.get("image_urls")
        if isinstance(image_urls, list):
            request.image_urls = [str(item) for item in image_urls]

        model = payload.get("model")
        request.model = None if model is None else str(model)

    @staticmethod
    def _core_llm_response_to_sdk_payload(
        response: CoreLLMResponse,
    ) -> dict[str, Any]:
        usage_payload = None
        if response.usage is not None:
            usage_payload = {
                "input_tokens": response.usage.input,
                "output_tokens": response.usage.output,
                "total_tokens": response.usage.total,
                "input_cached_tokens": response.usage.input_cached,
            }
        tool_calls: list[dict[str, Any]] = []
        for idx, tool_name in enumerate(response.tools_call_name):
            tool_calls.append(
                {
                    "id": (
                        response.tools_call_ids[idx]
                        if idx < len(response.tools_call_ids)
                        else None
                    ),
                    "name": tool_name,
                    "arguments": (
                        response.tools_call_args[idx]
                        if idx < len(response.tools_call_args)
                        else {}
                    ),
                    "extra_content": (
                        response.tools_call_extra_content.get(
                            response.tools_call_ids[idx]
                        )
                        if idx < len(response.tools_call_ids)
                        else None
                    ),
                }
            )
        return {
            "text": response.completion_text or "",
            "usage": usage_payload,
            "finish_reason": "tool_calls" if tool_calls else "stop",
            "tool_calls": tool_calls,
            "role": response.role,
            "reasoning_content": response.reasoning_content or None,
            "reasoning_signature": response.reasoning_signature,
        }

    @classmethod
    def _apply_sdk_result_payload(
        cls,
        result: MessageEventResult,
        payload: dict[str, Any],
    ) -> MessageEventResult:
        chain_payload = payload.get("chain")
        updated = (
            cls._build_core_result_from_chain_payload(chain_payload)
            if isinstance(chain_payload, list)
            else MessageEventResult()
        )
        result.chain = updated.chain
        result.use_t2i_ = updated.use_t2i_
        result.type = updated.type
        return result

    def get_effective_result(
        self, event: AstrMessageEvent
    ) -> MessageEventResult | None:
        dispatch_token = self._get_dispatch_token(event)
        if dispatch_token:
            return self._get_effective_result_for_token(dispatch_token)
        return event._result

    def before_platform_send(self, dispatch_token: str) -> None:
        request_context = self._request_contexts.get(dispatch_token)
        if request_context is None:
            raise AstrBotError.invalid_input(
                "Unknown SDK dispatch token for platform send"
            )
        overlay = self.get_request_overlay_by_token(dispatch_token)
        if overlay is None:
            raise AstrBotError.cancelled("The SDK request overlay has been closed")
        if request_context.cancelled:
            raise AstrBotError.cancelled("The SDK request has been cancelled")

    def mark_platform_send(self, dispatch_token: str) -> str:
        request_context = self._request_contexts.get(dispatch_token)
        if request_context is None:
            raise AstrBotError.invalid_input(
                "Unknown SDK dispatch token for platform send"
            )
        overlay = self.get_request_overlay_by_token(dispatch_token)
        if overlay is None:
            raise AstrBotError.cancelled("The SDK request overlay has been closed")
        if request_context.cancelled:
            raise AstrBotError.cancelled("The SDK request has been cancelled")
        if request_context.dispatch_state is not None:
            request_context.dispatch_state.sent_message = True
        overlay.should_call_llm = False
        if request_context.has_event:
            request_context.event._has_send_oper = True
        return f"sdk_{dispatch_token}"

    @staticmethod
    def _legacy_has_replied(event: AstrMessageEvent) -> bool:
        return getattr(event, "_has_send_oper", False)

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
        for record in sorted(self._records.values(), key=lambda item: item.load_order):
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
        normalized_platform = self._normalize_platform_name(
            (payload or {}).get("platform")
        )
        event_payload = {
            "type": event_type,
            "event_type": event_type,
            "text": str((payload or {}).get("message_outline", "")),
            "session_id": str((payload or {}).get("session_id", "")),
            "platform": str((payload or {}).get("platform", "")),
            "platform_id": str((payload or {}).get("platform_id", "")),
            "message_type": sdk_message_type((payload or {}).get("message_type", "")),
            "sender_name": str((payload or {}).get("sender_name", "")),
            "self_id": str((payload or {}).get("self_id", "")),
            "raw": {"event_type": event_type, **(payload or {})},
        }
        for key, value in (payload or {}).items():
            event_payload[key] = value
        matches = self._match_event_handlers(
            event_type,
            platform_name=normalized_platform,
        )
        for record, descriptor in matches:
            if record.session is None:
                continue
            try:
                await record.session.invoke_handler(
                    descriptor.id,
                    event_payload,
                    request_id=f"sdk_event_{record.plugin_id}_{uuid.uuid4().hex}",
                    args={},
                )
            except Exception as exc:
                logger.warning(
                    "SDK event handler failed: plugin=%s handler=%s error=%s",
                    record.plugin_id,
                    descriptor.id,
                    exc,
                )

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
        dispatch_token = self._get_dispatch_token(event)
        if not dispatch_token:
            return
        overlay = self.get_request_overlay_by_token(dispatch_token)
        if overlay is None:
            return
        normalized_platform = self._normalize_platform_name(event.get_platform_name())
        matches = self._match_event_handlers(
            event_type,
            allowed_plugins=overlay.handler_whitelist,
            platform_name=normalized_platform,
        )
        for record, descriptor in matches:
            if record.session is None:
                continue
            request_id = f"sdk_event_{record.plugin_id}_{uuid.uuid4().hex}"
            request_context = self._request_contexts.get(dispatch_token)
            if request_context is None:
                request_context = _RequestContext(
                    plugin_id=record.plugin_id,
                    request_id=request_id,
                    dispatch_token=dispatch_token,
                    dispatch_state=_DispatchState(event=event),
                )
                self._request_contexts[dispatch_token] = request_context
            request_context.plugin_id = record.plugin_id
            request_context.request_id = request_id
            request_context.dispatch_state.event = event
            request_context.cancelled = False
            self._track_request_scope(
                dispatch_token=dispatch_token,
                request_id=request_id,
                plugin_id=record.plugin_id,
            )
            event_payload = self._build_sdk_event_payload(
                event,
                dispatch_token=dispatch_token,
                plugin_id=record.plugin_id,
                request_id=request_id,
                overlay=overlay,
                raw_updates={"event_type": event_type, **(payload or {})},
                field_updates={
                    "type": event_type,
                    "event_type": event_type,
                    **(payload or {}),
                },
            )
            if provider_request is not None:
                request_payload = self._core_provider_request_to_sdk_payload(
                    provider_request
                )
                event_payload["provider_request"] = request_payload
                if isinstance(event_payload["raw"], dict):
                    event_payload["raw"]["provider_request"] = request_payload
            if llm_response is not None:
                response_payload = self._core_llm_response_to_sdk_payload(llm_response)
                event_payload["llm_response"] = response_payload
                if isinstance(event_payload["raw"], dict):
                    event_payload["raw"]["llm_response"] = response_payload
            if event_result is not None:
                result_payload = self._legacy_result_to_sdk_payload(event_result)
                if result_payload is not None:
                    event_payload["event_result"] = result_payload
                    if isinstance(event_payload["raw"], dict):
                        event_payload["raw"]["event_result"] = result_payload
            try:
                output = await record.session.invoke_handler(
                    descriptor.id,
                    event_payload,
                    request_id=request_id,
                    args={},
                )
                if isinstance(output, dict):
                    if "sdk_local_extras" in output:
                        self._persist_sdk_local_extras_from_handler(
                            overlay,
                            output.get("sdk_local_extras"),
                            plugin_id=record.plugin_id,
                            handler_id=descriptor.id,
                        )
                    request_payload = output.get("provider_request")
                    if provider_request is not None and isinstance(
                        request_payload, dict
                    ):
                        self._apply_sdk_provider_request_payload(
                            provider_request,
                            request_payload,
                        )
                    result_payload = output.get("event_result")
                    if event_result is not None and isinstance(result_payload, dict):
                        if not self.set_result_for_request(request_id, result_payload):
                            self._apply_sdk_result_payload(event_result, result_payload)
            except Exception as exc:
                logger.warning(
                    "SDK event handler failed: plugin=%s handler=%s error=%s",
                    record.plugin_id,
                    descriptor.id,
                    exc,
                )

    def _match_event_handlers(
        self,
        event_type: str,
        *,
        allowed_plugins: set[str] | None = None,
        platform_name: str = "",
    ) -> list[tuple[SdkPluginRecord, HandlerDescriptor]]:
        matches: list[tuple[int, int, int, SdkPluginRecord, HandlerDescriptor]] = []
        for record in self._records.values():
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
        for record in sorted(self._records.values(), key=lambda item: item.load_order):
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
        for record in self._records.values():
            for handler in record.handlers:
                if handler.descriptor.id == full_name:
                    return self._descriptor_metadata(
                        plugin_id=record.plugin_id,
                        descriptor=handler.descriptor,
                    )
        return None

    def list_dashboard_commands(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for record in sorted(self._records.values(), key=lambda item: item.load_order):
            items.extend(self._build_dashboard_command_items(record))
        items.sort(key=lambda item: str(item.get("effective_command", "")).lower())
        return items

    def list_dashboard_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for record in sorted(self._records.values(), key=lambda item: item.load_order):
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
        runtime.ready_event.clear()
        runtime.running = False
        runtime.last_error = None
        runtime.errlogs = []
        runtime.tools = []
        runtime.tool_specs = []
        self._remove_local_mcp_lease(runtime)
        await self._cleanup_mcp_client(runtime.client)
        runtime.client = None

        client = MCPClient()
        client.name = runtime.name
        try:
            await asyncio.wait_for(
                client.connect_to_server(dict(runtime.config), runtime.name),
                timeout=timeout,
            )
            await asyncio.wait_for(client.list_tools_and_save(), timeout=timeout)
        except asyncio.CancelledError:
            await self._cleanup_mcp_client(client)
            raise
        except TimeoutError:
            runtime.last_error = (
                f"Local MCP server '{runtime.name}' did not become ready within "
                f"{timeout:g} seconds"
            )
            runtime.errlogs = [runtime.last_error]
            await self._cleanup_mcp_client(client)
        except Exception as exc:
            runtime.last_error = str(exc)
            runtime.errlogs = [runtime.last_error]
            await self._cleanup_mcp_client(client)
        else:
            runtime.client = client
            runtime.running = True
            runtime.tools = [
                str(tool.name) for tool in client.tools if getattr(tool, "name", None)
            ]
            runtime.tool_specs = self._build_local_mcp_tool_specs(runtime.name, client)
            runtime.errlogs = list(client.server_errlogs)
            if client.process_pid is not None:
                runtime.lease_path = self._write_local_mcp_lease(
                    plugin_id=plugin_id,
                    server_name=runtime.name,
                    pid=client.process_pid,
                )
        finally:
            runtime.ready_event.set()
            runtime.connect_task = None

    async def _initialize_local_mcp_servers(self, record: SdkPluginRecord) -> None:
        tasks: list[asyncio.Task[None]] = []
        for runtime in record.local_mcp_servers.values():
            if not runtime.active:
                runtime.ready_event.set()
                continue
            task = asyncio.create_task(
                self._connect_local_mcp_server(
                    plugin_id=record.plugin_id,
                    runtime=runtime,
                    timeout=30.0,
                )
            )
            runtime.connect_task = task
            tasks.append(task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _shutdown_local_mcp_runtime(
        self,
        runtime: _LocalMCPServerRuntime,
    ) -> None:
        connect_task = runtime.connect_task
        runtime.connect_task = None
        if connect_task is not None and not connect_task.done():
            connect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await connect_task
        self._remove_local_mcp_lease(runtime)
        await self._cleanup_mcp_client(runtime.client)
        runtime.client = None
        runtime.running = False
        runtime.tools = []
        runtime.tool_specs = []
        runtime.ready_event.clear()

    async def _shutdown_local_mcp_servers(self, record: SdkPluginRecord) -> None:
        for runtime in record.local_mcp_servers.values():
            await self._shutdown_local_mcp_runtime(runtime)

    async def enable_local_mcp_server(
        self,
        plugin_id: str,
        name: str,
        *,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        runtime = self._local_mcp_record(plugin_id, name)
        if runtime is None:
            raise AstrBotError.invalid_input(f"Unknown local MCP server: {name}")
        if runtime.active and runtime.running and runtime.connect_task is None:
            return self._serialize_local_mcp_server(runtime)
        if runtime.connect_task is not None and not runtime.connect_task.done():
            runtime.active = True
            await runtime.connect_task
            return self._serialize_local_mcp_server(runtime)
        runtime.active = True
        task = asyncio.create_task(
            self._connect_local_mcp_server(
                plugin_id=plugin_id,
                runtime=runtime,
                timeout=timeout,
            )
        )
        runtime.connect_task = task
        await task
        return self._serialize_local_mcp_server(runtime)

    async def disable_local_mcp_server(
        self,
        plugin_id: str,
        name: str,
    ) -> dict[str, Any]:
        runtime = self._local_mcp_record(plugin_id, name)
        if runtime is None:
            raise AstrBotError.invalid_input(f"Unknown local MCP server: {name}")
        if not runtime.active and not runtime.running and runtime.connect_task is None:
            return self._serialize_local_mcp_server(runtime)
        runtime.active = False
        await self._shutdown_local_mcp_runtime(runtime)
        return self._serialize_local_mcp_server(runtime)

    async def wait_for_local_mcp_server(
        self,
        plugin_id: str,
        name: str,
        *,
        timeout: float,
    ) -> dict[str, Any]:
        runtime = self._local_mcp_record(plugin_id, name)
        if runtime is None:
            raise AstrBotError.invalid_input(f"Unknown local MCP server: {name}")
        await asyncio.wait_for(runtime.ready_event.wait(), timeout=timeout)
        if not runtime.running:
            raise TimeoutError(
                f"Local MCP server '{name}' did not become ready in time"
            )
        return self._serialize_local_mcp_server(runtime)

    async def open_temporary_mcp_session(
        self,
        plugin_id: str,
        *,
        name: str,
        config: dict[str, Any],
        timeout: float,
    ) -> tuple[str, list[str]]:
        client = MCPClient()
        client.name = name
        try:
            await asyncio.wait_for(
                client.connect_to_server(dict(config), name),
                timeout=timeout,
            )
            await asyncio.wait_for(client.list_tools_and_save(), timeout=timeout)
        except Exception:
            await self._cleanup_mcp_client(client)
            raise
        session_id = f"{plugin_id}:{uuid.uuid4().hex}"
        tools = [str(tool.name) for tool in client.tools if getattr(tool, "name", None)]
        self._temporary_mcp_sessions[session_id] = _TemporaryMCPSessionRuntime(
            plugin_id=plugin_id,
            name=name,
            client=client,
            tools=tools,
        )
        return session_id, tools

    async def close_temporary_mcp_session(
        self,
        plugin_id: str,
        session_id: str,
    ) -> None:
        runtime = self._temporary_mcp_sessions.get(session_id)
        if runtime is None or runtime.plugin_id != plugin_id:
            return
        self._temporary_mcp_sessions.pop(session_id, None)
        await self._cleanup_mcp_client(runtime.client)

    async def _close_temporary_mcp_sessions(self, plugin_id: str) -> None:
        session_ids = [
            session_id
            for session_id, runtime in self._temporary_mcp_sessions.items()
            if runtime.plugin_id == plugin_id
        ]
        for session_id in session_ids:
            await self.close_temporary_mcp_session(plugin_id, session_id)

    def get_temporary_mcp_session_tools(
        self,
        plugin_id: str,
        session_id: str,
    ) -> list[str]:
        runtime = self._temporary_mcp_sessions.get(session_id)
        if runtime is None or runtime.plugin_id != plugin_id:
            raise AstrBotError.invalid_input("Unknown MCP session")
        return list(runtime.tools)

    async def call_temporary_mcp_tool(
        self,
        plugin_id: str,
        *,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        runtime = self._temporary_mcp_sessions.get(session_id)
        if runtime is None or runtime.plugin_id != plugin_id:
            raise AstrBotError.invalid_input("Unknown MCP session")
        result = await runtime.client.call_tool_with_reconnect(
            tool_name=tool_name,
            arguments=arguments,
            read_timeout_seconds=timedelta(seconds=60),
        )
        text = self._mcp_call_result_to_text(result)
        return {"content": text, "is_error": bool(getattr(result, "isError", False))}

    async def execute_local_mcp_tool(
        self,
        plugin_id: str,
        *,
        server_name: str,
        tool_name: str,
        tool_args: dict[str, Any],
        timeout_seconds: int = 60,
    ) -> dict[str, Any]:
        runtime = self._local_mcp_record(plugin_id, server_name)
        if (
            runtime is None
            or not runtime.active
            or not runtime.running
            or runtime.client is None
        ):
            return {
                "content": f"Local MCP server unavailable: {server_name}",
                "success": False,
            }
        if tool_name not in runtime.tools:
            return {
                "content": f"Local MCP tool not found: {server_name}.{tool_name}",
                "success": False,
            }
        try:
            result = await runtime.client.call_tool_with_reconnect(
                tool_name=tool_name,
                arguments=tool_args,
                read_timeout_seconds=timedelta(seconds=timeout_seconds),
            )
        except Exception as exc:
            return {"content": f"Tool execution failed: {exc}", "success": False}
        text = self._mcp_call_result_to_text(result)
        return {
            "content": text,
            "success": not bool(getattr(result, "isError", False)),
        }

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
            local_mcp_servers={
                name: _LocalMCPServerRuntime(
                    name=name,
                    config=dict(config),
                    active=bool(config.get("active", True)),
                )
                for name, config in local_mcp_configs.items()
            },
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
    async def _refresh_native_platform_commands(
        self, platforms: set[str] | None = None
    ) -> None:
        platform_manager = getattr(self.star_context, "platform_manager", None)
        if platform_manager is None:
            return
        refresh_commands = getattr(platform_manager, "refresh_native_commands", None)
        if not callable(refresh_commands):
            return
        try:
            await refresh_commands(platforms=platforms)
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
        if self._stopping:
            return
        await self._cancel_plugin_requests(plugin_id)
        await self._close_temporary_mcp_sessions(plugin_id)
        record = self._records.get(plugin_id)
        if record is None:
            return
        await self._shutdown_local_mcp_servers(record)
        record.session = None
        if record.state in {SDK_STATE_RELOADING, SDK_STATE_DISABLED}:
            return
        if not record.restart_attempted:
            record.restart_attempted = True
            logger.warning(
                "SDK plugin worker closed unexpectedly, retrying once: %s",
                plugin_id,
            )
            await self._load_or_reload_plugin(
                record.plugin,
                load_order=record.load_order,
                reset_restart_budget=False,
            )
            return
        record.state = SDK_STATE_FAILED
        self._http_routes.pop(plugin_id, None)
        self._session_waiters.pop(plugin_id, None)
        await self._unregister_schedule_jobs(plugin_id)
        await self._clear_plugin_skills(
            plugin_id=plugin_id,
            record=record,
            reason="worker failure cleanup",
        )

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
            "repo": "",
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
        result = SdkDispatchResult()
        dispatch_state = _DispatchState(event=event)
        dispatch_token = self._get_dispatch_token(event) or uuid.uuid4().hex
        self._bind_dispatch_token(event, dispatch_token)
        overlay = self._ensure_request_overlay(
            dispatch_token,
            should_call_llm=not bool(getattr(event, "call_llm", False)),
        )
        request_context = _RequestContext(
            plugin_id="",
            request_id="",
            dispatch_token=dispatch_token,
            dispatch_state=dispatch_state,
        )
        self._request_contexts[dispatch_token] = request_context
        for record in records:
            if record.state in {
                SDK_STATE_DISABLED,
                SDK_STATE_FAILED,
                SDK_STATE_RELOADING,
            }:
                continue
            if record.session is None:
                continue
            whitelist = (
                None
                if overlay.handler_whitelist is None
                else set(overlay.handler_whitelist)
            )
            if whitelist is not None and record.plugin_id not in whitelist:
                continue
            request_id = f"sdk_waiter_{record.plugin_id}_{uuid.uuid4().hex}"
            request_context.plugin_id = record.plugin_id
            request_context.request_id = request_id
            request_context.cancelled = False
            self._set_sdk_origin_plugin_id(event, record.plugin_id)
            setattr(event, "_sdk_last_request_id", request_id)
            payload = self._build_sdk_event_payload(
                event,
                dispatch_token=dispatch_token,
                plugin_id=record.plugin_id,
                request_id=request_id,
                overlay=overlay,
            )
            self._track_request_scope(
                dispatch_token=dispatch_token,
                request_id=request_id,
                plugin_id=record.plugin_id,
            )
            try:
                output = await record.session.invoke_handler(
                    "__sdk_session_waiter__",
                    payload,
                    request_id=request_id,
                    args={},
                )
            except Exception as exc:
                logger.warning(
                    "SDK waiter dispatch failed: plugin=%s error=%s",
                    record.plugin_id,
                    exc,
                )
                output = {}
            handler_result = extract_sdk_handler_result(
                output if isinstance(output, dict) else {}
            )
            result.executed_handlers.append(
                {"plugin_id": record.plugin_id, "handler_id": "__sdk_session_waiter__"}
            )
            dispatch_state.sent_message = (
                dispatch_state.sent_message or handler_result["sent_message"]
            )
            dispatch_state.stopped = dispatch_state.stopped or handler_result["stop"]
            if handler_result["call_llm"]:
                overlay.requested_llm = True
                overlay.should_call_llm = True
            if handler_result["sent_message"] or handler_result["stop"]:
                overlay.should_call_llm = False
            if handler_result["stop"]:
                break
        result.sent_message = dispatch_state.sent_message
        result.stopped = dispatch_state.stopped
        if not result.executed_handlers:
            result.skipped_reason = SKIP_NO_MATCH
        if result.sent_message:
            event._has_send_oper = True
            overlay.should_call_llm = False
            event.should_call_llm(True)
        if result.stopped:
            event.stop_event()
            overlay.should_call_llm = False
            event.should_call_llm(True)
        return result
