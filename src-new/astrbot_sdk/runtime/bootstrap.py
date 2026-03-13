"""启动引导模块。

定义 SupervisorRuntime 和 PluginWorkerRuntime 的启动逻辑。
Supervisor 管理多个 Worker 进程，Worker 运行单个插件。

架构层次：
    AstrBot Core (Python)
        |
        v
    SupervisorRuntime (管理多插件)
        |
        +-- WorkerSession (插件 A) -- StdioTransport -- PluginWorkerRuntime (子进程)
        |
        +-- WorkerSession (插件 B) -- StdioTransport -- PluginWorkerRuntime (子进程)
        |
        +-- WorkerSession (插件 C) -- StdioTransport -- PluginWorkerRuntime (子进程)

核心类：
    SupervisorRuntime: 监管者运行时
        - 发现并加载所有插件
        - 为每个插件启动 Worker 进程
        - 聚合所有 handler 并向 Core 注册
        - 路由 Core 的调用请求到对应 Worker
        - 处理 Worker 进程崩溃和重连
        - handler ID 冲突检测和警告

    WorkerSession: Worker 会话
        - 管理单个插件 Worker 进程
        - 通过 Peer 与 Worker 通信
        - 提供 invoke_handler 和 cancel 方法
        - 处理连接关闭回调
        - 自动清理已注册的 handlers

    PluginWorkerRuntime: 插件 Worker 运行时
        - 加载单个插件
        - 通过 Peer 与 Supervisor 通信
        - 分发 handler 调用
        - 处理生命周期回调 (on_start, on_stop)

与旧版对比：
    旧版 supervisor.py:
        - WorkerRuntime 管理单个插件进程
        - SupervisorRuntime 管理所有 Worker
        - 使用 JSON-RPC 协议通信
        - call_context_function 调用核心功能
        - 使用 RPCRequestHelper 管理请求

    新版 bootstrap.py:
        - WorkerSession 封装 Worker 会话
        - SupervisorRuntime 使用 Peer 通信
        - 使用新协议 (initialize/invoke/event/cancel)
        - 通过 CapabilityRouter 路由能力调用
        - 支持 Worker 连接关闭回调
        - 支持 handler 冲突检测和警告

启动流程：
    Supervisor 启动:
        1. discover_plugins() 发现所有插件
        2. 为每个插件创建 WorkerSession
        3. 调用 session.start() 启动 Worker 进程
        4. 等待 Worker 初始化完成或连接关闭
        5. 聚合所有 handler 并向 Core 发送 initialize
        6. 等待 Core 的 initialize_result

    Worker 启动:
        1. load_plugin_spec() 加载插件规范
        2. load_plugin() 加载插件组件
        3. 创建 Peer 并设置处理器
        4. 向 Supervisor 发送 initialize
        5. 等待 Supervisor 的 initialize_result
        6. 执行 on_start 生命周期回调

信号处理：
    - SIGTERM: 设置 stop_event，触发优雅关闭
    - SIGINT: 设置 stop_event，触发优雅关闭

这层负责把 `loader`、`Peer`、`CapabilityRouter` 和 `HandlerDispatcher` 串起来：

- `SupervisorRuntime`: 启动多个插件 Worker，并把所有 handler 暴露给上游 Core
- `WorkerSession`: Supervisor 侧对单个 Worker 的会话包装
- `PluginWorkerRuntime`: Worker 进程内的插件加载与 handler 执行

当前实现会在 Worker 连接关闭时清理对应 handler，但不会自动重启或重连。
"""

from __future__ import annotations

import asyncio
import inspect
import os
import signal
import sys
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any

from loguru import logger

from ..context import Context as RuntimeContext
from ..errors import AstrBotError
from ..protocol.descriptors import CapabilityDescriptor
from ..protocol.messages import EventMessage, InitializeOutput, PeerInfo
from ..star import Star
from .capability_router import CapabilityRouter, StreamExecution
from .handler_dispatcher import CapabilityDispatcher, HandlerDispatcher
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


def _sdk_source_dir(repo_root: Path) -> Path:
    candidate = repo_root.resolve() / "src-new"
    if (candidate / "astrbot_sdk").exists():
        return candidate
    return Path(__file__).resolve().parents[2]


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
        on_closed: Callable[[], None] | None = None,
    ) -> None:
        self.plugin = plugin
        self.repo_root = repo_root.resolve()
        self.env_manager = env_manager
        self.capability_router = capability_router
        self.on_closed = on_closed
        self.peer: Peer | None = None
        self.handlers = []
        self.provided_capabilities: list[CapabilityDescriptor] = []
        self._connection_watch_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        python_path = self.env_manager.prepare_environment(self.plugin)
        repo_src_dir = str(_sdk_source_dir(self.repo_root))
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
            # 同时监听初始化完成和连接关闭，避免 worker 崩溃时等满超时
            init_task = asyncio.create_task(
                self.peer.wait_until_remote_initialized(timeout=None)
            )
            closed_task = asyncio.create_task(self.peer.wait_closed())
            done, pending = await asyncio.wait(
                {init_task, closed_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            if closed_task in done:
                raise RuntimeError(
                    f"插件 {self.plugin.name} worker 进程在初始化阶段退出"
                )

            self.handlers = list(self.peer.remote_handlers)
            self.provided_capabilities = list(self.peer.remote_provided_capabilities)

        except Exception:
            await self.stop()
            raise

    def start_close_watch(self) -> None:
        if (
            self.on_closed is None
            or self.peer is None
            or self._connection_watch_task is not None
        ):
            return
        self._connection_watch_task = asyncio.create_task(self._watch_connection())

    async def _watch_connection(self) -> None:
        """监听 Worker 连接关闭，触发清理回调"""
        try:
            if self.peer is not None:
                await self.peer.wait_closed()
            if self.on_closed is not None:
                try:
                    self.on_closed()
                except Exception:
                    logger.exception(
                        "on_closed callback failed for plugin {}", self.plugin.name
                    )
        finally:
            current_task = asyncio.current_task()
            if self._connection_watch_task is current_task:
                self._connection_watch_task = None

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

    async def invoke_capability(
        self,
        capability_name: str,
        payload: dict[str, Any],
        *,
        request_id: str,
    ) -> dict[str, Any]:
        if self.peer is None:
            raise RuntimeError("worker session is not running")
        return await self.peer.invoke(
            capability_name,
            payload,
            request_id=request_id,
        )

    async def invoke_capability_stream(
        self,
        capability_name: str,
        payload: dict[str, Any],
        *,
        request_id: str,
    ):
        if self.peer is None:
            raise RuntimeError("worker session is not running")
        event_stream = await self.peer.invoke_stream(
            capability_name,
            payload,
            request_id=request_id,
            include_completed=True,
        )
        async for event in event_stream:
            yield event

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
        self.capability_to_worker: dict[str, WorkerSession] = {}
        self._handler_sources: dict[str, str] = {}  # handler_id -> plugin_name
        self._capability_sources: dict[str, str] = {}  # capability_name -> plugin_name
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

    def _register_handler(
        self, handler, session: WorkerSession, plugin_name: str
    ) -> None:
        """注册 handler，处理冲突时输出警告。

        Args:
            handler: Handler 描述符
            session: Worker 会话
            plugin_name: 插件名称
        """
        handler_id = handler.id
        existing_plugin = self._handler_sources.get(handler_id)

        if existing_plugin is not None:
            logger.warning(
                f"Handler ID 冲突：'{handler_id}' 已被插件 '{existing_plugin}' 注册，"
                f"现在被插件 '{plugin_name}' 覆盖。"
            )

        self.handler_to_worker[handler_id] = session
        self._handler_sources[handler_id] = plugin_name

    def _register_plugin_capability(
        self,
        descriptor: CapabilityDescriptor,
        session: WorkerSession,
        plugin_name: str,
    ) -> None:
        capability_name = descriptor.name
        if self.capability_router.contains(capability_name):
            logger.warning(
                "Capability 名称冲突：'{}' 已存在，跳过插件 '{}' 的注册。",
                capability_name,
                plugin_name,
                # TODO: 更好的解决方案？
            )
            return
        self.capability_router.register(
            descriptor.model_copy(deep=True),
            call_handler=self._make_plugin_capability_caller(session, capability_name),
            stream_handler=(
                self._make_plugin_capability_streamer(session, capability_name)
                if descriptor.supports_stream
                else None
            ),
        )
        self.capability_to_worker[capability_name] = session
        self._capability_sources[capability_name] = plugin_name

    def _make_plugin_capability_caller(
        self,
        session: WorkerSession,
        capability_name: str,
    ):
        async def call_handler(
            request_id: str,
            payload: dict[str, Any],
            _cancel_token,
        ) -> dict[str, Any]:
            self.active_requests[request_id] = session
            try:
                return await session.invoke_capability(
                    capability_name,
                    payload,
                    request_id=request_id,
                )
            finally:
                self.active_requests.pop(request_id, None)

        return call_handler

    def _make_plugin_capability_streamer(
        self,
        session: WorkerSession,
        capability_name: str,
    ):
        async def stream_handler(
            request_id: str,
            payload: dict[str, Any],
            _cancel_token,
        ):
            completed_output: dict[str, Any] = {}

            async def iterator():
                self.active_requests[request_id] = session
                try:
                    async for event in session.invoke_capability_stream(
                        capability_name,
                        payload,
                        request_id=request_id,
                    ):
                        if not isinstance(event, EventMessage):
                            raise AstrBotError.protocol_error(
                                "插件 worker 返回了非法的流式事件"
                            )
                        if event.phase == "delta":
                            yield event.data or {}
                            continue
                        if event.phase == "completed":
                            completed_output.clear()
                            completed_output.update(event.output or {})
                finally:
                    self.active_requests.pop(request_id, None)

            return StreamExecution(
                iterator=iterator(),
                finalize=lambda chunks: completed_output or {"items": chunks},
            )

        return stream_handler

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
                    on_closed=lambda name=plugin.name: self._handle_worker_closed(name),
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
                    self._register_handler(handler, session, plugin.name)
                for descriptor in session.provided_capabilities:
                    self._register_plugin_capability(descriptor, session, plugin.name)
                session.start_close_watch()

            aggregated_handlers = list(self.handler_to_worker.keys())
            logger.info(
                "Loaded plugins: {}", ", ".join(sorted(self.loaded_plugins)) or "none"
            )

            await self.peer.start()
            await self.peer.initialize(
                [
                    handler
                    for session in self.worker_sessions.values()
                    for handler in session.handlers
                ],
                provided_capabilities=self.capability_router.descriptors(),
                metadata={
                    "plugins": sorted(self.loaded_plugins),
                    "skipped_plugins": self.skipped_plugins,
                    "aggregated_handler_ids": aggregated_handlers,
                },
            )
        except Exception:
            await self.stop()
            raise

    def _handle_worker_closed(self, plugin_name: str) -> None:
        """Worker 连接关闭时的清理回调"""
        session = self.worker_sessions.pop(plugin_name, None)
        if session is None:
            return
        # 从 handler_to_worker 中移除该插件注册的 handlers（仅当来源仍为此插件时）
        for handler in session.handlers:
            source_plugin = self._handler_sources.get(handler.id)
            if source_plugin == plugin_name:
                self.handler_to_worker.pop(handler.id, None)
                self._handler_sources.pop(handler.id, None)
        for descriptor in session.provided_capabilities:
            source_plugin = self._capability_sources.get(descriptor.name)
            if source_plugin == plugin_name:
                self.capability_to_worker.pop(descriptor.name, None)
                self._capability_sources.pop(descriptor.name, None)
                self.capability_router.unregister(descriptor.name)
        # 从 loaded_plugins 中移除
        if plugin_name in self.loaded_plugins:
            self.loaded_plugins.remove(plugin_name)
        stale_requests = [
            request_id
            for request_id, active_session in self.active_requests.items()
            if active_session is session
        ]
        for request_id in stale_requests:
            self.active_requests.pop(request_id, None)
        logger.warning("插件 {} worker 连接已关闭，已清理相关 handlers", plugin_name)

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
        self.capability_dispatcher = CapabilityDispatcher(
            plugin_id=self.plugin.name,
            peer=self.peer,
            capabilities=self.loaded_plugin.capabilities,
        )
        self._lifecycle_context = RuntimeContext(
            peer=self.peer, plugin_id=self.plugin.name
        )
        self.peer.set_invoke_handler(self._handle_invoke)
        self.peer.set_cancel_handler(self._handle_cancel)

    async def start(self) -> None:
        await self.peer.start()
        lifecycle_started = False
        try:
            await self._run_lifecycle("on_start")
            lifecycle_started = True
            await self.peer.initialize(
                [item.descriptor for item in self.loaded_plugin.handlers],
                provided_capabilities=[
                    item.descriptor for item in self.loaded_plugin.capabilities
                ],
                metadata={"plugin_id": self.plugin.name},
            )
        except Exception:
            if lifecycle_started:
                try:
                    await self._run_lifecycle("on_stop")
                except Exception:
                    logger.exception(
                        "插件 {} 在启动失败清理 on_stop 时发生异常",
                        self.plugin.name,
                    )
            await self.peer.stop()
            raise

    async def stop(self) -> None:
        try:
            await self._run_lifecycle("on_stop")
        finally:
            await self.peer.stop()

    async def _handle_invoke(self, message, cancel_token):
        if message.capability == "handler.invoke":
            return await self.dispatcher.invoke(message, cancel_token)
        try:
            return await self.capability_dispatcher.invoke(message, cancel_token)
        except LookupError as exc:
            raise AstrBotError.capability_not_found(message.capability) from exc

    async def _handle_cancel(self, request_id: str) -> None:
        await self.dispatcher.cancel(request_id)
        await self.capability_dispatcher.cancel(request_id)

    async def _run_lifecycle(self, method_name: str) -> None:
        for instance in self.loaded_plugin.instances:
            hook = self._resolve_lifecycle_hook(instance, method_name)
            if hook is None:
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
                    if parameter.kind
                    in (
                        inspect.Parameter.POSITIONAL_ONLY,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    )
                ]
                if positional_params:
                    args.append(self._lifecycle_context)
            result = hook(*args)
            if inspect.isawaitable(result):
                await result

    @staticmethod
    def _resolve_lifecycle_hook(instance: Any, method_name: str):
        hook = getattr(instance, method_name, None)
        marker = getattr(instance.__class__, "__astrbot_is_new_star__", None)
        is_new_star = True
        if callable(marker):
            is_new_star = bool(marker())

        if hook is not None and callable(hook):
            bound_func = getattr(hook, "__func__", hook)
            star_default = getattr(Star, method_name, None)
            if star_default is None or bound_func is not star_default:
                return hook

        if not is_new_star:
            alias = {
                "on_start": "initialize",
                "on_stop": "terminate",
            }.get(method_name)
            if alias is not None:
                legacy_hook = getattr(instance, alias, None)
                if legacy_hook is not None and callable(legacy_hook):
                    return legacy_hook

        if hook is not None and callable(hook):
            return hook
        return None


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
