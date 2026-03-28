import asyncio
import logging
import os
import sys
import subprocess
import shutil
from contextlib import AsyncExitStack
from datetime import timedelta
from typing import Generic

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from astrbot import logger
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.utils.log_pipe import LogPipe

from .run_context import TContext
from .tool import FunctionTool

try:
    import anyio
    import mcp
    from mcp.client.sse import sse_client
except (ModuleNotFoundError, ImportError):
    logger.warning(
        "Warning: Missing 'mcp' dependency, MCP services will be unavailable."
    )

try:
    from mcp.client.streamable_http import streamablehttp_client
except (ModuleNotFoundError, ImportError):
    logger.warning(
        "Warning: Missing 'mcp' dependency or MCP library version too old, Streamable HTTP connection unavailable.",
    )


def _prepare_config(config: dict) -> dict:
    """Prepare configuration, handle nested format"""
    if config.get("mcpServers"):
        first_key = next(iter(config["mcpServers"]))
        config = config["mcpServers"][first_key]
    config.pop("active", None)
    return config


def _prepare_stdio_env(config: dict) -> dict:
    """Preserve Windows executable resolution for stdio subprocesses."""
    if sys.platform != "win32":
        return config
    prepared = config.copy()
    env = dict(prepared.get("env") or {})
    env= _merge_environment_variables(env)
    prepared["env"] = env
    # 获取配置值，并转换为小写进行不区分大小写比较
    cmd_str = _extract_command_string(config)
    # 目前仅处理 dotnet，如有其他命令需求需扩展 
    if cmd_str and cmd_str.lower() == "dotnet":
        env= _ensure_dotnet_in_path(env)
        prepared["env"] = env
        return _create_subprocess_NO_WINDOW(prepared)
    return prepared

def _extract_command_string(config:dict)->str:
    """从配置中提取命令字符串"""
    command = config.get('command')
    cmd_str = ""
    if isinstance(command, str):
        cmd_str = command
    elif isinstance(command, list) and command:
        cmd_str = command[0]
    return cmd_str

def _merge_environment_variables(env: dict) -> dict:
    """合并环境变量，处理Windows不区分大小写的情况"""
    merged = env.copy()
    
    # 将用户环境变量转换为统一的大小写形式便于比较
    user_keys_lower = {k.lower(): k for k in merged.keys()}
    
    for sys_key, sys_value in os.environ.items():
        sys_key_lower = sys_key.lower()
        if sys_key_lower not in user_keys_lower:
            # 使用系统环境变量中的原始大小写
            merged[sys_key] = sys_value
    
    return merged

def _ensure_dotnet_in_path(env: dict) -> dict:
    """确保dotnet在PATH中，若不存在则发出警告而不是自动添加"""
    
    # 检查当前环境PATH中是否有dotnet
    current_path = env.get("PATH", "")
    if shutil.which("dotnet", path=current_path):
        return env
    
    # 检查系统PATH
    system_path = os.environ.get("PATH", "")
    if shutil.which("dotnet", path=system_path):
        # 安全地合并PATH：过滤空值后连接
        paths = [p for p in [current_path, system_path] if p]
        env["PATH"] = ";".join(paths)
        return env
    
    # 发出警告而不是静默添加
    logger.warning(
        "dotnet not found in PATH. .NET-based MCP servers may fail to start. "
        "Please ensure dotnet is installed and in your PATH."
    )
    return env

def _create_subprocess(prepared: dict)->dict:
    """准备子进程参数字典"""
    # 只在Windows平台处理
    if os.name == "nt":
        # 检查用户是否指定了控制台行为
        # 使用更清晰的参数名：show_console
        show_console = prepared.pop("show_console", None)
        
        if show_console is not None:
            # 确保是布尔值
            if isinstance(show_console, str):
                # 处理字符串形式的布尔值
                show_console = show_console.lower() in ("true", "1", "yes", "y", "t")
            elif not isinstance(show_console, bool):                
                # 如果不是字符串也不是布尔值，可以抛出异常或使用默认值                
                raise ValueError(f"show_console must be bool or str, got {type(show_console)}")
            existing_flags = prepared.get("creationflags", 0)
            if not show_console:  # 如果不要显示控制台
                prepared["creationflags"] = existing_flags | subprocess.CREATE_NO_WINDOW
            else:
                prepared["creationflags"] = existing_flags & ~subprocess.CREATE_NO_WINDOW
        else:
            # 保持向后兼容：默认添加CREATE_NO_WINDOW
            if "creationflags" not in prepared:
                prepared["creationflags"] = subprocess.CREATE_NO_WINDOW
    return prepared


async def _quick_test_mcp_connection(config: dict) -> tuple[bool, str]:
    """Quick test MCP server connectivity"""
    import aiohttp

    cfg = _prepare_config(config.copy())

    url = cfg["url"]
    headers = cfg.get("headers", {})
    timeout = cfg.get("timeout", 10)

    try:
        if "transport" in cfg:
            transport_type = cfg["transport"]
        elif "type" in cfg:
            transport_type = cfg["type"]
        else:
            raise Exception("MCP connection config missing transport or type field")

        async with aiohttp.ClientSession() as session:
            if transport_type == "streamable_http":
                test_payload = {
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "id": 0,
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "test-client", "version": "1.2.3"},
                    },
                }
                async with session.post(
                    url,
                    headers={
                        **headers,
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                    },
                    json=test_payload,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response:
                    if response.status == 200:
                        return True, ""
                    return False, f"HTTP {response.status}: {response.reason}"
            else:
                async with session.get(
                    url,
                    headers={
                        **headers,
                        "Accept": "application/json, text/event-stream",
                    },
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response:
                    if response.status == 200:
                        return True, ""
                    return False, f"HTTP {response.status}: {response.reason}"

    except asyncio.TimeoutError:
        return False, f"Connection timeout: {timeout} seconds"
    except Exception as e:
        return False, f"{e!s}"


class MCPClient:
    def __init__(self) -> None:
        # Initialize session and client objects
        self.session: mcp.ClientSession | None = None
        self.exit_stack = AsyncExitStack()
        self._old_exit_stacks: list[AsyncExitStack] = []  # Track old stacks for cleanup

        self.name: str | None = None
        self.active: bool = True
        self.tools: list[mcp.Tool] = []
        self.server_errlogs: list[str] = []
        self.running_event = asyncio.Event()

        # Store connection config for reconnection
        self._mcp_server_config: dict | None = None
        self._server_name: str | None = None
        self._reconnect_lock = asyncio.Lock()  # Lock for thread-safe reconnection
        self._reconnecting: bool = False  # For logging and debugging

    async def connect_to_server(self, mcp_server_config: dict, name: str) -> None:
        """Connect to MCP server

        If `url` parameter exists:
            1. When transport is specified as `streamable_http`, use Streamable HTTP connection.
            2. When transport is specified as `sse`, use SSE connection.
            3. If not specified, default to SSE connection to MCP service.

        Args:
            mcp_server_config (dict): Configuration for the MCP server. See https://modelcontextprotocol.io/quickstart/server

        """
        # Store config for reconnection
        self._mcp_server_config = mcp_server_config
        self._server_name = name

        cfg = _prepare_config(mcp_server_config.copy())

        def logging_callback(
            msg: str | mcp.types.LoggingMessageNotificationParams,
        ) -> None:
            # Handle MCP service error logs
            if isinstance(msg, mcp.types.LoggingMessageNotificationParams):
                if msg.level in ("warning", "error", "critical", "alert", "emergency"):
                    log_msg = f"[{msg.level.upper()}] {str(msg.data)}"
                    self.server_errlogs.append(log_msg)

        if "url" in cfg:
            success, error_msg = await _quick_test_mcp_connection(cfg)
            if not success:
                raise Exception(error_msg)

            if "transport" in cfg:
                transport_type = cfg["transport"]
            elif "type" in cfg:
                transport_type = cfg["type"]
            else:
                raise Exception("MCP connection config missing transport or type field")

            if transport_type != "streamable_http":
                # SSE transport method
                self._streams_context = sse_client(
                    url=cfg["url"],
                    headers=cfg.get("headers", {}),
                    timeout=cfg.get("timeout", 5),
                    sse_read_timeout=cfg.get("sse_read_timeout", 60 * 5),
                )
                streams = await self.exit_stack.enter_async_context(
                    self._streams_context,
                )

                # Create a new client session
                read_timeout = timedelta(seconds=cfg.get("session_read_timeout", 60))
                self.session = await self.exit_stack.enter_async_context(
                    mcp.ClientSession(
                        *streams,
                        read_timeout_seconds=read_timeout,
                        logging_callback=logging_callback,  # type: ignore
                    ),
                )
            else:
                timeout = timedelta(seconds=cfg.get("timeout", 30))
                sse_read_timeout = timedelta(
                    seconds=cfg.get("sse_read_timeout", 60 * 5),
                )
                self._streams_context = streamablehttp_client(
                    url=cfg["url"],
                    headers=cfg.get("headers", {}),
                    timeout=timeout,
                    sse_read_timeout=sse_read_timeout,
                    terminate_on_close=cfg.get("terminate_on_close", True),
                )
                read_s, write_s, _ = await self.exit_stack.enter_async_context(
                    self._streams_context,
                )

                # Create a new client session
                read_timeout = timedelta(seconds=cfg.get("session_read_timeout", 60))
                self.session = await self.exit_stack.enter_async_context(
                    mcp.ClientSession(
                        read_stream=read_s,
                        write_stream=write_s,
                        read_timeout_seconds=read_timeout,
                        logging_callback=logging_callback,  # type: ignore
                    ),
                )

        else:
            cfg = _prepare_stdio_env(cfg)
            server_params = mcp.StdioServerParameters(
                **cfg,
            )

            def callback(msg: str | mcp.types.LoggingMessageNotificationParams) -> None:
                # Handle MCP service error logs
                if isinstance(msg, mcp.types.LoggingMessageNotificationParams):
                    if msg.level in (
                        "warning",
                        "error",
                        "critical",
                        "alert",
                        "emergency",
                    ):
                        log_msg = f"[{msg.level.upper()}] {str(msg.data)}"
                        self.server_errlogs.append(log_msg)

            stdio_transport = await self.exit_stack.enter_async_context(
                mcp.stdio_client(
                    server_params,
                    errlog=LogPipe(
                        level=logging.INFO,
                        logger=logger,
                        identifier=f"MCPServer-{name}",
                        callback=callback,
                    ),  # type: ignore
                ),
            )

            # Create a new client session
            self.session = await self.exit_stack.enter_async_context(
                mcp.ClientSession(*stdio_transport),
            )
        await self.session.initialize()

    async def list_tools_and_save(self) -> mcp.ListToolsResult:
        """List all tools from the server and save them to self.tools"""
        if not self.session:
            raise Exception("MCP Client is not initialized")
        response = await self.session.list_tools()
        self.tools = response.tools
        return response

    async def _reconnect(self) -> None:
        """Reconnect to the MCP server using the stored configuration.

        Uses asyncio.Lock to ensure thread-safe reconnection in concurrent environments.

        Raises:
            Exception: raised when reconnection fails
        """
        async with self._reconnect_lock:
            # Check if already reconnecting (useful for logging)
            if self._reconnecting:
                logger.debug(
                    f"MCP Client {self._server_name} is already reconnecting, skipping"
                )
                return

            if not self._mcp_server_config or not self._server_name:
                raise Exception("Cannot reconnect: missing connection configuration")

            self._reconnecting = True
            try:
                logger.info(
                    f"Attempting to reconnect to MCP server {self._server_name}..."
                )

                # Save old exit_stack for later cleanup (don't close it now to avoid cancel scope issues)
                if self.exit_stack:
                    self._old_exit_stacks.append(self.exit_stack)

                # Mark old session as invalid
                self.session = None

                # Create new exit stack for new connection
                self.exit_stack = AsyncExitStack()

                # Reconnect using stored config
                await self.connect_to_server(self._mcp_server_config, self._server_name)
                await self.list_tools_and_save()

                logger.info(
                    f"Successfully reconnected to MCP server {self._server_name}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to reconnect to MCP server {self._server_name}: {e}"
                )
                raise
            finally:
                self._reconnecting = False

    async def call_tool_with_reconnect(
        self,
        tool_name: str,
        arguments: dict,
        read_timeout_seconds: timedelta,
    ) -> mcp.types.CallToolResult:
        """Call MCP tool with automatic reconnection on failure, max 2 retries.

        Args:
            tool_name: tool name
            arguments: tool arguments
            read_timeout_seconds: read timeout

        Returns:
            MCP tool call result

        Raises:
            ValueError: MCP session is not available
            anyio.ClosedResourceError: raised after reconnection failure
        """

        @retry(
            retry=retry_if_exception_type(anyio.ClosedResourceError),
            stop=stop_after_attempt(2),
            wait=wait_exponential(multiplier=1, min=1, max=3),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        async def _call_with_retry():
            if not self.session:
                raise ValueError("MCP session is not available for MCP function tools.")

            try:
                return await self.session.call_tool(
                    name=tool_name,
                    arguments=arguments,
                    read_timeout_seconds=read_timeout_seconds,
                )
            except anyio.ClosedResourceError:
                logger.warning(
                    f"MCP tool {tool_name} call failed (ClosedResourceError), attempting to reconnect..."
                )
                # Attempt to reconnect
                await self._reconnect()
                # Reraise the exception to trigger tenacity retry
                raise

        return await _call_with_retry()

    async def cleanup(self) -> None:
        """Clean up resources including old exit stacks from reconnections"""
        # Close current exit stack
        try:
            await self.exit_stack.aclose()
        except Exception as e:
            logger.debug(f"Error closing current exit stack: {e}")

        # Don't close old exit stacks as they may be in different task contexts
        # They will be garbage collected naturally
        # Just clear the list to release references
        self._old_exit_stacks.clear()

        # Set running_event first to unblock any waiting tasks
        self.running_event.set()


class MCPTool(FunctionTool, Generic[TContext]):
    """A function tool that calls an MCP service."""

    def __init__(
        self, mcp_tool: mcp.Tool, mcp_client: MCPClient, mcp_server_name: str, **kwargs
    ) -> None:
        super().__init__(
            name=mcp_tool.name,
            description=mcp_tool.description or "",
            parameters=mcp_tool.inputSchema,
        )
        self.mcp_tool = mcp_tool
        self.mcp_client = mcp_client
        self.mcp_server_name = mcp_server_name

    async def call(
        self, context: ContextWrapper[TContext], **kwargs
    ) -> mcp.types.CallToolResult:
        return await self.mcp_client.call_tool_with_reconnect(
            tool_name=self.mcp_tool.name,
            arguments=kwargs,
            read_timeout_seconds=timedelta(seconds=context.tool_call_timeout),
        )
