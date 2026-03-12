from __future__ import annotations

import asyncio
import inspect
import os
import signal
import sys
from pathlib import Path
from typing import IO, Any

from loguru import logger

from ..context import Context as RuntimeContext
from ..errors import AstrBotError
from ..protocol.descriptors import CapabilityDescriptor
from ..protocol.messages import InitializeOutput, PeerInfo
from .capability_router import CapabilityRouter
from .handler_dispatcher import HandlerDispatcher
from .loader import (
    PluginEnvironmentManager,
    PluginSpec,
    discover_plugins,
    load_plugin,
    load_plugin_spec,
)
from .peer import Peer
from .transport import StdioTransport, WebSocketServerTransport


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            logger.debug("Signal handlers are not supported for {}", sig)


def _prepare_stdio_transport(
    stdin: IO[str] | None,
    stdout: IO[str] | None,
) -> tuple[IO[str], IO[str], IO[str] | None]:
    if stdin is not None and stdout is not None:
        return stdin, stdout, None
    transport_stdin = stdin or sys.stdin
    transport_stdout = stdout or sys.stdout
    original_stdout = sys.stdout
    sys.stdout = sys.stderr
    return transport_stdin, transport_stdout, original_stdout


async def _wait_for_shutdown(peer: Peer, stop_event: asyncio.Event) -> None:
    stop_waiter = asyncio.create_task(stop_event.wait())
    transport_waiter = asyncio.create_task(peer.wait_closed())
    done, pending = await asyncio.wait(
        {stop_waiter, transport_waiter},
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
    for task in done:
        if not task.cancelled():
            task.result()


class WorkerSession:
    def __init__(
        self,
        *,
        plugin: PluginSpec,
        repo_root: Path,
        env_manager: PluginEnvironmentManager,
        capability_router: CapabilityRouter,
    ) -> None:
        self.plugin = plugin
        self.repo_root = repo_root.resolve()
        self.env_manager = env_manager
        self.capability_router = capability_router
        self.peer: Peer | None = None
        self.handlers = []

    async def start(self) -> None:
        python_path = self.env_manager.prepare_environment(self.plugin)
        repo_src_dir = str(self.repo_root / "src-new")
        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            f"{repo_src_dir}{os.pathsep}{existing_pythonpath}"
            if existing_pythonpath
            else repo_src_dir
        )

        transport = StdioTransport(
            command=[
                str(python_path),
                "-m",
                "astrbot_sdk",
                "worker",
                "--plugin-dir",
                str(self.plugin.plugin_dir),
            ],
            cwd=str(self.plugin.plugin_dir),
            env=env,
        )
        self.peer = Peer(
            transport=transport,
            peer_info=PeerInfo(name="astrbot-core", role="core", version="v4"),
        )
        self.peer.set_initialize_handler(self._handle_initialize)
        self.peer.set_invoke_handler(self._handle_capability_invoke)
        try:
            await self.peer.start()
            await self.peer.wait_until_remote_initialized()
            self.handlers = list(self.peer.remote_handlers)
        except Exception:
            await self.stop()
            raise

    async def stop(self) -> None:
        if self.peer is not None:
            await self.peer.stop()

    async def invoke_handler(
        self,
        handler_id: str,
        event_payload: dict[str, Any],
        *,
        request_id: str,
    ) -> dict[str, Any]:
        if self.peer is None:
            raise RuntimeError("worker session is not running")
        return await self.peer.invoke(
            "handler.invoke",
            {
                "handler_id": handler_id,
                "event": event_payload,
            },
            request_id=request_id,
        )

    async def cancel(self, request_id: str) -> None:
        if self.peer is None:
            return
        await self.peer.cancel(request_id)

    async def _handle_initialize(self, _message) -> InitializeOutput:
        return InitializeOutput(
            peer=PeerInfo(name="astrbot-supervisor", role="core", version="v4"),
            capabilities=self.capability_router.descriptors(),
            metadata={"plugin": self.plugin.name},
        )

    async def _handle_capability_invoke(self, message, cancel_token):
        return await self.capability_router.execute(
            message.capability,
            message.input,
            stream=message.stream,
            cancel_token=cancel_token,
            request_id=message.id,
        )


class SupervisorRuntime:
    def __init__(
        self,
        *,
        transport,
        plugins_dir: Path,
        env_manager: PluginEnvironmentManager | None = None,
    ) -> None:
        self.transport = transport
        self.plugins_dir = plugins_dir.resolve()
        self.repo_root = Path(__file__).resolve().parents[3]
        self.env_manager = env_manager or PluginEnvironmentManager(self.repo_root)
        self.capability_router = CapabilityRouter()
        self.peer = Peer(
            transport=self.transport,
            peer_info=PeerInfo(name="astrbot-supervisor", role="plugin", version="v4"),
        )
        self.peer.set_invoke_handler(self._handle_upstream_invoke)
        self.peer.set_cancel_handler(self._handle_upstream_cancel)
        self.worker_sessions: dict[str, WorkerSession] = {}
        self.handler_to_worker: dict[str, WorkerSession] = {}
        self.active_requests: dict[str, WorkerSession] = {}
        self.loaded_plugins: list[str] = []
        self.skipped_plugins: dict[str, str] = {}
        self._register_internal_capabilities()

    def _register_internal_capabilities(self) -> None:
        self.capability_router.register(
            CapabilityDescriptor(
                name="handler.invoke",
                description="框架内部：转发到插件 handler",
                input_schema={
                    "type": "object",
                    "properties": {
                        "handler_id": {"type": "string"},
                        "event": {"type": "object"},
                    },
                    "required": ["handler_id", "event"],
                },
                output_schema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
                cancelable=True,
            ),
            call_handler=self._route_handler_invoke,
            exposed=False,
        )

    async def start(self) -> None:
        discovery = discover_plugins(self.plugins_dir)
        self.skipped_plugins = dict(discovery.skipped_plugins)
        try:
            for plugin in discovery.plugins:
                session = WorkerSession(
                    plugin=plugin,
                    repo_root=self.repo_root,
                    env_manager=self.env_manager,
                    capability_router=self.capability_router,
                )
                try:
                    await session.start()
                except Exception as exc:
                    self.skipped_plugins[plugin.name] = str(exc)
                    await session.stop()
                    continue
                self.worker_sessions[plugin.name] = session
                self.loaded_plugins.append(plugin.name)
                for handler in session.handlers:
                    self.handler_to_worker[handler.id] = session

            aggregated_handlers = list(self.handler_to_worker.keys())
            logger.info("Loaded plugins: {}", ", ".join(sorted(self.loaded_plugins)) or "none")

            await self.peer.start()
            await self.peer.initialize(
                [handler for session in self.worker_sessions.values() for handler in session.handlers],
                metadata={
                    "plugins": sorted(self.loaded_plugins),
                    "skipped_plugins": self.skipped_plugins,
                    "aggregated_handler_ids": aggregated_handlers,
                },
            )
        except Exception:
            await self.stop()
            raise

    async def stop(self) -> None:
        for session in list(self.worker_sessions.values()):
            await session.stop()
        await self.peer.stop()

    async def _handle_upstream_invoke(self, message, cancel_token):
        return await self.capability_router.execute(
            message.capability,
            message.input,
            stream=message.stream,
            cancel_token=cancel_token,
            request_id=message.id,
        )

    async def _route_handler_invoke(
        self,
        request_id: str,
        payload: dict[str, Any],
        _cancel_token,
    ) -> dict[str, Any]:
        handler_id = str(payload.get("handler_id", ""))
        session = self.handler_to_worker.get(handler_id)
        if session is None:
            raise AstrBotError.invalid_input(f"handler not found: {handler_id}")
        self.active_requests[request_id] = session
        try:
            return await session.invoke_handler(
                handler_id,
                payload.get("event", {}),
                request_id=request_id,
            )
        finally:
            self.active_requests.pop(request_id, None)

    async def _handle_upstream_cancel(self, request_id: str) -> None:
        session = self.active_requests.get(request_id)
        if session is not None:
            await session.cancel(request_id)


class PluginWorkerRuntime:
    def __init__(self, *, plugin_dir: Path, transport) -> None:
        self.plugin = load_plugin_spec(plugin_dir)
        self.transport = transport
        self.loaded_plugin = load_plugin(self.plugin)
        self.peer = Peer(
            transport=self.transport,
            peer_info=PeerInfo(name=self.plugin.name, role="plugin", version="v4"),
        )
        self.dispatcher = HandlerDispatcher(
            plugin_id=self.plugin.name,
            peer=self.peer,
            handlers=self.loaded_plugin.handlers,
        )
        self._lifecycle_context = RuntimeContext(peer=self.peer, plugin_id=self.plugin.name)
        self.peer.set_invoke_handler(self._handle_invoke)
        self.peer.set_cancel_handler(self.dispatcher.cancel)

    async def start(self) -> None:
        await self.peer.start()
        await self.peer.initialize(
            [item.descriptor for item in self.loaded_plugin.handlers],
            metadata={"plugin_id": self.plugin.name},
        )
        await self._run_lifecycle("on_start")

    async def stop(self) -> None:
        try:
            await self._run_lifecycle("on_stop")
        finally:
            await self.peer.stop()

    async def _handle_invoke(self, message, cancel_token):
        if message.capability != "handler.invoke":
            raise AstrBotError.capability_not_found(message.capability)
        return await self.dispatcher.invoke(message, cancel_token)

    async def _run_lifecycle(self, method_name: str) -> None:
        for instance in self.loaded_plugin.instances:
            hook = getattr(instance, method_name, None)
            if hook is None or not callable(hook):
                continue
            args = []
            try:
                signature = inspect.signature(hook)
            except (TypeError, ValueError):
                signature = None
            if signature is not None:
                positional_params = [
                    parameter
                    for parameter in signature.parameters.values()
                    if parameter.kind in (
                        inspect.Parameter.POSITIONAL_ONLY,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    )
                ]
                if positional_params:
                    args.append(self._lifecycle_context)
            result = hook(*args)
            if inspect.isawaitable(result):
                await result


async def run_supervisor(
    *,
    plugins_dir: Path = Path("plugins"),
    stdin: IO[str] | None = None,
    stdout: IO[str] | None = None,
    env_manager: PluginEnvironmentManager | None = None,
) -> None:
    transport_stdin, transport_stdout, original_stdout = _prepare_stdio_transport(
        stdin,
        stdout,
    )
    transport = StdioTransport(stdin=transport_stdin, stdout=transport_stdout)
    runtime = SupervisorRuntime(
        transport=transport,
        plugins_dir=plugins_dir,
        env_manager=env_manager,
    )

    try:
        await runtime.start()
        stop_event = asyncio.Event()
        _install_signal_handlers(stop_event)
        await _wait_for_shutdown(runtime.peer, stop_event)
    finally:
        await runtime.stop()
        if original_stdout is not None:
            sys.stdout = original_stdout


async def run_plugin_worker(
    *,
    plugin_dir: Path,
    stdin: IO[str] | None = None,
    stdout: IO[str] | None = None,
) -> None:
    transport_stdin, transport_stdout, original_stdout = _prepare_stdio_transport(
        stdin,
        stdout,
    )
    transport = StdioTransport(stdin=transport_stdin, stdout=transport_stdout)
    runtime = PluginWorkerRuntime(plugin_dir=plugin_dir, transport=transport)
    try:
        await runtime.start()
        stop_event = asyncio.Event()
        _install_signal_handlers(stop_event)
        await _wait_for_shutdown(runtime.peer, stop_event)
    finally:
        await runtime.stop()
        if original_stdout is not None:
            sys.stdout = original_stdout


async def run_websocket_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    path: str = "/",
    plugin_dir: Path | None = None,
) -> None:
    runtime = PluginWorkerRuntime(
        plugin_dir=plugin_dir or Path.cwd(),
        transport=WebSocketServerTransport(host=host, port=port, path=path),
    )
    try:
        await runtime.start()
        stop_event = asyncio.Event()
        _install_signal_handlers(stop_event)
        await _wait_for_shutdown(runtime.peer, stop_event)
    finally:
        await runtime.stop()
