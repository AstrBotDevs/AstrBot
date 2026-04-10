"""Tools registry for AstrBot internal runtime.

This module provides the canonical FunctionToolManager implementation
for tool registration and MCP server management.
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import threading
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import aiohttp

from astrbot import logger
from astrbot._internal.tools.base import FunctionTool, ToolSchema, ToolSet

# Re-export MCP-related constants and exceptions from protocols
from astrbot._internal.protocols._mcp import (
    DEFAULT_MCP_CONFIG as _DEFAULT_MCP_CONFIG,
    MCPAllServicesFailedError,
    MCPInitError,
    MCPInitSummary,
    MCPInitTimeoutError,
    MCPShutdownTimeoutError,
)
from astrbot._internal.protocols._mcp.client import (
    McpClient,
    _prepare_config,
    _quick_test_mcp_connection,
)
from astrbot._internal.protocols._mcp.tool import MCPTool

__all__ = [
    "DEFAULT_MCP_CONFIG",
    "ENABLE_MCP_TIMEOUT_ENV",
    "FuncCall",
    "FunctionTool",
    "FunctionToolManager",
    "MCPAllServicesFailedError",
    "MCPInitError",
    "MCPInitSummary",
    "MCPInitTimeoutError",
    "MCPShutdownTimeoutError",
    "ToolSet",
]


DEFAULT_MCP_CONFIG: dict[str, Any] = _DEFAULT_MCP_CONFIG
ENABLE_MCP_TIMEOUT_ENV = "ASTRBOT_MCP_TIMEOUT_ENABLED"
MCP_INIT_TIMEOUT_ENV = "ASTRBOT_MCP_INIT_TIMEOUT"

DEFAULT_MCP_INIT_TIMEOUT_SECONDS = 180.0
DEFAULT_ENABLE_MCP_TIMEOUT_SECONDS = 180.0
MAX_MCP_TIMEOUT_SECONDS = 300.0


@dataclass
class _MCPServerRuntime:
    """Runtime state for a single MCP server."""

    name: str
    client: McpClient
    shutdown_event: asyncio.Event
    lifecycle_task: asyncio.Task[None]


class _MCPClientDictView(Mapping[str, McpClient]):
    """Read-only view of MCP clients derived from runtime state."""

    def __init__(self, runtime: dict[str, _MCPServerRuntime]) -> None:
        self._runtime = runtime

    def __getitem__(self, key: str) -> McpClient:
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
    source = f"environment variable {env_name}"
    if timeout is None:
        timeout = os.getenv(env_name, str(default))
    else:
        source = "explicit timeout argument"

    try:
        timeout_value = float(timeout)
    except (TypeError, ValueError):
        logger.warning(
            f"Timeout configuration ({source})={timeout!r} is invalid, using default {default:g} seconds.",
        )
        return default

    if timeout_value <= 0:
        logger.warning(
            f"Timeout configuration ({source})={timeout_value:g} must be greater than 0, using default {default:g} seconds.",
        )
        return default

    if timeout_value > MAX_MCP_TIMEOUT_SECONDS:
        logger.warning(
            f"Timeout configuration ({source})={timeout_value:g} is too large, limited to maximum "
            f"{MAX_MCP_TIMEOUT_SECONDS:g} seconds to avoid long waits.",
        )
        return MAX_MCP_TIMEOUT_SECONDS

    return timeout_value


# Alias for backward compatibility
FuncTool = FunctionTool


def _get_sp() -> Any:
    """Get the SharedPreferences instance, avoiding circular imports."""
    from astrbot.core import sp

    return sp


def _get_astrbot_data_path() -> str:
    """Get the AstrBot data directory path."""
    from astrbot.core.utils.astrbot_path import get_astrbot_data_path

    return get_astrbot_data_path()


# Builtin tools stubs - these functions don't exist in the new architecture
def _ensure_builtin_tools_loaded() -> None:
    """No-op in new architecture."""
    pass


def _get_builtin_tool_class(name: str) -> type[FunctionTool] | None:
    """No-op in new architecture."""
    return None


def _get_builtin_tool_name(tool_cls: type[FunctionTool]) -> str | None:
    """No-op in new architecture."""
    return None


def _iter_builtin_tool_classes() -> list[type[FunctionTool]]:
    """No-op in new architecture."""
    return []


class FunctionToolManager:
    """Central registry for all function tools."""

    def __init__(self) -> None:
        self.func_list: list[FuncTool] = []
        """All tools including MCP tools and plugin tools, except AstrBot builtin tools."""
        self.builtin_func_list: dict[type[FuncTool], FuncTool] = {}
        """All AstrBot builtin tools, keyed by their class. Values are instantiated tool objects, created on demand."""

        self._mcp_server_runtime: dict[str, _MCPServerRuntime] = {}
        """MCP runtime metadata, keyed by server name. Updated atomically on MCP lifecycle changes."""
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
    def mcp_client_dict(self) -> Mapping[str, McpClient]:
        """Read-only compatibility view for external callers that still read mcp_client_dict.

        Note: Mutating this mapping is unsupported and will raise TypeError.
        """
        return self._mcp_client_dict_view

    @property
    def mcp_server_runtime_view(self) -> Mapping[str, _MCPServerRuntime]:
        """Read-only view of MCP runtime metadata for external callers."""
        return self._mcp_server_runtime_view

    @property
    def mcp_server_runtime(self) -> Mapping[str, _MCPServerRuntime]:
        """Backward-compatible read-only view (deprecated). Do not mutate.

        Note: Mutations are not supported and will raise TypeError.
        """
        return self._mcp_server_runtime_view

    def empty(self) -> bool:
        return len(self.func_list) == 0

    def spec_to_func(
        self,
        name: str,
        func_args: list[dict],
        desc: str,
        handler: Any,
    ) -> FuncTool:
        """Create a FuncTool from a specification."""
        params = {
            "type": "object",  # hard-coded here
            "properties": {},
        }
        for param in func_args:
            p = copy.deepcopy(param)
            p.pop("name", None)
            params["properties"][param["name"]] = p
        return FuncTool(
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
        handler: Any,
    ) -> None:
        """Add a function tool.

        Args:
            name: Function name
            func_args: Function arguments list, format: [{"type": "string", "name": "arg_name", "description": "arg_description"}, ...]
            desc: Function description
            handler: Handler function
        """
        # Check if the tool has been added before
        self.remove_func(name)

        self.func_list.append(
            self.spec_to_func(
                name=name,
                func_args=func_args,
                desc=desc,
                handler=handler,
            ),
        )
        logger.info(f"Added function tool: {name}")

    def remove_func(self, name: str) -> None:
        """Remove a function tool by name."""
        for i, f in enumerate(self.func_list):
            if f.name == name:
                self.func_list.pop(i)
                break

    def remove(self, name: str) -> bool:
        """Remove a tool by name. Returns True if found."""
        for i, f in enumerate(self.func_list):
            if f.name == name:
                self.func_list.pop(i)
                return True
        return False

    def add(self, tool: ToolSchema) -> None:
        """Add a tool to the registry."""
        self.func_list.append(tool)

    def get_func(self, name: str | type[FuncTool]) -> FuncTool | None:
        # Prefer returning active tools (later loaded ones override earlier ones)
        # Using getattr(..., True) to match ToolSet.add_tool behavior: tools without active attribute are considered active
        if isinstance(name, str):
            for f in reversed(self.func_list):
                if f.name == name and getattr(f, "active", True):
                    return f
            # Fallback: get the last tool with the same name
            for f in reversed(self.func_list):
                if f.name == name:
                    return f
            # Try builtin tools
            try:
                builtin_tool = self.get_builtin_tool(name)
                if builtin_tool is not None and getattr(builtin_tool, "active", True):
                    return builtin_tool
                return builtin_tool
            except (KeyError, TypeError):
                return None
        return None

    def get_builtin_tool(self, tool: str | type[FuncTool]) -> FuncTool:
        """Get a builtin tool by name or class."""
        _ensure_builtin_tools_loaded()

        if isinstance(tool, str):
            tool_cls = _get_builtin_tool_class(tool)
            if tool_cls is None:
                raise KeyError(f"Builtin tool {tool} is not registered.")
        elif isinstance(tool, type) and issubclass(tool, FunctionTool):
            tool_cls = tool
            if _get_builtin_tool_name(tool_cls) is None:
                raise KeyError(
                    f"Builtin tool class {tool_cls.__module__}.{tool_cls.__name__} is not registered.",
                )
        else:
            raise TypeError("tool must be a builtin tool name or FunctionTool class.")

        cached_tool = self.builtin_func_list.get(tool_cls)
        if cached_tool is not None:
            return cached_tool

        builtin_tool = tool_cls()  # type: ignore
        self.builtin_func_list[tool_cls] = builtin_tool
        return builtin_tool

    def iter_builtin_tools(self) -> list[FuncTool]:
        """Iterate over all builtin tools."""
        _ensure_builtin_tools_loaded()
        return [
            self.get_builtin_tool(tool_cls) for tool_cls in _iter_builtin_tool_classes()
        ]

    def is_builtin_tool(self, name: str) -> bool:
        """Check if a tool name is a builtin tool."""
        _ensure_builtin_tools_loaded()
        return _get_builtin_tool_class(name) is not None

    def get_full_tool_set(self) -> ToolSet:
        """Get the full tool set.

        Uses ToolSet.add_tool for population. For tools with the same name,
        deduplication rules are:
        - Prefer tools with active=True
        - When active status is the same, later loaded tools override earlier ones

        Therefore, a later loaded inactive tool will not override an already active tool;
        MCP tools can still override disabled builtin tools when needed.
        """
        tool_set = ToolSet()
        for tool in self.func_list:
            tool_set.add_tool(tool)
        return tool_set

    def register_internal_tools(self) -> None:
        """Register built-in computer tools (shell, python, browser, neo)."""
        # Import here to avoid circular imports
        try:
            from astrbot.core.computer.computer_tool_provider import get_all_tools

            for tool in get_all_tools():
                if self.get_func(tool.name) is None:
                    self.add(tool)  # type: ignore[arg-type]
        except ImportError:
            logger.debug("Computer tools not available")

    @staticmethod
    def _log_safe_mcp_debug_config(cfg: dict) -> None:
        """Log sanitized MCP debug config info."""
        # Only log sanitized summary to avoid leaking sensitive info in command/args/url
        if "command" in cfg:
            cmd = cfg["command"]
            executable = str(
                cmd[0] if isinstance(cmd, (list, tuple)) and cmd else cmd
            )
            args_val = cfg.get("args", [])
            args_count = (
                len(args_val)
                if isinstance(args_val, (list, tuple))
                else (0 if args_val is None else 1)
            )
            logger.debug(f"  Command executable: {executable}, argument count: {args_count}")
            return

        if "url" in cfg:
            parsed = urllib.parse.urlparse(str(cfg["url"]))
            host = parsed.hostname or ""
            scheme = parsed.scheme or "unknown"
            try:
                port = f":{parsed.port}" if parsed.port else ""
            except ValueError:
                port = ""
            logger.debug(f"  Host: {scheme}://{host}{port}")

    async def init_mcp_clients(
        self,
        raise_on_all_failed: bool = False,
    ) -> MCPInitSummary:
        """Initialize MCP clients from mcp_server.json config file.

        The config file format:
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
        - Initialization timeout uses environment variable ASTRBOT_MCP_INIT_TIMEOUT or default.
        - Dynamic enable timeout uses ASTRBOT_MCP_ENABLE_TIMEOUT (independent from init timeout).
        """
        data_dir = _get_astrbot_data_path()

        mcp_json_file = os.path.join(data_dir, "mcp_server.json")
        if not os.path.exists(mcp_json_file):
            # Config file doesn't exist, create default
            with open(mcp_json_file, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_MCP_CONFIG, f, ensure_ascii=False, indent=4)
            logger.info(f"MCP config file not found, created default config at {mcp_json_file}")
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

        logger.info(f"Waiting for {len(active_configs)} MCP services to initialize...")

        init_tasks = [
            asyncio.create_task(
                self._start_mcp_server(
                    name=name,
                    cfg=cfg,
                    shutdown_event=shutdown_event,
                    timeout=init_timeout,
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
                        f"Connected to MCP server {name} timeout ({timeout_display} seconds)",
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
                f"Please check the mcp_server.json file and server availability.",
            )

        summary = MCPInitSummary(
            total=len(active_configs),
            success=success_count,
            failed=failed_services,
        )
        logger.info(
            f"MCP services initialization completed: {summary.success}/{summary.total} successful, {len(summary.failed)} failed.",
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
        timeout: float,
    ) -> None:
        """Initialize MCP server with timeout and register task/event together.

        This method is idempotent. If the server is already running, the existing
        runtime is kept and the new config is ignored.
        """
        async with self._runtime_lock:
            if name in self._mcp_server_runtime or name in self._mcp_starting:
                logger.warning(
                    f"Connected to MCP server {name}, ignoring this startup request (timeout={timeout:g}).",
                )
                self._log_safe_mcp_debug_config(cfg)
                return
            self._mcp_starting.add(name)

        if shutdown_event is None:
            shutdown_event = asyncio.Event()

        mcp_client: McpClient | None = None
        try:
            mcp_client = await asyncio.wait_for(
                self._init_mcp_client(name, cfg),
                timeout=timeout,
            )
        except asyncio.TimeoutError as exc:
            raise MCPInitTimeoutError(
                f"Connected to MCP server {name} timeout ({timeout:g} seconds)",
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
        timeout: float,
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
                timeout=timeout,
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
                raise MCPShutdownTimeoutError(pending_names, timeout)
            logger.warning(
                "MCP server shutdown timeout (%s seconds), the following servers were not fully closed: %s",
                f"{timeout:g}",
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
        self,
        mcp_client: McpClient,
        name: str,
    ) -> None:
        """Safely clean up a single MCP client, avoiding cleanup exceptions interrupting main flow."""
        try:
            await mcp_client.cleanup()
        except Exception as cleanup_exc:
            logger.error(
                f"Failed to cleanup MCP client resources {name}: {cleanup_exc}",
            )

    async def _init_mcp_client(self, name: str, config: dict) -> McpClient:
        """Initialize a single MCP client."""
        mcp_client = McpClient()
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

        # Remove any previous tools from this MCP server
        self.func_list = [
            f
            for f in self.func_list
            if not (isinstance(f, MCPTool) and f.mcp_server_name == name)
        ]

        # Convert MCP tools to FuncTool and add to func_list
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
        """Shut down and clean up an MCP client."""
        async with self._runtime_lock:
            runtime = self._mcp_server_runtime.get(name)
        if runtime:
            client = runtime.client
            # Close MCP connection
            await self._cleanup_mcp_client_safely(client, name)
            # Remove associated FuncTools
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

    async def test_mcp_server_connection(
        self,
        config: dict,
    ) -> tuple[bool, str]:
        """Test MCP server connection.

        Returns:
            Tuple of (success, message)
        """
        success, error_msg = await _quick_test_mcp_connection(config)
        if not success:
            return False, error_msg

        mcp_client = McpClient()
        try:
            logger.debug(f"testing MCP server connection with config: {config}")
            await mcp_client.connect_to_server(config, "test")
            tools_res = await mcp_client.list_tools_and_save()
            tool_names = [tool.name for tool in tools_res.tools]
            return True, f"Connection successful, tools: {tool_names}"
        except Exception as e:
            return False, str(e)
        finally:
            logger.debug("Cleaning up MCP client after testing connection.")
            await mcp_client.cleanup()

    async def enable_mcp_server(
        self,
        name: str,
        config: dict,
        shutdown_event: asyncio.Event | None = None,
        timeout: float | str | None = None,
    ) -> None:
        """Enable a new MCP server and initialize it.

        Args:
            name: The name of the MCP server.
            config: Configuration for the MCP server.
            shutdown_event: Event to signal when the MCP client should shut down.
            timeout: Timeout in seconds for initialization.
                Uses ASTRBOT_MCP_ENABLE_TIMEOUT by default (separate from init timeout).

        Raises:
            MCPInitTimeoutError: If initialization does not complete within timeout.
            Exception: If there is an error during initialization.
        """
        if timeout is None:
            timeout_value = self._enable_timeout_default
        else:
            timeout_value = _resolve_timeout(
                timeout=timeout,
                env_name=ENABLE_MCP_TIMEOUT_ENV,
                default=self._enable_timeout_default,
            )
        await self._start_mcp_server(
            name=name,
            cfg=config,
            shutdown_event=shutdown_event,
            timeout=timeout_value,
        )

    async def disable_mcp_server(
        self,
        name: str | None = None,
        timeout: float = 10,
    ) -> None:
        """Disable an MCP server by its name.

        Args:
            name: The name of the MCP server to disable. If None, ALL MCP servers will be disabled.
            timeout: Timeout in seconds for shutdown.

        Raises:
            MCPShutdownTimeoutError: If shutdown does not complete within timeout.
                Only raised when disabling a specific server (name is not None).
        """
        if name:
            async with self._runtime_lock:
                runtime = self._mcp_server_runtime.get(name)
            if runtime is None:
                return

            await self._shutdown_runtimes([runtime], timeout, strict=True)
        else:
            async with self._runtime_lock:
                runtimes = list(self._mcp_server_runtime.values())
            await self._shutdown_runtimes(runtimes, timeout, strict=False)

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
                "Detected different MCP initialization timeout and dynamic enable timeout: "
                "initialization uses %s seconds, dynamic enable uses %s seconds. "
                "Set them to the same value for consistency.",
                f"{init_timeout:g}",
                f"{enable_timeout:g}",
            )
            self._timeout_mismatch_warned = True

    def get_func_desc_openai_style(self, omit_empty_parameter_field: bool = False) -> list:
        """Get tools in OpenAI API style for all active tools."""
        tools = [f for f in self.func_list if getattr(f, "active", True)]
        toolset = ToolSet(tools)
        return toolset.openai_schema(
            omit_empty_parameter_field=omit_empty_parameter_field,
        )

    def get_func_desc_anthropic_style(self) -> list:
        """Get tools in Anthropic API style for all active tools."""
        tools = [f for f in self.func_list if getattr(f, "active", True)]
        toolset = ToolSet(tools)
        return toolset.anthropic_schema()

    def get_func_desc_google_genai_style(self) -> dict:
        """Get tools in Google GenAI API style for all active tools."""
        tools = [f for f in self.func_list if getattr(f, "active", True)]
        toolset = ToolSet(tools)
        return toolset.google_schema()

    def deactivate_llm_tool(self, name: str) -> bool:
        """Deactivate a registered function tool.

        Returns:
            False if not found
        """
        func_tool = self.get_func(name)
        if func_tool is not None:
            func_tool.active = False

            sp = _get_sp()
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

    def activate_llm_tool(self, name: str, star_map: dict | None = None) -> bool:
        """Activate a registered function tool.

        Args:
            name: Tool name
            star_map: Optional star_map for plugin dependency checking (ignored in new architecture)
        """
        func_tool = self.get_func(name)
        if func_tool is not None:
            if star_map is not None and func_tool.handler_module_path in star_map:
                if not star_map[func_tool.handler_module_path].activated:
                    raise ValueError(
                        f"The plugin {star_map[func_tool.handler_module_path].name} "
                        f"that this function tool belongs to has been disabled. "
                        f"Please enable the plugin in the management panel first.",
                    )

            func_tool.active = True

            sp = _get_sp()
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
        """Get the MCP config file path."""
        data_dir = _get_astrbot_data_path()
        return os.path.join(data_dir, "mcp_server.json")

    def load_mcp_config(self) -> dict[str, Any]:
        """Load MCP configuration from file."""
        if not os.path.exists(self.mcp_config_path):
            # Config file doesn't exist, create default
            os.makedirs(os.path.dirname(self.mcp_config_path), exist_ok=True)
            with open(self.mcp_config_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_MCP_CONFIG, f, ensure_ascii=False, indent=4)
            return DEFAULT_MCP_CONFIG

        try:
            with open(self.mcp_config_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load MCP config: {e}")
            return DEFAULT_MCP_CONFIG

    def save_mcp_config(self, config: dict) -> bool:
        """Save MCP configuration to file."""
        try:
            with open(self.mcp_config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            logger.error(f"Failed to save MCP config: {e}")
            return False

    async def sync_modelscope_mcp_servers(self, access_token: str) -> None:
        """Sync MCP servers from ModelScope platform."""
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
                        local_mcp_config = self.load_mcp_config()

                        synced_count = 0
                        for server in mcp_server_list:
                            server_name = server["name"]
                            operational_urls = server.get("operational_urls", [])
                            if not operational_urls:
                                continue
                            url_info = operational_urls[0]
                            server_url = url_info.get("url")
                            if not server_url:
                                continue
                            # Add to config (same name will override)
                            local_mcp_config["mcpServers"][server_name] = {
                                "url": server_url,
                                "transport": "sse",
                                "active": True,
                                "provider": "modelscope",
                            }
                            synced_count += 1

                        if synced_count > 0:
                            self.save_mcp_config(local_mcp_config)
                            tasks = []
                            for server in mcp_server_list:
                                name = server["name"]
                                tasks.append(
                                    self.enable_mcp_server(
                                        name=name,
                                        config=local_mcp_config["mcpServers"][name],
                                    ),
                                )
                            await asyncio.gather(*tasks)
                            logger.info(
                                f"Synced {synced_count} MCP servers from ModelScope",
                            )
                        else:
                            logger.warning("No available ModelScope MCP servers found")
                    else:
                        raise Exception(
                            f"ModelScope API request failed: HTTP {response.status}",
                        )

        except aiohttp.ClientError as e:
            raise Exception(f"Network connection error: {e!s}")
        except Exception as e:
            raise Exception(f"Error syncing ModelScope MCP servers: {e!s}")

    def __str__(self) -> str:
        return str(self.func_list)

    def __repr__(self) -> str:
        return str(self.func_list)


# Alias for backward compatibility
FuncCall = FunctionToolManager
