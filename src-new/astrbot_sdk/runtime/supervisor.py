"""Supervisor 端运行时：SupervisorRuntime 管理多个 Worker 进程，WorkerSession 封装与单个 Worker 的通信。

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

信号处理：
    - SIGTERM: 设置 stop_event，触发优雅关闭
    - SIGINT: 设置 stop_event，触发优雅关闭
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any

from loguru import logger

from ..errors import AstrBotError
from ..protocol.descriptors import CapabilityDescriptor
from ..protocol.messages import EventMessage, InitializeOutput, PeerInfo
from .capability_router import CapabilityRouter, StreamExecution
from .environment_groups import EnvironmentGroup
from .loader import (
    PluginEnvironmentManager,
    PluginSpec,
    discover_plugins,
    load_plugin_config,
)
from .peer import Peer
from .transport import StdioTransport

__all__ = [
    "SupervisorRuntime",
    "WorkerSession",
    "_install_signal_handlers",
    "_prepare_stdio_transport",
    "_sdk_source_dir",
    "_wait_for_shutdown",
]


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


def _plugin_name_from_handler_id(handler_id: str) -> str:
    if ":" in handler_id:
        return handler_id.split(":", 1)[0]
    return handler_id


class WorkerSession:
    def __init__(
        self,
        *,
        plugin: PluginSpec | None = None,
        group: EnvironmentGroup | None = None,
        repo_root: Path,
        env_manager: PluginEnvironmentManager,
        capability_router: CapabilityRouter,
        on_closed: Callable[[], None] | None = None,
    ) -> None:
        if plugin is None and group is None:
            raise ValueError("WorkerSession requires either plugin or group")
        self.group = group
        self.plugins = list(group.plugins) if group is not None else [plugin]
        self.plugin = plugin or self.plugins[0]
        self.group_id = group.id if group is not None else self.plugin.name
        self.repo_root = repo_root.resolve()
        self.env_manager = env_manager
        self.capability_router = capability_router
        self.on_closed = on_closed
        self.peer: Peer | None = None
        self.handlers = []
        self.provided_capabilities: list[CapabilityDescriptor] = []
        self.loaded_plugins: list[str] = []
        self.skipped_plugins: dict[str, str] = {}
        self.capability_sources: dict[str, str] = {}
        self._connection_watch_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        python_path, command, cwd = self._worker_command()
        repo_src_dir = str(_sdk_source_dir(self.repo_root))
        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            f"{repo_src_dir}{os.pathsep}{existing_pythonpath}"
            if existing_pythonpath
            else repo_src_dir
        )
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")

        transport = StdioTransport(
            command=command,
            cwd=cwd,
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
                raise RuntimeError(f"worker 组 {self.group_id} 在初始化阶段退出")

            self.handlers = list(self.peer.remote_handlers)
            self.provided_capabilities = list(self.peer.remote_provided_capabilities)
            metadata = dict(self.peer.remote_metadata)
            remote_loaded_plugins = metadata.get("loaded_plugins")
            if isinstance(remote_loaded_plugins, list):
                self.loaded_plugins = [
                    plugin_name
                    for plugin_name in remote_loaded_plugins
                    if isinstance(plugin_name, str)
                ]
            else:
                self.loaded_plugins = [plugin.name for plugin in self.plugins]
            remote_skipped_plugins = metadata.get("skipped_plugins")
            if isinstance(remote_skipped_plugins, dict):
                self.skipped_plugins = {
                    str(plugin_name): str(reason)
                    for plugin_name, reason in remote_skipped_plugins.items()
                }
            remote_capability_sources = metadata.get("capability_sources")
            if isinstance(remote_capability_sources, dict):
                self.capability_sources = {
                    str(capability_name): str(plugin_name)
                    for capability_name, plugin_name in remote_capability_sources.items()
                }

        except Exception:
            await self.stop()
            raise

    def _worker_command(self) -> tuple[Path, list[str], str]:
        if self.group is not None:
            prepare_group = getattr(self.env_manager, "prepare_group_environment", None)
            if callable(prepare_group):
                python_path = prepare_group(self.group)
            else:
                python_path = self.env_manager.prepare_environment(self.plugins[0])
            return (
                python_path,
                [
                    str(python_path),
                    "-m",
                    "astrbot_sdk",
                    "worker",
                    "--group-metadata",
                    str(self.group.metadata_path),
                ],
                str(self.repo_root),
            )

        python_path = self.env_manager.prepare_environment(self.plugin)
        return (
            python_path,
            [
                str(python_path),
                "-m",
                "astrbot_sdk",
                "worker",
                "--plugin-dir",
                str(self.plugin.plugin_dir),
            ],
            str(self.plugin.plugin_dir),
        )

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
                        "on_closed callback failed for worker group {}", self.group_id
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
            metadata={
                "group_id": self.group_id,
                "plugins": [plugin.name for plugin in self.plugins],
            },
        )

    async def _handle_capability_invoke(self, message, cancel_token):
        return await self.capability_router.execute(
            message.capability,
            message.input,
            stream=message.stream,
            cancel_token=cancel_token,
            request_id=message.id,
        )

    def describe(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "plugins": [plugin.name for plugin in self.plugins],
            "loaded_plugins": list(self.loaded_plugins),
            "skipped_plugins": dict(self.skipped_plugins),
        }


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
        self.plugin_to_worker_session: dict[str, WorkerSession] = {}
        self._handler_sources: dict[str, str] = {}  # handler_id -> plugin_name
        self._capability_sources: dict[str, str] = {}  # capability_name -> plugin_name
        self.active_requests: dict[str, WorkerSession] = {}
        self.loaded_plugins: list[str] = []
        self.skipped_plugins: dict[str, str] = {}
        self._register_internal_capabilities()

    def _sync_plugin_registry(self, plugins: list[PluginSpec]) -> None:
        loaded_plugin_set = set(self.loaded_plugins)
        for plugin in plugins:
            manifest = plugin.manifest_data
            self.capability_router.upsert_plugin(
                metadata={
                    "name": plugin.name,
                    "display_name": str(manifest.get("display_name") or plugin.name),
                    "description": str(
                        manifest.get("desc") or manifest.get("description") or ""
                    ),
                    "author": str(manifest.get("author") or ""),
                    "version": str(manifest.get("version") or "0.0.0"),
                    "enabled": plugin.name in loaded_plugin_set,
                },
                config=load_plugin_config(plugin),
            )

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
        """注册插件 capability，处理命名冲突。

        当 capability 名称冲突时：
        - 如果是保留命名空间（handler/system/internal），跳过并警告
        - 否则，使用插件名作为前缀重新命名，例如：
          - 插件 'my_plugin' 注册 'demo.echo' 冲突
          - 自动重命名为 'my_plugin.demo.echo'
        """
        capability_name = descriptor.name

        if not self.capability_router.contains(capability_name):
            # 无冲突，直接注册
            self._do_register_capability(
                descriptor, session, capability_name, plugin_name
            )
            return

        # 检查是否在保留命名空间内
        if capability_name.startswith(("handler.", "system.", "internal.")):
            logger.warning(
                "Capability '{}' 在保留命名空间内，跳过插件 '{}' 的注册。"
                "保留命名空间不允许插件覆盖。",
                capability_name,
                plugin_name,
            )
            return

        # 尝试添加插件前缀解决冲突
        prefixed_name = f"{plugin_name}.{capability_name}"
        if self.capability_router.contains(prefixed_name):
            logger.warning(
                "Capability '{}' 和 '{}.{}' 均已存在，"
                "跳过插件 '{}' 的注册。请考虑使用更唯一的命名。",
                capability_name,
                plugin_name,
                capability_name,
                plugin_name,
            )
            return

        # 使用前缀名称注册
        prefixed_descriptor = descriptor.model_copy(deep=True)
        prefixed_descriptor.name = prefixed_name
        logger.info(
            "Capability '{}' 与已注册能力冲突，自动重命名为 '{}' (插件: {})。",
            capability_name,
            prefixed_name,
            plugin_name,
        )
        self._do_register_capability(
            prefixed_descriptor, session, prefixed_name, plugin_name
        )
        # 记录原始名称到前缀名称的映射，便于调试
        self._capability_sources[f"_original:{prefixed_name}"] = capability_name

    def _do_register_capability(
        self,
        descriptor: CapabilityDescriptor,
        session: WorkerSession,
        capability_name: str,
        plugin_name: str,
    ) -> None:
        """实际执行 capability 注册。"""
        self.capability_router.register(
            descriptor,
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
        plan_result = self.env_manager.plan(discovery.plugins)
        self.skipped_plugins.update(plan_result.skipped_plugins)
        self._sync_plugin_registry(discovery.plugins)
        try:
            planned_sessions: list[WorkerSession] = []
            if plan_result.groups:
                for group in plan_result.groups:
                    planned_sessions.append(
                        WorkerSession(
                            group=group,
                            repo_root=self.repo_root,
                            env_manager=self.env_manager,
                            capability_router=self.capability_router,
                            on_closed=lambda group_id=group.id: (
                                self._handle_worker_closed(group_id)
                            ),
                        )
                    )
            else:
                for plugin in plan_result.plugins:
                    planned_sessions.append(
                        WorkerSession(
                            plugin=plugin,
                            repo_root=self.repo_root,
                            env_manager=self.env_manager,
                            capability_router=self.capability_router,
                            on_closed=lambda plugin_name=plugin.name: (
                                self._handle_worker_closed(plugin_name)
                            ),
                        )
                    )

            for session in planned_sessions:
                try:
                    await session.start()
                except Exception as exc:
                    for plugin in session.plugins:
                        self.skipped_plugins[plugin.name] = str(exc)
                    await session.stop()
                    continue
                self.worker_sessions[session.group_id] = session
                self.skipped_plugins.update(session.skipped_plugins)
                for plugin_name in session.loaded_plugins:
                    self.plugin_to_worker_session[plugin_name] = session
                    if plugin_name not in self.loaded_plugins:
                        self.loaded_plugins.append(plugin_name)
                for handler in session.handlers:
                    self._register_handler(
                        handler,
                        session,
                        _plugin_name_from_handler_id(handler.id),
                    )
                for descriptor in session.provided_capabilities:
                    plugin_name = session.capability_sources.get(descriptor.name)
                    if plugin_name is None and len(session.loaded_plugins) == 1:
                        plugin_name = session.loaded_plugins[0]
                    if plugin_name is None:
                        plugin_name = session.group_id
                    self._register_plugin_capability(descriptor, session, plugin_name)
                session.start_close_watch()

            self._sync_plugin_registry(discovery.plugins)

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
                    "worker_groups": [
                        session.describe() for session in self.worker_sessions.values()
                    ],
                    "worker_group_count": len(self.worker_sessions),
                },
            )
        except Exception:
            await self.stop()
            raise

    def _handle_worker_closed(self, group_id: str) -> None:
        """Worker 连接关闭时的清理回调"""
        session = self.worker_sessions.pop(group_id, None)
        if session is None:
            return
        # 从 handler_to_worker 中移除该插件注册的 handlers（仅当来源仍为此插件时）
        for handler in session.handlers:
            source_plugin = self._handler_sources.get(handler.id)
            if source_plugin == _plugin_name_from_handler_id(handler.id) or (
                source_plugin == group_id
            ):
                self.handler_to_worker.pop(handler.id, None)
                self._handler_sources.pop(handler.id, None)
        for descriptor in session.provided_capabilities:
            source_plugin = self._capability_sources.get(descriptor.name)
            capability_plugin = session.capability_sources.get(descriptor.name)
            if source_plugin == capability_plugin or (
                capability_plugin is None
                and (
                    source_plugin == group_id or source_plugin in session.loaded_plugins
                )
            ):
                self.capability_to_worker.pop(descriptor.name, None)
                self._capability_sources.pop(descriptor.name, None)
                self.capability_router.unregister(descriptor.name)
        session_loaded_plugins = getattr(session, "loaded_plugins", None)
        if not isinstance(session_loaded_plugins, list):
            session_loaded_plugins = [group_id]
        for plugin_name in session_loaded_plugins:
            if plugin_name in self.loaded_plugins:
                self.loaded_plugins.remove(plugin_name)
            self.plugin_to_worker_session.pop(plugin_name, None)
            self.capability_router.set_plugin_enabled(plugin_name, False)
            self.capability_router.remove_http_apis_for_plugin(plugin_name)
        stale_requests = [
            request_id
            for request_id, active_session in self.active_requests.items()
            if active_session is session
        ]
        for request_id in stale_requests:
            self.active_requests.pop(request_id, None)
        logger.warning("worker 组 {} 连接已关闭，已清理相关 handlers", group_id)

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
