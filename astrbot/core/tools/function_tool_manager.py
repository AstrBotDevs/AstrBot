"""Runtime-owned function-tool and MCP catalog implementation."""

import asyncio
import copy
import inspect
import json
import os
import threading
import urllib.parse
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol

import aiohttp

from astrbot import logger
from astrbot.core.agent.mcp_client import (
    MCPAuthorizationCoordinator,
    MCPAuthStore,
    MCPClient,
    MCPInteractionCoordinator,
    MCPTool,
    MCPToolNameAllocationError,
    MCPToolNameAllocator,
)
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.auth.service import AuthorizationService
from astrbot.core.tools.registry import (
    BUILTIN_TOOL_DECLARATION_ATTR,
    BUILTIN_TOOL_MODULES,
    DEFAULT_BUILTIN_TOOL_CONFIG_RULES,
    BuiltinToolConfigRule,
    BuiltinToolDeclaration,
)
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.utils.error_redaction import safe_error
from astrbot.core.utils.shared_preferences import SharedPreferences

DEFAULT_MCP_CONFIG = {"mcpServers": {}}

DEFAULT_MCP_INIT_TIMEOUT_SECONDS = 180.0
DEFAULT_ENABLE_MCP_TIMEOUT_SECONDS = 180.0
MCP_INIT_TIMEOUT_ENV = "ASTRBOT_MCP_INIT_TIMEOUT"
ENABLE_MCP_TIMEOUT_ENV = "ASTRBOT_MCP_ENABLE_TIMEOUT"
MAX_MCP_TIMEOUT_SECONDS = 300.0


class PluginLookup(Protocol):
    """The narrow plugin capability required for tool activation."""

    def get_by_module(self, module_path: str | None) -> Any: ...


class MCPInitError(Exception):
    """Base exception for MCP initialization failures."""


class MCPInitTimeoutError(asyncio.TimeoutError, MCPInitError):
    """Raised when MCP client initialization exceeds the configured timeout."""


class MCPAllServicesFailedError(MCPInitError):
    """Raised when all configured MCP services fail to initialize."""


class MCPShutdownTimeoutError(asyncio.TimeoutError):
    """Raised when MCP shutdown exceeds the configured timeout."""

    def __init__(self, names: list[str], timeout: float) -> None:
        self.names = names
        self.timeout = timeout
        message = f"MCP 服务关闭超时（{timeout:g} 秒）：{', '.join(names)}"
        super().__init__(message)


@dataclass
class MCPInitSummary:
    total: int
    success: int
    failed: list[str]


@dataclass
class _MCPServerRuntime:
    name: str
    client: MCPClient
    shutdown_event: asyncio.Event
    lifecycle_task: asyncio.Task[None]


def _resolve_timeout(
    timeout: float | int | str | None = None,
    *,
    env_name: str = MCP_INIT_TIMEOUT_ENV,
    default: float = DEFAULT_MCP_INIT_TIMEOUT_SECONDS,
) -> float:
    """Resolve timeout with precedence: explicit argument > env value > default."""
    source = f"环境变量 {env_name}"
    if timeout is None:
        timeout = os.getenv(env_name, str(default))
    else:
        source = "显式参数 timeout"

    try:
        timeout_value = float(timeout)
    except TypeError, ValueError:
        logger.warning(
            f"超时配置（{source}）={timeout!r} 无效，使用默认值 {default:g} 秒。"
        )
        return default

    if timeout_value <= 0:
        logger.warning(
            f"超时配置（{source}）={timeout_value:g} 必须大于 0，使用默认值 {default:g} 秒。"
        )
        return default

    if timeout_value > MAX_MCP_TIMEOUT_SECONDS:
        logger.warning(
            f"超时配置（{source}）={timeout_value:g} 过大，已限制为最大值 "
            f"{MAX_MCP_TIMEOUT_SECONDS:g} 秒，以避免长时间等待。"
        )
        return MAX_MCP_TIMEOUT_SECONDS

    return timeout_value


SUPPORTED_TYPES = [
    "string",
    "number",
    "object",
    "array",
    "boolean",
]  # json schema 支持的数据类型

PY_TO_JSON_TYPE = {
    "int": "number",
    "float": "number",
    "bool": "boolean",
    "str": "string",
    "dict": "object",
    "list": "array",
    "tuple": "array",
    "set": "array",
}


class FunctionToolManager:
    def __init__(self) -> None:
        self.preferences: SharedPreferences | None = None
        self.authorization: AuthorizationService | None = None
        self._plugins: PluginLookup | None = None
        self.func_list: list[FunctionTool] = []
        """All tools include mcp tools and plugin tools, except astrbot builtin tools."""
        self.builtin_func_list: dict[type[FunctionTool], FunctionTool] = {}
        """All astrbot builtin tools, keyed by their class. Values are instantiated tool objects, created on demand."""
        self._builtin_tool_classes_by_name: dict[str, type[FunctionTool]] = {}
        self._builtin_tool_names_by_class: dict[type[FunctionTool], str] = {}
        self._builtin_tool_config_rules: dict[str, BuiltinToolConfigRule] = {}
        self._builtin_tools_loaded = False
        self._runtime_state: dict[str, object] = {}

        self._mcp_server_runtime: dict[str, _MCPServerRuntime] = {}
        """MCP runtime metadata, keyed by server name. Updated atomically on MCP lifecycle changes."""
        self._mcp_server_runtime_view = MappingProxyType(self._mcp_server_runtime)
        self._timeout_mismatch_warned = False
        self._timeout_warn_lock = threading.Lock()
        self._runtime_lock = asyncio.Lock()
        self._mcp_starting: set[str] = set()
        self._mcp_tool_name_allocator = MCPToolNameAllocator()
        # These coordinators are runtime-owned by this manager. They are never
        # process globals, so a shutdown clears user input and OAuth state for
        # exactly the runtime that created the MCP clients.
        self.mcp_interaction_coordinator = MCPInteractionCoordinator()
        self.mcp_authorization_coordinator = MCPAuthorizationCoordinator()
        self.mcp_auth_store = MCPAuthStore(
            Path(get_astrbot_data_path()) / "mcp_auth.json"
        )
        self._init_timeout_default = _resolve_timeout(
            timeout=None,
            env_name=MCP_INIT_TIMEOUT_ENV,
            default=DEFAULT_MCP_INIT_TIMEOUT_SECONDS,
        )
        self._enable_timeout_default = _resolve_timeout(
            timeout=None,
            env_name=ENABLE_MCP_TIMEOUT_ENV,
            default=DEFAULT_ENABLE_MCP_TIMEOUT_SECONDS,
        )
        self._warn_on_timeout_mismatch(
            self._init_timeout_default,
            self._enable_timeout_default,
        )

    def bind_preferences(self, preferences: SharedPreferences) -> None:
        """Bind runtime preferences after the tool registry has been imported."""
        self.preferences = preferences

    def bind_authorization(self, authorization: AuthorizationService) -> None:
        """Bind the runtime's single authorization entry point."""

        self.authorization = authorization

    def bind_plugin_lookup(self, plugins: PluginLookup) -> None:
        """Bind the runtime-owned plugin catalog used for activation checks."""
        self._plugins = plugins

    def _register_mcp_tools(self, name: str, mcp_client: MCPClient) -> list[MCPTool]:
        """Replace one server's tools using stable, unambiguous LLM names."""
        previous_active = {
            tool.mcp_tool_name: tool.active
            for tool in self.func_list
            if isinstance(tool, MCPTool) and tool.mcp_server_name == name
        }
        self.func_list = [
            tool
            for tool in self.func_list
            if not (isinstance(tool, MCPTool) and tool.mcp_server_name == name)
        ]
        registered: list[MCPTool] = []
        raw_names: set[str] = set()
        for mcp_tool in mcp_client.tools:
            original_name = getattr(mcp_tool, "name", None)
            if not isinstance(original_name, str) or not original_name:
                logger.error(
                    "Refusing to register an MCP tool from server %r with an empty name.",
                    name,
                )
                continue
            if original_name in raw_names:
                logger.error(
                    "Refusing duplicate MCP tool registration for server %r and tool %r.",
                    name,
                    original_name,
                )
                continue
            raw_names.add(original_name)
            try:
                llm_tool_name = self._mcp_tool_name_allocator.allocate(
                    name,
                    original_name,
                )
                function_tool = MCPTool(
                    mcp_tool=mcp_tool,
                    mcp_client=mcp_client,
                    mcp_server_name=name,
                    llm_tool_name=llm_tool_name,
                )
                function_tool.active = previous_active.get(original_name, True)
            except MCPToolNameAllocationError as exc:
                logger.error(
                    "Refusing to register MCP tool for server %r: %s", name, exc
                )
                continue
            registered.append(function_tool)

        self.func_list.extend(registered)
        return registered

    async def _on_mcp_catalog_changed(self, name: str, catalog: str) -> None:
        """Install a complete tool snapshot after an SDK subscription cue."""
        if catalog == "tools":
            runtime = self._mcp_server_runtime.get(name)
            if runtime is not None:
                self._register_mcp_tools(name, runtime.client)

    def get_or_create_runtime_state(
        self,
        key: str,
        factory: Callable[[], object],
    ) -> object:
        """Return state shared by builtin tools within this manager only."""
        state = self._runtime_state.get(key)
        if state is None:
            state = factory()
            self._runtime_state[key] = state
        return state

    @property
    def mcp_server_runtime_view(self) -> Mapping[str, _MCPServerRuntime]:
        """Read-only view of MCP runtime metadata for external callers."""
        return self._mcp_server_runtime_view

    def empty(self) -> bool:
        return len(self.func_list) == 0

    def spec_to_func(
        self,
        name: str,
        func_args: list[dict],
        desc: str,
        handler: Callable[..., Awaitable[Any] | AsyncGenerator[Any]],
        *,
        required_actions: tuple[str, ...] = (),
    ) -> FunctionTool:
        params = {
            "type": "object",  # hard-coded here
            "properties": {},
        }
        for param in func_args:
            p = copy.deepcopy(param)
            p.pop("name", None)
            params["properties"][param["name"]] = p
        return FunctionTool(
            name=name,
            parameters=params,
            description=desc,
            handler=handler,
            required_actions=required_actions,
        )

    def add_tool(
        self,
        name: str,
        func_args: list,
        desc: str,
        handler: Callable[..., Awaitable[Any] | AsyncGenerator[Any]],
    ) -> None:
        """添加函数调用工具

        @param name: 函数名
        @param func_args: 函数参数列表，格式为 [{"type": "string", "name": "arg_name", "description": "arg_description"}, ...]
        @param desc: 函数描述
        @param func_obj: 处理函数
        """
        # check if the tool has been added before
        self.remove_tool(name)

        self.func_list.append(
            self.spec_to_func(
                name=name,
                func_args=func_args,
                desc=desc,
                handler=handler,
            ),
        )
        logger.info(f"Added llm tool: {name}")

    def remove_tool(self, name: str) -> None:
        """删除一个函数调用工具。"""
        for i, f in enumerate(self.func_list):
            if f.name == name:
                self.func_list.pop(i)
                break

    def get_tool(self, name) -> FunctionTool | None:
        # 优先返回已激活的工具（后加载的覆盖前面的，与 ToolSet.add_tool 保持一致）
        # 使用 getattr(..., True) 与 ToolSet.add_tool 保持一致：没有 active 属性的工具视为已激活
        for f in reversed(self.func_list):
            if f.name == name and getattr(f, "active", True):
                return f
        # 退化则拿最后一个同名工具
        for f in reversed(self.func_list):
            if f.name == name:
                return f
        if isinstance(name, str):
            try:
                builtin_tool = self.get_builtin_tool(name)
            except KeyError:
                return None
            if getattr(builtin_tool, "active", True):
                return builtin_tool
            return builtin_tool
        return None

    def get_builtin_tool(
        self,
        tool: str | type[FunctionTool],
    ) -> FunctionTool:
        self._ensure_builtin_tools_loaded()

        if isinstance(tool, str):
            tool_cls = self._builtin_tool_classes_by_name.get(tool)
            if tool_cls is None:
                raise KeyError(f"Builtin tool {tool} is not registered.")
        elif isinstance(tool, type) and issubclass(tool, FunctionTool):
            tool_cls = tool
            if tool_cls not in self._builtin_tool_names_by_class:
                raise KeyError(
                    f"Builtin tool class {tool_cls.__module__}.{tool_cls.__name__} is not registered.",
                )
        else:
            raise TypeError("tool must be a builtin tool name or FunctionTool class.")

        cached_tool = self.builtin_func_list.get(tool_cls)
        if cached_tool is not None:
            return cached_tool

        builtin_tool = tool_cls()  # type: ignore
        declaration = getattr(tool_cls, BUILTIN_TOOL_DECLARATION_ATTR)
        builtin_tool.required_actions = declaration.required_actions
        self.builtin_func_list[tool_cls] = builtin_tool
        return builtin_tool

    def iter_builtin_tools(self) -> list[FunctionTool]:
        self._ensure_builtin_tools_loaded()
        return [
            self.get_builtin_tool(tool_cls)
            for tool_cls in self._builtin_tool_classes_by_name.values()
        ]

    def is_builtin_tool(self, name: str) -> bool:
        self._ensure_builtin_tools_loaded()
        return name in self._builtin_tool_classes_by_name

    def get_builtin_tool_config_statuses(
        self,
        tool_name: str,
        config_entries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Evaluate one builtin tool's declared configuration requirements."""
        self._ensure_builtin_tools_loaded()
        rule = self._builtin_tool_config_rules.get(tool_name)
        if rule is None:
            return []

        statuses: list[dict[str, Any]] = []
        for entry in config_entries:
            config = entry.get("config")
            if not isinstance(config, dict):
                continue

            conditions = rule.evaluate(config)
            enabled = bool(conditions) and all(
                bool(condition.get("matched")) for condition in conditions
            )
            statuses.append(
                {
                    "conf_id": entry.get("conf_id"),
                    "conf_name": entry.get("conf_name"),
                    "enabled": enabled,
                    "matched_conditions": [
                        condition
                        for condition in conditions
                        if condition.get("matched")
                    ],
                    "failed_conditions": [
                        condition
                        for condition in conditions
                        if not condition.get("matched")
                    ],
                }
            )
        return statuses

    def _ensure_builtin_tools_loaded(self) -> None:
        """Discover builtin declarations into this runtime-owned manager.

        Modules may already be present in ``sys.modules`` after another runtime
        has started.  Discovery therefore scans class-local descriptors after
        every import rather than relying on decorator execution.
        """
        if self._builtin_tools_loaded:
            return

        for module_name in BUILTIN_TOOL_MODULES:
            module = import_module(module_name)
            for candidate in vars(module).values():
                if not inspect.isclass(candidate) or not issubclass(
                    candidate, FunctionTool
                ):
                    continue
                self._register_builtin_tool_class(candidate)
        self._builtin_tools_loaded = True

    def _register_builtin_tool_class(self, tool_cls: type[FunctionTool]) -> None:
        declaration = vars(tool_cls).get(BUILTIN_TOOL_DECLARATION_ATTR)
        if not isinstance(declaration, BuiltinToolDeclaration):
            return

        existing = self._builtin_tool_classes_by_name.get(declaration.name)
        if existing is not None and existing is not tool_cls:
            raise ValueError(
                f"Builtin tool name conflict detected: {declaration.name} is already registered by "
                f"{existing.__module__}.{existing.__name__}.",
            )

        self._builtin_tool_classes_by_name[declaration.name] = tool_cls
        self._builtin_tool_names_by_class[tool_cls] = declaration.name
        rule = declaration.config_rule or DEFAULT_BUILTIN_TOOL_CONFIG_RULES.get(
            declaration.name,
        )
        if rule is not None:
            self._builtin_tool_config_rules[declaration.name] = rule

    def get_full_tool_set(self) -> ToolSet:
        """获取完整工具集

        使用 ToolSet.add_tool 进行填充。对于同名工具，去重规则为：
        - 优先保留 active=True 的工具；
        - 当 active 状态相同时，后加载的工具会覆盖前面的工具。

        因此，后加载的 inactive 工具不会覆盖已激活的工具；
        同时，MCP 工具在需要时仍可覆盖被禁用的内置工具。

        Every tool is checked by ``FunctionToolExecutor`` immediately before
        execution.
        """
        tool_set = ToolSet()
        for tool in self.func_list:
            tool_set.add_tool(tool)
        return tool_set

    @staticmethod
    def _log_safe_mcp_debug_config(cfg: dict) -> None:
        # 仅记录脱敏后的摘要，避免泄露 command/args/url 中的敏感信息
        if "command" in cfg:
            cmd = cfg["command"]
            executable = str(cmd[0] if isinstance(cmd, (list, tuple)) and cmd else cmd)
            args_val = cfg.get("args", [])
            args_count = (
                len(args_val)
                if isinstance(args_val, (list, tuple))
                else (0 if args_val is None else 1)
            )
            logger.debug(f"  命令可执行文件: {executable}, 参数数量: {args_count}")
            return

        if "url" in cfg:
            parsed = urllib.parse.urlparse(str(cfg["url"]))
            host = parsed.hostname or ""
            scheme = parsed.scheme or "unknown"
            try:
                port = f":{parsed.port}" if parsed.port else ""
            except ValueError:
                port = ""
            logger.debug(f"  主机: {scheme}://{host}{port}")

    async def init_mcp_clients(
        self, raise_on_all_failed: bool = False
    ) -> MCPInitSummary:
        """从项目根目录读取 mcp_server.json 文件，初始化 MCP 服务列表。文件格式如下：
        ```
        {
            "mcpServers": {
                "weather": {
                    "command": "uv",
                    "args": [
                        "--directory",
                        "/ABSOLUTE/PATH/TO/PARENT/FOLDER/weather",
                        "run",
                        "weather.py"
                    ]
                }
            }
            ...
        }
        ```

        Timeout behavior:
        - 初始化超时使用环境变量 ASTRBOT_MCP_INIT_TIMEOUT 或默认值。
        - 动态启用超时使用 ASTRBOT_MCP_ENABLE_TIMEOUT（独立于初始化超时）。
        """
        data_dir = get_astrbot_data_path()

        mcp_json_file = os.path.join(data_dir, "mcp_server.json")
        if not os.path.exists(mcp_json_file):
            # 配置文件不存在错误处理
            with open(mcp_json_file, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_MCP_CONFIG, f, ensure_ascii=False, indent=4)
            logger.info(f"未找到 MCP 服务配置文件，已创建默认配置文件 {mcp_json_file}")
            return MCPInitSummary(total=0, success=0, failed=[])

        with open(mcp_json_file, encoding="utf-8") as f:
            mcp_server_json_obj: dict[str, dict] = json.load(f)["mcpServers"]

        init_timeout = self._init_timeout_default
        timeout_display = f"{init_timeout:g}"

        active_configs: list[tuple[str, dict, asyncio.Event]] = []
        for name, cfg in mcp_server_json_obj.items():
            if cfg.get("active", True):
                shutdown_event = asyncio.Event()
                active_configs.append((name, cfg, shutdown_event))

        if not active_configs:
            return MCPInitSummary(total=0, success=0, failed=[])

        logger.info(f"等待 {len(active_configs)} 个 MCP 服务初始化...")

        init_tasks = [
            asyncio.create_task(
                self._start_mcp_server(
                    name=name,
                    cfg=cfg,
                    shutdown_event=shutdown_event,
                    timeout_seconds=init_timeout,
                ),
                name=f"mcp-init:{name}",
            )
            for (name, cfg, shutdown_event) in active_configs
        ]
        results = await asyncio.gather(*init_tasks, return_exceptions=True)

        success_count = 0
        failed_services: list[str] = []

        for (name, cfg, _), result in zip(active_configs, results, strict=False):
            if isinstance(result, Exception):
                if isinstance(result, MCPInitTimeoutError):
                    logger.error(
                        f"Connected to MCP server {name} timeout ({timeout_display} seconds)"
                    )
                else:
                    logger.error(f"Failed to initialize MCP server {name}: {result}")
                self._log_safe_mcp_debug_config(cfg)
                failed_services.append(name)
                async with self._runtime_lock:
                    self._mcp_server_runtime.pop(name, None)
                continue

            success_count += 1

        if failed_services:
            logger.warning(
                f"The following MCP services failed to initialize: {', '.join(failed_services)}. "
                f"Please check the mcp_server.json file and server availability."
            )

        summary = MCPInitSummary(
            total=len(active_configs), success=success_count, failed=failed_services
        )
        logger.info(
            f"MCP services initialization completed: {summary.success}/{summary.total} successful, {len(summary.failed)} failed."
        )
        if summary.total > 0 and summary.success == 0:
            msg = "All MCP services failed to initialize, please check the mcp_server.json and server availability."
            if raise_on_all_failed:
                raise MCPAllServicesFailedError(msg)
            logger.error(msg)
        return summary

    async def _start_mcp_server(
        self,
        name: str,
        cfg: dict,
        *,
        shutdown_event: asyncio.Event | None = None,
        timeout_seconds: float,
    ) -> None:
        """Initialize MCP server with timeout and register task/event together.

        This method is idempotent. If the server is already running, the existing
        runtime is kept and the new config is ignored.
        """
        async with self._runtime_lock:
            if name in self._mcp_server_runtime or name in self._mcp_starting:
                logger.warning(
                    f"Connected to MCP server {name}, ignoring this startup request (timeout={timeout_seconds:g})."
                )
                self._log_safe_mcp_debug_config(cfg)
                return
            self._mcp_starting.add(name)

        if shutdown_event is None:
            shutdown_event = asyncio.Event()

        mcp_client = MCPClient(
            interaction_coordinator=self.mcp_interaction_coordinator,
            auth_store=self.mcp_auth_store,
            auth_coordinator=self.mcp_authorization_coordinator,
            on_catalog_changed=self._on_mcp_catalog_changed,
        )
        mcp_client.name = name

        connect_done = asyncio.Event()
        connect_error: BaseException | None = None

        async def connect_and_lifecycle() -> None:
            # Single task that handles connect, lifecycle, and cleanup.

            nonlocal connect_error
            try:
                await mcp_client.connect_to_server(cfg, name)
                # Connection, initial discovery and registration are one
                # operation. Any registration error must resolve connect_done
                # and remove the runtime instead of becoming a fake timeout.
                self._register_mcp_tools(name, mcp_client)
                logger.info(
                    "Connected to MCP server %s, Tools: %s",
                    name,
                    [tool.name for tool in mcp_client.tools],
                )
            except asyncio.CancelledError:
                # cleanup on cancellation
                try:
                    await mcp_client.cleanup()
                except Exception:
                    pass
                raise
            except Exception as e:
                connect_error = e
                try:
                    await mcp_client.cleanup()
                except Exception:
                    pass
                return
            finally:
                # This signal is set for success and every failure path.
                connect_done.set()

            try:
                await shutdown_event.wait()
                logger.info(f"Received shutdown signal for MCP client {name}")
            except asyncio.CancelledError:
                logger.debug(f"MCP client {name} task was cancelled")
                raise
            finally:
                await self._terminate_mcp_client(name)

        lifecycle_task = asyncio.create_task(
            connect_and_lifecycle(), name=f"mcp-client:{name}"
        )
        async with self._runtime_lock:
            self._mcp_server_runtime[name] = _MCPServerRuntime(
                name=name,
                client=mcp_client,
                shutdown_event=shutdown_event,
                lifecycle_task=lifecycle_task,
            )
            self._mcp_starting.discard(name)

        try:
            await asyncio.wait_for(connect_done.wait(), timeout=timeout_seconds)
        except (TimeoutError, asyncio.CancelledError) as e:
            lifecycle_task.cancel()
            await asyncio.gather(lifecycle_task, return_exceptions=True)
            async with self._runtime_lock:
                self._mcp_starting.discard(name)
                self._mcp_server_runtime.pop(name, None)
            if isinstance(e, asyncio.TimeoutError):
                raise MCPInitTimeoutError(
                    f"Connected to MCP server {name} timeout ({timeout_seconds:g} seconds)"
                ) from e
            raise

        if connect_error is not None:
            async with self._runtime_lock:
                self._mcp_starting.discard(name)
                self._mcp_server_runtime.pop(name, None)
            raise connect_error

    async def _shutdown_runtimes(
        self,
        runtimes: list[_MCPServerRuntime],
        timeout_seconds: float,
        *,
        strict: bool = True,
    ) -> list[str]:
        """Shutdown runtimes and wait for lifecycle tasks to complete."""
        lifecycle_tasks = [
            runtime.lifecycle_task
            for runtime in runtimes
            if not runtime.lifecycle_task.done()
        ]
        if not lifecycle_tasks:
            return []

        for runtime in runtimes:
            runtime.shutdown_event.set()

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*lifecycle_tasks, return_exceptions=True),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            pending_names = [
                runtime.name
                for runtime in runtimes
                if not runtime.lifecycle_task.done()
            ]
            for task in lifecycle_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*lifecycle_tasks, return_exceptions=True)
            if strict:
                raise MCPShutdownTimeoutError(pending_names, timeout_seconds)
            logger.warning(
                "MCP server shutdown timeout (%s seconds), the following servers were not fully closed: %s",
                f"{timeout_seconds:g}",
                ", ".join(pending_names),
            )
            return pending_names
        else:
            for result in results:
                if isinstance(result, asyncio.CancelledError):
                    raise result
                elif isinstance(result, Exception):
                    logger.error(
                        "MCP lifecycle task failed during shutdown.",
                        exc_info=(type(result), result, result.__traceback__),
                    )
        return []

    async def _cleanup_mcp_client_safely(
        self, mcp_client: MCPClient, name: str
    ) -> None:
        """安全清理单个 MCP 客户端，避免清理异常中断主流程。"""
        try:
            await mcp_client.cleanup()
        except Exception as cleanup_exc:  # noqa: BLE001 - only log here
            logger.error(
                f"Failed to cleanup MCP client resources {name}: {cleanup_exc}"
            )

    async def _terminate_mcp_client(self, name: str) -> None:
        """关闭并清理MCP客户端"""
        async with self._runtime_lock:
            runtime = self._mcp_server_runtime.get(name)
        if runtime:
            client = runtime.client
            try:
                await self._cleanup_mcp_client_safely(client, name)
            finally:
                # Manager state must not stay stale even when cancellation is
                # propagated from cleanup.
                self.func_list = [
                    f
                    for f in self.func_list
                    if not (isinstance(f, MCPTool) and f.mcp_server_name == name)
                ]
                async with self._runtime_lock:
                    self._mcp_server_runtime.pop(name, None)
                    self._mcp_starting.discard(name)
            logger.info(f"Disconnected from MCP server {name}")
            return

        # Runtime missing but stale tools may still exist after failed flows.
        self.func_list = [
            f
            for f in self.func_list
            if not (isinstance(f, MCPTool) and f.mcp_server_name == name)
        ]
        async with self._runtime_lock:
            self._mcp_starting.discard(name)

    @staticmethod
    async def test_mcp_server_connection(config: dict) -> list[str]:
        mcp_client = MCPClient()
        try:
            logger.debug(f"testing MCP server connection with config: {config}")
            # A test connection is short-lived.  The initial catalog is already
            # fetched by connect_to_server(); opening a subscription here can
            # race the cleanup and some servers only allow one subscription.
            await mcp_client.connect_to_server(config, "test", watch_catalog=False)
            tool_names = [tool.name for tool in mcp_client.tools]
        finally:
            logger.debug("Cleaning up MCP client after testing connection.")
            await mcp_client.cleanup()
        return tool_names

    async def enable_mcp_server(
        self,
        name: str,
        config: dict,
        shutdown_event: asyncio.Event | None = None,
        timeout_seconds: float | int | str | None = None,
        **legacy_kwargs: float | int | str | None,
    ) -> None:
        """Enable a new MCP server and initialize it.

        Args:
            name: The name of the MCP server.
            config: Configuration for the MCP server.
            shutdown_event: Event to signal when the MCP client should shut down.
            timeout_seconds: Timeout in seconds for initialization.
                Uses ASTRBOT_MCP_ENABLE_TIMEOUT by default (separate from init timeout).

        Raises:
            MCPInitTimeoutError: If initialization does not complete within timeout.
            Exception: If there is an error during initialization.
        """
        timeout_arg = timeout_seconds
        if "timeout" in legacy_kwargs:
            if timeout_arg is None:
                timeout_arg = legacy_kwargs.pop("timeout")
            else:
                legacy_kwargs.pop("timeout")
        if legacy_kwargs:
            unexpected = ", ".join(sorted(legacy_kwargs))
            raise TypeError(f"Unexpected keyword argument(s): {unexpected}")
        if timeout_arg is None:
            timeout_value = self._enable_timeout_default
        else:
            timeout_value = _resolve_timeout(
                timeout=timeout_arg,
                env_name=ENABLE_MCP_TIMEOUT_ENV,
                default=self._enable_timeout_default,
            )
        await self._start_mcp_server(
            name=name,
            cfg=config,
            shutdown_event=shutdown_event,
            timeout_seconds=timeout_value,
        )

    async def disable_mcp_server(
        self,
        name: str | None = None,
        timeout_seconds: float | int | str | None = 10,
        **legacy_kwargs: float | int | str | None,
    ) -> None:
        """Disable an MCP server by its name.

        Args:
            name (str): The name of the MCP server to disable. If None, ALL MCP servers will be disabled.
            timeout_seconds (int): Timeout.

        Raises:
            MCPShutdownTimeoutError: If shutdown does not complete within timeout.
                Only raised when disabling a specific server (name is not None).

        """
        timeout_arg = timeout_seconds
        if "timeout" in legacy_kwargs:
            if timeout_arg == 10:
                timeout_arg = legacy_kwargs.pop("timeout")
            else:
                legacy_kwargs.pop("timeout")
        if legacy_kwargs:
            unexpected = ", ".join(sorted(legacy_kwargs))
            raise TypeError(f"Unexpected keyword argument(s): {unexpected}")

        timeout_value = _resolve_timeout(
            timeout=timeout_arg,
            env_name=ENABLE_MCP_TIMEOUT_ENV,
            default=10,
        )

        if name:
            async with self._runtime_lock:
                runtime = self._mcp_server_runtime.get(name)
            if runtime is None:
                return

            await self._shutdown_runtimes([runtime], timeout_value, strict=True)
        else:
            async with self._runtime_lock:
                runtimes = list(self._mcp_server_runtime.values())
            await self._shutdown_runtimes(runtimes, timeout_value, strict=False)
            await self.mcp_interaction_coordinator.close()
            await self.mcp_authorization_coordinator.close()

    def _warn_on_timeout_mismatch(
        self,
        init_timeout: float,
        enable_timeout: float,
    ) -> None:
        if init_timeout == enable_timeout:
            return
        with self._timeout_warn_lock:
            if self._timeout_mismatch_warned:
                return
            logger.info(
                "检测到 MCP 初始化超时与动态启用超时配置不同："
                "初始化使用 %s 秒，动态启用使用 %s 秒。如需一致，请设置相同值。",
                f"{init_timeout:g}",
                f"{enable_timeout:g}",
            )
            self._timeout_mismatch_warned = True

    def openai_chat_completions_schema(self, omit_empty_parameter_field=False) -> list:
        """获得 OpenAI API 风格的**已经激活**的工具描述"""
        tools = [f for f in self.func_list if f.active]
        toolset = ToolSet(tools)
        return toolset.openai_chat_completions_schema(
            omit_empty_parameter_field=omit_empty_parameter_field,
        )

    def openai_responses_schema(self) -> list:
        """Return active tools in the OpenAI Responses format."""
        return ToolSet(
            [f for f in self.func_list if f.active]
        ).openai_responses_schema()

    def anthropic_schema(self) -> list:
        """获得 Anthropic API 风格的**已经激活**的工具描述"""
        tools = [f for f in self.func_list if f.active]
        toolset = ToolSet(tools)
        return toolset.anthropic_schema()

    def google_schema(self) -> dict:
        """获得 Google GenAI API 风格的**已经激活**的工具描述"""
        tools = [f for f in self.func_list if f.active]
        toolset = ToolSet(tools)
        return toolset.google_schema()

    async def deactivate_llm_tool(self, name: str) -> bool:
        """停用一个已经注册的函数调用工具。

        Returns:
            如果没找到，会返回 False

        """
        func_tool = self.get_tool(name)
        if func_tool is not None:
            func_tool.active = False

            if self.preferences is None:
                return False
            inactivated_llm_tools = await self.preferences.global_get(
                "inactivated_llm_tools", []
            )
            if name not in inactivated_llm_tools:
                inactivated_llm_tools.append(name)
                await self.preferences.global_put(
                    "inactivated_llm_tools", inactivated_llm_tools
                )

            return True
        return False

    async def activate_llm_tool(self, name: str) -> bool:
        func_tool = self.get_tool(name)
        if func_tool is not None:
            plugin = (
                self._plugins.get_by_module(func_tool.handler_module_path)
                if self._plugins is not None
                else None
            )
            if plugin is not None:
                if not plugin.activated:
                    raise ValueError(
                        f"此函数调用工具所属的插件 {plugin.name} 已被禁用，请先在管理面板启用再激活此工具。",
                    )

            func_tool.active = True

            if self.preferences is None:
                return False
            inactivated_llm_tools = await self.preferences.global_get(
                "inactivated_llm_tools", []
            )
            if name in inactivated_llm_tools:
                inactivated_llm_tools.remove(name)
                await self.preferences.global_put(
                    "inactivated_llm_tools", inactivated_llm_tools
                )

            return True
        return False

    @property
    def mcp_config_path(self):
        data_dir = get_astrbot_data_path()
        return os.path.join(data_dir, "mcp_server.json")

    def load_mcp_config(self):
        if not os.path.exists(self.mcp_config_path):
            # 配置文件不存在，创建默认配置
            os.makedirs(os.path.dirname(self.mcp_config_path), exist_ok=True)
            with open(self.mcp_config_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_MCP_CONFIG, f, ensure_ascii=False, indent=4)
            return DEFAULT_MCP_CONFIG

        try:
            with open(self.mcp_config_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载 MCP 配置失败: {e}")
            return DEFAULT_MCP_CONFIG

    def save_mcp_config(self, config: dict) -> bool:
        try:
            with open(self.mcp_config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            logger.error(f"保存 MCP 配置失败: {e}")
            return False

    async def sync_modelscope_mcp_servers(self, access_token: str) -> None:
        """从 ModelScope 平台同步 MCP 服务器配置"""
        base_url = "https://www.modelscope.cn/openapi/v1"
        url = f"{base_url}/mcp/servers/operational"
        headers = {
            "Authorization": f"Bearer {access_token.strip()}",
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        mcp_server_list = data.get("data", {}).get(
                            "mcp_server_list",
                            [],
                        )
                        local_mcp_config = copy.deepcopy(self.load_mcp_config())

                        mcp_servers = local_mcp_config.setdefault("mcpServers", {})
                        synced_servers: list[tuple[str, dict]] = []
                        unsupported_legacy = 0
                        for server in mcp_server_list:
                            server_name = server.get("name")
                            if not server_name:
                                continue
                            operational_urls = server.get("operational_urls", [])
                            if not operational_urls:
                                continue
                            url_info = next(
                                (
                                    item
                                    for item in operational_urls
                                    if isinstance(item, dict)
                                    and item.get("transport") == "streamable_http"
                                ),
                                None,
                            )
                            if url_info is None:
                                unsupported_legacy += 1
                                continue
                            server_url = url_info.get("url")
                            if not isinstance(server_url, str):
                                continue
                            server_config = {
                                "url": server_url,
                                "transport": "streamable_http",
                                "active": True,
                            }
                            try:
                                await self.test_mcp_server_connection(server_config)
                            except Exception as exc:
                                logger.warning(
                                    "Skipping ModelScope MCP server %s: %s",
                                    server_name,
                                    safe_error("", exc),
                                )
                                continue
                            mcp_servers[server_name] = server_config
                            synced_servers.append((server_name, server_config))

                        if synced_servers:
                            self.save_mcp_config(local_mcp_config)
                            tasks = []
                            for name, config in synced_servers:
                                tasks.append(
                                    self.enable_mcp_server(
                                        name=name,
                                        config=config,
                                    ),
                                )
                            await asyncio.gather(*tasks)
                            logger.info(
                                f"从 ModelScope 同步了 {len(synced_servers)} 个 MCP 服务器",
                            )
                        else:
                            if unsupported_legacy:
                                raise Exception(
                                    "ModelScope only returned legacy SSE endpoints, which this fork does not support."
                                )
                            logger.warning("没有找到可用的 ModelScope MCP 服务器")
                    else:
                        raise Exception(
                            f"ModelScope API 请求失败: HTTP {response.status}",
                        )

        except aiohttp.ClientError as e:
            raise Exception(f"网络连接错误: {e!s}")
        except Exception as e:
            raise Exception(f"同步 ModelScope MCP 服务器时发生错误: {e!s}")

    def __str__(self) -> str:
        return str(self.func_list)

    def __repr__(self) -> str:
        return str(self.func_list)
