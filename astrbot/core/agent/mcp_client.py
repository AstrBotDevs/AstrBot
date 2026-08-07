import asyncio
import copy
import ipaddress
import logging
import os
import re
import socket
import sys
from contextlib import AsyncExitStack
from pathlib import Path, PureWindowsPath
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlparse

import httpx2
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

if TYPE_CHECKING:
    import anyio
    import mcp
    from mcp import ClientSession as MCPClientSession
else:
    MCPClientSession = Any

try:
    import anyio as _anyio
    import mcp as _mcp
    from mcp.client.sse import sse_client as _sse_client
except ModuleNotFoundError, ImportError:
    anyio = cast(Any, None)
    mcp = cast(Any, None)
    sse_client = cast(Any, None)
    logger.warning(
        "Warning: Missing 'mcp' dependency, MCP services will be unavailable."
    )
else:
    anyio = _anyio
    mcp = _mcp
    sse_client = _sse_client

streamable_http_client = None

try:
    from mcp.client.streamable_http import (
        streamable_http_client as streamable_http_client,
    )
except ModuleNotFoundError, ImportError:
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


def _is_truthy_config_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _allow_private_network_access(config: dict) -> bool:
    return _is_truthy_config_value(config.get("allow_private_network", False))


def _validate_remote_url(url: str, *, allow_private_network: bool = False) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("MCP remote connection URL must use http or https.")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("MCP remote connection URL must include a hostname.")
    if not allow_private_network and hostname.lower() in {
        "localhost",
        "localhost.localdomain",
    }:
        raise ValueError(
            "MCP remote connection URL cannot target private or local IP addresses."
        )
    if allow_private_network:
        return

    resolved_ips: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    try:
        resolved_ips.add(ipaddress.ip_address(hostname))
    except ValueError:
        try:
            for result in socket.getaddrinfo(
                hostname, parsed.port or 80, proto=socket.IPPROTO_TCP
            ):
                sockaddr = result[4]
                if not sockaddr:
                    continue
                resolved_ips.add(ipaddress.ip_address(sockaddr[0]))
        except socket.gaierror as exc:
            raise ValueError(
                f"MCP remote connection URL hostname could not be resolved: {hostname}"
            ) from exc

    for ip in resolved_ips:
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError(
                "MCP remote connection URL cannot target private or local IP addresses."
            )


def _create_mcp_http_client_without_redirects(
    headers: dict[str, str] | None = None,
    timeout: httpx2.Timeout | None = None,
    auth: httpx2.Auth | None = None,
) -> httpx2.AsyncClient:
    kwargs: dict[str, Any] = {"follow_redirects": False}
    if timeout is not None:
        kwargs["timeout"] = timeout
    if headers is not None:
        kwargs["headers"] = headers
    if auth is not None:
        kwargs["auth"] = auth
    return httpx2.AsyncClient(**kwargs)


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
    _validate_remote_url(
        url,
        allow_private_network=_allow_private_network_access(cfg),
    )
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
                    allow_redirects=False,
                ) as response:
                    if 300 <= response.status < 400:
                        return (
                            False,
                            "Redirect responses are not allowed for MCP endpoints",
                        )
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
                    allow_redirects=False,
                ) as response:
                    if 300 <= response.status < 400:
                        return (
                            False,
                            "Redirect responses are not allowed for MCP endpoints",
                        )
                    if response.status == 200:
                        return True, ""
                    return False, f"HTTP {response.status}: {response.reason}"

    except TimeoutError:
        return False, f"Connection timeout: {timeout} seconds"
    except Exception as e:
        return False, f"{e!s}"


def _normalize_mcp_input_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Normalize common non-standard MCP JSON Schema variants.

    Some MCP servers incorrectly mark required properties with a boolean
    `required: true` on the property schema itself. Draft 2020-12 requires the
    parent object to declare `required` as an array of property names instead.
    We lift those booleans to the parent object so the schema remains usable
    without disabling validation entirely.
    """

    def _normalize(node: Any) -> Any:
        if isinstance(node, list):
            return [_normalize(item) for item in node]

        if not isinstance(node, dict):
            return node

        normalized = {key: _normalize(value) for key, value in node.items()}

        properties = normalized.get("properties")
        if isinstance(properties, dict):
            original_properties = node.get("properties")
            if not isinstance(original_properties, dict):
                original_properties = {}
            required = normalized.get("required")
            required_list = required[:] if isinstance(required, list) else []

            for prop_name, prop_schema in properties.items():
                if not isinstance(prop_schema, dict):
                    continue

                original_prop_schema = original_properties.get(prop_name, {})
                prop_required = (
                    original_prop_schema.get("required")
                    if isinstance(original_prop_schema, dict)
                    else None
                )
                if isinstance(prop_required, bool):
                    if prop_schema.get("required") is prop_required:
                        prop_schema.pop("required", None)
                    if prop_required:
                        required_list.append(prop_name)

            if required_list:
                normalized["required"] = list(dict.fromkeys(required_list))
            elif isinstance(required, list):
                normalized.pop("required", None)

        return normalized

    return _normalize(copy.deepcopy(schema))


class MCPClient:
    def __init__(self) -> None:
        self.session: MCPClientSession | None = None

        # Each connection runs in its own task so that anyio cancel scopes
        # are always exited from the task that entered them, preventing
        #   RuntimeError: Attempted to exit cancel scope in a different task
        self._connection_task: asyncio.Task | None = None
        self._old_connection_tasks: list[asyncio.Task] = []

        # Internal; managed exclusively by _run_connection.
        self.exit_stack: AsyncExitStack | None = None

        self.name: str | None = None
        self.active: bool = True
        self.tools: list[Any] = []
        self.server_errlogs: list[str] = []
        self.running_event = asyncio.Event()

        self._mcp_server_config: dict | None = None
        self._server_name: str | None = None
        self._reconnect_lock = asyncio.Lock()  # Lock for thread-safe reconnection
        self._reconnecting: bool = False
        self._parallel_limit = 1
        self._parallel_semaphore: asyncio.Semaphore | None = None

    def configure_parallel_limit(self, limit: int) -> None:
        """Set the per-server MCP call limit used by concurrent agent batches."""
        normalized = max(1, min(8, int(limit)))
        if normalized == self._parallel_limit and self._parallel_semaphore is not None:
            return
        self._parallel_limit = normalized
        self._parallel_semaphore = asyncio.Semaphore(normalized)

    async def _run_connection(
        self,
        mcp_server_config: dict,
        name: str,
        ready: asyncio.Future,
    ) -> None:
        """Own the full lifetime of one MCP connection.

        This coroutine is always run inside a dedicated asyncio.Task
        (_connection_task).  Because *this task* is the one that enters every
        anyio cancel scope (via sse_client / streamablehttp_client), anyio's
        _host_task check is always satisfied when the stack is later closed —
        either in the task's own finally block (normal path) or when the task
        is cancelled from outside (cleanup / reconnect path).

        This avoids the
            RuntimeError: Attempted to exit cancel scope in a different task
        that previously occurred when aclose() was called from a different task
        or from the asyncio async-generator GC finalizer.
        """
        # Capture the stack in a local variable so that if self.exit_stack is
        # overwritten by a concurrent _run_connection (during reconnect), this
        # task's finally block still closes only the resources it opened.
        stack = self.exit_stack = AsyncExitStack()
        try:
            try:
                await self._do_connect(mcp_server_config, name)
            except Exception as exc:
                if not ready.done():
                    ready.set_exception(exc)
                raise
            else:
                if not ready.done():
                    ready.set_result(None)
            # Hold the connection open until cancelled.
            await asyncio.Event().wait()
        finally:
            try:
                await stack.aclose()
            except Exception as e:
                logger.debug(f"Error closing exit stack for {name}: {e}")
            # Clear the instance reference only if it still points to this task's
            # stack; a concurrent reconnect may have already replaced it.
            if self.exit_stack is stack:
                self.exit_stack = None
            # Guard against the task exiting before ready was resolved.
            if not ready.done():
                ready.set_exception(RuntimeError("Connection task exited early"))

    async def connect_to_server(self, mcp_server_config: dict, name: str) -> None:
        """Connect to MCP server by spawning a dedicated owner task.

        The owner task (_connection_task) holds the AsyncExitStack and all
        anyio cancel scopes for the lifetime of this connection.  To disconnect,
        cancel _connection_task — the finally block in _run_connection will call
        aclose() from within the correct task context.

        If `url` parameter exists:
            1. When transport is specified as `streamable_http`, use Streamable HTTP connection.
            2. When transport is specified as `sse`, use SSE connection.
            3. If not specified, default to SSE connection to MCP service.

        Args:
            mcp_server_config (dict): Configuration for the MCP server. See https://modelcontextprotocol.io/quickstart/server

        """
        self._mcp_server_config = mcp_server_config
        self._server_name = name

        ready: asyncio.Future = asyncio.get_running_loop().create_future()

        # Defensively cancel any existing connection task that was not cleaned
        # up before this call (e.g. if connect_to_server is called twice).
        if self._connection_task and not self._connection_task.done():
            self._cancel_connection_task(self._connection_task)
            self._connection_task = None

        self._connection_task = asyncio.create_task(
            self._run_connection(mcp_server_config, name, ready),
            name=f"mcp-conn:{name}",
        )

        try:
            await ready
        except asyncio.CancelledError:
            # Caller was cancelled while waiting — tear down the connection task.
            # cancel() is asynchronous; the task will not finish until the next
            # event-loop iteration, so we track it in _old_connection_tasks so
            # that cleanup() can await it later.
            if self._connection_task and not self._connection_task.done():
                self._cancel_connection_task(self._connection_task)
            self._connection_task = None
            raise
        except Exception:
            # _do_connect raised; the connection task's finally block may still
            # be running (e.g. awaiting stack.aclose()).  Track it so that
            # cleanup() can await it, but do NOT cancel it — we want the
            # finally block to finish cleaning up resources naturally.
            if self._connection_task and not self._connection_task.done():
                self._old_connection_tasks.append(self._connection_task)
            self._connection_task = None
            raise

    async def _do_connect(self, mcp_server_config: dict, name: str) -> None:
        """Internal: perform the actual connection inside _run_connection's task."""
        # exit_stack is always set by _run_connection before _do_connect is called.
        assert self.exit_stack is not None
        cfg = _prepare_config(mcp_server_config.copy())

        def logging_callback(msg: Any) -> None:
            # Handle MCP service error logs
            if (
                hasattr(msg, "level")
                and hasattr(msg, "data")
                and msg.level in ("warning", "error", "critical", "alert", "emergency")
            ):
                log_msg = f"[{str(msg.level).upper()}] {str(msg.data)}"
                self.server_errlogs.append(log_msg)

        if "url" in cfg:
            _validate_remote_url(
                cfg["url"],
                allow_private_network=_allow_private_network_access(cfg),
            )
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
                if sse_client is None or mcp is None:
                    raise RuntimeError("MCP SSE transport is unavailable.")
                self._streams_context = sse_client(
                    url=cfg["url"],
                    headers=cfg.get("headers", {}),
                    timeout=cfg.get("timeout", 5),
                    sse_read_timeout=cfg.get("sse_read_timeout", 60 * 5),
                    httpx_client_factory=_create_mcp_http_client_without_redirects,
                )
                streams = await self.exit_stack.enter_async_context(
                    self._streams_context,
                )

                # Create a new client session
                read_timeout = float(cfg.get("session_read_timeout", 60))
                self.session = await self.exit_stack.enter_async_context(
                    mcp.ClientSession(
                        *streams,
                        read_timeout_seconds=read_timeout,
                        logging_callback=logging_callback,  # type: ignore
                    ),
                )
            else:
                timeout_seconds = cfg.get("timeout", 30)
                sse_read_timeout_seconds = cfg.get("sse_read_timeout", 60 * 5)
                if streamable_http_client:
                    http_client = await self.exit_stack.enter_async_context(
                        httpx2.AsyncClient(
                            headers=cfg.get("headers", {}),
                            timeout=httpx2.Timeout(
                                timeout_seconds,
                                read=sse_read_timeout_seconds,
                            ),
                            follow_redirects=False,
                        ),
                    )
                    self._streams_context = streamable_http_client(
                        url=cfg["url"],
                        http_client=http_client,
                        terminate_on_close=cfg.get("terminate_on_close", True),
                    )
                else:
                    raise RuntimeError(
                        "Streamable HTTP transport is not available in the installed MCP library version."
                    )
                read_s, write_s = await self.exit_stack.enter_async_context(
                    self._streams_context,
                )

                # Create a new client session
                read_timeout = float(cfg.get("session_read_timeout", 60))
                self.session = await self.exit_stack.enter_async_context(
                    mcp.ClientSession(
                        read_stream=read_s,
                        write_stream=write_s,
                        read_timeout_seconds=read_timeout,
                        logging_callback=logging_callback,  # type: ignore
                    ),
                )

        else:
            if mcp is None:
                raise RuntimeError("MCP stdio transport is unavailable.")
            validate_mcp_stdio_config(cfg)
            cfg = _prepare_stdio_env(cfg)
            server_params = mcp.StdioServerParameters(
                **cfg,
            )

            def callback(msg: Any) -> None:
                # Handle MCP service error logs
                if (
                    hasattr(msg, "level")
                    and hasattr(msg, "data")
                    and msg.level
                    in ("warning", "error", "critical", "alert", "emergency")
                ):
                    log_msg = f"[{str(msg.level).upper()}] {str(msg.data)}"
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
        session = self.session
        if session is None:
            raise RuntimeError("MCP session initialization failed.")
        await session.initialize()

    async def list_tools_and_save(self) -> Any:
        """List all tools from the server and save them to self.tools"""
        if not self.session:
            raise Exception("MCP Client is not initialized")
        response = await self.session.list_tools()
        self.tools = response.tools
        return response

    def _cancel_connection_task(self, task: asyncio.Task) -> None:
        """Cancel a connection owner task and track it until it finishes."""
        # Prune already-finished tasks to avoid accumulating references over
        # many reconnections in a long-running process.
        self._old_connection_tasks = [
            t for t in self._old_connection_tasks if not t.done()
        ]
        if task.done():
            return
        task.cancel()
        self._old_connection_tasks.append(task)

    async def _reconnect(self) -> None:
        """Reconnect to the MCP server using the stored configuration.

        Cancels the current _connection_task (which owns the exit_stack and all
        anyio cancel scopes) and starts a fresh one.  Because each connection
        task enters and exits its own anyio cancel scope, there is no
        cross-task cancel-scope violation and no GC finalizer surprise.

        Uses asyncio.Lock to ensure thread-safe reconnection in concurrent environments.

        Raises:
            Exception: raised when reconnection fails
        """
        async with self._reconnect_lock:
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

                # Cancel the old connection task.  Its finally block will call
                # exit_stack.aclose() from within the correct task context, so
                # anyio cancel scopes are exited cleanly without triggering the
                # GC-finalizer busy-spin bug.
                if self._connection_task and not self._connection_task.done():
                    self._cancel_connection_task(self._connection_task)
                self._connection_task = None
                self.session = None

                # Reconnect — this creates a new _connection_task.
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
        read_timeout_seconds: float,
    ) -> Any:
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

        closed_resource_error = getattr(anyio, "ClosedResourceError", RuntimeError)

        @retry(
            retry=retry_if_exception_type(closed_resource_error),
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
            except closed_resource_error:
                logger.warning(
                    f"MCP tool {tool_name} call failed (ClosedResourceError), attempting to reconnect..."
                )
                # Attempt to reconnect
                await self._reconnect()
                # Reraise the exception to trigger tenacity retry
                raise

        if self._parallel_semaphore is None:
            self.configure_parallel_limit(1)
        assert self._parallel_semaphore is not None
        async with self._parallel_semaphore:
            return await _call_with_retry()

    async def cleanup(self) -> None:
        """Clean up resources by cancelling the connection owner task."""
        # Cancel current and any old connection tasks via the shared helper so
        # all cancellation + tracking behaviour goes through one code path.
        if self._connection_task:
            self._cancel_connection_task(self._connection_task)
            self._connection_task = None

        if self._old_connection_tasks:
            pending = [t for t in self._old_connection_tasks if not t.done()]
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            self._old_connection_tasks.clear()

        # Set running_event to unblock any waiting tasks
        self.running_event.set()


class MCPTool[TContext](FunctionTool):
    """A function tool that calls an MCP service."""

    def __init__(
        self, mcp_tool: Any, mcp_client: MCPClient, mcp_server_name: str, **kwargs
    ) -> None:
        super().__init__(
            name=mcp_tool.name,
            description=mcp_tool.description or "",
            parameters=_normalize_mcp_input_schema(mcp_tool.inputSchema),
        )
        self.mcp_tool = mcp_tool
        self.mcp_client = mcp_client
        self.mcp_server_name = mcp_server_name

    async def call(self, context: ContextWrapper[TContext], **kwargs) -> Any:
        return await self.mcp_client.call_tool_with_reconnect(
            tool_name=self.mcp_tool.name,
            arguments=kwargs,
            read_timeout_seconds=context.tool_call_timeout,
        )
