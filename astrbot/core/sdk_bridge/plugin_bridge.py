from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quart import request as quart_request

from astrbot.core import logger
from astrbot.core.message.components import ComponentTypes, Image, Plain
from astrbot.core.message.message_event_result import MessageChain, MessageEventResult
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.llm.agents import AgentSpec
from astrbot_sdk.llm.entities import LLMToolSpec
from astrbot_sdk.message_components import component_to_payload_sync
from astrbot_sdk.protocol.descriptors import (
    CommandTrigger,
    EventTrigger,
    HandlerDescriptor,
    MessageTrigger,
    ScheduleTrigger,
)
from astrbot_sdk.runtime.loader import (
    PluginDiscoveryIssue,
    PluginEnvironmentManager,
    PluginSpec,
    discover_plugins,
    load_plugin_config,
)
from astrbot_sdk.runtime.supervisor import WorkerSession

from .capability_bridge import CoreCapabilityBridge
from .event_converter import EventConverter
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
SUPPORTED_SYSTEM_EVENTS = {
    "astrbot_loaded",
    "platform_loaded",
    "after_message_sent",
    "waiting_llm_request",
    "llm_request",
    "llm_response",
    "decorating_result",
    "calling_func_tool",
    "using_llm_tool",
    "llm_tool_respond",
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
    dispatch_state: _DispatchState
    cancelled: bool = False

    @property
    def event(self) -> AstrMessageEvent:
        return self.dispatch_state.event


@dataclass(slots=True)
class _InFlightRequest:
    request_id: str
    dispatch_token: str
    task: asyncio.Task[dict[str, Any]]
    logical_cancelled: bool = False


@dataclass(slots=True)
class _RequestOverlayState:
    dispatch_token: str
    should_call_llm: bool
    requested_llm: bool = False
    result_payload: dict[str, Any] | None = None
    result_object: MessageEventResult | None = None
    result_is_set: bool = False
    handler_whitelist: set[str] | None = None
    closed: bool = False
    cleanup_task: asyncio.Task[None] | None = None


@dataclass(slots=True)
class SdkPluginRecord:
    plugin: PluginSpec
    load_order: int
    state: str
    unsupported_features: list[str]
    config: dict[str, Any]
    handlers: list[SdkHandlerRef]
    llm_tools: dict[str, LLMToolSpec] = field(default_factory=dict)
    active_llm_tools: set[str] = field(default_factory=set)
    agents: dict[str, AgentSpec] = field(default_factory=dict)
    dynamic_command_routes: list[SdkDynamicCommandRoute] = field(default_factory=list)
    session: WorkerSession | None = None
    restart_attempted: bool = False
    failure_reason: str = ""
    issues: list[dict[str, Any]] = field(default_factory=list)

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

    async def start(self) -> None:
        if self._started:
            return
        await self.reload_all(reset_restart_budget=True)
        self._started = True

    async def stop(self) -> None:
        if not self._started and not self._records:
            return
        self._stopping = True
        for plugin_id in list(self._records.keys()):
            await self._cancel_plugin_requests(plugin_id)
        for record in list(self._records.values()):
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
        self._started = False
        self._stopping = False

    async def reload_all(self, *, reset_restart_budget: bool = False) -> None:
        discovered = discover_plugins(self.plugins_dir)
        self._set_discovery_issues(discovered.issues)
        self.env_manager.plan(discovered.plugins)
        known = {plugin.name for plugin in discovered.plugins}
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
            setattr(event, "_sdk_last_request_id", request_id)
            payload = EventConverter.core_to_sdk(
                event,
                dispatch_token=dispatch_token,
                plugin_id=record.plugin_id,
                request_id=request_id,
            )
            task = asyncio.create_task(
                record.session.invoke_handler(
                    match.handler_id,
                    payload,
                    request_id=request_id,
                    args=match.args,
                )
            )
            self._request_id_to_token[request_id] = dispatch_token
            self._request_plugin_ids[request_id] = record.plugin_id
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
                self._request_id_to_token.pop(request_id, None)
                self._request_plugin_ids.pop(request_id, None)

            if inflight is not None and inflight.logical_cancelled:
                continue

            handler_result = EventConverter.extract_handler_result(
                output if isinstance(output, dict) else {}
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

    def _close_request_overlay(self, dispatch_token: str) -> None:
        overlay = self._request_overlays.pop(dispatch_token, None)
        if overlay is None:
            return
        overlay.closed = True
        if overlay.cleanup_task is not None:
            overlay.cleanup_task.cancel()
        request_context = self._request_contexts.get(dispatch_token)
        if request_context is not None:
            request_context.cancelled = True

    def close_request_overlay_for_event(self, event: AstrMessageEvent) -> None:
        dispatch_token = self._get_dispatch_token(event)
        if not dispatch_token:
            return
        self._close_request_overlay(dispatch_token)
        self._request_contexts.pop(dispatch_token, None)
        request_id = getattr(event, "_sdk_last_request_id", None)
        if request_id:
            self._request_id_to_token.pop(str(request_id), None)
            self._request_plugin_ids.pop(str(request_id), None)

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

    def set_result_for_request(
        self,
        request_id: str,
        result_payload: dict[str, Any] | None,
    ) -> bool:
        overlay = self.get_request_overlay_by_request_id(request_id)
        if overlay is None:
            return False
        if result_payload is None:
            overlay.result_payload = None
            overlay.result_object = None
        else:
            normalized_payload = json.loads(json.dumps(result_payload))
            overlay.result_payload = normalized_payload
            chain_payload = normalized_payload.get("chain")
            overlay.result_object = (
                self._build_core_result_from_chain_payload(chain_payload)
                if isinstance(chain_payload, list)
                else None
            )
        overlay.result_is_set = True
        return True

    def clear_result_for_request(self, request_id: str) -> bool:
        overlay = self.get_request_overlay_by_request_id(request_id)
        if overlay is None:
            return False
        overlay.result_payload = None
        overlay.result_object = None
        overlay.result_is_set = True
        return True

    def get_result_payload_for_request(self, request_id: str) -> dict[str, Any] | None:
        overlay = self.get_request_overlay_by_request_id(request_id)
        request_context = self.resolve_request_session(request_id)
        if overlay is not None and overlay.result_is_set:
            if overlay.result_object is not None:
                overlay.result_payload = self._legacy_result_to_sdk_payload(
                    overlay.result_object
                )
            return (
                json.loads(json.dumps(overlay.result_payload))
                if overlay.result_payload is not None
                else None
            )
        if request_context is None:
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

    def get_handler_whitelist_for_request(
        self, request_id: str
    ) -> set[str] | None | object:
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
        components = []
        for item in chain_payload:
            if not isinstance(item, dict):
                continue
            comp_type = str(item.get("type", "")).lower()
            data = item.get("data", {})
            if comp_type in {"text", "plain"} and isinstance(data, dict):
                components.append(Plain(str(data.get("text", "")), convert=False))
                continue
            if comp_type == "image" and isinstance(data, dict):
                file_value = str(data.get("file") or data.get("url") or "")
                if file_value.startswith(("http://", "https://")):
                    components.append(Image.fromURL(file_value))
                elif file_value:
                    file_path = (
                        file_value[8:]
                        if file_value.startswith("file:///")
                        else file_value
                    )
                    components.append(Image.fromFileSystem(file_path))
                continue
            component_cls = ComponentTypes.get(comp_type)
            if component_cls is None:
                components.append(
                    Plain(json.dumps(item, ensure_ascii=False), convert=False)
                )
                continue
            try:
                if isinstance(data, dict):
                    components.append(component_cls(**data))
                else:
                    components.append(Plain(str(item), convert=False))
            except Exception:
                components.append(
                    Plain(json.dumps(item, ensure_ascii=False), convert=False)
                )
        return MessageChain(components)

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
            "chain": [
                component_to_payload_sync(component) for component in (chain or [])
            ],
        }

    def get_effective_result(
        self, event: AstrMessageEvent
    ) -> MessageEventResult | None:
        dispatch_token = self._get_dispatch_token(event)
        if dispatch_token:
            overlay = self.get_request_overlay_by_token(dispatch_token)
            if overlay is not None and overlay.result_is_set:
                if overlay.result_payload is None:
                    return None
                if overlay.result_object is None:
                    chain_payload = overlay.result_payload.get("chain")
                    if not isinstance(chain_payload, list):
                        return None
                    overlay.result_object = self._build_core_result_from_chain_payload(
                        chain_payload
                    )
                return overlay.result_object
        return event.get_result()

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
        request_context.dispatch_state.sent_message = True
        overlay.should_call_llm = False
        request_context.event._has_send_oper = True
        return f"sdk_{dispatch_token}"

    @staticmethod
    def _legacy_has_replied(event: AstrMessageEvent) -> bool:
        return getattr(event, "_has_send_oper", False)

    def _match_handlers(self, event: AstrMessageEvent) -> list[TriggerMatch]:
        matches: list[TriggerMatch] = []
        for record in self._records.values():
            if record.state in {SDK_STATE_DISABLED, SDK_STATE_FAILED}:
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
        event_payload = {
            "type": event_type,
            "event_type": event_type,
            "text": str((payload or {}).get("message_outline", "")),
            "session_id": str((payload or {}).get("session_id", "")),
            "platform": str((payload or {}).get("platform", "")),
            "platform_id": str((payload or {}).get("platform_id", "")),
            "message_type": str((payload or {}).get("message_type", "")),
            "sender_name": str((payload or {}).get("sender_name", "")),
            "self_id": str((payload or {}).get("self_id", "")),
            "raw": {"event_type": event_type, **(payload or {})},
        }
        matches = self._match_event_handlers(event_type)
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
    ) -> None:
        dispatch_token = self._get_dispatch_token(event)
        if not dispatch_token:
            return
        overlay = self.get_request_overlay_by_token(dispatch_token)
        if overlay is None:
            return
        matches = self._match_event_handlers(
            event_type,
            allowed_plugins=overlay.handler_whitelist,
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
            self._request_id_to_token[request_id] = dispatch_token
            self._request_plugin_ids[request_id] = record.plugin_id
            event_payload = EventConverter.core_to_sdk(
                event,
                dispatch_token=dispatch_token,
                plugin_id=record.plugin_id,
                request_id=request_id,
            )
            event_payload["type"] = event_type
            event_payload["event_type"] = event_type
            event_payload["raw"] = {
                **(
                    event_payload["raw"]
                    if isinstance(event_payload.get("raw"), dict)
                    else {}
                ),
                "event_type": event_type,
                **(payload or {}),
            }
            for key, value in (payload or {}).items():
                event_payload[key] = value
            try:
                await record.session.invoke_handler(
                    descriptor.id,
                    event_payload,
                    request_id=request_id,
                    args={},
                )
            except Exception as exc:
                logger.warning(
                    "SDK event handler failed: plugin=%s handler=%s error=%s",
                    record.plugin_id,
                    descriptor.id,
                    exc,
                )
            finally:
                self._request_id_to_token.pop(request_id, None)
                self._request_plugin_ids.pop(request_id, None)

    def _match_event_handlers(
        self,
        event_type: str,
        *,
        allowed_plugins: set[str] | None = None,
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
            for handler in record.handlers:
                trigger = handler.descriptor.trigger
                if not isinstance(trigger, EventTrigger):
                    continue
                if trigger.event_type != event_type:
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
            "event_types": self._descriptor_event_types(descriptor),
            "enabled": True,
            "group_path": self._descriptor_group_path(descriptor),
        }

    def get_handlers_by_event_type(self, event_type: str) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for record in sorted(self._records.values(), key=lambda item: item.load_order):
            if record.state in {SDK_STATE_DISABLED, SDK_STATE_FAILED}:
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

    def get_handler_by_full_name(self, full_name: str) -> dict[str, Any] | None:
        for record in self._records.values():
            for handler in record.handlers:
                if handler.descriptor.id == full_name:
                    return self._descriptor_metadata(
                        plugin_id=record.plugin_id,
                        descriptor=handler.descriptor,
                    )
        return None

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
        record = SdkPluginRecord(
            plugin=plugin,
            load_order=load_order,
            state=SDK_STATE_DISABLED if disabled else SDK_STATE_ENABLED,
            unsupported_features=[],
            config=load_plugin_config(plugin),
            handlers=[],
            llm_tools={},
            active_llm_tools=set(),
            agents={},
            restart_attempted=False
            if reset_restart_budget
            else (current.restart_attempted if current is not None else False),
            issues=[dict(item) for item in self._discovery_issues.get(plugin.name, [])],
        )
        self._records[plugin.name] = record
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
        if record is None or record.session is None:
            return
        try:
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
            job = await cron_manager.add_basic_job(
                name=schedule_key,
                cron_expression=trigger.cron,
                interval_seconds=trigger.interval_seconds,
                handler=self._build_schedule_runner(
                    plugin_id=record.plugin_id,
                    handler_id=handler.handler_id,
                    trigger=trigger,
                ),
                description=f"SDK schedule handler {handler.handler_id}",
                enabled=True,
                persistent=False,
            )
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
    ):
        async def _run() -> None:
            await self._invoke_schedule_handler(
                plugin_id=plugin_id,
                handler_id=handler_id,
                trigger=trigger,
            )

        return _run

    def _set_discovery_issues(self, issues: list[PluginDiscoveryIssue]) -> None:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for issue in issues:
            grouped.setdefault(issue.plugin_id, []).append(issue.to_payload())
        self._discovery_issues = grouped

    async def _invoke_schedule_handler(
        self,
        *,
        plugin_id: str,
        handler_id: str,
        trigger: ScheduleTrigger,
    ) -> None:
        record = self._records.get(plugin_id)
        if (
            record is None
            or record.session is None
            or record.state
            in {SDK_STATE_DISABLED, SDK_STATE_FAILED, SDK_STATE_RELOADING}
        ):
            return
        request_id = f"sdk_schedule_{plugin_id}_{uuid.uuid4().hex}"
        self._request_plugin_ids[request_id] = plugin_id
        payload = self._build_schedule_payload(
            plugin_id=plugin_id,
            handler_id=handler_id,
            trigger=trigger,
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
            self._request_plugin_ids.pop(request_id, None)

    @staticmethod
    def _build_schedule_payload(
        *,
        plugin_id: str,
        handler_id: str,
        trigger: ScheduleTrigger,
    ) -> dict[str, Any]:
        scheduled_at = datetime.now(timezone.utc).isoformat()
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
                "plugin_id": plugin_id,
                "handler_id": handler_id,
                "trigger_kind": "cron" if trigger.cron is not None else "interval",
                "cron": trigger.cron,
                "interval_seconds": trigger.interval_seconds,
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
        record = self._records.get(plugin_id)
        if record is None:
            return
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
        base = {
            "event_type": "SDKMessageEvent",
            "event_type_h": "SDK 消息触发",
            "handler_full_name": handler.handler_id,
            "desc": "SDK handler",
            "handler_name": handler.handler_name,
            "has_admin": handler.descriptor.permissions.require_admin,
        }
        trigger = handler.descriptor.trigger
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
            setattr(event, "_sdk_last_request_id", request_id)
            payload = EventConverter.core_to_sdk(
                event,
                dispatch_token=dispatch_token,
                plugin_id=record.plugin_id,
                request_id=request_id,
            )
            self._request_id_to_token[request_id] = dispatch_token
            self._request_plugin_ids[request_id] = record.plugin_id
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
            finally:
                self._request_id_to_token.pop(request_id, None)
                self._request_plugin_ids.pop(request_id, None)
            handler_result = EventConverter.extract_handler_result(
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
