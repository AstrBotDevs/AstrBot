from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import sys
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

from ..capabilities import (
    DEFAULT_CAPABILITY_IDS,
    CapabilityGrant,
    CapabilitySet,
)
from ..errors import (
    CallScopeRetired,
    CapabilityDenied,
    Conflict,
    HostUnavailable,
    InvalidRequest,
    NotFound,
    RemotePluginError,
)
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
    decode_result,
    decode_value,
    encode_frame,
    encode_value,
)
from ..registration import HandlerKind
from ..results import EventResult, Propagation
from ..tools import ToolCallContext
from .env import runner_env
from .metadata import load_metadata
from .peer import Peer
from .transport import FrameTransport, StreamTransport

HostCapabilityHandler = Callable[
    [CapabilityGrant, str, Mapping[str, Any]],
    Awaitable[Any],
]
HostServiceHandler = Callable[
    [str, str, Mapping[str, Any]],
    Awaitable[Any],
]
ToolsInvalidatedHandler = Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class HandlerDescriptor:
    """Describe one remotely registered plugin handler."""

    id: str
    kind: HandlerKind
    description: str | None
    priority: int
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Freeze handler details after construction."""
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))


@dataclass(frozen=True, slots=True)
class PluginHandshake:
    """Contain negotiated plugin and handler metadata."""

    protocol_version: int
    plugin_id: str
    name: str
    version: str
    schema_version: int
    handlers: tuple[HandlerDescriptor, ...]
    capabilities: tuple[str, ...]
    web_routes: tuple[dict[str, Any], ...] = ()
    services: tuple[dict[str, Any], ...] = ()
    features: tuple[str, ...] = ()


class StdioPluginClient:
    """Control one isolated SDK plugin Runner over a frame transport.

    The base class spawns the Runner as a local subprocess and talks over
    its stdio pipes; subclasses (for example the WebSocket client) attach
    to Runners spawned elsewhere by overriding the transport hooks.
    """

    def __init__(
        self,
        plugin_root: Path | None,
        *,
        python_executable: Path | str | None = None,
        timeout: float = 10.0,
        logger: logging.Logger | None = None,
        capability_handler: HostCapabilityHandler | None = None,
        service_handler: HostServiceHandler | None = None,
        tools_invalidated_handler: ToolsInvalidatedHandler | None = None,
        legacy: bool = False,
        env: Mapping[str, str] | None = None,
        start_timeout: float | None = None,
    ) -> None:
        """Initialize the Host-side stdio client.

        Args:
            plugin_root: Plugin repository root, or None when the Runner is
                external and the Host has no local checkout.
            python_executable: Python executable in the plugin environment.
            timeout: Request and process shutdown timeout in seconds.
            logger: Logger used for Runner stderr.
            capability_handler: Dispatcher for authorized Runner-to-Host calls.
            service_handler: Dispatcher for `plugin.service.invoke` calls.
            tools_invalidated_handler: Callback invoked on `tools.invalidate`.
            legacy: Load the plugin through the legacy compat layer.
            env: Extra environment variables merged over the parent env.
            start_timeout: Timeout for the initialize handshake; defaults to
                timeout. Heavy plugins may need a larger value.
        """
        self.plugin_root = plugin_root.resolve() if plugin_root is not None else None
        self.legacy = legacy
        self._extra_env = dict(env or {})
        self.start_timeout = start_timeout if start_timeout is not None else timeout
        self.python_executable = str(python_executable or sys.executable)
        self.timeout = timeout
        self.logger = logger or logging.getLogger("astrbot.plugin_runner")
        self.capability_handler = capability_handler
        self.service_handler = service_handler
        self.tools_invalidated_handler = tools_invalidated_handler
        self.handshake: PluginHandshake | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._peer: Peer | None = None
        self._granted_capabilities = CapabilitySet()
        self._active_call_ids: set[str] = set()
        self._streams: dict[
            str,
            asyncio.Queue[ProtocolFrame | Exception],
        ] = {}
        self._capability_stream_acks: dict[
            str,
            asyncio.Queue[int | Exception],
        ] = {}
        self._transport: FrameTransport | None = None
        self._started = False

    async def start(
        self,
        *,
        config: Any = None,
        granted_capabilities: CapabilitySet | None = None,
        host_info: Mapping[str, Any] | None = None,
    ) -> PluginHandshake:
        """Start the Runner and negotiate protocol and plugin metadata.

        Args:
            config: Validated plugin configuration.
            granted_capabilities: Capabilities granted by the user.
            host_info: Optional Host metadata (e.g. the AstrBot version)
                forwarded to the Runner during initialization.

        Returns:
            Negotiated plugin handshake.

        Raises:
            Conflict: The client has already started.
            HostUnavailable: The Runner cannot start or exits during initialization.
            InvalidRequest: The Runner returns malformed handshake data.
            RemotePluginError: Plugin loading or startup fails remotely.
        """
        if self._started:
            raise Conflict("plugin client is already started")
        self._started = True

        grants = self._compute_grants(granted_capabilities)
        self._granted_capabilities = grants
        self._transport = await self._open_transport()
        self._peer = Peer(
            send=self._send,
            request_handler=self._handle_runner_request,
            request_id_prefix="host:",
            remote_error_factory=RemotePluginError,
            internal_error_code="HOST_RUNTIME_ERROR",
        )
        self._reader_task = asyncio.create_task(self._read_frames())
        if self._process is not None and self._process.stderr is not None:
            self._stderr_task = asyncio.create_task(self._read_stderr())

        try:
            try:
                result = await self._request(
                    "initialize",
                    {
                        "protocol_versions": [PROTOCOL_VERSION],
                        "config": encode_value(config),
                        "host": encode_value(dict(host_info or {})),
                        "capabilities": [
                            {
                                "id": grant.id,
                                "scope": encode_value(grant.scope),
                            }
                            for grant in grants.values()
                        ],
                        "features": [
                            "cancel_v1",
                            "capability_update_v1",
                            "direct_service_v1",
                            "dynamic_tools_v1",
                            "external_attach_v1",
                            "live_config_v1",
                            "plugin_service_v1",
                            "resume_stream_v1",
                            "scoped_host_v1",
                        ],
                    },
                )
            except TimeoutError as exc:
                # asyncio.TimeoutError stringifies to an empty message; report
                # which phase timed out so slow plugin imports/initializers
                # (e.g. dataset downloads) are diagnosable.
                raise HostUnavailable(
                    "plugin Runner did not finish initialization within "
                    f"{self.start_timeout:g}s (slow plugin import or initialize)"
                ) from exc
            handshake = self._parse_handshake(result)
            self.handshake = handshake
            return handshake
        except Exception:
            await self._close_transport()
            if self._peer is not None:
                await self._peer.close(
                    HostUnavailable("plugin Runner failed to initialize")
                )
            await self._finish_tasks()
            self._transport = None
            self._process = None
            self._peer = None
            self._granted_capabilities = CapabilitySet()
            self._started = False
            raise

    def _compute_grants(
        self,
        granted_capabilities: CapabilitySet | None,
    ) -> CapabilitySet:
        """Resolve the effective capability grants for this Runner.

        Local runners are intersected with the plugin's declared
        capabilities from its on-disk metadata; legacy and external runners
        without a local checkout receive Host grants directly.
        """
        if self.legacy or self.plugin_root is None:
            return granted_capabilities or CapabilitySet()
        declared_capabilities = load_metadata(
            self.plugin_root,
        ).capabilities.all_ids
        requested = granted_capabilities or CapabilitySet()
        return CapabilitySet(
            [grant for grant in requested.values() if grant.id in declared_capabilities]
            + [
                CapabilityGrant(id=capability_id)
                for capability_id in sorted(
                    DEFAULT_CAPABILITY_IDS - declared_capabilities
                )
            ]
        )

    async def _open_transport(self) -> FrameTransport:
        """Spawn the local Runner subprocess and wrap its stdio pipes."""
        if self.plugin_root is None:
            raise InvalidRequest("local runners require a plugin root")
        cwd: str | None = None
        if not self.legacy:
            meta = load_metadata(self.plugin_root)
            if meta.runtime.command:
                cmd0 = meta.runtime.command[0]
                candidate = self.plugin_root / cmd0
                executable = (
                    str(candidate)
                    if candidate.exists() or "/" in cmd0 or "\\" in cmd0
                    else cmd0
                )
                argv = [executable, *meta.runtime.command[1:]]
                cwd = str(self.plugin_root)
            else:
                argv = [
                    self.python_executable,
                    "-m",
                    "astrbot_sdk.runtime",
                    "--stdio",
                    "--plugin-root",
                    str(self.plugin_root),
                ]
        else:
            argv = [
                self.python_executable,
                "-m",
                "astrbot_sdk.runtime",
                "--stdio",
                "--plugin-root",
                str(self.plugin_root),
                "--legacy",
            ]
        self._process = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=runner_env(self._extra_env),
            limit=MAX_FRAME_BYTES + 1,
        )
        if self._process.stdout is None or self._process.stdin is None:
            raise HostUnavailable("stdio plugin Runner pipes are unavailable")
        return StreamTransport(self._process.stdout, self._process.stdin)

    async def _close_transport(self) -> None:
        """Close the transport, escalating to terminate/kill if needed."""
        transport = self._transport
        process = self._process
        if transport is not None:
            with contextlib.suppress(BrokenPipeError, ConnectionError):
                await transport.close()
        if process is not None and process.returncode is None:
            try:
                await asyncio.wait_for(process.wait(), timeout=self.timeout)
            except TimeoutError:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=self.timeout)
                except TimeoutError:
                    process.kill()
                    await process.wait()

    async def invoke(
        self,
        handler_id: str,
        *args: Any,
        **kwargs: Any,
    ) -> AsyncIterator[EventResult | None]:
        """Invoke a remote handler while preserving yield acknowledgements.

        Args:
            handler_id: Registered handler ID.
            *args: Positional handler arguments.
            **kwargs: Keyword handler arguments.

        Yields:
            Decoded handler results. Requesting the next item acknowledges the
            previous yield and resumes the remote generator.

        Raises:
            HostUnavailable: The Runner is not running or disconnects.
            InvalidRequest: The Runner sends an invalid stream sequence.
            RemotePluginError: The remote handler fails.
        """
        if not self.is_running:
            raise HostUnavailable("plugin Runner is not running")

        invocation_id = f"host-invoke:{uuid.uuid4().hex}"
        queue: asyncio.Queue[ProtocolFrame | Exception] = asyncio.Queue()
        self._streams[invocation_id] = queue
        self._active_call_ids.add(invocation_id)
        completed = False
        expected_sequence = 0
        try:
            await self._send(
                RequestFrame(
                    id=invocation_id,
                    method="invoke",
                    params={
                        "handler_id": handler_id,
                        "args": [encode_value(value) for value in args],
                        "kwargs": {
                            key: encode_value(value) for key, value in kwargs.items()
                        },
                    },
                )
            )
            while True:
                frame = await queue.get()
                if isinstance(frame, Exception):
                    raise frame
                if isinstance(frame, YieldFrame):
                    expected_sequence += 1
                    if frame.sequence != expected_sequence:
                        raise InvalidRequest("remote yield sequence does not match")
                    result = decode_result(frame.result)
                    stopped = (
                        result is not None and result.propagation is Propagation.STOP
                    )
                    if stopped:
                        completed = True
                    yield result
                    if stopped:
                        return
                    await self._send(
                        AckFrame(
                            id=invocation_id,
                            sequence=frame.sequence,
                        )
                    )
                elif isinstance(frame, ResponseFrame):
                    completed = True
                    return
                elif isinstance(frame, ErrorFrame):
                    completed = True
                    raise RemotePluginError(frame.code, frame.message)
                else:
                    raise InvalidRequest(
                        f"unexpected invocation frame: {type(frame).__name__}"
                    )
        finally:
            self._active_call_ids.discard(invocation_id)
            self._streams.pop(invocation_id, None)
            if not completed and self.is_running:
                with contextlib.suppress(HostUnavailable):
                    await self._send(CancelFrame(id=invocation_id))

    async def invoke_resumable(
        self,
        handler_id: str,
        *args: Any,
        invocation_id: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[EventResult | None]:
        """Invoke a handler over a resumable stream, deduplicating replayed yields."""
        if not self.is_running:
            raise HostUnavailable("plugin Runner is not running")

        req_id = invocation_id or f"host-invoke:{uuid.uuid4().hex}"
        queue: asyncio.Queue[ProtocolFrame | Exception] = asyncio.Queue()
        self._streams[req_id] = queue
        self._active_call_ids.add(req_id)
        completed = False
        expected_sequence = 0
        try:
            await self._send(
                RequestFrame(
                    id=req_id,
                    method="resumable.invoke",
                    params={
                        "handler_id": handler_id,
                        "args": [encode_value(value) for value in args],
                        "kwargs": {
                            key: encode_value(value) for key, value in kwargs.items()
                        },
                    },
                )
            )
            while True:
                frame = await queue.get()
                if isinstance(frame, Exception):
                    raise frame
                if isinstance(frame, YieldFrame):
                    if frame.sequence <= expected_sequence:
                        await self._send(AckFrame(id=req_id, sequence=frame.sequence))
                        continue
                    expected_sequence += 1
                    if frame.sequence != expected_sequence:
                        raise InvalidRequest("remote yield sequence does not match")
                    result = decode_result(frame.result)
                    stopped = (
                        result is not None and result.propagation is Propagation.STOP
                    )
                    if stopped:
                        completed = True
                    yield result
                    if stopped:
                        return
                    await self._send(AckFrame(id=req_id, sequence=frame.sequence))
                elif isinstance(frame, ResponseFrame):
                    completed = True
                    return
                elif isinstance(frame, ErrorFrame):
                    completed = True
                    raise RemotePluginError(frame.code, frame.message)
                else:
                    raise InvalidRequest(
                        f"unexpected invocation frame: {type(frame).__name__}"
                    )
        finally:
            self._active_call_ids.discard(req_id)
            self._streams.pop(req_id, None)
            if not completed and self.is_running:
                with contextlib.suppress(HostUnavailable):
                    await self._send(CancelFrame(id=req_id))

    def attach_resumable_queue(
        self,
        invocation_id: str,
    ) -> asyncio.Queue[ProtocolFrame | Exception]:
        """Re-register a stream queue across transport reconnects."""
        queue: asyncio.Queue[ProtocolFrame | Exception] = asyncio.Queue()
        self._streams[invocation_id] = queue
        self._active_call_ids.add(invocation_id)
        return queue

    async def invoke_web(
        self,
        request: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        """Invoke one remote web route and stream the response.

        Yields the response info first (``{"info": WebResponseInfo}``),
        then body chunks (``{"chunk": bytes}``); each consumed item sends
        the acknowledgement that resumes the remote stream (backpressure).
        """
        async for item in self._invoke_stream(
            {
                "web": True,
                "request": encode_value(request),
            },
        ):
            yield item

    async def _invoke_stream(
        self,
        params: Mapping[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        """Run one streaming invocation and yield decoded items."""
        if not self.is_running:
            raise HostUnavailable("plugin Runner is not running")
        invocation_id = f"host-invoke:{uuid.uuid4().hex}"
        queue: asyncio.Queue[ProtocolFrame | Exception] = asyncio.Queue()
        self._streams[invocation_id] = queue
        self._active_call_ids.add(invocation_id)
        completed = False
        expected_sequence = 0
        try:
            await self._send(
                RequestFrame(
                    id=invocation_id,
                    method="invoke",
                    params=dict(params),
                )
            )
            while True:
                frame = await queue.get()
                if isinstance(frame, Exception):
                    raise frame
                if isinstance(frame, YieldFrame):
                    expected_sequence += 1
                    if frame.sequence != expected_sequence:
                        raise InvalidRequest("remote yield sequence does not match")
                    yield decode_value(frame.result)
                    await self._send(
                        AckFrame(
                            id=invocation_id,
                            sequence=frame.sequence,
                        )
                    )
                elif isinstance(frame, ResponseFrame):
                    completed = True
                    return
                elif isinstance(frame, ErrorFrame):
                    completed = True
                    raise RemotePluginError(frame.code, frame.message)
                else:
                    raise InvalidRequest(
                        f"unexpected invocation frame: {type(frame).__name__}"
                    )
        finally:
            self._active_call_ids.discard(invocation_id)
            self._streams.pop(invocation_id, None)
            if not completed and self.is_running:
                with contextlib.suppress(HostUnavailable):
                    await self._send(CancelFrame(id=invocation_id))

    async def invoke_views(
        self,
        operation: str,
        page: str | None = None,
        path: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Fetch the views manifest or stream one view file's content."""
        params: dict[str, Any] = {"operation": operation}
        if page is not None:
            params["page"] = page
        if path is not None:
            params["path"] = path
        async for item in self._invoke_stream(
            {
                "views": params,
            },
        ):
            yield item

    async def invoke_tool(
        self,
        handler_id: str,
        call: ToolCallContext,
        args: Mapping[str, Any],
    ) -> Any:
        """Invoke one remote tool handler and return its result.

        Args:
            handler_id: Registered tool handler ID.
            call: Tool call context forwarded to the plugin.
            args: Tool arguments supplied by the LLM.

        Returns:
            Decoded handler result.
        """
        result = await self._request(
            "invoke_tool",
            {
                "handler_id": handler_id,
                "context": encode_value(call),
                "args": encode_value(dict(args)),
            },
        )
        return decode_value(result)

    async def invoke_hook(
        self,
        handler_id: str,
        event: Any,
        stage: str,
        payload: Mapping[str, Any],
    ) -> Any:
        """Invoke one remote Pipeline hook handler.

        Args:
            handler_id: Registered hook handler ID.
            event: SDK MessageEvent for the hook, or None.
            stage: Hook stage name.
            payload: Stage DTO snapshot fields.

        Returns:
            Dict with write ops and an optional decision.
        """
        result = await self._request(
            "invoke_hook",
            {
                "handler_id": handler_id,
                "event": encode_value(event),
                "stage": stage,
                "payload": encode_value(dict(payload), allow_unknown=True),
            },
        )
        return decode_value(result)

    async def invoke_cron(self, handler_id: str, payload: Mapping[str, Any]) -> Any:
        """Invoke one remote cron job handler and return its result.

        Args:
            handler_id: Registered cron handler ID.
            payload: Job payload forwarded to the plugin handler.

        Returns:
            Decoded handler result.
        """
        result = await self._request(
            "invoke_cron",
            {
                "handler_id": handler_id,
                "payload": encode_value(dict(payload)),
            },
        )
        return decode_value(result)

    async def ping(self) -> Any:
        """Probe Runner liveness; returns its protocol version payload."""
        return await self._request("ping", {})

    async def validate_config(self, config: Any) -> Any:
        """Ask the Runner to validate a candidate configuration without applying it."""
        return await self._request("validate_config", {"config": encode_value(config)})

    async def configure(self, config: Any) -> Any:
        """Apply a confirmed configuration update live on the running Runner."""
        return await self._request("configure", {"config": encode_value(config)})

    async def update_capabilities(
        self,
        granted_capabilities: CapabilitySet,
    ) -> CapabilitySet:
        """Atomically update the granted capability set on the Runner."""
        effective = self._compute_grants(granted_capabilities)
        await self._request(
            "capabilities.update",
            {
                "capabilities": [
                    {"id": grant.id, "scope": encode_value(grant.scope)}
                    for grant in effective.values()
                ]
            },
        )
        self._granted_capabilities = effective
        return effective

    async def invoke_service(
        self,
        service: str,
        payload: Mapping[str, Any] | None = None,
    ) -> Any:
        """Invoke an exported plugin service handler."""
        result = await self._request(
            "invoke_service",
            {
                "service": service,
                "input": encode_value(dict(payload or {})),
            },
        )
        return decode_value(result)

    async def discover_tools(self) -> Any:
        """Invoke `@on.tool_discovery` and return the current dynamic tool snapshot."""
        return await self._request("tools.discover", {})

    async def session_consider(
        self,
        event: Any,
        *,
        timeout: float = 1.0,  # noqa: ASYNC109
    ) -> Mapping[str, Any]:
        """Ask the Runner which of its session waiters match one event.

        Args:
            event: SDK MessageEvent to test against local session filters.
            timeout: Round-trip budget in seconds; kept short because this
                runs inside the inbound message pipeline.

        Returns:
            Mapping with a ``matches`` list of waiter_id/key pairs.
        """
        result = await self._request(
            "session_consider",
            {"event": encode_value(event)},
            timeout=timeout,
        )
        return result or {}

    async def session_matched(self, waiter_id: str, event: Any) -> None:
        """Deliver one claimed inbound event to a Runner session waiter.

        Args:
            waiter_id: Runner-side waiter identifier.
            event: SDK MessageEvent to queue for the waiter.
        """
        await self._request(
            "session_matched",
            {"waiter_id": waiter_id, "event": encode_value(event)},
        )

    async def session_timeout(self, waiter_id: str) -> None:
        """Fail one Runner session waiter with TimeoutError.

        Args:
            waiter_id: Runner-side waiter identifier.
        """
        await self._request("session_timeout", {"waiter_id": waiter_id})

    @property
    def is_running(self) -> bool:
        """Whether the Runner process is alive."""
        return self._process is not None and self._process.returncode is None

    async def wait_exited(self) -> int | None:
        """Wait for the Runner process to exit and return its exit code."""
        process = self._process
        if process is None:
            return None
        return await process.wait()

    def kill_process(self) -> None:
        """Force-kill the Runner process when it is unresponsive."""
        process = self._process
        if process is not None and process.returncode is None:
            process.kill()

    async def close(self, *, reason: str = "shutdown") -> None:
        """Shut down the Runner and release transport resources."""
        if not self._started:
            return
        try:
            if self.is_running:
                with contextlib.suppress(
                    HostUnavailable,
                    RemotePluginError,
                    TimeoutError,
                ):
                    await asyncio.wait_for(
                        self._request("shutdown", {"reason": reason}),
                        timeout=self.timeout,
                    )
            await self._close_transport()
        finally:
            if self._peer is not None:
                await self._peer.close(HostUnavailable("plugin Runner is closed"))
            await self._finish_tasks()
            self._transport = None
            self._process = None
            self._peer = None
            self.handshake = None
            self._granted_capabilities = CapabilitySet()
            self._active_call_ids.clear()
            self._started = False

    async def _request(
        self,
        method: str,
        params: Mapping[str, Any],
        *,
        timeout: float | None = None,  # noqa: ASYNC109
    ) -> Any:
        """Send one request and wait for its final response.

        Args:
            method: Runner method name.
            params: JSON-compatible request parameters.
            timeout: Optional per-request timeout override in seconds.

        Returns:
            Successful response result.

        Raises:
            HostUnavailable: The Runner disconnects.
            RemotePluginError: The Runner returns an error frame.
            TimeoutError: The request exceeds the configured timeout.
        """
        peer = self._peer
        if peer is None:
            raise HostUnavailable("stdio plugin Runner is not running")
        effective = timeout if timeout is not None else self.timeout
        if method == "initialize":
            effective = self.start_timeout
        return await peer.request(method, params, timeout_seconds=effective)

    async def _handle_runner_request(self, frame: RequestFrame) -> Any:
        """Authorize and dispatch one Runner-to-Host request.

        Args:
            frame: Request received from this client's bound Runner connection.

        Returns:
            Encoded Host response payload.

        Raises:
            CallScopeRetired: `parent_call_id` refers to an already finished call.
            InvalidRequest: The request method or payload is malformed.
            CapabilityDenied: The capability is not granted on this connection.
            NotFound: No Host dispatcher is configured.
        """
        if frame.method == "tools.invalidate":
            if self.tools_invalidated_handler is not None:
                await self.tools_invalidated_handler()
            return {"invalidated": True}

        if frame.method in ("capability.invoke", "plugin.service.invoke"):
            raw_parent = frame.params.get("parent_call_id")
            if raw_parent is not None:
                cid = str(raw_parent)
                active = cid in self._active_call_ids or (
                    self._peer is not None and self._peer.has_pending(cid)
                )
                if not active:
                    raise CallScopeRetired(f"call scope has retired: {cid}")

        if frame.method == "plugin.service.invoke":
            plugin_id = frame.params.get("plugin_id")
            service = frame.params.get("service")
            payload = decode_value(frame.params.get("input", {}))
            if payload is None:
                payload = {}
            if (
                not isinstance(plugin_id, str)
                or not plugin_id
                or not isinstance(service, str)
                or not service
                or not isinstance(payload, Mapping)
            ):
                raise InvalidRequest("plugin.service.invoke request is invalid")
            if self.service_handler is None:
                raise NotFound("Host plugin service router is unavailable")
            result = await self.service_handler(plugin_id, service, payload)
            return encode_value(result)

        if frame.method != "capability.invoke":
            raise InvalidRequest(f"unknown Host method: {frame.method}")

        capability_id = frame.params.get("capability")
        operation = frame.params.get("operation")
        payload = decode_value(frame.params.get("input", {}))
        if (
            not isinstance(capability_id, str)
            or not capability_id
            or not isinstance(operation, str)
            or not operation
            or not isinstance(payload, Mapping)
        ):
            raise InvalidRequest("Host capability request is invalid")

        grant = self._granted_capabilities.get(capability_id)
        if grant is None:
            raise CapabilityDenied(f"capability was not granted: {capability_id}")
        if self.capability_handler is None:
            raise NotFound("Host capability dispatcher is unavailable")
        result = await self.capability_handler(grant, operation, payload)
        if inspect.isasyncgen(result) or isinstance(result, AsyncIterator):
            return await self._stream_capability_result(frame.id, result)
        return encode_value(result)

    async def _stream_capability_result(
        self,
        request_id: str,
        stream: AsyncIterator[Any],
    ) -> None:
        """Send one async-generator capability result as a YieldFrame stream.

        Each item is acknowledged by the Runner before the next is produced,
        giving the stream end-to-end backpressure.

        Args:
            request_id: ID of the triggering capability request.
            stream: Async iterator of stream items.

        Returns:
            None, which becomes the final ResponseFrame result.
        """
        ack_queue: asyncio.Queue[int | Exception] = asyncio.Queue()
        self._capability_stream_acks[request_id] = ack_queue
        sequence = 0
        try:
            async for item in stream:
                sequence += 1
                await self._send(
                    YieldFrame(
                        id=request_id,
                        sequence=sequence,
                        result=encode_value(item),
                    ),
                )
                acked = await ack_queue.get()
                if isinstance(acked, Exception):
                    raise acked
                if acked != sequence:
                    raise InvalidRequest(
                        "capability stream ack sequence does not match"
                    )
            return None
        finally:
            self._capability_stream_acks.pop(request_id, None)
            await stream.aclose()

    def _parse_handshake(self, result: Any) -> PluginHandshake:
        """Validate an initialize response.

        Args:
            result: Raw initialize result.

        Returns:
            Validated plugin handshake.

        Raises:
            InvalidRequest: The initialize result is malformed or unsupported.
        """
        if not isinstance(result, Mapping):
            raise InvalidRequest("initialize result must be an object")
        plugin = result.get("plugin")
        raw_handlers = result.get("handlers")
        raw_capabilities = result.get("capabilities")
        protocol_version = result.get("protocol_version")
        if (
            not isinstance(plugin, Mapping)
            or not isinstance(raw_handlers, list)
            or not isinstance(raw_capabilities, list)
            or type(protocol_version) is not int
        ):
            raise InvalidRequest("initialize result is incomplete")

        plugin_id = plugin.get("id")
        name = plugin.get("name")
        version = plugin.get("version")
        schema_version = plugin.get("schema_version")
        if (
            not isinstance(plugin_id, str)
            or not plugin_id
            or not isinstance(name, str)
            or not name
            or not isinstance(version, str)
            or not version
            or type(schema_version) is not int
            or not all(isinstance(item, str) for item in raw_capabilities)
        ):
            raise InvalidRequest("initialize plugin metadata is invalid")

        web_routes = result.get("web_routes")
        if web_routes is None:
            web_routes = []
        if not isinstance(web_routes, list):
            raise InvalidRequest("initialize web_routes must be a list")

        raw_services = result.get("services")
        if raw_services is None:
            raw_services = []
        if not isinstance(raw_services, list) or not all(
            isinstance(item, Mapping) for item in raw_services
        ):
            raise InvalidRequest("initialize services must be a list of objects")

        raw_features = result.get("features")
        if raw_features is None:
            raw_features = []
        if not isinstance(raw_features, list) or not all(
            isinstance(item, str) for item in raw_features
        ):
            raise InvalidRequest("initialize features must be a list of strings")

        handlers: list[HandlerDescriptor] = []
        try:
            for raw_handler in raw_handlers:
                if not isinstance(raw_handler, Mapping):
                    raise InvalidRequest("handler descriptor must be an object")
                handler_id = raw_handler.get("id")
                kind = raw_handler.get("kind")
                priority = raw_handler.get("priority")
                details = raw_handler.get("details", {})
                description = raw_handler.get("description")
                if (
                    not isinstance(handler_id, str)
                    or not handler_id
                    or not isinstance(kind, str)
                    or type(priority) is not int
                    or not isinstance(details, Mapping)
                    or not (description is None or isinstance(description, str))
                ):
                    raise InvalidRequest("handler descriptor is invalid")
                handlers.append(
                    HandlerDescriptor(
                        id=handler_id,
                        kind=HandlerKind(kind),
                        description=description,
                        priority=priority,
                        details=details,
                    )
                )
        except ValueError as exc:
            raise InvalidRequest("handler kind is unsupported") from exc

        if protocol_version != PROTOCOL_VERSION:
            raise InvalidRequest("Runner selected an unsupported protocol version")
        return PluginHandshake(
            protocol_version=protocol_version,
            plugin_id=plugin_id,
            name=name,
            version=version,
            schema_version=schema_version,
            handlers=tuple(handlers),
            capabilities=tuple(raw_capabilities),
            web_routes=tuple(dict(item) for item in web_routes),
            services=tuple(dict(item) for item in raw_services),
            features=tuple(raw_features),
        )

    async def _send(
        self,
        frame: ProtocolFrame,
    ) -> None:
        """Write one Host peer frame to the Runner.

        Args:
            frame: Frame to send.

        Raises:
            HostUnavailable: The Runner transport is closed.
        """
        transport = self._transport
        if transport is None or not self.is_running:
            raise HostUnavailable("plugin Runner is not running")
        await transport.write(encode_frame(frame))

    async def _read_frames(self) -> None:
        """Dispatch Runner frames to peer calls and invocations."""
        transport = self._transport
        peer = self._peer
        if transport is None or peer is None:
            return
        failure: Exception = HostUnavailable("plugin Runner disconnected")
        try:
            while (line := await transport.read()) is not None:
                frame = decode_frame(line)
                if isinstance(frame, (ErrorFrame, ResponseFrame)):
                    self._active_call_ids.discard(frame.id)
                if await peer.receive(frame):
                    continue
                if isinstance(frame, (ErrorFrame, ResponseFrame, YieldFrame)):
                    queue = self._streams.get(frame.id)
                    if queue is not None:
                        queue.put_nowait(frame)
                        continue
                    self.logger.debug(
                        "Ignoring late Runner frame for completed invocation %s",
                        frame.id,
                    )
                    continue
                if isinstance(frame, AckFrame):
                    ack_queue = self._capability_stream_acks.get(frame.id)
                    if ack_queue is not None:
                        ack_queue.put_nowait(frame.sequence)
                        continue
                    self.logger.debug(
                        "Ignoring late Runner ack for %s",
                        frame.id,
                    )
                    continue
                raise InvalidRequest(f"Runner cannot send {type(frame).__name__}")
        except Exception as exc:
            failure = exc
        finally:
            await peer.close(failure)
            for queue in list(self._streams.values()):
                queue.put_nowait(failure)

    async def _read_stderr(self) -> None:
        """Forward Runner stderr to the Host logger."""
        process = self._process
        if process is None or process.stderr is None:
            return
        while line := await process.stderr.readline():
            self.logger.debug(
                "Plugin Runner stderr: %s",
                line.decode("utf-8", errors="replace").rstrip(),
            )

    async def _finish_tasks(self) -> None:
        """Wait for process reader tasks and cancel stragglers."""
        tasks = [
            task for task in (self._reader_task, self._stderr_task) if task is not None
        ]
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._reader_task = None
        self._stderr_task = None
