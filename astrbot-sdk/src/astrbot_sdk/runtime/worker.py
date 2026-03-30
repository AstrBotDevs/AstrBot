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

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .._internal.decorator_lifecycle import run_lifecycle_with_decorators
from .._internal.invocation_context import caller_plugin_scope
from .._internal.sdk_logger import logger
from ..context import Context as RuntimeContext
from ..errors import AstrBotError
from ..protocol.messages import PeerInfo
from .handler_dispatcher import CapabilityDispatcher, HandlerDispatcher
from .loader import (
    LoadedPlugin,
    PluginDiscoveryIssue,
    PluginSpec,
    load_plugin,
    load_plugin_config,
    load_plugin_spec,
)
from .peer import Peer

__all__ = [
    "GroupPluginRuntimeState",
    "GroupWorkerRuntime",
    "PluginWorkerRuntime",
    "_load_plugin_specs",
    "_load_group_plugin_specs",
]

GLOBAL_MCP_RISK_ATTR = "__astrbot_acknowledge_global_mcp_risk__"


@dataclass(slots=True)
class GroupPluginRuntimeState:
    plugin: PluginSpec
    loaded_plugin: LoadedPlugin
    lifecycle_context: RuntimeContext


def _plugin_acknowledges_global_mcp_risk(instances: list[Any]) -> bool:
    return any(
        bool(getattr(instance.__class__, GLOBAL_MCP_RISK_ATTR, False))
        for instance in instances
    )


def _metadata_plugin_instances(loaded_plugin: Any) -> list[Any]:
    """Return plugin instances for metadata-only inspection.

    Metadata serialization is also exercised by lightweight tests that stub
    ``loaded_plugin`` with only the fields relevant to the payload. Missing
    ``instances`` means the plugin cannot acknowledge the global MCP risk, but
    it should not break issue/metadata reporting.
    """
    instances = getattr(loaded_plugin, "instances", [])
    if isinstance(instances, list):
        return instances
    if isinstance(instances, tuple):
        return list(instances)
    return []


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


def _load_plugin_specs(plugin_dirs: list[Path]) -> list[PluginSpec]:
    if not plugin_dirs:
        raise RuntimeError("worker requires at least one plugin directory")
    return [load_plugin_spec(plugin_dir) for plugin_dir in plugin_dirs]


def _build_worker_registry_entry(
    plugin: PluginSpec,
    *,
    enabled: bool,
) -> dict[str, Any]:
    manifest = plugin.manifest_data
    return {
        "name": plugin.name,
        "display_name": str(manifest.get("display_name") or plugin.name),
        "description": str(manifest.get("desc") or manifest.get("description") or ""),
        "repo": str(manifest.get("repo") or ""),
        "author": str(manifest.get("author") or ""),
        "version": str(manifest.get("version") or "0.0.0"),
        "enabled": enabled,
        "config": load_plugin_config(plugin),
    }


async def run_plugin_lifecycle(
    instances: list[Any],
    method_name: str,
    context: RuntimeContext,
) -> None:
    """运行插件生命周期方法。"""
    for instance in instances:
        method = getattr(instance, method_name, None)
        with caller_plugin_scope(context.plugin_id):
            await run_lifecycle_with_decorators(
                instance=instance,
                hook=method if callable(method) else None,
                method_name=method_name,
                context=context,
            )


class GroupWorkerRuntime:
    def __init__(
        self,
        *,
        transport,
        group_metadata_path: Path | None = None,
        plugin_dirs: list[Path] | None = None,
        worker_id: str | None = None,
    ) -> None:
        if group_metadata_path is None and not plugin_dirs:
            raise ValueError("group_metadata_path or plugin_dirs is required")
        if group_metadata_path is not None and plugin_dirs:
            raise ValueError(
                "group_metadata_path and plugin_dirs are mutually exclusive"
            )
        self.group_metadata_path = (
            group_metadata_path.resolve() if group_metadata_path is not None else None
        )
        if self.group_metadata_path is not None:
            default_worker_id, plugins = _load_group_plugin_specs(
                self.group_metadata_path
            )
        else:
            assert plugin_dirs is not None
            plugins = _load_plugin_specs([path.resolve() for path in plugin_dirs])
            default_worker_id = plugins[0].name
        self.plugins = plugins
        self.worker_id = str(worker_id or default_worker_id)
        self.transport = transport
        self.peer = Peer(
            transport=self.transport,
            peer_info=PeerInfo(name=self.worker_id, role="plugin", version="s5r"),
        )
        self.skipped_plugins: dict[str, str] = {}
        self.issues: list[PluginDiscoveryIssue] = []
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
                self.issues.append(
                    PluginDiscoveryIssue(
                        severity="error",
                        phase="load",
                        plugin_id=plugin.name,
                        message="插件加载失败",
                        details=str(exc),
                    )
                )
                logger.exception(
                    "worker {} 中插件 {} 加载失败，启动时将跳过",
                    self.worker_id,
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
            plugin_id=self.worker_id,
            peer=self.peer,
            handlers=handlers,
        )
        self.capability_dispatcher = CapabilityDispatcher(
            plugin_id=self.worker_id,
            peer=self.peer,
            capabilities=capabilities,
            llm_tools=[
                tool
                for state in self._active_plugin_states
                for tool in state.loaded_plugin.llm_tools
            ],
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
                    self.issues.append(
                        PluginDiscoveryIssue(
                            severity="error",
                            phase="lifecycle",
                            plugin_id=state.plugin.name,
                            message="插件 on_start 失败",
                            details=str(exc),
                        )
                    )
                    logger.exception(
                        "worker {} 中插件 {} on_start 失败，启动时将跳过",
                        self.worker_id,
                        state.plugin.name,
                    )
                    continue
                active_states.append(state)
                started_states.append(state)

            self._active_plugin_states = active_states
            self._refresh_dispatchers()
            if not self._active_plugin_states:
                raise RuntimeError(f"worker {self.worker_id} has no active plugins")

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
                        "worker {} 在启动失败清理插件 {} on_stop 时发生异常",
                        self.worker_id,
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
                        "worker {} 停止插件 {} 时发生异常",
                        self.worker_id,
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
            "worker_id": self.worker_id,
            "plugins": [plugin.name for plugin in self.plugins],
            "loaded_plugins": [
                state.plugin.name for state in self._active_plugin_states
            ],
            "skipped_plugins": dict(self.skipped_plugins),
            "worker_registry": [
                _build_worker_registry_entry(
                    plugin,
                    enabled=plugin.name
                    in {state.plugin.name for state in self._active_plugin_states},
                )
                for plugin in self.plugins
            ],
            "capability_sources": {
                capability.descriptor.name: state.plugin.name
                for state in self._active_plugin_states
                for capability in state.loaded_plugin.capabilities
            },
            "issues": [issue.to_payload() for issue in self.issues],
            "llm_tools": [
                {
                    **tool.spec.to_payload(),
                    "plugin_id": state.plugin.name,
                }
                for state in self._active_plugin_states
                for tool in state.loaded_plugin.llm_tools
            ],
            "agents": [
                {
                    **agent.spec.to_payload(),
                    "plugin_id": state.plugin.name,
                }
                for state in self._active_plugin_states
                for agent in state.loaded_plugin.agents
            ],
            "acknowledge_global_mcp_risk": any(
                _plugin_acknowledges_global_mcp_risk(
                    _metadata_plugin_instances(state.loaded_plugin)
                )
                for state in self._active_plugin_states
            ),
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
    def __init__(
        self,
        *,
        plugin_dir: Path,
        transport,
        worker_id: str | None = None,
    ) -> None:
        self.plugin = load_plugin_spec(plugin_dir)
        self.worker_id = str(worker_id or self.plugin.name)
        self.transport = transport
        self.loaded_plugin = load_plugin(self.plugin)
        self.peer = Peer(
            transport=self.transport,
            peer_info=PeerInfo(name=self.worker_id, role="plugin", version="s5r"),
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
            llm_tools=self.loaded_plugin.llm_tools,
        )
        self._lifecycle_context = RuntimeContext(
            peer=self.peer, plugin_id=self.plugin.name
        )
        self.issues: list[PluginDiscoveryIssue] = []
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
                    "worker_id": self.worker_id,
                    "plugins": [self.plugin.name],
                    "loaded_plugins": [self.plugin.name],
                    "skipped_plugins": {},
                    "worker_registry": [
                        _build_worker_registry_entry(self.plugin, enabled=True)
                    ],
                    "issues": [issue.to_payload() for issue in self.issues],
                    "capability_sources": {
                        item.descriptor.name: self.plugin.name
                        for item in self.loaded_plugin.capabilities
                    },
                    "llm_tools": [
                        {
                            **item.spec.to_payload(),
                            "plugin_id": self.plugin.name,
                        }
                        for item in self.loaded_plugin.llm_tools
                    ],
                    "agents": [
                        {
                            **item.spec.to_payload(),
                            "plugin_id": self.plugin.name,
                        }
                        for item in self.loaded_plugin.agents
                    ],
                    "acknowledge_global_mcp_risk": _plugin_acknowledges_global_mcp_risk(
                        _metadata_plugin_instances(self.loaded_plugin)
                    ),
                },
            )
        except Exception:
            if lifecycle_started:
                logger.exception(
                    "插件 {} 在向 supervisor 上报 initialize 时失败",
                    self.plugin.name,
                )
            else:
                logger.exception(
                    "插件 {} 在 on_start / 装饰器初始化阶段失败；"
                    "supervisor 可能随后只看到初始化超时，请优先检查这条异常",
                    self.plugin.name,
                )
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
