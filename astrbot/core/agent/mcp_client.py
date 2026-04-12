import asyncio
import logging
import os
import re
import sys
from contextlib import AsyncExitStack
from datetime import timedelta
from pathlib import Path, PureWindowsPath
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

_DEFAULT_STDIO_COMMAND_ALLOWLIST = frozenset(
    {
        "python",
        "python3",
        "py",
        "node",
        "npx",
        "npm",
        "pnpm",
        "yarn",
        "bun",
        "bunx",
        "deno",
        "uv",
        "uvx",
    }
)
_DENIED_STDIO_COMMANDS = frozenset(
    {
        "bash",
        "sh",
        "zsh",
        "fish",
        "cmd",
        "cmd.exe",
        "powershell",
        "powershell.exe",
        "pwsh",
        "pwsh.exe",
        "osascript",
        "open",
        "curl",
        "wget",
        "nc",
        "netcat",
        "telnet",
        "ssh",
        "scp",
        "rm",
        "mv",
        "cp",
        "dd",
        "mkfs",
        "sudo",
        "su",
        "chmod",
        "chown",
        "kill",
        "killall",
        "shutdown",
        "reboot",
        "poweroff",
        "halt",
    }
)
_SHELL_META_RE = re.compile(r"[\r\n\x00;&|<>`$]")
_PYTHON_INLINE_CODE_FLAGS = frozenset({"-c"})
_JS_INLINE_CODE_FLAGS = frozenset({"-e", "--eval", "-p", "--print"})
_DENIED_DOCKER_ARGS = frozenset(
    {
        "--privileged",
        "--pid=host",
        "--network=host",
        "--net=host",
        "--ipc=host",
    }
)
_STDIO_ALLOWLIST_ENV = "ASTRBOT_MCP_STDIO_ALLOWED_COMMANDS"

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
        config = dict(config["mcpServers"][first_key])
    else:
        config = dict(config)
    config.pop("active", None)
    return config


def _normalize_stdio_command_name(command: str) -> str:
    command = command.strip()
    if "\\" in command:
        command_name = PureWindowsPath(command).name
    else:
        command_name = Path(command).name
    command_name = command_name.lower()
    for suffix in (".exe", ".cmd", ".bat"):
        if command_name.endswith(suffix):
            return command_name[: -len(suffix)]
    return command_name


def _get_stdio_command_allowlist() -> set[str]:
    allowed = set(_DEFAULT_STDIO_COMMAND_ALLOWLIST)
    configured = os.environ.get(_STDIO_ALLOWLIST_ENV, "")
    if configured.strip():
        allowed = {
            _normalize_stdio_command_name(item)
            for item in configured.split(",")
            if item.strip()
        }
    return allowed


def _is_stdio_config(config: dict) -> bool:
    cfg = _prepare_config(config.copy())
    return "url" not in cfg


def _validate_stdio_args(command_name: str, args: object) -> None:
    if args is None:
        return
    if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
        raise ValueError("MCP stdio args must be a list of strings.")

    for arg in args:
        if "\x00" in arg or "\r" in arg or "\n" in arg:
            raise ValueError("MCP stdio args cannot contain control characters.")

    if command_name.startswith("python") or command_name == "py":
        if any(
            arg == "-c"
            or (arg.startswith("-") and not arg.startswith("--") and "c" in arg)
            for arg in args
        ):
            raise ValueError(
                "MCP stdio Python servers must be launched from a module or file; inline code flags such as -c are not allowed."
            )
    elif command_name in {"node", "deno", "bun"} or command_name.startswith("node"):
        if any(
            arg in _JS_INLINE_CODE_FLAGS
            or arg == "eval"
            or (
                arg.startswith("-")
                and not arg.startswith("--")
                and any(c in arg for c in "ep")
            )
            for arg in args
        ):
            raise ValueError(
                "MCP stdio JavaScript servers must be launched from a package or file; inline eval flags are not allowed."
            )
    elif command_name == "docker":
        denied = []
        for i, arg in enumerate(args):
            if arg in _DENIED_DOCKER_ARGS:
                denied.append(arg)
            elif (
                arg in {"--network", "--net", "--pid", "--ipc"}
                and i + 1 < len(args)
                and args[i + 1] == "host"
            ):
                denied.append(f"{arg} {args[i + 1]}")
        if denied:
            raise ValueError(
                f"MCP stdio Docker args are unsafe and not allowed: {', '.join(denied)}."
            )


def validate_mcp_stdio_config(config: dict) -> None:
    """Validate stdio MCP config before any subprocess can be spawned."""
    cfg = _prepare_config(config.copy())
    if "url" in cfg:
        return

    command = cfg.get("command")
    if not isinstance(command, str) or not command.strip():
        raise ValueError("MCP stdio server requires a non-empty command.")
    if _SHELL_META_RE.search(command):
        raise ValueError("MCP stdio command contains unsafe shell metacharacters.")

    command_name = _normalize_stdio_command_name(command)
    if command_name in _DENIED_STDIO_COMMANDS:
        raise ValueError(f"MCP stdio command `{command_name}` is not allowed.")

    allowed = _get_stdio_command_allowlist()
    if command_name not in allowed:
        allowed_display = ", ".join(sorted(allowed))
        raise ValueError(
            f"MCP stdio command `{command_name}` is not allowed. "
            f"Allowed commands: {allowed_display}. "
            f"Set {_STDIO_ALLOWLIST_ENV} to override this list if you trust another launcher."
        )

    _validate_stdio_args(command_name, cfg.get("args"))

    env = cfg.get("env")
    if env is not None and not isinstance(env, dict):
        raise ValueError("MCP stdio env must be an object.")
    if isinstance(env, dict) and not all(
        isinstance(key, str) and isinstance(value, str) for key, value in env.items()
    ):
        raise ValueError("MCP stdio env keys and values must be strings.")


def _prepare_stdio_env(config: dict) -> dict:
    """Preserve Windows executable resolution for stdio subprocesses."""
    if sys.platform != "win32":
        return config
    prepared = config.copy()
    env = dict(prepared.get("env") or {})
    env = _merge_environment_variables(env)
    prepared["env"] = env
    return prepared


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
            validate_mcp_stdio_config(cfg)
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
