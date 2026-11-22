from __future__ import annotations

import asyncio
import copy
import inspect
import json
import logging
from collections.abc import Callable, Collection, Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from astrbot_sdk.capabilities import CapabilityGrant, CapabilitySet
from astrbot_sdk.errors import (
    DependencyBlocked,
    InvalidConfig,
    InvalidRequest,
    NotFound,
    RemotePluginError,
)
from astrbot_sdk.results import GroupUsage, Propagation
from astrbot_sdk.results import ViewResult as SDKViewResult
from astrbot_sdk.runtime.metadata import PluginMetadata, load_metadata
from astrbot_sdk.runtime.stdio_client import StdioPluginClient
from astrbot_sdk.tools import ToolCallContext

from astrbot.core import logger, sp
from astrbot.core.chatui import ViewResult as CoreViewResult
from astrbot.core.chatui import ViewSpec
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.provider.register import llm_tools
from astrbot.core.star.filter import HandlerFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.star import StarMetadata, star_map, star_registry
from astrbot.core.star.star_handler import (
    EventType,
    StarHandlerMetadata,
    star_handlers_registry,
)

from .approval import CapabilityApprovalStore, compute_package_fingerprint
from .config_schema import (
    load_plugin_json_schema,
    to_astrbot_config_schema,
    validate_against_json_schema,
)
from .convert import apply_sdk_result, to_sdk_event, to_umo_string
from .dependencies import BlockedPlugin, DependencyPlan, build_dependency_plan
from .detect import _BRIDGE_MODULE_PREFIX
from .detect import is_isolated_legacy_dir as is_isolated_legacy_dir
from .detect import is_sdk_plugin_dir as is_sdk_plugin_dir
from .hooks import (
    apply_hook_result,
    is_metadata_stage,
    snapshot_stage,
    stage_event_type,
)
from .services import (
    AgentRunService,
    AssetStore,
    AssetTransferService,
    ConfigWriteService,
    ConversationReadService,
    ConversationWriteService,
    CronScheduleService,
    DbService,
    EventInjectService,
    EventStateService,
    FileTokenService,
    HandlerRegisterService,
    HostService,
    KnowledgeBaseService,
    LLMEmbedService,
    LLMGenerateService,
    MessageHistoryService,
    MessageSendService,
    PersonaWriteService,
    PlatformRawService,
    PluginInspectService,
    PluginLifecycleService,
    ProviderWriteService,
    RenderImageService,
    SessionWaitService,
    SpeechSynthesizeService,
    SpeechTranscribeService,
    SpStoreService,
    StorageService,
    SubagentReloadService,
    ToolRegisterService,
    WebRouteService,
    dispatch_capability,
    purge_bridge_sessions,
)
from .services.plugin_service_router import PluginServiceRouter
from .snapshot import build_legacy_snapshot
from .supervisor import ExternalRunnerSupervisor, RunnerSupervisor
from .uds_listener import ExternalUDSListener
from .venv import ensure_plugin_venv
from .ws_listener import ExternalRunnerListener

if TYPE_CHECKING:
    from astrbot.core.star.context import Context


def _asset_root() -> Path:
    """Return the shared asset root below the AstrBot data directory."""
    from astrbot.core.utils.astrbot_path import get_astrbot_data_path

    return Path(get_astrbot_data_path()) / "sdk_assets"


def _metadata_views(metadata: Any) -> list[ViewSpec]:
    """Extract the views declaration from plugin metadata (views or pages)."""
    views = getattr(metadata, "views", None) or getattr(metadata, "pages", None)
    if not views:
        return []
    return [
        ViewSpec.model_validate(dict(item))
        for item in views
        if isinstance(item, dict | Mapping)
    ]


def _param_types() -> dict[str, type]:
    from astrbot.core.star.filter.command import GreedyStr

    return {
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "GreedyStr": GreedyStr,
    }


# Capabilities granted to isolated legacy plugins. Legacy plugins declare no
# capability set; the compat facade is constrained by this fixed set so the
# old API surface (KV, LLM, conversations, render, tools, send) keeps working.
_LEGACY_GRANT_IDS = (
    "storage.kv",
    "assets.transfer",
    "message.send",
    "llm.observe",
    "llm.modify",
    "message.observe",
    "message.modify",
    "llm.generate",
    "llm.agent",
    "llm.embed",
    "speech.transcribe",
    "speech.synthesize",
    "conversation.read",
    "conversation.write",
    "render.image",
    "llm.tool.register",
    "plugin.inspect",
    "web.route",
    "message.wait",
    "platform.raw",
    "event.state",
    "config.write",
    "persona.write",
    "provider.write",
    "plugin.lifecycle",
    "subagents.reload",
    "cron.schedule",
    "kb.manage",
    "message.history",
    "file.token",
    "handler.register",
    "event.inject",
    "db.read",
    "sp.store",
)


def _load_legacy_plugin_config(plugin_root: Path, root_dir_name: str) -> Any:
    """Load one legacy plugin's config from its _conf_schema.json.

    Mirrors the in-process star manager: when the plugin ships a config
    schema, its values live at data/config/{root_dir_name}_config.json.
    """
    schema_path = plugin_root / "_conf_schema.json"
    if not schema_path.is_file():
        return None
    from astrbot.core.star.star_manager import PluginManager
    from astrbot.core.utils.astrbot_path import get_astrbot_config_path

    return AstrBotConfig(
        config_path=str(
            Path(get_astrbot_config_path()) / f"{root_dir_name}_config.json"
        ),
        schema=PluginManager._load_plugin_config_schema(str(schema_path)),
    )


def _load_sdk_plugin_config(
    plugin_root: Path,
    root_dir_name: str,
) -> tuple[Any, dict[str, Any] | None]:
    """Load an SDK plugin's config from `_conf_schema.json` or `config.schema.json`."""
    schema_path = plugin_root / "_conf_schema.json"
    if schema_path.is_file():
        return _load_legacy_plugin_config(plugin_root, root_dir_name), None

    json_schema = load_plugin_json_schema(plugin_root)
    if json_schema is None:
        return None, None
    from astrbot.core.utils.astrbot_path import get_astrbot_config_path

    cfg = AstrBotConfig(
        config_path=str(
            Path(get_astrbot_config_path()) / f"{root_dir_name}_config.json"
        ),
        schema=to_astrbot_config_schema(json_schema),
    )
    validate_against_json_schema(json_schema, dict(cfg))
    return cfg, json_schema


class _DeferringCommandGroupFilter(CommandGroupFilter):
    """Command group filter that defers the bare-message reply to the Runner.

    In-process, a bare group-name message raises the usage-tree reply after
    the group's custom filters pass. Those custom filters live in the plugin
    Runner and cannot be evaluated synchronously by waking_check, so a bare
    message falls through to the synthetic bare-group handler instead of
    raising here. Sub-command matching is unchanged.
    """

    def filter(self, event, cfg) -> bool:
        if not event.is_at_or_wake_command:
            return False
        if not self.custom_filter_ok(event, cfg):
            return False
        if self.equals(event.message_str.strip()):
            return False
        return self.startswith(event.message_str)


class _BareGroupHandlerFilter(HandlerFilter):
    """Matches exactly the bare group-name message of one command group.

    Registered on the synthetic handler that asks the plugin Runner to
    evaluate group-level custom filters and answer with a usage-tree
    request. Must not be a CommandGroupFilter, or waking_check would exclude
    the handler from activation like any group anchor.
    """

    def __init__(self, group_filter: CommandGroupFilter) -> None:
        self._group_filter = group_filter

    def filter(self, event, cfg) -> bool:
        return bool(
            event.is_at_or_wake_command
            and self._group_filter.equals(event.message_str.strip())
        )


class SDKPluginBridge:
    """Host one isolated SDK plugin inside the AstrBot Pipeline.

    The bridge starts a Runner subprocess, registers its command handlers as
    pipeline stubs, and serves the plugin-scoped Host capabilities used by the
    vertical slice (KV storage and proactive message send).
    """

    def __init__(
        self,
        plugin_root: Path,
        context: Context,
        *,
        plugin_logger: logging.Logger | None = None,
        legacy: bool = False,
        external: Mapping[str, Any] | None = None,
        listener: ExternalRunnerListener | None = None,
        external_queue: asyncio.Queue[Any] | None = None,
        revoke_external: Callable[[], None] | None = None,
    ) -> None:
        """Initialize the bridge for one SDK plugin.

        Args:
            plugin_root: Plugin repository root with metadata.yaml/plugin.json. For
                external plugins this is a pseudo path; only its name is
                used for registry naming.
            context: AstrBot star context used for platform and config access.
            plugin_logger: Logger receiving Runner stderr output.
            legacy: Load the plugin through the legacy compat layer.
            external: External plugin spec (plugin_id, token, capabilities,
                config); when set, the Runner attaches over WebSocket or UDS
                instead of being spawned locally.
            listener: Shared external WebSocket listener the token claims belong to.
            external_queue: Optional external transport queue (e.g. from UDS attach).
            revoke_external: Optional callback revoking external UDS credentials.
        """
        self.plugin_root = plugin_root
        self.context = context
        self.plugin_logger = plugin_logger or logger
        self.root_dir_name = plugin_root.name
        self.module_path = f"{_BRIDGE_MODULE_PREFIX}.{self.root_dir_name}"
        self.plugin_id = ""
        # StarMetadata.name from the handshake; used for plugin page token scopes.
        self.plugin_name = ""
        self.legacy = legacy
        self._external = external
        self._listener = listener
        self._external_queue = external_queue
        self._revoke_external = revoke_external
        self._claims_token: str | None = None
        self._supervisor: RunnerSupervisor | None = None
        self.handshake: Any = None
        self.manifest_metadata: PluginMetadata | None = None
        self._json_schema: dict[str, Any] | None = None
        self._fingerprint = ""
        self._approval_store: CapabilityApprovalStore = CapabilityApprovalStore()
        self._service_router: PluginServiceRouter | None = None
        self._grants = CapabilitySet()
        self._services: dict[str, HostService] = {}
        self._asset_store: AssetStore | None = None
        self._plugin_config: Any = None
        self._handler_full_names: list[str] = []
        self._tool_names: list[str] = []
        self._discovered_tool_names: list[str] = []
        # Activation state read from shared preferences during start(); tools
        # registered before start() default to active.
        self._activated = True
        self._inactivated_llm_tools: list = []
        # Legacy command groups: full group path -> CommandGroupFilter, plus
        # (parent path, filter) pairs linked after every handler registers.
        self._command_group_filters: dict[str, Any] = {}
        self._pending_command_links: list[tuple[str, Any]] = []
        self._web_routes: list[tuple[str, tuple[str, ...]]] = []
        self._views_manifest: dict = {}
        # Core events currently being served by the Runner, keyed by umo
        # string. Proactive sends mark them so the pipeline skips the LLM
        # stage, mirroring in-process event.send().
        self._inflight_events: dict[str, list[Any]] = {}

    @property
    def runner_pid(self) -> int | None:
        """Return the managed Runner subprocess PID, or None if external/stopped."""
        if self._supervisor is None:
            return None
        return self._supervisor.pid

    async def start(self) -> None:
        """Start the Runner subprocess and register pipeline handlers.

        Raises:
            Exception: Runner startup or handshake failures propagate so the
                plugin manager can record this plugin as failed.
        """
        if self._external is not None:
            # External runners have no local checkout; identity and grants
            # come from the host-side external plugin spec.
            spec = self._external
            self.plugin_id = str(spec["plugin_id"])
            if self.legacy:
                grants = CapabilitySet.from_ids(*_LEGACY_GRANT_IDS)
            else:
                grants = CapabilitySet.from_ids(*(spec.get("capabilities") or ()))
            metadata = SimpleNamespace(
                author=str(spec.get("author") or ""),
                desc=str(spec.get("desc") or ""),
                views=[],
                pages=None,
                display_name=spec.get("display_name"),
                short_desc=spec.get("short_desc"),
                repo=spec.get("repo"),
                support_platforms=[],
                astrbot_version=None,
            )
        elif self.legacy:
            from astrbot_sdk.runtime.loader import _load_metadata_for_legacy

            metadata = _load_metadata_for_legacy(self.plugin_root)
            self.plugin_id = metadata.plugin_id
            grants = CapabilitySet.from_ids(*_LEGACY_GRANT_IDS)
            language = "python"
            command: tuple[str, ...] = ()
        else:
            metadata = load_metadata(self.plugin_root)
            self.manifest_metadata = metadata
            self.plugin_id = metadata.plugin_id
            legacy_only = {
                "config.write",
                "persona.write",
            }
            declared = legacy_only & metadata.capabilities.all_ids
            if declared:
                raise RuntimeError(
                    f"SDK plugin {metadata.name} declares {sorted(declared)}, "
                    "which are legacy-compat capabilities; new SDK plugins "
                    "cannot declare them",
                )
            language = str(getattr(metadata.runtime, "language", "python"))
            command = tuple(getattr(metadata.runtime, "command", ()) or ())
            if language != "python" and not command:
                raise RuntimeError(
                    f"SDK plugin {metadata.name} declares "
                    f"runtime.language={language}; only Python runners are "
                    "supported yet",
                )
            self._fingerprint = compute_package_fingerprint(self.plugin_root)
            grants = await self._approval_store.resolve_grants(
                self.plugin_id,
                metadata.capabilities,
                fingerprint=self._fingerprint,
            )
        # Mirror the in-process loader: reject plugins whose declared
        # astrbot_version range excludes the running core version.
        from astrbot.core.star.star_manager import (
            PluginManager,
            PluginVersionUnsupportedError,
        )

        is_valid, error_message = PluginManager._validate_astrbot_version_specifier(
            getattr(metadata, "astrbot_version", None),
        )
        if not is_valid:
            raise PluginVersionUnsupportedError(
                error_message
                or "The plugin does not support the current AstrBot version."
            )
        self._grants = grants
        python_executable = None
        if self._external is None and (self.legacy or language == "python"):
            python_executable = await ensure_plugin_venv(
                self.plugin_root,
                self.plugin_logger,
            )

        # Services must be ready before start(): capability calls can already
        # arrive while the Runner executes lifecycle.startup during handshake.
        self._asset_store = AssetStore(_asset_root(), self.plugin_id)
        self._services = self._build_services()
        host_info: dict[str, Any] = {}
        if self.legacy:
            # Legacy sync getters (config/providers/personas) are served from
            # this snapshot by the compat layer inside the runner.
            host_info["snapshot"] = await build_legacy_snapshot(self.context)
        config = None
        if self._external is not None:
            config = self._external.get("config")
        elif self.legacy:
            config = _load_legacy_plugin_config(self.plugin_root, self.root_dir_name)
        else:
            config, self._json_schema = _load_sdk_plugin_config(
                self.plugin_root,
                self.root_dir_name,
            )
        self._plugin_config = config
        if self._external is not None:
            if self._external_queue is not None:
                claims = self._external_queue
            elif self._listener is not None:
                token = str(self._external["token"])
                claims = self._listener.register(token)
                self._claims_token = token
            else:
                raise RuntimeError(
                    f"external SDK plugin {self.root_dir_name} has no listener",
                )
            self._supervisor = ExternalRunnerSupervisor(
                self.root_dir_name,
                claims=claims,
                legacy=self.legacy,
                grants=grants,
                config=config,
                capability_handler=self._dispatch_capability,
                service_handler=self._handle_service_call,
                tools_invalidated_handler=self._on_tools_invalidated,
                logger=self.plugin_logger,
                on_circuit_open=self._mark_circuit_open,
                host_info=host_info,
            )
        else:
            self._supervisor = RunnerSupervisor(
                self.plugin_root,
                legacy=self.legacy,
                python_executable=python_executable,
                env={
                    "ASTRBOT_DATA_PATH": str(_asset_root().parent),
                    # Keep SDK plugin data under the AstrBot data directory
                    # instead of the inherited cwd.
                    "ASTRBOT_SDK_DATA_DIR": str(_asset_root().parent / "plugin_data"),
                },
                grants=grants,
                config=config,
                capability_handler=self._dispatch_capability,
                service_handler=self._handle_service_call,
                tools_invalidated_handler=self._on_tools_invalidated,
                logger=self.plugin_logger,
                on_circuit_open=self._mark_circuit_open,
                host_info=host_info,
            )
        try:
            handshake = await self._supervisor.start()
        except Exception:
            if self._claims_token is not None and self._listener is not None:
                self._listener.unregister(self._claims_token)
                self._claims_token = None
            if self._revoke_external is not None:
                self._revoke_external()
            raise
        self.handshake = handshake
        if self._external is not None and handshake.plugin_id != self.plugin_id:
            await self.stop()
            raise RuntimeError(
                f"external runner for {self.root_dir_name} presented "
                f"plugin_id {handshake.plugin_id!r}; expected {self.plugin_id!r}",
            )

        # Views manifest (pages + i18n) is fetched once at start and served
        # to the dashboard from this cache; view file contents stream
        # through the pipeline on demand.
        self._views_manifest = await self._fetch_views_manifest()

        for route_info in handshake.web_routes or []:
            self._services["web.route"].register_route(
                route_info["route"],
                list(route_info["methods"]),
                str(route_info.get("description") or ""),
            )

        self.plugin_name = handshake.name
        inactivated_plugins: list = await sp.global_get("inactivated_plugins", [])
        self._activated = self.module_path not in inactivated_plugins
        self._inactivated_llm_tools = await sp.global_get(
            "inactivated_llm_tools",
            [],
        )
        logo_path = None
        if self._external is None:
            # Same logo.png convention as in-process plugins; external runners
            # have no local checkout to read from.
            logo_file = self.plugin_root / "logo.png"
            if logo_file.is_file():
                logo_path = str(logo_file)
        star_metadata = StarMetadata(
            name=handshake.name,
            author=metadata.author,
            desc=metadata.desc,
            version=handshake.version,
            module_path=self.module_path,
            root_dir_name=self.root_dir_name,
            activated=self._activated,
            logo_path=logo_path,
            views=_metadata_views(metadata),
            i18n=self._views_i18n(),
            display_name=getattr(metadata, "display_name", None),
            short_desc=getattr(metadata, "short_desc", None),
            repo=getattr(metadata, "repo", None),
            support_platforms=list(
                getattr(metadata, "support_platforms", None) or [],
            ),
            astrbot_version=getattr(metadata, "astrbot_version", None),
        )
        if isinstance(config, AstrBotConfig):
            # Same as in-process plugins: the dashboard config tab reads
            # metadata.config and metadata.config.schema.
            star_metadata.config = config
        star_metadata._sdk_views_pages = {
            page["name"]
            for page in (self._views_manifest.get("pages") or [])
            if isinstance(page, dict) and page.get("name")
        }
        star_metadata._sdk_plugin_root = (
            self.plugin_root if self._external is None else None
        )
        star_map[self.module_path] = star_metadata
        star_registry.append(star_metadata)

        registrars = {
            "command": self._register_command,
            "message": self._register_message,
            "tool": self._register_tool,
        }
        for descriptor in handshake.handlers:
            if descriptor.kind.value.startswith("lifecycle."):
                # Lifecycle handlers run inside the Runner, not the Pipeline.
                continue
            if descriptor.kind.value.startswith("hook."):
                registrar = self._register_hook
            else:
                registrar = registrars.get(descriptor.kind.value)
            if registrar is None:
                logger.warning(
                    f"SDK plugin {handshake.name}: handler {descriptor.id} "
                    f"({descriptor.kind.value}) is not supported yet; skipped.",
                )
                continue
            full_name = registrar(descriptor)
            self._handler_full_names.append(full_name)
        # Command-group filters are referenced by their sub-commands for the
        # usage tree; link them only after every handler has been registered
        # so a sub-command declared before its group still resolves.
        for parent_path, sub_filter in sorted(
            self._pending_command_links,
            key=lambda item: item[0].count(" "),
        ):
            parent = self._command_group_filters.get(parent_path)
            if parent is None:
                continue
            parent.add_sub_command_filter(sub_filter)
            if isinstance(sub_filter, CommandGroupFilter):
                sub_filter.parent_group = parent
            else:
                sub_filter.parent_command_names = parent.get_complete_command_names()
                sub_filter._cmpl_cmd_names = None
        star_metadata.star_handler_full_names = list(self._handler_full_names)
        if any(h.kind.value == "lifecycle.tool_discovery" for h in handshake.handlers):
            await self.sync_discovered_tools()
        if self._service_router is not None:
            self._service_router.register(self)
        await self._fire_lifecycle_hooks(EventType.OnPluginLoadedEvent, star_metadata)

    async def stop(self, *, reason: str = "shutdown") -> None:
        """Unregister handlers and shut the Runner down."""
        if self._service_router is not None:
            self._service_router.unregister(self)
        metadata = star_map.get(self.module_path)
        if metadata is not None:
            await self._fire_lifecycle_hooks(
                EventType.OnPluginUnloadedEvent,
                metadata,
            )
        for tool_name in [*self._tool_names, *self._discovered_tool_names]:
            llm_tools.remove_func(tool_name)
        self._tool_names = []
        self._discovered_tool_names = []
        for full_name in self._handler_full_names:
            handler = star_handlers_registry.star_handlers_map.pop(full_name, None)
            if handler is not None:
                star_handlers_registry.remove(handler)
        self._handler_full_names = []
        self._command_group_filters = {}
        self._pending_command_links = []
        star_registry[:] = [
            metadata
            for metadata in star_registry
            if metadata.module_path != self.module_path
        ]
        star_map.pop(self.module_path, None)
        purge_bridge_sessions(self)
        if self._services:
            service = self._services.get("web.route")
            if service is not None:
                service.unregister_all()
        if self._supervisor is not None:
            await self._supervisor.stop(reason=reason)
            self._supervisor = None
        if self._claims_token is not None and self._listener is not None:
            self._listener.unregister(self._claims_token)
            self._claims_token = None
        if self._revoke_external is not None:
            self._revoke_external()

    def supports_live_configure(self) -> bool:
        """Return whether this bridge can apply config updates without restarting."""
        if self.legacy or self._supervisor is None:
            return False
        features = getattr(self.handshake, "features", ()) if self.handshake else ()
        return "live_config_v1" in features or self._json_schema is not None

    async def validate_config(self, candidate: Mapping[str, Any]) -> None:
        """Validate a candidate configuration via schema and live Worker hook."""
        payload = dict(candidate)
        if self._json_schema is not None:
            validate_against_json_schema(self._json_schema, payload)
        if self._supervisor is not None and not self.legacy:
            try:
                await self._require_client().validate_config(payload)
            except RemotePluginError as exc:
                raise InvalidConfig(str(exc)) from exc

    async def configure(self, new_config: Mapping[str, Any]) -> None:
        """Apply a confirmed configuration update live without restarting Runner PID."""
        payload = dict(new_config)
        if self._json_schema is not None:
            validate_against_json_schema(self._json_schema, payload)
        try:
            await self._require_client().configure(payload)
        except RemotePluginError as exc:
            raise InvalidConfig(str(exc)) from exc
        if isinstance(self._plugin_config, AstrBotConfig):
            self._plugin_config.update(payload)
        else:
            self._plugin_config = copy.deepcopy(payload)
        if self._supervisor is not None:
            self._supervisor.config = self._plugin_config

    async def update_capabilities(self, approved_ids: Collection[str]) -> CapabilitySet:
        """Persist Host capability approvals and apply `declared ∩ approved` live."""
        await self._approval_store.set_approved(
            self.plugin_id,
            approved_ids,
            fingerprint=self._fingerprint,
        )
        if self.manifest_metadata is not None:
            effective = await self._approval_store.resolve_grants(
                self.plugin_id,
                self.manifest_metadata.capabilities,
                fingerprint=self._fingerprint,
            )
        else:
            effective = CapabilitySet.from_ids(*approved_ids)
        self._grants = await self._require_client().update_capabilities(effective)
        if self._supervisor is not None:
            self._supervisor.grants = self._grants
        return self._grants

    async def invoke_service(
        self,
        service: str,
        payload: Mapping[str, Any] | None = None,
    ) -> Any:
        """Invoke an exported service on this plugin's running Worker."""
        if self.handshake and self.handshake.services:
            names = {
                str(s.get("name") or s.get("handler_id") or "")
                for s in self.handshake.services
            }
            if service not in names:
                raise NotFound(f"service not found on {self.plugin_name}: {service}")
        return await self._require_client().invoke_service(service, payload or {})

    async def _handle_service_call(
        self,
        plugin_id: str,
        service: str,
        payload: Mapping[str, Any],
    ) -> Any:
        if self._service_router is None:
            raise NotFound("plugin service router is unavailable")
        return await self._service_router.route(self, plugin_id, service, payload)

    async def _on_tools_invalidated(self) -> None:
        await self.sync_discovered_tools()

    async def sync_discovered_tools(self) -> list[str]:
        """Refresh `@on.tool_discovery` tools into `llm_tools` atomically."""
        result = await self._require_client().discover_tools()
        for prev_name in self._discovered_tool_names:
            if prev_name not in self._tool_names:
                llm_tools.remove_func(prev_name)
        self._discovered_tool_names = []
        raw_tools = result.get("tools", []) if isinstance(result, Mapping) else []
        for entry in raw_tools:
            if not isinstance(entry, Mapping):
                continue
            name = str(entry.get("name") or "")
            if not name or name in self._tool_names:
                continue
            func_args = [
                {
                    "type": str(p.get("type", "string")),
                    "name": str(p.get("name", "")),
                    "description": str(p.get("description", "")),
                }
                for p in (entry.get("params") or [])
                if isinstance(p, Mapping)
            ]
            stub = self._make_tool_stub(f"tool:{name}")
            llm_tools.add_func(
                name,
                func_args,
                str(entry.get("description") or name),
                stub,
            )
            func_tool = llm_tools.get_func(name)
            if func_tool is not None:
                func_tool.handler_module_path = self.module_path
                func_tool.active = (
                    self._activated and name not in self._inactivated_llm_tools
                )
            self._discovered_tool_names.append(name)
        return list(self._discovered_tool_names)

    def _register_command(self, descriptor: Any) -> str:
        """Register one remote command handler as a pipeline stub.

        Args:
            descriptor: Handler descriptor received in the Runner handshake.

        Returns:
            The registered handler full name.

        Raises:
            InvalidRequest: The command declaration cannot be mapped onto the
                pipeline command filter.
        """
        command_path = descriptor.details.get("path")
        if not isinstance(command_path, str) or not command_path.strip():
            raise InvalidRequest(f"command handler {descriptor.id} has no path")
        parts = command_path.split()

        aliases: set[str] = set()
        parent_prefix = " ".join(parts[:-1])
        for alias in descriptor.details.get("aliases", []):
            alias_str = str(alias).strip()
            if not alias_str:
                continue
            if not parent_prefix:
                aliases.add(alias_str)
            elif alias_str.startswith(f"{parent_prefix} "):
                aliases.add(alias_str[len(parent_prefix) + 1 :].strip())
            elif " " not in alias_str:
                aliases.add(alias_str)
            else:
                raise InvalidRequest(
                    f"alias {alias!r} must share the parent path of {command_path!r}",
                )

        is_group = bool(descriptor.details.get("group"))
        group_custom_filters = bool(descriptor.details.get("group_custom_filters"))
        stub = self._make_command_stub(descriptor.id, command_path)
        stub.__signature__ = self._build_stub_signature(descriptor)

        full_name = f"{self.module_path}_{descriptor.id}"
        handler_md = StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name=full_name,
            handler_name=descriptor.id,
            handler_module_path=self.module_path,
            handler=stub,
            event_filters=[],
            desc=descriptor.description or "",
            extras_configs={
                "priority": descriptor.priority,
                # Mirror the in-process quirk: a sub-command handler nests
                # under its group in list_commands() only when the command
                # decorator created the handler metadata (bottom-most
                # decorator); otherwise it lists flat at root level.
                **(
                    {"sub_command": True}
                    if descriptor.details.get("sub_command")
                    else {}
                ),
            },
        )
        command_filter = self._build_command_filter(
            parts,
            aliases,
            handler_md,
            group=is_group,
            defer_bare=group_custom_filters,
        )
        handler_md.event_filters.append(command_filter)
        roles = set(descriptor.details.get("roles", []))
        if roles == {"admin"}:
            from astrbot.core.star.filter.permission import (
                PermissionType,
                PermissionTypeFilter,
            )

            # Runs after the command filter, mirroring in-process decorator
            # order: the usage reply wins over a silent permission skip.
            handler_md.event_filters.append(
                PermissionTypeFilter(PermissionType.ADMIN),
            )
        elif roles:
            logger.warning(
                "member-only role filtering is not supported yet; "
                f"handler {descriptor.id} ignores roles {sorted(roles)}",
            )
        msg_types = descriptor.details.get("message_types") or []
        if msg_types:
            from astrbot.core.star.filter.event_message_type import (
                EventMessageType,
                EventMessageTypeFilter,
            )

            type_flags = EventMessageType(0)
            for message_type in msg_types:
                type_flags |= {
                    "private": EventMessageType.PRIVATE_MESSAGE,
                    "group": EventMessageType.GROUP_MESSAGE,
                    "other": EventMessageType.OTHER_MESSAGE,
                }[message_type]
            handler_md.event_filters.append(EventMessageTypeFilter(type_flags))
        platforms = descriptor.details.get("platforms") or []
        if platforms:
            from astrbot.core.star.filter.platform_adapter_type import (
                ADAPTER_NAME_2_TYPE,
                PlatformAdapterType,
                PlatformAdapterTypeFilter,
            )

            platform_flags = PlatformAdapterType(0)
            matched_all = False
            for platform in platforms:
                p_name = str(platform)
                if p_name == "all":
                    matched_all = True
                    break
                flag = ADAPTER_NAME_2_TYPE.get(p_name)
                if flag is not None:
                    platform_flags |= flag
            if not matched_all and platform_flags:
                handler_md.event_filters.append(
                    PlatformAdapterTypeFilter(platform_flags),
                )
            elif not matched_all:
                handler_md.event_filters.append(
                    PlatformAdapterTypeFilter(str(platforms[0])),
                )
        star_handlers_registry.append(handler_md)
        if is_group:
            self._command_group_filters[command_path] = command_filter
            if group_custom_filters:
                # Group-level custom filters live in the Runner and cannot be
                # evaluated synchronously by waking_check. A synthetic handler
                # matching exactly the bare group-name message activates
                # instead, letting the plugin decide between the usage tree
                # and a silent fall-through to the LLM stage.
                bare_filters: list = [_BareGroupHandlerFilter(command_filter)]
                if roles == {"admin"}:
                    bare_filters.append(PermissionTypeFilter(PermissionType.ADMIN))
                star_handlers_registry.append(
                    StarHandlerMetadata(
                        event_type=EventType.AdapterMessageEvent,
                        handler_full_name=f"{full_name}__bare",
                        handler_name=f"{descriptor.id}__bare",
                        handler_module_path=self.module_path,
                        handler=self._make_command_stub(
                            descriptor.id,
                            command_path,
                            group_filter=command_filter,
                        ),
                        event_filters=bare_filters,
                        desc=descriptor.description or "",
                        extras_configs={"priority": descriptor.priority},
                    ),
                )
                self._handler_full_names.append(f"{full_name}__bare")
        if parts[:-1]:
            self._pending_command_links.append(
                (" ".join(parts[:-1]), command_filter),
            )
        return full_name

    def _build_stub_signature(self, descriptor: Any) -> inspect.Signature:
        """Reconstruct the declared command signature for argument parsing."""
        parameters = [
            inspect.Parameter("self", inspect.Parameter.POSITIONAL_OR_KEYWORD),
            inspect.Parameter("event", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        ]
        for entry in descriptor.details.get("params", []):
            name = str(entry["name"])
            param_type = _param_types()[str(entry["type"])]
            if entry.get("required", True):
                parameters.append(
                    inspect.Parameter(
                        name,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        annotation=param_type,
                    ),
                )
            else:
                parameters.append(
                    inspect.Parameter(
                        name,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        default=entry.get("default"),
                    ),
                )
        return inspect.Signature(parameters)

    @staticmethod
    def _build_command_filter(
        parts: list[str],
        aliases: set[str],
        handler_md: StarHandlerMetadata,
        *,
        group: bool = False,
        defer_bare: bool = False,
    ) -> Any:
        """Build the core command filter matching the SDK command path."""
        if group:
            # Group anchors replicate the in-process CommandGroupFilter: a
            # bare group-name message raises the usage-tree reply instead of
            # running the (usually empty) fallback handler. With Runner-side
            # custom filters, the bare reply is deferred to the plugin.
            cls = _DeferringCommandGroupFilter if defer_bare else CommandGroupFilter
            return cls(
                group_name=parts[-1],
                alias=aliases,
            )
        from astrbot.core.star.filter.command import CommandFilter

        return CommandFilter(
            command_name=parts[-1],
            alias=aliases,
            handler_md=handler_md,
            parent_command_names=([" ".join(parts[:-1])] if len(parts) > 1 else [""]),
        )

    def _register_message(self, descriptor: Any) -> str:
        """Register one remote message handler as a pipeline stub.

        FilterSpec from the handshake is compiled onto core's existing handler
        filters; the Host applies them before invoking the Runner.

        Args:
            descriptor: Message handler descriptor from the handshake.

        Returns:
            The registered handler full name.
        """
        stub = self._make_message_stub(descriptor.id)

        full_name = f"{self.module_path}_{descriptor.id}"
        handler_md = StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name=full_name,
            handler_name=descriptor.id,
            handler_module_path=self.module_path,
            handler=stub,
            event_filters=self._build_message_filters(descriptor),
            desc=descriptor.description or "",
            extras_configs={"priority": descriptor.priority},
        )
        star_handlers_registry.append(handler_md)
        return full_name

    @staticmethod
    def _build_message_filters(descriptor: Any) -> list:
        """Compile handshake filter details into core handler filters."""
        from astrbot.core.star.filter.button_action import ButtonActionFilter
        from astrbot.core.star.filter.event_message_type import (
            EventMessageType,
            EventMessageTypeFilter,
        )
        from astrbot.core.star.filter.permission import (
            PermissionType,
            PermissionTypeFilter,
        )
        from astrbot.core.star.filter.platform_adapter_type import (
            ADAPTER_NAME_2_TYPE,
            PlatformAdapterType,
            PlatformAdapterTypeFilter,
        )
        from astrbot.core.star.filter.regex import RegexFilter
        from astrbot.core.star.filter.ui_action import UIActionFilter

        details = descriptor.details
        filters: list = []

        type_flags = EventMessageType(0)
        for message_type in details.get("message_types", []):
            type_flags |= {
                "private": EventMessageType.PRIVATE_MESSAGE,
                "group": EventMessageType.GROUP_MESSAGE,
                "other": EventMessageType.OTHER_MESSAGE,
            }[message_type]
        filters.append(
            EventMessageTypeFilter(type_flags or EventMessageType.ALL),
        )

        platforms = details.get("platforms") or []
        if platforms:
            platform_flags = PlatformAdapterType(0)
            matched_all = False
            for platform in platforms:
                p_name = str(platform)
                if p_name == "all":
                    matched_all = True
                    break
                flag = ADAPTER_NAME_2_TYPE.get(p_name)
                if flag is not None:
                    platform_flags |= flag
            if not matched_all and platform_flags:
                filters.append(PlatformAdapterTypeFilter(platform_flags))
            elif not matched_all:
                filters.append(PlatformAdapterTypeFilter(str(platforms[0])))

        roles = set(details.get("roles", []))
        if roles == {"admin"}:
            filters.append(PermissionTypeFilter(PermissionType.ADMIN))
        elif roles:
            logger.warning(
                "member-only role filtering is not supported yet; "
                f"handler {descriptor.id} ignores roles {sorted(roles)}",
            )

        regex = details.get("regex")
        if regex:
            import re

            filters.append(
                RegexFilter(
                    re.compile(str(regex), int(details.get("regex_flags", 0))),
                ),
            )
        if details.get("button_action"):
            filters.append(ButtonActionFilter(details.get("button_action_id")))
        if details.get("ui_action"):
            filters.append(UIActionFilter(details.get("ui_action_id")))
        return filters

    def _mark_event_sent(self, umo: Any) -> None:
        """Mirror in-process event.send() on every in-flight event for umo."""
        for event in self._inflight_events.get(to_umo_string(umo), ()):
            event._has_send_oper = True

    def _make_message_stub(self, handler_id: str) -> Any:
        """Create the async generator bridging pipeline and message invocation.

        Args:
            handler_id: Remote handler ID.

        Returns:
            Async generator function compatible with call_handler.
        """
        bridge = self

        async def stub(event, **_kwargs):
            client = bridge._require_client()
            sdk_event = to_sdk_event(event, asset_store=bridge._asset_store)
            key = to_umo_string(sdk_event.umo)
            bridge._inflight_events.setdefault(key, []).append(event)
            try:
                async for result in client.invoke(handler_id, sdk_event):
                    if result is not None:
                        if isinstance(result, SDKViewResult):
                            if result.propagation is Propagation.STOP:
                                event.stop_event()
                            yield CoreViewResult(
                                name=result.name,
                                data=dict(result.data),
                                text=result.text,
                                title=result.title,
                            )
                            continue
                        apply_sdk_result(
                            event,
                            result,
                            resolve_asset=bridge._require_asset_store().resolve,
                        )
                    yield
            finally:
                events = bridge._inflight_events.get(key)
                if events and event in events:
                    events.remove(event)
                    if not events:
                        bridge._inflight_events.pop(key, None)

        stub.__module__ = bridge.module_path
        return stub

    def _register_tool(self, descriptor: Any) -> str:
        """Register one remote tool handler into the core tool registry.

        Args:
            descriptor: Tool handler descriptor from the handshake.

        Returns:
            The registered handler full name.

        Raises:
            InvalidRequest: The tool declaration is incomplete.
        """
        tool_name = descriptor.details.get("name")
        if not isinstance(tool_name, str) or not tool_name:
            raise InvalidRequest(f"tool handler {descriptor.id} has no name")
        func_args = [
            {
                "type": str(param["type"]),
                "name": str(param["name"]),
                "description": str(param.get("description", "")),
            }
            for param in descriptor.details.get("params", [])
        ]
        stub = self._make_tool_stub(descriptor.id)
        llm_tools.add_func(
            tool_name,
            func_args,
            descriptor.description or "",
            stub,
        )
        self._tool_names.append(tool_name)
        func_tool = llm_tools.get_func(tool_name)
        if func_tool is not None:
            # Attribute the tool to this plugin so plugin-level activation,
            # per-plugin tool listing, and tool toggles all apply.
            func_tool.handler_module_path = self.module_path
            func_tool.active = (
                self._activated and tool_name not in self._inactivated_llm_tools
            )
        full_name = f"{self.module_path}_{descriptor.id}"
        # Mirror the in-process register_llm_tool decorator so the tool shows
        # up on the dashboard plugin detail page.
        star_handlers_registry.append(
            StarHandlerMetadata(
                event_type=EventType.OnCallingFuncToolEvent,
                handler_full_name=full_name,
                handler_name=tool_name,
                handler_module_path=self.module_path,
                handler=stub,
                event_filters=[],
                desc=descriptor.description or "",
            )
        )
        return full_name

    def _register_hook(self, descriptor: Any) -> str:
        """Register one remote Pipeline hook into the core hook registry.

        Args:
            descriptor: Hook handler descriptor from the handshake.

        Returns:
            The registered handler full name.
        """
        stage = str(descriptor.details.get("stage", ""))
        event_type = stage_event_type(stage)
        stub = self._make_hook_stub(descriptor.id, stage)

        full_name = f"{self.module_path}_{descriptor.id}"
        handler_md = StarHandlerMetadata(
            event_type=event_type,
            handler_full_name=full_name,
            handler_name=descriptor.id,
            handler_module_path=self.module_path,
            handler=stub,
            event_filters=[],
            desc=descriptor.description or "",
            extras_configs={"priority": descriptor.priority},
        )
        star_handlers_registry.append(handler_md)
        return full_name

    def _make_hook_stub(self, handler_id: str, stage: str) -> Any:
        """Create the coroutine bridging core hook points to the Runner.

        Args:
            handler_id: Remote hook handler ID.
            stage: Hook stage name.

        Returns:
            Async callable compatible with call_event_hook.
        """
        bridge = self

        async def stub(event, *args):
            client = bridge._require_client()
            if is_metadata_stage(stage):
                # plugin_loaded/unloaded pass StarMetadata, not an event.
                payload = snapshot_stage(stage, None, (event,))
                sdk_event = None
            else:
                payload = snapshot_stage(stage, event, args, store=bridge._asset_store)
                sdk_event = to_sdk_event(event, asset_store=bridge._asset_store)
            result = await client.invoke_hook(
                handler_id,
                sdk_event,
                stage,
                payload,
            )
            apply_hook_result(
                stage,
                event,
                args,
                result,
                grants=bridge._grants,
                store=bridge._asset_store,
                logger=bridge.plugin_logger,
            )

        return stub

    def _make_tool_stub(self, handler_id: str) -> Any:
        """Create the callable bridging agent tool calls to the Runner.

        The core tool executor invokes it as ``handler(event, **tool_args)``;
        the return value flows back into the agent prompt.

        Args:
            handler_id: Remote tool handler ID.

        Returns:
            Async callable compatible with the core tool executor.
        """
        bridge = self

        async def stub(event, **kwargs):
            client = bridge._require_client()
            sdk_event = None
            unified = getattr(event, "unified_msg_origin", None)
            if isinstance(unified, str):
                sdk_event = to_sdk_event(event, asset_store=bridge._asset_store)
            call = ToolCallContext(
                id=f"call_{uuid4().hex[:12]}",
                umo=sdk_event.umo if sdk_event is not None else None,
                event=sdk_event,
            )
            key = to_umo_string(sdk_event.umo) if sdk_event is not None else None
            if key is not None:
                bridge._inflight_events.setdefault(key, []).append(event)
            try:
                result = await client.invoke_tool(handler_id, call, kwargs)
                if isinstance(result, SDKViewResult):
                    return CoreViewResult(
                        name=result.name,
                        data=dict(result.data),
                        text=result.text,
                        title=result.title,
                    )
                return result
            finally:
                if key is not None:
                    events = bridge._inflight_events.get(key)
                    if events and event in events:
                        events.remove(event)
                        if not events:
                            bridge._inflight_events.pop(key, None)

        stub.__module__ = bridge.module_path
        return stub

    def _make_command_stub(
        self,
        handler_id: str,
        command_path: str,
        *,
        group_filter: CommandGroupFilter | None = None,
    ) -> Any:
        """Create the async generator bridging pipeline and Runner invocation.

        Args:
            handler_id: Remote handler ID.
            command_path: Full command path used for the invocation DTO.
            group_filter: Set for the synthetic bare-group handler: the Runner
                is told the message is the bare group name and its GroupUsage
                marker is rendered into the in-process usage-tree reply.

        Returns:
            Async generator function compatible with call_handler.
        """
        bridge = self

        async def stub(event, **kwargs):
            client = bridge._require_client()
            if group_filter is not None:
                kwargs = {**kwargs, "bare_group": True}
            sdk_event = to_sdk_event(
                event,
                command_path=command_path,
                arguments=kwargs,
                asset_store=bridge._asset_store,
            )
            key = to_umo_string(sdk_event.umo)
            bridge._inflight_events.setdefault(key, []).append(event)
            try:
                async for result in client.invoke(handler_id, sdk_event, **kwargs):
                    if result is not None:
                        if group_filter is not None and isinstance(result, GroupUsage):
                            # Mirror the waking_check ValueError reply
                            # byte-for-byte: the group's custom filters
                            # accepted the bare group-name message.
                            tree = (
                                group_filter.group_name
                                + "\n"
                                + (
                                    group_filter.print_cmd_tree(
                                        group_filter.sub_command_filters,
                                    )
                                )
                            )
                            await event.send(
                                MessageEventResult()
                                .message(
                                    f"插件 {bridge.plugin_name}: 参数不足。"
                                    f"{group_filter.group_name} 指令组下有如下指令，"
                                    f"请参考：\n{tree}",
                                )
                                .use_markdown(False),
                            )
                            event.stop_event()
                        elif isinstance(result, SDKViewResult):
                            if result.propagation is Propagation.STOP:
                                event.stop_event()
                            yield CoreViewResult(
                                name=result.name,
                                data=dict(result.data),
                                text=result.text,
                                title=result.title,
                            )
                            continue
                        else:
                            apply_sdk_result(
                                event,
                                result,
                                resolve_asset=bridge._require_asset_store().resolve,
                            )
                    # Each resume of this generator advances the client stream,
                    # which acknowledges the previous plugin yield.
                    yield
            finally:
                events = bridge._inflight_events.get(key)
                if events and event in events:
                    events.remove(event)
                    if not events:
                        bridge._inflight_events.pop(key, None)

        stub.__module__ = bridge.module_path
        return stub

    async def _dispatch_capability(
        self,
        grant: CapabilityGrant,
        operation: str,
        payload: dict[str, Any],
    ) -> Any:
        """Route one authorized Runner-to-Host call through the service registry.

        Args:
            grant: Effective capability grant of this connection.
            operation: Operation within the capability namespace.
            payload: Decoded operation input.

        Returns:
            Operation result encoded by the caller.
        """
        return await dispatch_capability(
            self._services,
            grant.id,
            operation,
            payload,
            plugin_id=self.plugin_id,
            logger=self.plugin_logger,
        )

    def _build_services(self) -> dict[str, HostService]:
        """Create the Host services available to this plugin."""
        store = self._require_asset_store()
        services: tuple[HostService, ...] = (
            StorageService(self.plugin_id),
            SpStoreService(),
            MessageSendService(self.context, store, mark_sent=self._mark_event_sent),
            ConversationReadService(self.context),
            ConversationWriteService(self.context, store=store),
            AssetTransferService(store),
            FileTokenService(store),
            PluginInspectService(),
            PluginLifecycleService(self.context),
            ProviderWriteService(self.context),
            PlatformRawService(self.context),
            EventStateService(self._inflight_events, store),
            EventInjectService(self.context),
            DbService(self.context),
            ConfigWriteService(
                lambda: self._plugin_config,
                lambda: self.context.astrbot_config_mgr.ucr,
            ),
            PersonaWriteService(self.context),
            SubagentReloadService(self.context),
            CronScheduleService(self),
            KnowledgeBaseService(self.context),
            MessageHistoryService(self.context),
            RenderImageService(self.context, store),
            LLMGenerateService(self.context, store),
            LLMEmbedService(self.context),
            SpeechTranscribeService(self.context, store),
            SpeechSynthesizeService(self.context, store),
            ToolRegisterService(
                self._make_tool_stub,
                self._tool_names.append,
                self.module_path,
            ),
            AgentRunService(self.context, self._tool_names, store),
            SessionWaitService(self),
            WebRouteService(self),
            HandlerRegisterService(self),
        )
        return {service.capability_id: service for service in services}

    async def _fire_lifecycle_hooks(
        self,
        event_type: EventType,
        metadata: StarMetadata,
    ) -> None:
        """Fire plugin_loaded/unloaded hooks for this bridge's plugin.

        Legacy plugin loading fires these inside the PluginManager loop;
        SDK plugins need their own trigger at bridge start/stop.
        """
        handlers = star_handlers_registry.get_handlers_by_event_type(event_type)
        for handler in handlers:
            try:
                await handler.handler(metadata)
            except Exception:
                self.plugin_logger.exception(
                    "plugin lifecycle hook failed: %s",
                    handler.handler_full_name,
                )

    def _require_asset_store(self) -> AssetStore:
        """Return the plugin asset store or fail the invocation."""
        if self._asset_store is None:
            raise RuntimeError(
                f"SDK plugin {self.root_dir_name} has no asset store",
            )
        return self._asset_store

    def _require_client(self) -> StdioPluginClient:
        """Return the running client or fail the invocation."""
        if self._supervisor is None:
            raise RuntimeError(f"SDK plugin {self.root_dir_name} is not running")
        return self._supervisor.require_client()

    async def _fetch_views_manifest(self) -> dict:
        """Fetch the views manifest (pages and i18n) from the Runner.

        Failures degrade to empty views rather than breaking plugin load.
        """
        try:
            client = self._require_client()
            items = [item async for item in client.invoke_views("manifest")]
        except Exception as exc:  # noqa: BLE001 - views must not break load
            self.plugin_logger.warning(
                "views manifest fetch failed for %s: %s",
                self.root_dir_name,
                exc,
            )
            return {}
        info = items[0].get("info") if items else {}
        return {
            "pages": list(info.get("pages") or []),
            "i18n": dict(info.get("i18n") or {}),
        }

    def _views_i18n(self) -> dict[str, dict]:
        """Parse the manifest's inline i18n JSON strings into dicts."""
        import json

        translations: dict[str, dict] = {}
        for locale, content in (self._views_manifest.get("i18n") or {}).items():
            try:
                translations[locale] = json.loads(content)
            except (TypeError, json.JSONDecodeError):
                self.plugin_logger.warning(
                    "invalid i18n file for locale %s in %s",
                    locale,
                    self.root_dir_name,
                )
        return translations

    def _mark_circuit_open(self) -> None:
        """Record the circuit-open state on the plugin's registry entry."""
        purge_bridge_sessions(self)
        metadata = star_map.get(self.module_path)
        if metadata is not None:
            metadata.error = (
                "plugin runner crashed repeatedly; circuit opened "
                "(reload the plugin to retry)"
            )


class SDKPluginManager:
    """Load and track every SDK plugin below the plugin store directory."""

    def __init__(self, context: Context, plugin_store_path: str | Path) -> None:
        """Initialize the manager.

        Args:
            context: AstrBot star context.
            plugin_store_path: Directory containing installed plugins.
        """
        self.context = context
        self.plugin_store_path = Path(plugin_store_path)
        self.bridges: dict[str, SDKPluginBridge] = {}
        self.listeners: dict[tuple[str, int], ExternalRunnerListener] = {}
        self.uds_listener: ExternalUDSListener | None = None
        self.approval_store = CapabilityApprovalStore()
        self.service_router = PluginServiceRouter()
        self.blocked_plugins: dict[str, BlockedPlugin] = {}
        self._last_plan: DependencyPlan | None = None

    def find_bridge(self, identifier: str) -> Any | None:
        """Find a running bridge by directory name, plugin name, or plugin ID."""
        if identifier in self.bridges:
            return self.bridges[identifier]
        for bridge in self.bridges.values():
            if identifier in (
                getattr(bridge, "plugin_name", ""),
                getattr(bridge, "plugin_id", ""),
                getattr(bridge, "root_dir_name", ""),
            ):
                return bridge
        return None

    async def load_all(
        self,
        specified_dir_name: str | None = None,
        runtime_overrides: dict | None = None,
    ) -> list[str]:
        """Start bridges for every SDK plugin directory in dependency order.

        Args:
            specified_dir_name: Load only this plugin directory when given.
            runtime_overrides: User runtime choices keyed by plugin directory
                name; they take precedence over metadata declarations when
                detecting isolated legacy plugins.

        Returns:
            Directory names of successfully loaded SDK plugins.

        Raises:
            Exception: The first plugin failure aborts the load; the caller
                records it in the plugin manager failed list.
        """
        from astrbot_sdk.errors import InvalidPluginMetadata, UnsupportedMetadataVersion

        loaded: list[str] = []
        if not self.plugin_store_path.is_dir():
            return loaded

        legacy_dirs: list[Path] = []
        sdk_dirs: dict[str, Path] = {}
        sdk_candidates: dict[str, PluginMetadata] = {}
        unplanned_sdk_dirs: list[Path] = []

        for entry in self.plugin_store_path.iterdir():
            if not entry.is_dir():
                continue
            if is_sdk_plugin_dir(entry):
                sdk_dirs[entry.name] = entry
                try:
                    sdk_candidates[entry.name] = load_metadata(entry)
                except (InvalidPluginMetadata, UnsupportedMetadataVersion):
                    if specified_dir_name is None or entry.name == specified_dir_name:
                        unplanned_sdk_dirs.append(entry)
            elif is_isolated_legacy_dir(entry, runtime_overrides):
                if specified_dir_name is None or entry.name == specified_dir_name:
                    legacy_dirs.append(entry)

        plan = build_dependency_plan(sdk_candidates)
        if specified_dir_name is None:
            self._last_plan = plan
            self.blocked_plugins = dict(plan.blocked)
            for dir_name, blocked_info in plan.blocked.items():
                logger.warning(f"Blocked SDK plugin {dir_name}: {blocked_info.reason}")
        elif specified_dir_name in plan.blocked:
            blocked_info = plan.blocked[specified_dir_name]
            self.blocked_plugins[specified_dir_name] = blocked_info
            raise DependencyBlocked(blocked_info.reason)

        for entry in legacy_dirs:
            bridge = SDKPluginBridge(entry, self.context, legacy=True)
            await bridge.start()
            self.bridges[entry.name] = bridge
            loaded.append(entry.name)
            logger.info(f"Loaded SDK plugin {entry.name} (isolated)")

        sdk_order = (
            [specified_dir_name]
            if specified_dir_name and specified_dir_name in plan.load_order
            else list(plan.load_order)
            if specified_dir_name is None
            else []
        )
        for dir_name in sdk_order:
            entry = sdk_dirs[dir_name]
            bridge = SDKPluginBridge(entry, self.context)
            if isinstance(bridge, SDKPluginBridge):
                bridge._approval_store = self.approval_store
                bridge._service_router = self.service_router
            await bridge.start()
            self.bridges[dir_name] = bridge
            loaded.append(dir_name)
            logger.info(f"Loaded SDK plugin {dir_name} (isolated)")

        for entry in unplanned_sdk_dirs:
            bridge = SDKPluginBridge(entry, self.context)
            if isinstance(bridge, SDKPluginBridge):
                bridge._approval_store = self.approval_store
                bridge._service_router = self.service_router
            await bridge.start()
            self.bridges[entry.name] = bridge
            loaded.append(entry.name)
            logger.info(f"Loaded SDK plugin {entry.name} (isolated)")

        return loaded

    async def load_external(self, specified_name: str | None = None) -> list[str]:
        """Start bridges for external plugins declared in the host config.

        External plugins are declared in ``data/config/sdk_bridge_external.json``
        and attach over WebSocket or Unix domain sockets (`"transport": "uds"`).

        Args:
            specified_name: Load only this external plugin when given.

        Returns:
            Names of successfully loaded external plugins.
        """
        from astrbot.core.utils.astrbot_path import get_astrbot_config_path

        loaded: list[str] = []
        config_path = Path(get_astrbot_config_path()) / "sdk_bridge_external.json"
        if not config_path.is_file():
            return loaded
        spec = json.loads(config_path.read_text(encoding="utf-8"))
        default_transport = str(spec.get("transport") or "websocket").lower()
        cred_dir = Path(
            spec.get("credential_dir")
            or (Path(get_astrbot_config_path()) / "sdk_external_credentials")
        )

        listener: ExternalRunnerListener | None = None
        for plugin in spec.get("plugins") or []:
            name = str(plugin["name"])
            if specified_name and name != specified_name:
                continue
            transport = str(plugin.get("transport") or default_transport).lower()
            if transport == "uds":
                if self.uds_listener is None:
                    sock_dir = spec.get("socket_dir")
                    self.uds_listener = ExternalUDSListener(
                        Path(sock_dir) if sock_dir else None
                    )
                    await self.uds_listener.start()
                plugin_id = str(plugin["plugin_id"])
                _, queue = self.uds_listener.enroll(
                    plugin_id,
                    cred_dir,
                    credential=plugin.get("credential"),
                )
                uds_ref = self.uds_listener
                bridge = SDKPluginBridge(
                    self.plugin_store_path / name,
                    self.context,
                    legacy=bool(plugin.get("legacy")),
                    external=plugin,
                    external_queue=queue,
                    revoke_external=lambda pid=plugin_id: uds_ref.revoke(pid),
                )
            else:
                if listener is None:
                    host, _, port_text = str(
                        spec.get("listen") or "127.0.0.1:6195"
                    ).rpartition(":")
                    key = (host or "127.0.0.1", int(port_text or "6195"))
                    listener = self.listeners.get(key)
                    if listener is None:
                        listener = ExternalRunnerListener(*key)
                        await listener.start()
                        self.listeners[key] = listener
                bridge = SDKPluginBridge(
                    self.plugin_store_path / name,
                    self.context,
                    legacy=bool(plugin.get("legacy")),
                    external=plugin,
                    listener=listener,
                )
            if isinstance(bridge, SDKPluginBridge):
                bridge._approval_store = self.approval_store
                bridge._service_router = self.service_router
            await bridge.start()
            self.bridges[name] = bridge
            loaded.append(name)
            logger.info(f"Loaded external SDK plugin {name} ({transport})")
        return loaded

    async def unload(self, dir_name: str, *, reason: str = "shutdown") -> None:
        """Stop and forget the bridge of one plugin directory.

        Args:
            dir_name: Plugin directory name previously loaded by this manager.
            reason: Shutdown reason forwarded to the Worker lifecycle hook.
        """
        bridge = self.bridges.pop(dir_name, None)
        if bridge is not None:
            await bridge.stop(reason=reason)

    async def stop_all(self) -> None:
        """Shut down every running bridge (reverse topological order) and listener."""
        ordered: list[str] = []
        if self._last_plan is not None:
            for d in self._last_plan.unload_order:
                if d in self.bridges and d not in ordered:
                    ordered.append(d)
        for d in reversed(list(self.bridges.keys())):
            if d not in ordered:
                ordered.append(d)
        for dir_name in ordered:
            bridge = self.bridges.pop(dir_name, None)
            if bridge is not None:
                await bridge.stop(reason="shutdown")
        self.bridges.clear()
        for listener in list(self.listeners.values()):
            await listener.stop()
        self.listeners.clear()
        if self.uds_listener is not None:
            await self.uds_listener.stop()
            self.uds_listener = None
