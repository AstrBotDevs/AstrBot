from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import os
import sys
import time
import uuid
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any, BinaryIO

from ..capabilities import CapabilityGrant, CapabilitySet
from ..context import _AMBIENT_CALL_ID
from ..errors import (
    AstrBotSDKError,
    HostUnavailable,
    InvalidPluginDefinition,
    InvalidRequest,
    RemoteHostError,
)
from ..events import MessageEvent
from ..protocol import (
    MAX_FRAME_BYTES,
    PROTOCOL_VERSION,
    AckFrame,
    CancelFrame,
    ErrorFrame,
    ProtocolFrame,
    RequestFrame,
    ResponseFrame,
    YieldFrame,
    decode_frame,
    decode_value,
    encode_frame,
    encode_result,
    encode_value,
)
from ..registration import HandlerKind
from ..results import Propagation
from ..tools import tool_params_schema
from .loader import LoadedPlugin, load_plugin
from .peer import Peer
from .transport import FrameTransport, StdioTransport

_SUPPORTED_PARAM_TYPES = {"str": str, "int": int, "float": float, "bool": bool}
_SUPPORTED_FEATURES = (
    "cancel_v1",
    "capability_update_v1",
    "dynamic_tools_v1",
    "external_attach_v1",
    "live_config_v1",
    "plugin_service_v1",
    "resume_stream_v1",
    "scoped_host_v1",
)
_RESUMABLE_GRACE_SECONDS = 30.0


def _is_message_event_annotation(annotation: Any) -> bool:
    """Check whether one parameter annotation marks the MessageEvent injection.

    Args:
        annotation: Raw parameter annotation, possibly a postponed string.

    Returns:
        True when the parameter receives the injected MessageEvent.
    """
    if annotation is MessageEvent:
        return True
    return isinstance(annotation, str) and annotation.rsplit(".", 1)[-1] == (
        "MessageEvent"
    )


def _is_event_parameter(param: inspect.Parameter) -> bool:
    """Check whether one parameter is the MessageEvent injection slot.

    Args:
        param: Handler signature parameter.

    Returns:
        True when the parameter receives the injected MessageEvent.

    Raises:
        InvalidPluginDefinition: The reserved name carries another annotation.
    """
    if _is_message_event_annotation(param.annotation):
        return True
    if param.name == "event":
        if param.annotation is inspect.Parameter.empty:
            return True
        raise InvalidPluginDefinition(
            "the 'event' parameter name is reserved for the MessageEvent injection"
        )
    return False


def _command_params_schema(registration: Any) -> list[dict[str, Any]]:
    """Build the Host-facing parameter schema for one command handler.

    Args:
        registration: Discovered command handler registration.

    Returns:
        Ordered parameter schema entries for the protocol handshake.

    Raises:
        InvalidPluginDefinition: A user parameter uses an unsupported type.
    """
    parameters = list(inspect.signature(registration.handler).parameters.values())
    # registration.handler is a bound method, so self is usually already
    # omitted; skip it only when it is still present.
    if parameters and parameters[0].name == "self":
        parameters = parameters[1:]
    user_params = parameters
    if user_params and _is_event_parameter(user_params[0]):
        user_params = user_params[1:]

    schema: list[dict[str, Any]] = []
    for param in user_params:
        if param.kind in (
            inspect.Parameter.VAR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        ):
            continue
        if _is_message_event_annotation(param.annotation):
            raise InvalidPluginDefinition(
                "the MessageEvent injection must be the first handler parameter"
            )
        annotation = param.annotation
        param_type = None
        if annotation in _SUPPORTED_PARAM_TYPES.values():
            param_type = annotation
        elif isinstance(annotation, str):
            param_type = _SUPPORTED_PARAM_TYPES.get(annotation)

        has_default = param.default is not inspect.Parameter.empty
        if param_type is None and has_default:
            default_type = type(param.default)
            if default_type in _SUPPORTED_PARAM_TYPES.values():
                param_type = default_type
        if param_type is None:
            raise InvalidPluginDefinition(
                f"command parameter {param.name!r} of handler {registration.id!r} "
                "must use str, int, float or bool"
            )
        if has_default and not isinstance(param.default, param_type):
            raise InvalidPluginDefinition(
                f"default of command parameter {param.name!r} does not match "
                f"its {param_type.__name__} annotation"
            )
        schema.append(
            {
                "name": param.name,
                "type": param_type.__name__,
                "required": not has_default,
                "default": param.default if has_default else None,
            }
        )
    return schema


def _legacy_data_dir(metadata: Any) -> Path:
    """Resolve the legacy plugin data directory shared with in-process mode.

    Legacy plugins keep their files under the AstrBot data directory at
    plugin_data/{name}; when the Host exports ASTRBOT_DATA_PATH the isolated
    Runner must use the same location so switching runtimes keeps the data.
    """
    from .loader import _default_data_dir

    base = os.environ.get("ASTRBOT_DATA_PATH")
    if not base:
        return _default_data_dir(metadata)
    data_dir = Path(base) / "plugin_data" / metadata.name
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


class StdioPluginServer:
    """Serve one SDK plugin over newline-delimited stdio frames."""

    def __init__(
        self,
        plugin_root: Path,
        *,
        reader: BinaryIO | None = None,
        writer: BinaryIO | None = None,
        legacy: bool = False,
        transport: FrameTransport | None = None,
    ) -> None:
        """Initialize the Runner server.

        Args:
            plugin_root: Plugin repository root.
            reader: Binary input stream. Defaults to process stdin.
            writer: Binary output stream. Defaults to process stdout.
            legacy: Load the plugin through the legacy compat layer.
            transport: Frame transport override (e.g. WebSocket). Defaults to
                a stdio transport over reader/writer.
        """
        self.plugin_root = plugin_root.resolve()
        self.legacy = legacy
        if transport is None and writer is None:
            # stdio carries protocol frames; a plugin (or a subprocess it
            # spawns) writing to stdout would corrupt framing. Keep a private
            # copy of fd 1 for the transport and point process stdout at
            # stderr instead.
            writer = os.fdopen(os.dup(1), "wb", closefd=True)
            os.dup2(2, 1)
            sys.stdout = sys.stderr
        self._transport = transport or StdioTransport(
            reader or sys.stdin.buffer,
            writer or sys.stdout.buffer,
        )
        self.loaded_plugin: LoadedPlugin | None = None
        self._peer = Peer(
            send=self._send,
            request_handler=self._handle_request,
            request_id_prefix="runner:",
            remote_error_factory=RemoteHostError,
            internal_error_code="PLUGIN_RUNTIME_ERROR",
        )
        self._invocations: dict[
            str,
            tuple[asyncio.Task[None], asyncio.Queue[int]],
        ] = {}
        self._capability_streams: dict[
            str,
            asyncio.Queue[ProtocolFrame | Exception],
        ] = {}
        self._resumable_streams: dict[str, dict[str, Any]] = {}
        self._stop_reason = "shutdown"
        self._tool_discovery_version = 0
        self._initializing = False
        self._closing = False

    async def serve(self, *, stop_on_exit: bool = True) -> None:
        """Read frames until shutdown or EOF.

        Args:
            stop_on_exit: Stop the loaded plugin and close the peer when the
                read loop exits. External transports with reconnect grace pass
                False on transient disconnects.

        Raises:
            BrokenPipeError: The Host closes stdout while a response is written.
        """
        try:
            while not self._closing:
                line = await self._transport.read()
                if line is None:
                    break
                if len(line) > MAX_FRAME_BYTES:
                    await self._send(
                        ErrorFrame(
                            id="protocol",
                            code=InvalidRequest.code,
                            message="protocol frame exceeds the size limit",
                        )
                    )
                    break
                frame = None
                try:
                    frame = decode_frame(line)
                    if isinstance(frame, RequestFrame) and frame.method in (
                        "invoke",
                        "resumable.invoke",
                    ):
                        if self.loaded_plugin is None:
                            raise InvalidRequest("Runner is not initialized")
                        if frame.id in self._invocations:
                            raise InvalidRequest(f"duplicate invocation id: {frame.id}")
                        acknowledgements: asyncio.Queue[int] = asyncio.Queue()
                        resumable = frame.method == "resumable.invoke" or bool(
                            frame.params.get("resumable")
                        )
                        if resumable:
                            self._prune_resumable_streams()
                            self._resumable_streams[frame.id] = {
                                "last_unacked": None,
                                "terminal": None,
                                "last_acked_seq": 0,
                                "finished_at": None,
                            }
                        task = asyncio.create_task(
                            self._run_web_invocation(frame, acknowledgements)
                            if frame.params.get("web") or frame.params.get("views")
                            else self._run_invocation(
                                frame,
                                acknowledgements,
                                resumable=resumable,
                            )
                        )
                        self._invocations[frame.id] = (task, acknowledgements)
                    elif await self._peer.receive(frame):
                        continue
                    elif isinstance(frame, AckFrame):
                        resumable_state = self._resumable_streams.get(frame.id)
                        if resumable_state is not None:
                            if frame.sequence > resumable_state["last_acked_seq"]:
                                resumable_state["last_acked_seq"] = frame.sequence
                            last_unacked = resumable_state["last_unacked"]
                            if (
                                isinstance(last_unacked, YieldFrame)
                                and last_unacked.sequence <= frame.sequence
                            ):
                                resumable_state["last_unacked"] = None
                        invocation = self._invocations.get(frame.id)
                        if invocation is not None:
                            invocation[1].put_nowait(frame.sequence)
                    elif isinstance(frame, CancelFrame):
                        invocation = self._invocations.get(frame.id)
                        if invocation is not None:
                            invocation[0].cancel()
                    elif isinstance(frame, (YieldFrame, ResponseFrame, ErrorFrame)):
                        queue = self._capability_streams.get(frame.id)
                        if queue is not None:
                            queue.put_nowait(frame)
                        # Late frames for finished streams are dropped.
                    else:
                        raise InvalidRequest(f"Host cannot send {type(frame).__name__}")
                except Exception as exc:
                    code = (
                        exc.code
                        if isinstance(exc, AstrBotSDKError)
                        else "PLUGIN_RUNTIME_ERROR"
                    )
                    await self._send(
                        ErrorFrame(
                            id=getattr(frame, "id", "protocol"),
                            code=code,
                            message=str(exc),
                        )
                    )
        finally:
            if stop_on_exit or self._closing:
                await self._stop_plugin()
                await self._peer.close()

    async def _send(
        self,
        frame: ProtocolFrame,
    ) -> None:
        """Write one Runner peer frame atomically.

        Args:
            frame: Frame to send to the Host.
        """
        await self._transport.write(encode_frame(frame))

    async def _handle_request(self, frame: RequestFrame) -> Any:
        """Dispatch one generic Host-to-Runner request.

        Args:
            frame: Request to dispatch.

        Returns:
            Request result encoded by the Peer.

        Raises:
            InvalidRequest: The method is unknown or invalid for the current state.
        """
        if frame.method == "ping":
            # Liveness probe for the Host supervisor; also runs health check
            # when initialized.
            if self.loaded_plugin is not None and not self.legacy:
                await self.loaded_plugin.check_health()
            return {"protocol_version": PROTOCOL_VERSION}
        if frame.method == "initialize":
            return await self._initialize(frame)
        if frame.method == "validate_config":
            if self.loaded_plugin is None:
                raise InvalidRequest("Runner is not initialized")
            if self.legacy:
                return {"valid": True}
            config = decode_value(frame.params.get("config"))
            await self.loaded_plugin.validate_config(config)
            return {"valid": True}
        if frame.method == "configure":
            if self.loaded_plugin is None:
                raise InvalidRequest("Runner is not initialized")
            if self.legacy:
                raise InvalidRequest("legacy plugins do not support live configure")
            config = decode_value(frame.params.get("config"))
            await self.loaded_plugin.reconfigure(config)
            return {"configured": True}
        if frame.method == "capabilities.update":
            if self.loaded_plugin is None:
                raise InvalidRequest("Runner is not initialized")
            raw_grants = frame.params.get("capabilities", [])
            if not isinstance(raw_grants, list):
                raise InvalidRequest("capabilities must be a list")
            grants: list[CapabilityGrant] = []
            for item in raw_grants:
                if not isinstance(item, Mapping):
                    raise InvalidRequest("capability grant must be an object")
                scope = decode_value(item.get("scope", {}))
                if not isinstance(scope, Mapping):
                    raise InvalidRequest("capability scope must be an object")
                grants.append(CapabilityGrant(id=str(item["id"]), scope=scope))
            target_ctx = getattr(self.loaded_plugin, "sdk_ctx", None)
            if target_ctx is None:
                target_ctx = getattr(self.loaded_plugin.instance, "ctx", None)
            if target_ctx is None:
                raise InvalidRequest("plugin context is unavailable")
            updated = CapabilitySet(grants)
            target_ctx._update_capabilities(updated)
            return {"capabilities": list(updated)}
        if frame.method == "tools.discover":
            if self.loaded_plugin is None:
                raise InvalidRequest("Runner is not initialized")
            if self.legacy:
                return {"version": self._tool_discovery_version, "tools": []}
            discovered = await self.loaded_plugin.discover_tools()
            self._tool_discovery_version += 1
            serialized_tools: list[dict[str, Any]] = []
            for item in discovered:
                if isinstance(item, Mapping):
                    serialized_tools.append(dict(encode_value(dict(item))))
                else:
                    serialized_tools.append(
                        {
                            "name": str(getattr(item, "name", "")),
                            "description": str(getattr(item, "description", "")),
                            "params": [
                                {
                                    "name": param.name,
                                    "type": param.type,
                                    "description": param.description,
                                    "required": param.required,
                                }
                                for param in getattr(item, "params", ())
                            ],
                            "resumable": bool(getattr(item, "resumable", False)),
                            "streaming_input": bool(
                                getattr(item, "streaming_input", False)
                            ),
                        }
                    )
            return {
                "version": self._tool_discovery_version,
                "tools": serialized_tools,
            }
        if frame.method == "invoke_service":
            if self.loaded_plugin is None:
                raise InvalidRequest("Runner is not initialized")
            if self.legacy:
                raise InvalidRequest("legacy plugins do not export services")
            service_name = str(
                frame.params.get("service") or frame.params.get("handler_id") or ""
            )
            if not service_name:
                raise InvalidRequest("service name must be a non-empty string")
            payload = decode_value(frame.params.get("input", {}))
            if payload is None:
                payload = {}
            if not isinstance(payload, Mapping):
                raise InvalidRequest("service input must be an object")
            result = await self.loaded_plugin.invoke_service(
                service_name,
                payload,
                call_id=frame.id,
            )
            return encode_value(result)
        if frame.method == "invoke_tool":
            if self.loaded_plugin is None:
                raise InvalidRequest("Runner is not initialized")
            call = decode_value(frame.params.get("context"))
            args = decode_value(frame.params.get("args", {}))
            if not isinstance(args, Mapping):
                raise InvalidRequest("tool args must be an object")
            if self.legacy:
                result = await self.loaded_plugin.invoke_tool(
                    str(frame.params["handler_id"]),
                    call,
                    args,
                )
            else:
                result = await self.loaded_plugin.invoke_tool(
                    str(frame.params["handler_id"]),
                    call,
                    args,
                    call_id=frame.id,
                )
            return encode_value(result)
        if frame.method == "invoke_hook":
            if self.loaded_plugin is None:
                raise InvalidRequest("Runner is not initialized")
            event = decode_value(frame.params.get("event"))
            if event is not None and not isinstance(event, MessageEvent):
                raise InvalidRequest("hook event must be a MessageEvent or null")
            payload = decode_value(frame.params.get("payload", {}))
            if not isinstance(payload, Mapping):
                raise InvalidRequest("hook payload must be an object")
            if self.legacy:
                result = await self.loaded_plugin.invoke_hook(
                    str(frame.params["handler_id"]),
                    event,
                    payload,
                )
            else:
                result = await self.loaded_plugin.invoke_hook(
                    str(frame.params["handler_id"]),
                    event,
                    payload,
                    call_id=frame.id,
                )
            return encode_value(result)
        if frame.method == "invoke_cron":
            if self.loaded_plugin is None:
                raise InvalidRequest("Runner is not initialized")
            invoker = getattr(self.loaded_plugin, "invoke_cron", None)
            if invoker is None:
                raise InvalidRequest("plugin does not support cron handlers")
            payload = decode_value(frame.params.get("payload", {}))
            if not isinstance(payload, Mapping):
                raise InvalidRequest("cron payload must be an object")
            result = await invoker(
                str(frame.params["handler_id"]),
                payload,
            )
            return encode_value(result)
        if frame.method == "session_consider":
            event = decode_value(frame.params.get("event"))
            if not isinstance(event, MessageEvent):
                raise InvalidRequest("session_consider event must be a MessageEvent")
            return {"matches": self._session_service()._consider(event)}
        if frame.method == "session_matched":
            event = decode_value(frame.params.get("event"))
            if not isinstance(event, MessageEvent):
                raise InvalidRequest("session_matched event must be a MessageEvent")
            self._session_service()._deliver(str(frame.params["waiter_id"]), event)
            return None
        if frame.method == "session_timeout":
            self._session_service()._timeout(str(frame.params["waiter_id"]))
            return None
        if frame.method == "shutdown":
            self._stop_reason = str(frame.params.get("reason") or "shutdown")
            await self._stop_plugin()
            self._closing = True
            return None
        raise InvalidRequest(f"unknown Runner method: {frame.method}")

    def _session_service(self) -> Any:
        """Return the loaded plugin's session service.

        Raises:
            InvalidRequest: The Runner or its session service is unavailable.
        """
        loaded = self.loaded_plugin
        if loaded is None:
            raise InvalidRequest("Runner is not initialized")
        ctx = getattr(getattr(loaded, "instance", None), "ctx", None)
        if ctx is None:
            ctx = getattr(loaded, "sdk_ctx", None)
        sessions = getattr(ctx, "sessions", None)
        if sessions is None:
            raise InvalidRequest("plugin context has no session service")
        return sessions

    async def _initialize(self, frame: RequestFrame) -> dict[str, Any]:
        """Load and start the plugin after protocol negotiation.

        Args:
            frame: Initialize request containing config and capability grants.

        Raises:
            InvalidRequest: Initialization is repeated or negotiation fails.
        """
        if self.loaded_plugin is not None or self._initializing:
            raise InvalidRequest("Runner is already initialized")
        self._initializing = True
        try:
            protocol_versions = frame.params.get("protocol_versions")
            if not isinstance(protocol_versions, list) or not any(
                type(version) is int and version == PROTOCOL_VERSION
                for version in protocol_versions
            ):
                raise InvalidRequest("no supported protocol version")

            raw_grants = frame.params.get("capabilities", [])
            if not isinstance(raw_grants, list):
                raise InvalidRequest("capabilities must be a list")
            grants: list[CapabilityGrant] = []
            for item in raw_grants:
                if not isinstance(item, Mapping):
                    raise InvalidRequest("capability grant must be an object")
                scope = decode_value(item.get("scope", {}))
                if not isinstance(scope, Mapping):
                    raise InvalidRequest("capability scope must be an object")
                grants.append(CapabilityGrant(id=str(item["id"]), scope=scope))

            config = decode_value(frame.params.get("config"))
            host_info = decode_value(frame.params.get("host") or {})
            if not isinstance(host_info, Mapping):
                host_info = {}
            if self.legacy:
                loaded = self._load_legacy(
                    config,
                    CapabilitySet(grants),
                    host_info=host_info,
                )
            else:
                loaded = load_plugin(
                    self.plugin_root,
                    config=config,
                    granted_capabilities=CapabilitySet(grants),
                    host_capability_invoker=self._invoke_host_capability,
                    host_capability_stream_invoker=self._invoke_host_capability_stream,
                    host_service_invoker=self._invoke_host_service,
                )
            await loaded.start()
            self.loaded_plugin = loaded

            handlers: list[dict[str, Any]] = []
            services: list[dict[str, Any]] = []
            for registration in loaded.registrations:
                spec = registration.spec
                if spec.kind in (HandlerKind.SERVICE, HandlerKind.DIRECT_SERVICE):
                    services.append(
                        {
                            "handler_id": registration.id,
                            "name": spec.service_name or registration.id,
                            "description": spec.description or "",
                            "mode": (
                                "direct"
                                if spec.kind is HandlerKind.DIRECT_SERVICE
                                else "host_scoped"
                            ),
                            "input_schema": (
                                dict(spec.input_schema)
                                if spec.input_schema is not None
                                else None
                            ),
                        }
                    )
                    continue
                details: dict[str, Any] = {}
                if spec.kind is HandlerKind.COMMAND:
                    pre_cmd = getattr(
                        registration.handler,
                        "__command_params__",
                        None,
                    )
                    details = {
                        "path": spec.path,
                        "group": spec.group,
                        "group_custom_filters": spec.group_custom_filters,
                        "sub_command": spec.sub_command,
                        "aliases": list(spec.aliases),
                        "message_types": [
                            message_type.value for message_type in spec.message_types
                        ],
                        "platforms": list(spec.platforms),
                        "roles": [role.value for role in spec.roles],
                        "params": (
                            pre_cmd
                            if pre_cmd is not None
                            else _command_params_schema(registration)
                        ),
                    }
                elif spec.kind.value.startswith("hook."):
                    details = {
                        "stage": spec.kind.value.removeprefix("hook."),
                    }
                elif spec.kind is HandlerKind.TOOL:
                    precomputed = getattr(
                        registration.handler,
                        "__tool_params__",
                        None,
                    )
                    details = {
                        "name": spec.tool_name,
                        "description": spec.description,
                        "resumable": bool(spec.resumable),
                        "streaming_input": bool(spec.streaming_input),
                        "params": precomputed
                        if precomputed is not None
                        else [
                            {
                                "name": param.name,
                                "type": param.type,
                                "description": param.description,
                                "required": param.required,
                            }
                            for param in tool_params_schema(
                                registration.handler,
                                handler_label=f"handler {registration.id!r}",
                            )
                        ],
                    }
                elif spec.kind is HandlerKind.MESSAGE:
                    details = {
                        "message_types": [
                            message_type.value for message_type in spec.message_types
                        ],
                        "platforms": list(spec.platforms),
                        "roles": [role.value for role in spec.roles],
                        "regex": spec.regex,
                        "regex_flags": spec.regex_flags,
                        "button_action": spec.button_action,
                        "button_action_id": spec.button_action_id,
                        "ui_action": spec.ui_action,
                        "ui_action_id": spec.ui_action_id,
                    }
                handlers.append(
                    {
                        "id": registration.id,
                        "kind": spec.kind.value,
                        "description": spec.description,
                        "priority": spec.priority,
                        "details": details,
                    }
                )

            requested_features = frame.params.get("features")
            if isinstance(requested_features, list) and requested_features:
                supported = set(_SUPPORTED_FEATURES)
                features = [
                    str(item) for item in requested_features if str(item) in supported
                ]
            else:
                features = list(_SUPPORTED_FEATURES)

            # Resolve the SDK context: legacy loaded plugins expose it as
            # sdk_ctx (their Star instance may carry an unrelated own "ctx"
            # attribute), new-style plugins as instance.ctx.
            handshake_ctx = getattr(loaded, "sdk_ctx", None)
            if handshake_ctx is None:
                handshake_ctx = getattr(loaded.instance, "ctx", None)
            return {
                "protocol_version": PROTOCOL_VERSION,
                "plugin": {
                    "id": loaded.metadata.plugin_id,
                    "name": loaded.metadata.name,
                    "version": loaded.metadata.version,
                    "schema_version": loaded.metadata.schema_version,
                },
                "handlers": handlers,
                "services": services,
                "web_routes": [
                    {
                        "route": route.route,
                        "methods": list(route.methods),
                        "description": route.description,
                    }
                    for route in handshake_ctx.web.routes
                ]
                if getattr(handshake_ctx, "web", None) is not None
                else [],
                "capabilities": list(handshake_ctx.capabilities),
                "features": features,
            }
        finally:
            self._initializing = False

    def _load_legacy(
        self,
        config: Any,
        grants: CapabilitySet,
        *,
        host_info: Mapping[str, Any] | None = None,
    ) -> Any:
        """Load a legacy plugin through the compat layer."""
        from ..compat.v1.loader import load_legacy_plugin
        from ..context import PluginContext, PluginInfo, RuntimeMode
        from .loader import _load_metadata_for_legacy

        metadata = _load_metadata_for_legacy(self.plugin_root)
        data_dir = _legacy_data_dir(metadata)
        ctx = PluginContext(
            plugin=PluginInfo(
                id=metadata.plugin_id,
                name=metadata.name,
                version=metadata.version,
                runtime_mode=RuntimeMode.ISOLATED,
            ),
            config=config,
            logger=logging.getLogger(f"astrbot.plugin.{metadata.name}"),
            capabilities=grants,
            data_dir=data_dir,
            _host_capability_invoker=self._invoke_host_capability,
            _host_capability_stream_invoker=self._invoke_host_capability_stream,
            _host_service_invoker=self._invoke_host_service,
        )
        return load_legacy_plugin(
            self.plugin_root,
            ctx=ctx,
            config=config,
            logger=logging.getLogger(f"astrbot.plugin.{metadata.name}"),
            host_info=host_info,
        )

    async def _invoke_host_capability(
        self,
        capability_id: str,
        operation: str,
        payload: Mapping[str, Any],
    ) -> Any:
        """Invoke one authorized capability through the Host peer.

        Args:
            capability_id: Capability required by the SDK service operation.
            operation: Operation within the capability namespace.
            payload: Operation input DTOs.

        Returns:
            Decoded Host capability result.
        """
        params: dict[str, Any] = {
            "capability": capability_id,
            "operation": operation,
            "input": encode_value(dict(payload)),
        }
        parent_call_id = _AMBIENT_CALL_ID.get()
        if parent_call_id is not None:
            params["parent_call_id"] = parent_call_id
        result = await self._peer.request("capability.invoke", params)
        return decode_value(result)

    async def _invoke_host_service(
        self,
        plugin_id: str,
        service: str,
        payload: Mapping[str, Any],
        parent_call_id: str | None = None,
    ) -> Any:
        """Route one cross-plugin service invocation through the Host peer."""
        params: dict[str, Any] = {
            "plugin_id": plugin_id,
            "service": service,
            "input": encode_value(dict(payload)),
        }
        resolved_call_id = parent_call_id or _AMBIENT_CALL_ID.get()
        if resolved_call_id is not None:
            params["parent_call_id"] = resolved_call_id
        result = await self._peer.request("plugin.service.invoke", params)
        return decode_value(result)

    async def _run_web_invocation(
        self,
        frame: RequestFrame,
        acknowledgements: asyncio.Queue[int],
    ) -> None:
        """Invoke one web route and stream the response with backpressure.

        Every yielded item (response info and each body chunk) is
        acknowledged by the Host before the next is produced, so slow
        clients throttle the plugin's generator (SSE, large files).
        """
        try:
            if self.loaded_plugin is None:
                raise InvalidRequest("Runner is not initialized")
            if frame.params.get("views") is not None:
                views_params = frame.params["views"]
                if not isinstance(views_params, Mapping):
                    raise InvalidRequest("views params must be an object")
                operation = str(views_params.get("operation") or "")
                page = views_params.get("page")
                path = views_params.get("path")
                stream = self.loaded_plugin.invoke_views(
                    operation,
                    str(page) if page is not None else None,
                    str(path) if path is not None else None,
                )
            else:
                from ..web import WebRequestInfo

                request = decode_value(frame.params.get("request"))
                if not isinstance(request, WebRequestInfo):
                    raise InvalidRequest("web request must be a WebRequestInfo")
                if self.legacy:
                    stream = self.loaded_plugin.invoke_web(request)
                else:
                    stream = self.loaded_plugin.invoke_web(
                        request,
                        call_id=frame.id,
                    )
            sequence = 0
            async for item in stream:
                sequence += 1
                await self._send(
                    YieldFrame(
                        id=frame.id,
                        sequence=sequence,
                        result=encode_value(item),
                    ),
                )
                acknowledged_sequence = await acknowledgements.get()
                if acknowledged_sequence != sequence:
                    raise InvalidRequest(
                        "web stream acknowledgement sequence does not match"
                    )
            await self._send(ResponseFrame(id=frame.id, result=None))
        except asyncio.CancelledError:
            await self._send(
                ErrorFrame(
                    id=frame.id,
                    code="CANCELLED",
                    message="web invocation was cancelled",
                ),
            )
            raise
        except Exception as exc:
            code = (
                exc.code if isinstance(exc, AstrBotSDKError) else "PLUGIN_RUNTIME_ERROR"
            )
            await self._send(ErrorFrame(id=frame.id, code=code, message=str(exc)))
        finally:
            self._invocations.pop(frame.id, None)

    def rebind_transport(self, transport: FrameTransport) -> None:
        """Bind a new transport after a resumable external reconnect."""
        self._transport = transport

    def _prune_resumable_streams(self) -> None:
        """Discard resumable stream states whose grace window has elapsed."""
        now = time.monotonic()
        expired = [
            call_id
            for call_id, state in self._resumable_streams.items()
            if state["finished_at"] is not None
            and now - state["finished_at"] > _RESUMABLE_GRACE_SECONDS
        ]
        for call_id in expired:
            self._resumable_streams.pop(call_id, None)

    def stream_replay_frames(self) -> list[ProtocolFrame]:
        """Collect unacknowledged yields and terminal frames for replay."""
        self._prune_resumable_streams()
        replay: list[ProtocolFrame] = []
        for state in self._resumable_streams.values():
            last_unacked = state["last_unacked"]
            if (
                isinstance(last_unacked, YieldFrame)
                and last_unacked.sequence > state["last_acked_seq"]
            ):
                replay.append(last_unacked)
            terminal = state["terminal"]
            if terminal is not None:
                replay.append(terminal)
        return replay

    async def _run_invocation(
        self,
        frame: RequestFrame,
        acknowledgements: asyncio.Queue[int],
        *,
        resumable: bool = False,
    ) -> None:
        """Invoke a handler and suspend after each yielded result.

        Args:
            frame: Invoke request.
            acknowledgements: Sequence acknowledgements from the Host.
            resumable: Retain bounded 1-unacked-yield replay state on disconnect.
        """
        resumable_state = self._resumable_streams.get(frame.id) if resumable else None
        try:
            if self.loaded_plugin is None:
                raise InvalidRequest("Runner is not initialized")
            handler_id = frame.params.get("handler_id")
            raw_args = frame.params.get("args", [])
            raw_kwargs = frame.params.get("kwargs", {})
            if not isinstance(handler_id, str) or not handler_id:
                raise InvalidRequest("handler_id must be a non-empty string")
            if not isinstance(raw_args, list) or not isinstance(raw_kwargs, Mapping):
                raise InvalidRequest("handler args or kwargs are invalid")

            args = [decode_value(value) for value in raw_args]
            kwargs = {
                str(key): decode_value(value) for key, value in raw_kwargs.items()
            }
            sequence = 0
            stream = (
                self.loaded_plugin.invoke(handler_id, *args, **kwargs)
                if self.legacy
                else self.loaded_plugin.invoke(
                    handler_id,
                    *args,
                    call_id=frame.id,
                    **kwargs,
                )
            )
            async for result in stream:
                sequence += 1
                yield_frame = YieldFrame(
                    id=frame.id,
                    sequence=sequence,
                    result=encode_result(result),
                )
                if resumable_state is not None:
                    resumable_state["last_unacked"] = yield_frame
                await self._send(yield_frame)
                if result is not None and result.propagation is Propagation.STOP:
                    if resumable_state is not None:
                        resumable_state["last_acked_seq"] = sequence
                        resumable_state["last_unacked"] = None
                    continue
                acknowledged_sequence = await acknowledgements.get()
                if acknowledged_sequence != sequence:
                    raise InvalidRequest(
                        "yield acknowledgement sequence does not match"
                    )
                if resumable_state is not None:
                    resumable_state["last_acked_seq"] = acknowledged_sequence
                    resumable_state["last_unacked"] = None
            terminal = ResponseFrame(id=frame.id, result=None)
            if resumable_state is not None:
                resumable_state["terminal"] = terminal
                resumable_state["finished_at"] = time.monotonic()
            await self._send(terminal)
        except asyncio.CancelledError:
            err_frame = ErrorFrame(
                id=frame.id,
                code="CANCELLED",
                message="handler invocation was cancelled",
            )
            if resumable_state is not None:
                resumable_state["terminal"] = err_frame
                resumable_state["finished_at"] = time.monotonic()
            await self._send(err_frame)
            raise
        except Exception as exc:
            code = (
                exc.code if isinstance(exc, AstrBotSDKError) else "PLUGIN_RUNTIME_ERROR"
            )
            err_frame = ErrorFrame(id=frame.id, code=code, message=str(exc))
            if resumable_state is not None:
                resumable_state["terminal"] = err_frame
                resumable_state["finished_at"] = time.monotonic()
            await self._send(err_frame)
        finally:
            self._invocations.pop(frame.id, None)

    async def _invoke_host_capability_stream(
        self,
        capability_id: str,
        operation: str,
        payload: Mapping[str, Any],
    ) -> AsyncIterator[Any]:
        """Call a Host capability as a flow-controlled stream.

        The Host sends each item as a YieldFrame; requesting the next item
        from this iterator acknowledges the previous one, so the Host never
        outpaces the plugin.
        """
        stream_id = f"runner-cap-stream:{uuid.uuid4().hex}"
        queue: asyncio.Queue[ProtocolFrame | Exception] = asyncio.Queue()
        self._capability_streams[stream_id] = queue
        try:
            req_params: dict[str, Any] = {
                "capability": capability_id,
                "operation": operation,
                "input": encode_value(payload),
            }
            parent_call_id = _AMBIENT_CALL_ID.get()
            if parent_call_id is not None:
                req_params["parent_call_id"] = parent_call_id
            await self._send(
                RequestFrame(
                    id=stream_id,
                    method="capability.invoke",
                    params=req_params,
                ),
            )
            while True:
                frame = await queue.get()
                if isinstance(frame, Exception):
                    raise frame
                if isinstance(frame, YieldFrame):
                    yield decode_value(frame.result)
                    await self._send(
                        AckFrame(id=stream_id, sequence=frame.sequence),
                    )
                elif isinstance(frame, ResponseFrame):
                    return
                elif isinstance(frame, ErrorFrame):
                    raise RemoteHostError(frame.code, frame.message)
                else:
                    raise InvalidRequest(
                        f"unexpected capability stream frame: {type(frame).__name__}"
                    )
        finally:
            self._capability_streams.pop(stream_id, None)

    async def _stop_plugin(self) -> None:
        """Cancel active invocations and stop the loaded plugin."""
        if self.loaded_plugin is not None:
            # Unblock pending session waits before tasks are cancelled so a
            # waiting next() fails with HostUnavailable instead of hanging.
            with contextlib.suppress(Exception):
                self._session_service()._fail_all(
                    HostUnavailable("plugin Runner is shutting down")
                )
        current_task = asyncio.current_task()
        tasks = [
            task for task, _ in self._invocations.values() if task is not current_task
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._invocations.clear()
        if self.loaded_plugin is not None:
            with contextlib.suppress(Exception):
                if self.legacy:
                    await self.loaded_plugin.shutdown()
                else:
                    await self.loaded_plugin.shutdown(reason=self._stop_reason)
            self.loaded_plugin = None


async def serve_stdio_plugin(plugin_root: Path, *, legacy: bool = False) -> None:
    """Run one plugin Runner on process stdio.

    Args:
        plugin_root: Plugin repository root.
        legacy: Load the plugin through the legacy compat layer.
    """
    await StdioPluginServer(plugin_root, legacy=legacy).serve()
