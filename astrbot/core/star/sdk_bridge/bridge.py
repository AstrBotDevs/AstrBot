from __future__ import annotations

import inspect
import json
import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from astrbot_sdk.capabilities import CapabilityGrant, CapabilitySet
from astrbot_sdk.chatui import ViewResult as SDKViewResult
from astrbot_sdk.errors import InvalidRequest
from astrbot_sdk.events import MessageEvent
from astrbot_sdk.runtime.metadata import load_metadata
from astrbot_sdk.runtime.stdio_client import StdioPluginClient
from astrbot_sdk.tools import ToolCallContext

from astrbot.core import logger, sp
from astrbot.core.provider.register import llm_tools
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.star import StarMetadata, star_map, star_registry
from astrbot.core.star.star_handler import (
    EventType,
    StarHandlerMetadata,
    star_handlers_registry,
)

from ..sdk_plugin_metadata import _BRIDGE_MODULE_PREFIX, is_sdk_plugin_dir
from .convert import apply_sdk_result, to_core_view_result, to_sdk_event
from .hooks import (
    apply_hook_result,
    is_metadata_stage,
    snapshot_stage,
    stage_event_type,
)
from .services import (
    AgentRunService,
    AgentSessionService,
    AssetStore,
    AssetTransferService,
    ConversationReadService,
    ConversationWriteService,
    DecisionModelService,
    HostService,
    LLMEmbedService,
    LLMGenerateService,
    MessageSendService,
    PluginInspectService,
    RenderImageService,
    SessionLocaleService,
    SessionWaitService,
    SpeechSynthesizeService,
    SpeechTranscribeService,
    StorageService,
    ToolRegisterService,
    WebRouteService,
    dispatch_capability,
    purge_bridge_sessions,
)
from .supervisor import ExternalRunnerSupervisor, RunnerSupervisor
from .venv import ensure_plugin_venv
from .ws_listener import ExternalRunnerListener

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent
    from astrbot.core.star.context import Context


def _asset_root() -> Path:
    """Return the shared asset root below the AstrBot data directory."""
    from astrbot.core.utils.astrbot_path import get_astrbot_data_path

    return Path(get_astrbot_data_path()) / "sdk_assets"


def _param_types() -> dict[str, type]:
    return {
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
    }


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
        external: Mapping[str, Any] | None = None,
        listener: ExternalRunnerListener | None = None,
    ) -> None:
        """Initialize the bridge for one SDK plugin.

        Args:
            plugin_root: Plugin repository root with metadata.yaml. For
                external plugins this is a pseudo path; only its name is
                used for registry naming.
            context: AstrBot star context used for platform and config access.
            plugin_logger: Logger receiving Runner stderr output.
            external: External plugin spec (plugin_id, token, capabilities,
                config); when set, the Runner dials in over WebSocket
                instead of being spawned locally.
            listener: Shared external listener the token claims belong to.
        """
        self.plugin_root = plugin_root
        self.context = context
        self.plugin_logger = plugin_logger or logger
        self.root_dir_name = plugin_root.name
        self.module_path = f"{_BRIDGE_MODULE_PREFIX}.{self.root_dir_name}"
        self.plugin_id = ""
        # StarMetadata.name from the handshake; used for plugin page token scopes.
        self.plugin_name = ""
        self._external = external
        self._listener = listener
        self._claims_token: str | None = None
        self._supervisor: RunnerSupervisor | None = None
        self._grants = CapabilitySet()
        self._services: dict[str, HostService] = {}
        self._asset_store: AssetStore | None = None
        self._handler_full_names: list[str] = []
        self._tool_names: list[str] = []
        # Activation state read from shared preferences during start(); tools
        # registered before start() default to active.
        self._activated = True
        self._inactivated_llm_tools: list = []
        self._web_routes: list[tuple[str, tuple[str, ...]]] = []
        self._views_manifest: dict = {}
        self._agent_sources: dict[str, AstrMessageEvent] = {}

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
            grants = CapabilitySet.from_ids(*(spec.get("capabilities") or ()))
            metadata = SimpleNamespace(
                author=str(spec.get("author") or ""),
                desc=str(spec.get("desc") or ""),
                pages=spec.get("views", ()),
                display_name=spec.get("display_name"),
                short_desc=spec.get("short_desc"),
                repo=spec.get("repo"),
                support_platforms=[],
                astrbot_version=None,
            )
        else:
            metadata = load_metadata(self.plugin_root)
            self.plugin_id = metadata.plugin_id
            # The vertical slice grants every declared capability; the user
            # authorization flow will replace this in a later step.
            grants = CapabilitySet.from_ids(*metadata.capabilities.all_ids)
            language = getattr(metadata.runtime, "language", "python")
            if str(language) != "python":
                raise RuntimeError(
                    f"SDK plugin {metadata.name} declares "
                    f"runtime.language={language}; only Python runners are "
                    "supported yet",
                )
        from astrbot.core.chatui import ViewSpec

        views = [
            ViewSpec.model_validate(
                {key: value for key, value in page.items() if key != "entry_file"}
            )
            for page in metadata.pages or ()
        ]
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
        if self._external is None:
            python_executable = await ensure_plugin_venv(
                self.plugin_root,
                self.plugin_logger,
            )

        # Services must be ready before start(): capability calls can already
        # arrive while the Runner executes lifecycle.startup during handshake.
        self._asset_store = AssetStore(_asset_root(), self.plugin_id)
        self._services = self._build_services()
        config = self._external.get("config") if self._external is not None else None
        if self._external is not None:
            if self._listener is None:
                raise RuntimeError(
                    f"external SDK plugin {self.root_dir_name} has no listener",
                )
            token = str(self._external["token"])
            claims = self._listener.register(token)
            self._claims_token = token
            self._supervisor = ExternalRunnerSupervisor(
                self.root_dir_name,
                claims=claims,
                grants=grants,
                config=config,
                capability_handler=self._dispatch_capability,
                logger=self.plugin_logger,
                on_circuit_open=self._mark_circuit_open,
                on_runner_exit=self._clear_runner_state,
            )
        else:
            self._supervisor = RunnerSupervisor(
                self.plugin_root,
                python_executable=python_executable,
                env={
                    # Keep SDK plugin data under the AstrBot data directory
                    # instead of the inherited cwd.
                    "ASTRBOT_SDK_DATA_DIR": str(_asset_root().parent / "plugin_data"),
                },
                grants=grants,
                config=config,
                capability_handler=self._dispatch_capability,
                logger=self.plugin_logger,
                on_circuit_open=self._mark_circuit_open,
                on_runner_exit=self._clear_runner_state,
            )
        try:
            handshake = await self._supervisor.start()
        except Exception:
            await self.stop()
            raise
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

        view_names = frozenset(
            page["name"]
            for page in self._views_manifest.get("pages", [])
            if any(file.get("path") == "index.html" for file in page.get("files", []))
        )
        action_ids = {
            handler.details.get("action_id")
            for handler in handshake.handlers
            if handler.kind.value == "ui_action"
        }
        for spec in views:
            if spec.target == "plugin_page":
                continue
            if spec.name not in view_names or (
                None not in action_ids and set(spec.actions) - action_ids
            ):
                await self.stop()
                raise InvalidRequest(
                    f"view {spec.name!r} needs an entry file and handlers for its declared actions"
                )

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
            views=views,
            runner_view_names=view_names,
            i18n=self._views_i18n(),
            display_name=getattr(metadata, "display_name", None),
            short_desc=getattr(metadata, "short_desc", None),
            repo=getattr(metadata, "repo", None),
            support_platforms=list(
                getattr(metadata, "support_platforms", None) or [],
            ),
            astrbot_version=getattr(metadata, "astrbot_version", None),
        )
        star_map[self.module_path] = star_metadata
        star_registry.append(star_metadata)

        registrars = {
            "command": self._register_command,
            "message": self._register_message,
            "button_action": self._register_message,
            "ui_action": self._register_message,
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
        star_metadata.star_handler_full_names = list(self._handler_full_names)
        await self._fire_lifecycle_hooks(EventType.OnPluginLoadedEvent, star_metadata)

    async def stop(self) -> None:
        """Unregister handlers and shut the Runner subprocess down."""
        metadata = star_map.get(self.module_path)
        if metadata is not None:
            await self._fire_lifecycle_hooks(
                EventType.OnPluginUnloadedEvent,
                metadata,
            )
        for tool_name in self._tool_names:
            llm_tools.remove_func(tool_name)
        self._tool_names = []
        for full_name in self._handler_full_names:
            handler = star_handlers_registry.star_handlers_map.pop(full_name, None)
            if handler is not None:
                star_handlers_registry.remove(handler)
        self._handler_full_names = []
        star_registry[:] = [
            metadata
            for metadata in star_registry
            if metadata.module_path != self.module_path
        ]
        star_map.pop(self.module_path, None)
        if self._services:
            service = self._services.get("web.route")
            if service is not None:
                service.unregister_all()
        if self._supervisor is not None:
            await self._supervisor.stop()
            self._supervisor = None
        await self._clear_runner_state()
        if self._claims_token is not None and self._listener is not None:
            self._listener.unregister(self._claims_token)
            self._claims_token = None

    async def _clear_runner_state(self) -> None:
        """Retire handles owned by the exited Runner."""
        purge_bridge_sessions(self)
        self._agent_sources.clear()
        service = self._services.get("agent.run")
        if isinstance(service, AgentSessionService):
            await service.close()

    @contextmanager
    def _agent_source(
        self,
        event: AstrMessageEvent,
        sdk_event: MessageEvent | None,
    ) -> Iterator[MessageEvent | None]:
        """Bind a source event for the duration of its Runner invocation.

        Args:
            event: Host-owned event, including its effective privileges.
            sdk_event: Portable event delivered to the Runner.

        Yields:
            An event with an opaque reference scoped to this bridge.
        """
        if sdk_event is None or not self._grants.has("agent.run"):
            yield sdk_event
            return
        token = uuid4().hex
        self._agent_sources[token] = event
        try:
            yield replace(sdk_event, _source_token=token)
        finally:
            self._agent_sources.pop(token, None)

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
        for alias in descriptor.details.get("aliases", []):
            alias_parts = str(alias).split()
            if alias_parts[:-1] != parts[:-1]:
                raise InvalidRequest(
                    f"alias {alias!r} must share the parent path of {command_path!r}",
                )
            aliases.add(alias_parts[-1])

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
            extras_configs={"priority": descriptor.priority},
        )
        handler_md.event_filters.append(
            CommandFilter(
                command_name=parts[-1],
                alias=aliases,
                handler_md=handler_md,
                parent_command_names=parts[:-1],
            ),
        )
        roles = set(descriptor.details.get("roles", []))
        if roles == {"admin"}:
            from astrbot.core.star.filter.permission import (
                PermissionType,
                PermissionTypeFilter,
            )

            handler_md.event_filters.append(
                PermissionTypeFilter(PermissionType.ADMIN),
            )
        elif roles:
            logger.warning(
                "member-only role filtering is not supported yet; "
                f"handler {descriptor.id} ignores roles {sorted(roles)}",
            )
        star_handlers_registry.append(handler_md)
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

    def _register_message(self, descriptor: Any) -> str:
        """Register one remote message handler as a pipeline stub.

        FilterSpec from the handshake is compiled onto core's existing handler
        filters; the Host applies them before invoking the Runner.

        Args:
            descriptor: Message handler descriptor from the handshake.

        Returns:
            The registered handler full name.
        """
        from astrbot.core.star.filter.button_action import ButtonActionFilter
        from astrbot.core.star.filter.ui_action import UIActionFilter

        stub = self._make_message_stub(descriptor.id)
        if descriptor.kind.value == "button_action":
            filters = [ButtonActionFilter(descriptor.details.get("action_id"))]
        elif descriptor.kind.value == "ui_action":
            filters = [UIActionFilter(descriptor.details.get("action_id"))]
        else:
            filters = self._build_message_filters(descriptor)

        full_name = f"{self.module_path}_{descriptor.id}"
        handler_md = StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name=full_name,
            handler_name=descriptor.id,
            handler_module_path=self.module_path,
            handler=stub,
            event_filters=filters,
            desc=descriptor.description or "",
            extras_configs={"priority": descriptor.priority},
        )
        star_handlers_registry.append(handler_md)
        return full_name

    @staticmethod
    def _build_message_filters(descriptor: Any) -> list:
        """Compile handshake filter details into core handler filters."""
        from astrbot.core.star.filter.event_message_type import (
            EventMessageType,
            EventMessageTypeFilter,
        )
        from astrbot.core.star.filter.permission import (
            PermissionType,
            PermissionTypeFilter,
        )
        from astrbot.core.star.filter.platform_adapter_type import (
            PlatformAdapterTypeFilter,
        )
        from astrbot.core.star.filter.regex import RegexFilter

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

        for platform in details.get("platforms", []):
            filters.append(PlatformAdapterTypeFilter(str(platform)))

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
        return filters

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
            with bridge._agent_source(event, sdk_event) as source:
                async for result in client.invoke(handler_id, source):
                    if isinstance(result, SDKViewResult):
                        yield to_core_view_result(result)
                        continue
                    if result is not None:
                        apply_sdk_result(
                            event,
                            result,
                            resolve_asset=bridge._require_asset_store().resolve,
                        )
                    yield

        stub.__module__ = self.module_path
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
            with bridge._agent_source(event, sdk_event) as source:
                result = await client.invoke_hook(handler_id, source, stage, payload)
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
            with bridge._agent_source(event, sdk_event) as source:
                call = ToolCallContext(
                    id=f"call_{uuid4().hex[:12]}",
                    umo=source.umo if source is not None else None,
                    event=source,
                )
                result = await client.invoke_tool(handler_id, call, kwargs)
                return (
                    to_core_view_result(result)
                    if isinstance(result, SDKViewResult)
                    else result
                )

        return stub

    def _make_command_stub(
        self,
        handler_id: str,
        command_path: str,
    ) -> Any:
        """Create the async generator bridging pipeline and Runner invocation.

        Args:
            handler_id: Remote handler ID.
            command_path: Full command path used for the invocation DTO.

        Returns:
            Async generator function compatible with call_handler.
        """
        bridge = self

        async def stub(event, **kwargs):
            client = bridge._require_client()
            sdk_event = to_sdk_event(
                event,
                command_path=command_path,
                arguments=kwargs,
                asset_store=bridge._asset_store,
            )
            with bridge._agent_source(event, sdk_event) as source:
                async for result in client.invoke(handler_id, source, **kwargs):
                    if isinstance(result, SDKViewResult):
                        yield to_core_view_result(result)
                        continue
                    if result is not None:
                        apply_sdk_result(
                            event,
                            result,
                            resolve_asset=bridge._require_asset_store().resolve,
                        )
                    yield

        stub.__module__ = self.module_path
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
            MessageSendService(self.context, store),
            ConversationReadService(
                self.context, allow_create=self._grants.has("conversation.write")
            ),
            ConversationWriteService(self.context, self.plugin_id, store),
            AssetTransferService(store),
            PluginInspectService(),
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
            AgentSessionService(self),
            DecisionModelService(self.context),
            SessionLocaleService(self.context),
            SessionWaitService(self),
            WebRouteService(self),
        )
        return {service.capability_id: service for service in services}

    async def _fire_lifecycle_hooks(
        self,
        event_type: EventType,
        metadata: StarMetadata,
    ) -> None:
        """Fire plugin_loaded/unloaded hooks for this bridge's plugin.

        The bridge dispatches these hooks when its Runner starts or stops.
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

    def __init__(self, context: Context, plugin_store_path: str) -> None:
        """Initialize the manager.

        Args:
            context: AstrBot star context.
            plugin_store_path: Directory containing installed plugins.
        """
        self.context = context
        self.plugin_store_path = Path(plugin_store_path)
        self.bridges: dict[str, SDKPluginBridge] = {}
        self.listeners: dict[tuple[str, int], ExternalRunnerListener] = {}

    async def load_all(
        self,
        specified_dir_name: str | None = None,
    ) -> list[str]:
        """Start bridges for every SDK plugin directory.

        Args:
            specified_dir_name: Load only this plugin directory when given.

        Returns:
            Directory names of successfully loaded SDK plugins.

        Raises:
            Exception: The first plugin failure aborts the load; the caller
                records it in the plugin manager failed list.
        """
        loaded: list[str] = []
        if not self.plugin_store_path.is_dir():
            return loaded
        # Iterate in raw directory order to match the in-process loader
        # (_get_modules): handler registration order follows plugin load
        # order, so both runtimes must agree.
        for entry in self.plugin_store_path.iterdir():
            if not entry.is_dir():
                continue
            if specified_dir_name and entry.name != specified_dir_name:
                continue
            if is_sdk_plugin_dir(entry):
                bridge = SDKPluginBridge(entry, self.context)
            else:
                continue
            await bridge.start()
            self.bridges[entry.name] = bridge
            loaded.append(entry.name)
            logger.info(f"Loaded SDK plugin {entry.name} (isolated)")
        return loaded

    async def load_external(self, specified_name: str | None = None) -> list[str]:
        """Start bridges for external plugins declared in the host config.

        External plugins are declared in
        ``data/config/sdk_bridge_external.json``; their Runners dial in
        over the shared WebSocket listener instead of being spawned.

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
        host, _, port_text = str(spec.get("listen") or "127.0.0.1:6195").rpartition(":")
        key = (host or "127.0.0.1", int(port_text or "6195"))
        listener = self.listeners.get(key)
        if listener is None:
            listener = ExternalRunnerListener(*key)
            await listener.start()
            self.listeners[key] = listener
        for plugin in spec.get("plugins") or []:
            name = str(plugin["name"])
            if specified_name and name != specified_name:
                continue
            bridge = SDKPluginBridge(
                self.plugin_store_path / name,
                self.context,
                external=plugin,
                listener=listener,
            )
            await bridge.start()
            self.bridges[name] = bridge
            loaded.append(name)
            logger.info(f"Loaded external SDK plugin {name} (websocket)")
        return loaded

    async def unload(self, dir_name: str) -> None:
        """Stop and forget the bridge of one plugin directory.

        Args:
            dir_name: Plugin directory name previously loaded by this manager.
        """
        bridge = self.bridges.pop(dir_name, None)
        if bridge is not None:
            await bridge.stop()

    async def stop_all(self) -> None:
        """Shut down every running bridge and external listener."""
        for bridge in list(self.bridges.values()):
            await bridge.stop()
        self.bridges.clear()
        for listener in list(self.listeners.values()):
            await listener.stop()
        self.listeners.clear()
