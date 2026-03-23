"""FunctionTool registry and manager for AstrBot.

This module provides the FunctionToolManager class that serves as the central
registry for all function tools (built-in, plugin, and MCP).
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import urllib.parse
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, ClassVar

import aiofiles
import anyio

from astrbot import logger
from astrbot.core import sp
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .base import FunctionTool, ToolSet

# Deferred imports to avoid circular dependency
_mcp_client_module = None
_mcp_tool_module = None


def _get_mcp_client():
    global _mcp_client_module
    if _mcp_client_module is None:
        from astrbot._internal.mcp import client as module
        _mcp_client_module = module
    return _mcp_client_module


def _get_mcp_tool():
    global _mcp_tool_module
    if _mcp_tool_module is None:
        from astrbot._internal.mcp import tool as module
        _mcp_tool_module = module
    return _mcp_tool_module


DEFAULT_MCP_CONFIG = {"mcpServers": {}}

DEFAULT_MCP_INIT_TIMEOUT_SECONDS = 180.0
DEFAULT_ENABLE_MCP_TIMEOUT_SECONDS = 180.0
MCP_INIT_TIMEOUT_ENV = "ASTRBOT_MCP_INIT_TIMEOUT"
ENABLE_MCP_TIMEOUT_ENV = "ASTRBOT_MCP_ENABLE_TIMEOUT"
MAX_MCP_TIMEOUT_SECONDS = 300.0


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
        message = f"MCP 服务关闭超时({timeout:g} 秒):{', '.join(names)}"
        super().__init__(message)


@dataclass
class MCPInitSummary:
    total: int
    success: int
    failed: list[str]


@dataclass
class _MCPServerRuntime:
    name: str
    client: Any  # MCPClient
    shutdown_event: asyncio.Event
    lifecycle_task: asyncio.Task[None]


class _MCPClientDictView(Mapping[str, Any]):
    """Read-only view of MCP clients derived from runtime state."""

    def __init__(self, runtime: dict[str, _MCPServerRuntime]) -> None:
        self._runtime = runtime

    def __getitem__(self, key: str) -> Any:
        return self._runtime[key].client

    def __iter__(self):
        return iter(self._runtime)

    def __len__(self) -> int:
        return len(self._runtime)


def _resolve_timeout(
    timeout: float | str | None = None,
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
    except (TypeError, ValueError):
        logger.warning(
            f"超时配置({source})={timeout!r} 无效,使用默认值 {default:g} 秒｡"
        )
        return default

    if timeout_value <= 0:
        logger.warning(
            f"超时配置({source})={timeout_value:g} 必须大于 0,使用默认值 {default:g} 秒｡"
        )
        return default

    if timeout_value > MAX_MCP_TIMEOUT_SECONDS:
        logger.warning(
            f"超时配置({source})={timeout_value:g} 过大,已限制为最大值 "
            f"{MAX_MCP_TIMEOUT_SECONDS:g} 秒,以避免长时间等待｡"
        )
        return MAX_MCP_TIMEOUT_SECONDS

    return timeout_value


SUPPORTED_TYPES = [
    "string",
    "number",
    "object",
    "array",
    "boolean",
]

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
    """Central registry for all function tools in AstrBot.

    This class manages:
    - Built-in tools (cron, KB query, send message, computer)
    - Plugin tools
    - MCP tools (from external MCP servers)

    Tools are stored in func_list and can be queried by name.
    MCP servers are tracked separately in _mcp_server_runtime.
    """

    def __init__(self) -> None:
        self.func_list: list[FunctionTool] = []
        self._mcp_server_runtime: dict[str, _MCPServerRuntime] = {}
        self._mcp_server_runtime_view = MappingProxyType(self._mcp_server_runtime)
        self._mcp_client_dict_view = _MCPClientDictView(self._mcp_server_runtime)
        self._timeout_mismatch_warned = False
        self._timeout_warn_lock = threading.Lock()
        self._runtime_lock = asyncio.Lock()
        self._mcp_starting: set[str] = set()
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

    @property
    def mcp_client_dict(self) -> Mapping[str, Any]:
        """Read-only view of MCP clients."""
        return self._mcp_client_dict_view

    @property
    def mcp_server_runtime_view(self) -> Mapping[str, _MCPServerRuntime]:
        """Read-only view of MCP runtime metadata."""
        return self._mcp_server_runtime_view

    @property
    def mcp_server_runtime(self) -> Mapping[str, _MCPServerRuntime]:
        """Backward-compatible read-only view (deprecated)."""
        return self._mcp_server_runtime_view

    def empty(self) -> bool:
        return len(self.func_list) == 0

    def spec_to_func(
        self,
        name: str,
        func_args: list[dict],
        desc: str,
        handler: Callable[..., Awaitable[Any] | AsyncGenerator[Any]],
    ) -> FunctionTool:
        params = {
            "type": "object",
            "properties": {},
        }
        for param in func_args:
            p = param.copy()
            p.pop("name", None)
            params["properties"][param["name"]] = p
        return FunctionTool(
            name=name,
            parameters=params,
            description=desc,
            handler=handler,
        )

    def add_func(
        self,
        name: str,
        func_args: list,
        desc: str,
        handler: Callable[..., Awaitable[Any] | AsyncGenerator[Any]],
    ) -> None:
        """Add a function tool."""
        self.remove_func(name)
        self.func_list.append(
            self.spec_to_func(
                name=name,
                func_args=func_args,
                desc=desc,
                handler=handler,
            ),
        )
        logger.info(f"添加函数调用工具: {name}")

    def remove_func(self, name: str) -> None:
        """Remove a function tool by name."""
        for i, f in enumerate(self.func_list):
            if f.name == name:
                self.func_list.pop(i)
                break

    def get_func(self, name: str) -> FunctionTool | None:
        """Get a function tool by name.

        Prefers active tools, falls back to last registered.
        """
        for f in reversed(self.func_list):
            if f.name == name and getattr(f, "active", True):
                return f
        for f in reversed(self.func_list):
            if f.name == name:
                return f
        return None

    def get_full_tool_set(self) -> ToolSet:
        """Get all tools as a ToolSet."""
        tool_set = ToolSet()
        for tool in self.func_list:
            tool_set.add_tool(tool)
        return tool_set

    @staticmethod
    def _log_safe_mcp_debug_config(cfg: dict) -> None:
        """Log sanitized MCP config for debugging."""
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
        """Initialize MCP clients from mcp_server.json config."""
        data_dir = get_astrbot_data_path()

        mcp_json_file = os.path.join(data_dir, "mcp_server.json")
        mcp_json_path = anyio.Path(mcp_json_file)
        if not await mcp_json_path.exists():
            async with aiofiles.open(mcp_json_file, "w", encoding="utf-8") as f:
                await f.write(
                    json.dumps(DEFAULT_MCP_CONFIG, ensure_ascii=False, indent=4)
                )
            logger.info(f"未找到 MCP 服务配置文件,已创建默认配置文件 {mcp_json_file}")
            return MCPInitSummary(total=0, success=0, failed=[])

        async with aiofiles.open(mcp_json_file, encoding="utf-8") as f:
            mcp_server_json_obj: dict[str, dict] = json.loads(await f.read())[
                "mcpServers"
            ]

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
                    init_timeout=init_timeout,
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
        init_timeout: float,
    ) -> None:
        """Start an MCP server with timeout."""
        async with self._runtime_lock:
            if name in self._mcp_server_runtime or name in self._mcp_starting:
                logger.warning(
                    f"Connected to MCP server {name}, ignoring this startup request (timeout={init_timeout:g})."
                )
                self._log_safe_mcp_debug_config(cfg)
                return
            self._mcp_starting.add(name)

        if shutdown_event is None:
            shutdown_event = asyncio.Event()

        mcp_client: Any = None
        try:
            mcp_client = await asyncio.wait_for(
                self._init_mcp_client(name, cfg),
                timeout=init_timeout,
            )
        except asyncio.TimeoutError as exc:
            raise MCPInitTimeoutError(
                f"Connected to MCP server {name} timeout ({init_timeout:g} seconds)"
            ) from exc
        except Exception:
            logger.error(f"Failed to initialize MCP client {name}", exc_info=True)
            raise
        finally:
            if mcp_client is None:
                async with self._runtime_lock:
                    self._mcp_starting.discard(name)

        async def lifecycle() -> None:
            try:
                await shutdown_event.wait()
                logger.info(f"Received shutdown signal for MCP client {name}")
            except asyncio.CancelledError:
                logger.debug(f"MCP client {name} task was cancelled")
                raise
            finally:
                await self._terminate_mcp_client(name)

        lifecycle_task = asyncio.create_task(lifecycle(), name=f"mcp-client:{name}")
        async with self._runtime_lock:
            self._mcp_server_runtime[name] = _MCPServerRuntime(
                name=name,
                client=mcp_client,
                shutdown_event=shutdown_event,
                lifecycle_task=lifecycle_task,
            )
            self._mcp_starting.discard(name)

    async def _shutdown_runtimes(
        self,
        runtimes: list[_MCPServerRuntime],
        shutdown_timeout: float,
        *,
        strict: bool = True,
    ) -> list[str]:
        """Shutdown runtimes and wait for lifecycle tasks."""
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
                timeout=shutdown_timeout,
            )
        except asyncio.TimeoutError:
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
                raise MCPShutdownTimeoutError(pending_names, shutdown_timeout)
            logger.warning(
                "MCP server shutdown timeout (%s seconds), the following servers were not fully closed: %s",
                f"{shutdown_timeout:g}",
                ", ".join(pending_names),
            )
            return pending_names
        else:
            for result in results:
                if isinstance(result, asyncio.CancelledError):
                    logger.debug("MCP lifecycle task was cancelled during shutdown.")
                elif isinstance(result, Exception):
                    logger.error(
                        "MCP lifecycle task failed during shutdown.",
                        exc_info=(type(result), result, result.__traceback__),
                    )
        return []

    async def _cleanup_mcp_client_safely(
        self, mcp_client: Any, name: str
    ) -> None:
        """Safely cleanup an MCP client."""
        try:
            await mcp_client.cleanup()
        except Exception as cleanup_exc:
            logger.error(
                f"Failed to cleanup MCP client resources {name}: {cleanup_exc}"
            )

    async def _init_mcp_client(self, name: str, config: dict) -> Any:
        """Initialize a single MCP client."""
        mcp_mod = _get_mcp_client()
        MCPClient = mcp_mod.MCPClient
        mcp_tool_mod = _get_mcp_tool()
        MCPTool = mcp_tool_mod.MCPTool

        mcp_client = MCPClient()
        mcp_client.name = name
        try:
            await mcp_client.connect_to_server(config, name)
            tools_res = await mcp_client.list_tools_and_save()
        except asyncio.CancelledError:
            await self._cleanup_mcp_client_safely(mcp_client, name)
            raise
        except Exception:
            await self._cleanup_mcp_client_safely(mcp_client, name)
            raise
        logger.debug(f"MCP server {name} list tools response: {tools_res}")
        tool_names = [tool.name for tool in tools_res.tools]

        # Remove old MCP tools for this server
        self.func_list = [
            f
            for f in self.func_list
            if not (isinstance(f, MCPTool) and f.mcp_server_name == name)
        ]

        # Add new MCP tools
        for tool in mcp_client.tools:
            func_tool = MCPTool(
                mcp_tool=tool,
                mcp_client=mcp_client,
                mcp_server_name=name,
            )
            self.func_list.append(func_tool)

        logger.info(f"Connected to MCP server {name}, Tools: {tool_names}")
        return mcp_client

    async def _terminate_mcp_client(self, name: str) -> None:
        """Terminate and cleanup an MCP client."""
        async with self._runtime_lock:
            runtime = self._mcp_server_runtime.get(name)
        if runtime:
            client = runtime.client
            await self._cleanup_mcp_client_safely(client, name)
            self.func_list = [
                f
                for f in self.func_list
                if not (isinstance(f, _get_mcp_tool().MCPTool) and f.mcp_server_name == name)
            ]
            async with self._runtime_lock:
                self._mcp_server_runtime.pop(name, None)
                self._mcp_starting.discard(name)
            logger.info(f"Disconnected from MCP server {name}")
            return

        self.func_list = [
            f
            for f in self.func_list
            if not (isinstance(f, _get_mcp_tool().MCPTool) and f.mcp_server_name == name)
        ]
        async with self._runtime_lock:
            self._mcp_starting.discard(name)

    async def test_mcp_server_connection(self, config: dict) -> list[str]:
        """Test connection to an MCP server."""
        mcp_mod = _get_mcp_client()
        MCPClient = mcp_mod.MCPClient
        _prepare_config = mcp_mod._prepare_config
        _quick_test_mcp_connection = mcp_mod._quick_test_mcp_connection

        if "url" in config:
            cfg = _prepare_config(config.copy())
            success, error_msg = await _quick_test_mcp_connection(cfg)
            if not success:
                raise Exception(error_msg)

        mcp_client = MCPClient()
        try:
            logger.debug(f"testing MCP server connection with config: {config}")
            await mcp_client.connect_to_server(config, "test")
            tools_res = await mcp_client.list_tools_and_save()
            tool_names = [tool.name for tool in tools_res.tools]
        finally:
            logger.debug("Cleaning up MCP client after testing connection.")
            await mcp_client.cleanup()
        return tool_names

    async def enable_mcp_server(
        self,
        name: str,
        config: dict,
        shutdown_event: asyncio.Event | None = None,
        init_timeout: float | str | None = None,
    ) -> None:
        """Enable and initialize an MCP server."""
        if init_timeout is None:
            timeout_value = self._enable_timeout_default
        else:
            timeout_value = _resolve_timeout(
                timeout=init_timeout,
                env_name=ENABLE_MCP_TIMEOUT_ENV,
                default=self._enable_timeout_default,
            )
        await self._start_mcp_server(
            name=name,
            cfg=config,
            shutdown_event=shutdown_event,
            init_timeout=timeout_value,
        )

    async def disable_mcp_server(
        self,
        name: str | None = None,
        shutdown_timeout: float = 10,
    ) -> None:
        """Disable an MCP server by name, or all if name is None."""
        if name:
            async with self._runtime_lock:
                runtime = self._mcp_server_runtime.get(name)
            if runtime is None:
                return
            await self._shutdown_runtimes([runtime], shutdown_timeout, strict=True)
        else:
            async with self._runtime_lock:
                runtimes = list(self._mcp_server_runtime.values())
            await self._shutdown_runtimes(runtimes, shutdown_timeout, strict=False)

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
                "检测到 MCP 初始化超时与动态启用超时配置不同:"
                "初始化使用 %s 秒,动态启用使用 %s 秒｡如需一致,请设置相同值｡",
                f"{init_timeout:g}",
                f"{enable_timeout:g}",
            )
            self._timeout_mismatch_warned = True

    def get_func_desc_openai_style(self, omit_empty_parameter_field=False) -> list:
        """Get OpenAI-style function descriptions for active tools."""
        tools = [f for f in self.func_list if f.active]
        toolset = ToolSet(tools)
        return toolset.openai_schema(
            omit_empty_parameter_field=omit_empty_parameter_field,
        )

    def get_func_desc_anthropic_style(self) -> list:
        """Get Anthropic-style function descriptions for active tools."""
        tools = [f for f in self.func_list if f.active]
        toolset = ToolSet(tools)
        return toolset.anthropic_schema()

    def get_func_desc_google_genai_style(self) -> dict:
        """Get Google GenAI-style function descriptions for active tools."""
        tools = [f for f in self.func_list if f.active]
        toolset = ToolSet(tools)
        return toolset.google_schema()

    def deactivate_llm_tool(self, name: str) -> bool:
        """Deactivate a registered function tool."""
        func_tool = self.get_func(name)
        if func_tool is not None:
            func_tool.active = False

            inactivated_llm_tools: list = sp.get(
                "inactivated_llm_tools",
                [],
                scope="global",
                scope_id="global",
            )
            if name not in inactivated_llm_tools:
                inactivated_llm_tools.append(name)
                sp.put(
                    "inactivated_llm_tools",
                    inactivated_llm_tools,
                    scope="global",
                    scope_id="global",
                )

            return True
        return False

    def activate_llm_tool(self, name: str, star_map: dict) -> bool:
        """Activate a registered function tool."""
        func_tool = self.get_func(name)
        if func_tool is not None:
            if func_tool.handler_module_path in star_map:
                if not star_map[func_tool.handler_module_path].activated:
                    raise ValueError(
                        f"此函数调用工具所属的插件 {star_map[func_tool.handler_module_path].name} 已被禁用,请先在管理面板启用再激活此工具｡"
                    )

            func_tool.active = True

            inactivated_llm_tools: list = sp.get(
                "inactivated_llm_tools",
                [],
                scope="global",
                scope_id="global",
            )
            if name in inactivated_llm_tools:
                inactivated_llm_tools.remove(name)
                sp.put(
                    "inactivated_llm_tools",
                    inactivated_llm_tools,
                    scope="global",
                    scope_id="global",
                )

            return True
        return False

    @property
    def mcp_config_path(self) -> str:
        data_dir = get_astrbot_data_path()
        return os.path.join(data_dir, "mcp_server.json")

    def load_mcp_config(self) -> dict:
        """Load MCP configuration from file."""
        if not os.path.exists(self.mcp_config_path):
            os.makedirs(os.path.dirname(self.mcp_config_path), exist_ok=True)
            with open(self.mcp_config_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_MCP_CONFIG, f, ensure_ascii=False, indent=4)
            return DEFAULT_MCP_CONFIG.copy()

        try:
            with open(self.mcp_config_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载 MCP 配置失败: {e}")
            return DEFAULT_MCP_CONFIG.copy()

    def save_mcp_config(self, config: dict) -> bool:
        """Save MCP configuration to file."""
        try:
            with open(self.mcp_config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            logger.error(f"保存 MCP 配置失败: {e}")
            return False

    # Module paths for built-in tool providers
    _INTERNAL_TOOL_PROVIDERS: ClassVar[list[str]] = [
        "astrbot.core.tools.cron_tools",
        "astrbot.core.tools.kb_query",
        "astrbot.core.tools.send_message",
        "astrbot.core.computer.computer_tool_provider",
    ]

    def register_internal_tools(self) -> None:
        """Register AstrBot built-in tools from all internal providers.

        Each provider module should expose a get_all_tools() function.
        """
        import importlib

        existing_names = {t.name for t in self.func_list}

        for module_path in self._INTERNAL_TOOL_PROVIDERS:
            try:
                mod = importlib.import_module(module_path)
                provider_tools = mod.get_all_tools()
            except Exception as e:
                logger.warning(
                    "Failed to load internal tool provider %s: %s",
                    module_path,
                    e,
                )
                continue

            for tool in provider_tools:
                tool.source = "internal"
                if tool.name not in existing_names:
                    self.func_list.append(tool)
                    existing_names.add(tool.name)
                    logger.info("Registered internal tool: %s", tool.name)

    def __str__(self) -> str:
        return str(self.func_list)

    def __repr__(self) -> str:
        return str(self.func_list)


# Alias for backward compatibility
FuncCall = FunctionToolManager
