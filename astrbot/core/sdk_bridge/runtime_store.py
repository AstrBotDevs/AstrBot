from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.llm.agents import AgentSpec
from astrbot_sdk.llm.entities import LLMToolSpec
from astrbot_sdk.protocol.descriptors import HandlerDescriptor
from astrbot_sdk.runtime.loader import PluginSpec
from astrbot_sdk.runtime.supervisor import WorkerSession

from astrbot.core.agent.mcp_client import MCPClient
from astrbot.core.message.message_event_result import MessageEventResult

from .event_payload import InboundEventSnapshot

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent


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
class SdkRuntimeStore:
    # 可重入锁：保护所有 request_overlays / request_contexts 等字典的并发读写。
    # 使用 RLock 而非 Lock 是因为同一线程内可能嵌套调用（如 close_request_overlay
    # 内部调用 get_effective_result_for_token），RLock 允许同线程重入不死锁。
    mutation_lock: threading.RLock = field(default_factory=threading.RLock)
    records: dict[str, SdkPluginRecord] = field(default_factory=dict)
    request_contexts: dict[str, _RequestContext] = field(default_factory=dict)
    request_id_to_token: dict[str, str] = field(default_factory=dict)
    request_plugin_ids: dict[str, str] = field(default_factory=dict)
    request_overlays: dict[str, _RequestOverlayState] = field(default_factory=dict)
    plugin_requests: dict[str, dict[str, _InFlightRequest]] = field(
        default_factory=dict
    )
    http_routes: dict[str, list[SdkHttpRoute]] = field(default_factory=dict)
    session_waiters: dict[str, set[str]] = field(default_factory=dict)
    schedule_job_ids: dict[str, set[str]] = field(default_factory=dict)
    discovery_issues: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    temporary_mcp_sessions: dict[str, _TemporaryMCPSessionRuntime] = field(
        default_factory=dict
    )

    def snapshot_records(self) -> list[SdkPluginRecord]:
        with self.mutation_lock:
            return list(self.records.values())

    def snapshot_records_sorted(self) -> list[SdkPluginRecord]:
        with self.mutation_lock:
            return sorted(self.records.values(), key=lambda item: item.load_order)

    def snapshot_http_routes(self, plugin_id: str | None = None) -> list[SdkHttpRoute]:
        with self.mutation_lock:
            if plugin_id is None:
                routes: list[SdkHttpRoute] = []
                for entries in self.http_routes.values():
                    routes.extend(list(entries))
                return routes
            return list(self.http_routes.get(plugin_id, []))
