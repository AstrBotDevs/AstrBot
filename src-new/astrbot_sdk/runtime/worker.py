"""Worker 端运行时：PluginWorkerRuntime 运行单个插件，GroupWorkerRuntime 在同一进程中运行多个插件。

核心类：
    GroupWorkerRuntime: 组 Worker 运行时
        - 在同一进程中加载并运行多个插件
        - 聚合所有插件的 handlers 和 capabilities
        - 统一处理 invoke 和 cancel 请求
        - 管理每个插件的生命周期回调

    PluginWorkerRuntime: 单插件 Worker 运行时
        - 加载单个插件
        - 通过 Peer 与 Supervisor 通信
        - 分发 handler 调用
        - 处理生命周期回调 (on_start, on_stop)

启动流程：
    Worker 启动:
        1. load_plugin_spec() 加载插件规范
        2. load_plugin() 加载插件组件
        3. 创建 Peer 并设置处理器
        4. 向 Supervisor 发送 initialize
        5. 等待 Supervisor 的 initialize_result
        6. 执行 on_start 生命周期回调
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from .._invocation_context import caller_plugin_scope
from ..context import Context as RuntimeContext
from ..errors import AstrBotError
from ..protocol.messages import PeerInfo
from .handler_dispatcher import CapabilityDispatcher, HandlerDispatcher
from .loader import (
    LoadedPlugin,
    PluginSpec,
    load_plugin,
    load_plugin_spec,
)
from .peer import Peer

__all__ = [
    "GroupPluginRuntimeState",
    "GroupWorkerRuntime",
    "PluginWorkerRuntime",
    "_load_group_plugin_specs",
]


@dataclass(slots=True)
class GroupPluginRuntimeState:
    plugin: PluginSpec
    loaded_plugin: LoadedPlugin
    lifecycle_context: RuntimeContext


def _load_group_plugin_specs(group_metadata_path: Path) -> tuple[str, list[PluginSpec]]:
    try:
        payload = json.loads(group_metadata_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(
            f"failed to read worker group metadata: {group_metadata_path}"
        ) from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid worker group metadata: {group_metadata_path}")

    entries = payload.get("plugin_entries")
    if not isinstance(entries, list) or not entries:
        raise RuntimeError(
            f"worker group metadata missing plugin_entries: {group_metadata_path}"
        )

    plugins: list[PluginSpec] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise RuntimeError(
                f"worker group metadata contains invalid plugin entry: {group_metadata_path}"
            )
        plugin_dir = entry.get("plugin_dir")
        if not isinstance(plugin_dir, str) or not plugin_dir:
            raise RuntimeError(
                f"worker group metadata contains invalid plugin_dir: {group_metadata_path}"
            )
        plugins.append(load_plugin_spec(Path(plugin_dir)))

    group_id = payload.get("group_id")
    if not isinstance(group_id, str) or not group_id:
        group_id = group_metadata_path.stem
    return group_id, plugins


async def run_plugin_lifecycle(
    instances: list[Any],
    method_name: str,
    context: RuntimeContext,
) -> None:
    """运行插件生命周期方法。"""
    for instance in instances:
        method = getattr(instance, method_name, None)
        if method is None:
            continue
        with caller_plugin_scope(context.plugin_id):
            result = method(context)
            if inspect.isawaitable(result):
                await result


class GroupWorkerRuntime:
    def __init__(self, *, group_metadata_path: Path, transport) -> None:
        self.group_metadata_path = group_metadata_path.resolve()
        self.group_id, self.plugins = _load_group_plugin_specs(self.group_metadata_path)
        self.transport = transport
        self.peer = Peer(
            transport=self.transport,
            peer_info=PeerInfo(name=self.group_id, role="plugin", version="v4"),
        )
        self.skipped_plugins: dict[str, str] = {}
        self._plugin_states: list[GroupPluginRuntimeState] = []
        self._active_plugin_states: list[GroupPluginRuntimeState] = []
        self._load_plugins()
        self._refresh_dispatchers()
        self.peer.set_invoke_handler(self._handle_invoke)
        self.peer.set_cancel_handler(self._handle_cancel)

    def _load_plugins(self) -> None:
        for plugin in self.plugins:
            try:
                loaded_plugin = load_plugin(plugin)
            except Exception as exc:
                self.skipped_plugins[plugin.name] = str(exc)
                logger.exception(
                    "组 {} 中插件 {} 加载失败，启动时将跳过",
                    self.group_id,
                    plugin.name,
                )
                continue

            lifecycle_context = RuntimeContext(peer=self.peer, plugin_id=plugin.name)
            self._plugin_states.append(
                GroupPluginRuntimeState(
                    plugin=plugin,
                    loaded_plugin=loaded_plugin,
                    lifecycle_context=lifecycle_context,
                )
            )
        self._active_plugin_states = list(self._plugin_states)

    def _refresh_dispatchers(self) -> None:
        handlers = [
            handler
            for state in self._active_plugin_states
            for handler in state.loaded_plugin.handlers
        ]
        capabilities = [
            capability
            for state in self._active_plugin_states
            for capability in state.loaded_plugin.capabilities
        ]
        self.dispatcher = HandlerDispatcher(
            plugin_id=self.group_id,
            peer=self.peer,
            handlers=handlers,
        )
        self.capability_dispatcher = CapabilityDispatcher(
            plugin_id=self.group_id,
            peer=self.peer,
            capabilities=capabilities,
        )

    async def start(self) -> None:
        await self.peer.start()
        started_states: list[GroupPluginRuntimeState] = []
        try:
            active_states: list[GroupPluginRuntimeState] = []
            for state in self._plugin_states:
                try:
                    await self._run_lifecycle(state, "on_start")
                except Exception as exc:
                    self.skipped_plugins[state.plugin.name] = str(exc)
                    logger.exception(
                        "组 {} 中插件 {} on_start 失败，启动时将跳过",
                        self.group_id,
                        state.plugin.name,
                    )
                    continue
                active_states.append(state)
                started_states.append(state)

            self._active_plugin_states = active_states
            self._refresh_dispatchers()
            if not self._active_plugin_states:
                raise RuntimeError(
                    f"worker group {self.group_id} has no active plugins"
                )

            await self.peer.initialize(
                [
                    handler.descriptor
                    for state in self._active_plugin_states
                    for handler in state.loaded_plugin.handlers
                ],
                provided_capabilities=[
                    capability.descriptor
                    for state in self._active_plugin_states
                    for capability in state.loaded_plugin.capabilities
                ],
                metadata=self._initialize_metadata(),
            )
        except Exception:
            for state in reversed(started_states):
                try:
                    await self._run_lifecycle(state, "on_stop")
                except Exception:
                    logger.exception(
                        "组 {} 在启动失败清理插件 {} on_stop 时发生异常",
                        self.group_id,
                        state.plugin.name,
                    )
            await self.peer.stop()
            raise

    async def stop(self) -> None:
        first_error: Exception | None = None
        try:
            for state in reversed(self._active_plugin_states):
                try:
                    await self._run_lifecycle(state, "on_stop")
                except Exception as exc:
                    if first_error is None:
                        first_error = exc
                    logger.exception(
                        "组 {} 停止插件 {} 时发生异常",
                        self.group_id,
                        state.plugin.name,
                    )
        finally:
            await self.peer.stop()
        if first_error is not None:
            raise first_error

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

    def _initialize_metadata(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "plugins": [plugin.name for plugin in self.plugins],
            "loaded_plugins": [
                state.plugin.name for state in self._active_plugin_states
            ],
            "skipped_plugins": dict(self.skipped_plugins),
            "capability_sources": {
                capability.descriptor.name: state.plugin.name
                for state in self._active_plugin_states
                for capability in state.loaded_plugin.capabilities
            },
        }

    async def _run_lifecycle(
        self,
        state: GroupPluginRuntimeState,
        method_name: str,
    ) -> None:
        await run_plugin_lifecycle(
            state.loaded_plugin.instances, method_name, state.lifecycle_context
        )


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
                metadata={
                    "plugin_id": self.plugin.name,
                    "plugins": [self.plugin.name],
                    "loaded_plugins": [self.plugin.name],
                    "skipped_plugins": {},
                    "capability_sources": {
                        item.descriptor.name: self.plugin.name
                        for item in self.loaded_plugin.capabilities
                    },
                },
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
        await run_plugin_lifecycle(
            self.loaded_plugin.instances, method_name, self._lifecycle_context
        )
