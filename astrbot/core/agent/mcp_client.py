"""
MCP client - DEPRECATED

.. deprecated::
    This module has been moved to :mod:`astrbot._internal.mcp`.
    Please update your imports accordingly.

    Old import (deprecated):
        from astrbot.core.agent.mcp_client import MCPClient, MCPTool

    New import:
        from astrbot._internal.mcp import MCPClient, MCPTool

This file exists solely for backward compatibility and will be removed in a future version.
"""

import asyncio
import copy
import logging
import os
import re
import sys
import warnings
from contextlib import AsyncExitStack
from datetime import timedelta
from typing import Any, Generic
from urllib.parse import quote

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from astrbot.core.agent.mcp_prompt_bridge import build_mcp_prompt_tool_names
from astrbot.core.agent.run_context import ContextWrapper, TContext
from astrbot.core.utils.log_pipe import LogPipe

from .mcp_elicitation_registry import cleanup_elicitation_periodically
from .mcp_oauth import create_mcp_http_auth, has_mcp_oauth_config
from .mcp_resource_bridge import build_mcp_resource_tool_names
from .mcp_stdio_client import tolerant_stdio_client
from .mcp_subcapability_bridge import (
    MCPClientSubCapabilityBridge,
    normalize_mcp_server_config,
)
from .tool import FunctionTool

logger = logging.getLogger("astrbot")

_STDIO_ALLOWLIST_ENV = "ASTRBOT_MCP_STDIO_ALLOWLIST"
_DEFAULT_STDIO_COMMAND_ALLOWLIST = {
    "uv",
    "uvx",
    "python",
    "python3",
    "py",
    "node",
    "npx",
    "pnpm",
    "bun",
    "deno",
    "docker",
}
_DENIED_STDIO_COMMANDS = {"cmd", "powershell", "pwsh", "sh", "bash", "wsl"}
_DENIED_DOCKER_ARGS = {"--privileged"}
_JS_INLINE_CODE_FLAGS = {"-e", "--eval", "-p", "--print"}
_SHELL_META_RE = re.compile(r"[;&|<>`$]")

warnings.warn(
    "astrbot.core.agent.mcp_client has been moved to astrbot._internal.mcp. "
    "Please update your imports.",
    DeprecationWarning,
    stacklevel=2,
)
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


try:
    import httpx as _httpx

    def _create_no_verify_httpx_client(
        headers: dict[str, str] | None = None,
        timeout: _httpx.Timeout | None = None,
        auth: _httpx.Auth | None = None,
    ) -> _httpx.AsyncClient:
        kwargs: dict[str, Any] = {
            "follow_redirects": True,
            "verify": False,
        }
        if timeout is None:
            kwargs["timeout"] = _httpx.Timeout(30, read=300)
        else:
            kwargs["timeout"] = timeout
        if headers is not None:
            kwargs["headers"] = headers
        if auth is not None:
            kwargs["auth"] = auth
        return _httpx.AsyncClient(**kwargs)

except (ModuleNotFoundError, ImportError):
    _create_no_verify_httpx_client = None


class TenacityLogger:
    """Wraps a logging.Logger to satisfy tenacity's LoggerProtocol."""

    __slots__ = ("_logger",)
    _logger: logging.Logger

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def log(
        self,
        level: int,
        msg: str,
        /,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        self._logger.log(level, msg, *args, **kwargs)


def _prepare_config(config: dict) -> dict:
    """Prepare configuration, handle nested format"""
    if config.get("mcpServers"):
        first_key = next(iter(config["mcpServers"]))
        config = config["mcpServers"][first_key]
    config = normalize_mcp_server_config(config)
    config.pop("active", None)
    config.pop("client_capabilities", None)
    config.pop("provider", None)
    return config


def _prepare_stdio_env(config: dict) -> dict:
    """Preserve Windows executable resolution for stdio subprocesses."""
    if sys.platform != "win32":
        return config

    pathext = os.environ.get("PATHEXT")
    if not pathext:
        return config

    prepared = config.copy()
    env = dict(prepared.get("env") or {})
    env.setdefault("PATHEXT", pathext)
    prepared["env"] = env
    return prepared


def _normalize_stdio_command_name(command: str) -> str:
    command_name = os.path.basename(command.strip().replace("\\", "/")).lower()
    for suffix in (".exe", ".cmd", ".bat"):
        if command_name.endswith(suffix):
            return command_name[: -len(suffix)]
    return command_name


def _get_stdio_command_allowlist() -> set[str]:
    configured = os.environ.get(_STDIO_ALLOWLIST_ENV, "")
    if configured.strip():
        return {
            _normalize_stdio_command_name(item)
            for item in configured.split(",")
            if item.strip()
        }
    return set(_DEFAULT_STDIO_COMMAND_ALLOWLIST)


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
    """Validate stdio MCP config before a subprocess can be spawned."""
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


_NONSTANDARD_TYPE_MAP: dict[str, str] = {
    "int": "integer",
    "float": "number",
    "double": "number",
    "decimal": "number",
    "bool": "boolean",
    "str": "string",
    "dict": "object",
    "list": "array",
}


def _normalize_mcp_input_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Normalize common non-standard MCP JSON Schema variants."""

    def _normalize(node: Any) -> Any:
        if isinstance(node, list):
            return [_normalize(item) for item in node]

        if not isinstance(node, dict):
            return node

        normalized = {key: _normalize(value) for key, value in node.items()}

        type_val = normalized.get("type")
        if isinstance(type_val, str) and type_val in _NONSTANDARD_TYPE_MAP:
            normalized["type"] = _NONSTANDARD_TYPE_MAP[type_val]
        elif isinstance(type_val, list):
            normalized["type"] = [
                _NONSTANDARD_TYPE_MAP.get(t, t) if isinstance(t, str) else t
                for t in type_val
            ]

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


class _EmptyMCPArgument:
    pass


_EMPTY_MCP_ARGUMENT = _EmptyMCPArgument()


def _sanitize_mcp_arguments(
    value: Any,
    schema: dict[str, Any] | None = None,
    *,
    required: bool = False,
) -> Any:
    """Remove empty optional payload values before sending to MCP tools."""
    if value is None:
        return value if required else _EMPTY_MCP_ARGUMENT

    if isinstance(value, str):
        return value if value != "" or required else _EMPTY_MCP_ARGUMENT

    if isinstance(value, list):
        if not value:
            return value if required else _EMPTY_MCP_ARGUMENT
        item_schema = schema.get("items") if isinstance(schema, dict) else None
        cleaned_items = []
        for item in value:
            cleaned_item = _sanitize_mcp_arguments(item, item_schema)
            cleaned_items.append(item if cleaned_item is _EMPTY_MCP_ARGUMENT else cleaned_item)
        return cleaned_items

    if isinstance(value, dict):
        if not value:
            return value if required else _EMPTY_MCP_ARGUMENT

        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        required_names = schema.get("required", []) if isinstance(schema, dict) else []
        if not isinstance(properties, dict):
            properties = {}
        if not isinstance(required_names, list):
            required_names = []

        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            item_required = key in required_names
            item_schema = properties.get(key)
            cleaned_item = _sanitize_mcp_arguments(
                item,
                item_schema if isinstance(item_schema, dict) else None,
                required=item_required,
            )
            if cleaned_item is not _EMPTY_MCP_ARGUMENT:
                cleaned[key] = cleaned_item
        if not cleaned:
            return value if required else _EMPTY_MCP_ARGUMENT
        return cleaned

    return value


class MCPClient(Generic[TContext]):
    def __init__(self) -> None:
        self.session: mcp.ClientSession | None = None

        # Each connection runs in its own task so that anyio cancel scopes
        # are always exited from the task that entered them, preventing
        #   RuntimeError: Attempted to exit cancel scope in a different task
        self._connection_task: asyncio.Task | None = None
        self._old_connection_tasks: list[asyncio.Task] = []

        # Internal; managed exclusively by _run_connection.
        self.exit_stack: AsyncExitStack | None = None

        self.name: str | None = None
        self.active: bool = True
        self.tools: list[mcp.Tool] = []
        self.prompts: list[mcp.types.Prompt] = []
        self.prompt_bridge_tool_names: list[str] = []
        self.resources: list[mcp.types.Resource] = []
        self.resource_templates: list[mcp.types.ResourceTemplate] = []
        self.resource_templates_supported: bool = False
        self.resource_bridge_tool_names: list[str] = []
        self.server_errlogs: list[str] = []
        self.running_event = asyncio.Event()
        self.process_pid: int | None = None

        self._mcp_server_config: dict | None = None
        self._server_name: str | None = None
        self._server_capabilities: mcp.types.ServerCapabilities | None = None
        self._streams_context: Any = None
        self._reconnect_lock = asyncio.Lock()  # Lock for thread-safe reconnection
        self._reconnecting: bool = False  # For logging and debugging
        self.subcapability_bridge = MCPClientSubCapabilityBridge[TContext]()

        # Elicitation cleanup task
        self._elicitation_cleanup_task: asyncio.Task[None] | None = None
        self._start_elicitation_cleanup()

    def _start_elicitation_cleanup(self) -> None:
        """启动后台 elicitation 清理任务。"""
        self._elicitation_cleanup_task = asyncio.create_task(
            cleanup_elicitation_periodically(interval=60),
            name="mcp-elicitation-cleanup",
        )
        logger.debug("已启动 MCP elicitation 后台清理任务")

    @staticmethod
    def _extract_stdio_process_pid(streams_context: object) -> int | None:
        """Best-effort extraction for stdio subprocess PID used by lease cleanup.

        TODO(refactor): replace this async-generator frame introspection with a
        stable MCP library hook once the upstream transport exposes process PID.
        """
        generator = getattr(streams_context, "gen", None)
        frame = getattr(generator, "ag_frame", None)
        if frame is None:
            return None
        process = frame.f_locals.get("process")
        pid = getattr(process, "pid", None)
        try:
            return int(pid) if pid is not None else None
        except (TypeError, ValueError):
            return None
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
        self.subcapability_bridge.set_server_name(name)
        self.subcapability_bridge.configure_from_server_config(mcp_server_config)
        self.process_pid = None

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

        def logging_callback(
            msg: str | mcp.types.LoggingMessageNotificationParams,
        ) -> None:
            # Handle MCP service error logs
            if isinstance(msg, mcp.types.LoggingMessageNotificationParams):
                if msg.level in ("warning", "error", "critical", "alert", "emergency"):
                    log_msg = f"[{msg.level.upper()}] {msg.data!s}"
                    self.server_errlogs.append(log_msg)

        if "url" in cfg:
            auth = await create_mcp_http_auth(cfg)

            if not has_mcp_oauth_config(cfg):
                success, error_msg = await _quick_test_mcp_connection(cfg)
                if not success:
                    raise Exception(error_msg)

            if "transport" in cfg:
                transport_type = cfg["transport"]
            elif "type" in cfg:
                transport_type = cfg["type"]
            else:
                raise Exception("MCP connection config missing transport or type field")

            http_client_kwargs: dict[str, Any] = {
                "url": cfg["url"],
                "headers": cfg.get("headers", {}),
            }
            if auth is not None:
                http_client_kwargs["auth"] = auth
            if _create_no_verify_httpx_client is not None:
                http_client_kwargs["httpx_client_factory"] = (
                    _create_no_verify_httpx_client
                )

            if transport_type != "streamable_http":
                # SSE transport method
                http_client_kwargs["timeout"] = cfg.get("timeout", 5)
                http_client_kwargs["sse_read_timeout"] = cfg.get(
                    "sse_read_timeout",
                    60 * 5,
                )
                self._streams_context = sse_client(**http_client_kwargs)
                streams = await self.exit_stack.enter_async_context(
                    self._streams_context,
                )

                # Create a new client session
                read_timeout = timedelta(seconds=cfg.get("session_read_timeout", 60))
                self.session = await self.exit_stack.enter_async_context(
                    mcp.ClientSession(
                        *streams,
                        read_timeout_seconds=read_timeout,
                        logging_callback=logging_callback,  # type: ignore[arg-type]
                        sampling_callback=(
                            self.subcapability_bridge.handle_sampling
                            if self.subcapability_bridge.sampling_enabled
                            else None
                        ),
                        elicitation_callback=(
                            self.subcapability_bridge.handle_elicitation
                            if self.subcapability_bridge.elicitation_enabled
                            else None
                        ),
                        list_roots_callback=(
                            self.subcapability_bridge.handle_list_roots
                            if self.subcapability_bridge.roots_enabled
                            else None
                        ),
                        sampling_capabilities=self.subcapability_bridge.get_sampling_capabilities(),
                    ),
                )
            else:
                http_client_kwargs["timeout"] = timedelta(
                    seconds=cfg.get("timeout", 30)
                )
                http_client_kwargs["sse_read_timeout"] = timedelta(
                    seconds=cfg.get("sse_read_timeout", 60 * 5),
                )
                http_client_kwargs["terminate_on_close"] = cfg.get(
                    "terminate_on_close",
                    True,
                )
                self._streams_context = streamablehttp_client(**http_client_kwargs)
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
                        logging_callback=logging_callback,  # type: ignore[arg-type]
                        sampling_callback=(
                            self.subcapability_bridge.handle_sampling
                            if self.subcapability_bridge.sampling_enabled
                            else None
                        ),
                        elicitation_callback=(
                            self.subcapability_bridge.handle_elicitation
                            if self.subcapability_bridge.elicitation_enabled
                            else None
                        ),
                        list_roots_callback=(
                            self.subcapability_bridge.handle_list_roots
                            if self.subcapability_bridge.roots_enabled
                            else None
                        ),
                        sampling_capabilities=self.subcapability_bridge.get_sampling_capabilities(),
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
                        log_msg = f"[{msg.level.upper()}] {msg.data!s}"
                        self.server_errlogs.append(log_msg)

            stdio_transport = await self.exit_stack.enter_async_context(
                tolerant_stdio_client(
                    server_params,
                    errlog=LogPipe(
                        level=logging.INFO,
                        logger=logger,
                        identifier=f"MCPServer-{name}",
                        callback=callback,
                    ),
                ),
            )
            self.process_pid = self._extract_stdio_process_pid(stdio_transport)

            # Create a new client session
            self.session = await self.exit_stack.enter_async_context(
                mcp.ClientSession(
                    *stdio_transport,
                    sampling_callback=(
                        self.subcapability_bridge.handle_sampling
                        if self.subcapability_bridge.sampling_enabled
                        else None
                    ),
                    elicitation_callback=(
                        self.subcapability_bridge.handle_elicitation
                        if self.subcapability_bridge.elicitation_enabled
                        else None
                    ),
                    list_roots_callback=(
                        self.subcapability_bridge.handle_list_roots
                        if self.subcapability_bridge.roots_enabled
                        else None
                    ),
                    sampling_capabilities=self.subcapability_bridge.get_sampling_capabilities(),
                ),
            )
        await self.session.initialize()
        get_server_capabilities = getattr(
            self.session,
            "get_server_capabilities",
            None,
        )
        self._server_capabilities = (
            get_server_capabilities() if callable(get_server_capabilities) else None
        )
        self.resources = []
        self.resource_templates = []
        self.resource_templates_supported = False
        self.prompts = []
        self.prompt_bridge_tool_names = []
        self.resource_bridge_tool_names = []

    async def list_tools_and_save(self) -> mcp.ListToolsResult:
        """List all tools from the server and save them to self.tools"""
        if not self.session:
            raise Exception("MCP Client is not initialized")
        response = await self.session.list_tools()
        self.tools = response.tools
        return response

    @property
    def supports_resources(self) -> bool:
        return bool(self._server_capabilities and self._server_capabilities.resources)

    @property
    def supports_prompts(self) -> bool:
        return bool(self._server_capabilities and self._server_capabilities.prompts)

    async def load_resource_capabilities(self) -> None:
        self.resources = []
        self.resource_templates = []
        self.resource_templates_supported = False
        self.resource_bridge_tool_names = []

        if not self._server_name or not self.supports_resources:
            return

        try:
            await self.list_resources_and_save()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to preload MCP resources for server %s: %s",
                self._server_name,
                exc,
            )

        try:
            await self.list_resource_templates_and_save()
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Skipping MCP resource templates for server %s: %s",
                self._server_name,
                exc,
            )

        self.resource_bridge_tool_names = build_mcp_resource_tool_names(
            self._server_name,
            include_templates=self.resource_templates_supported,
        )

    async def load_prompt_capabilities(self) -> None:
        self.prompts = []
        self.prompt_bridge_tool_names = []

        if not self._server_name or not self.supports_prompts:
            return

        try:
            await self.list_prompts_and_save()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to preload MCP prompts for server %s: %s",
                self._server_name,
                exc,
            )

        self.prompt_bridge_tool_names = build_mcp_prompt_tool_names(
            self._server_name,
        )

    async def list_prompts_and_save(
        self,
        cursor: str | None = None,
    ) -> mcp.types.ListPromptsResult:
        if not self.session:
            raise ValueError("MCP session is not available for prompt listing.")

        params = (
            mcp.types.PaginatedRequestParams(cursor=cursor)
            if cursor is not None
            else None
        )
        response = await self.session.list_prompts(params=params)
        if cursor is None:
            self.prompts = response.prompts
        return response

    async def list_resources_and_save(
        self,
        cursor: str | None = None,
    ) -> mcp.types.ListResourcesResult:
        if not self.session:
            raise ValueError("MCP session is not available for resource listing.")

        params = (
            mcp.types.PaginatedRequestParams(cursor=cursor)
            if cursor is not None
            else None
        )
        response = await self.session.list_resources(params=params)
        if cursor is None:
            self.resources = response.resources
        return response

    async def list_resource_templates_and_save(
        self,
        cursor: str | None = None,
    ) -> mcp.types.ListResourceTemplatesResult:
        if not self.session:
            raise ValueError(
                "MCP session is not available for resource template listing."
            )

        params = (
            mcp.types.PaginatedRequestParams(cursor=cursor)
            if cursor is not None
            else None
        )
        response = await self.session.list_resource_templates(params=params)
        self.resource_templates_supported = True
        if cursor is None:
            self.resource_templates = response.resourceTemplates
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
                self.subcapability_bridge.clear_runtime_state()

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
                await self.load_resource_capabilities()
                await self.load_prompt_capabilities()

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
        run_context: ContextWrapper[TContext] | None = None,
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

        tool_schema = next(
            (tool.inputSchema for tool in self.tools if tool.name == tool_name),
            None,
        )
        sanitized_arguments = _sanitize_mcp_arguments(arguments, tool_schema)
        if sanitized_arguments is _EMPTY_MCP_ARGUMENT:
            sanitized_arguments = {}
        if sanitized_arguments != arguments:
            logger.debug(
                "Sanitized MCP tool %s arguments from %s to %s",
                tool_name,
                arguments,
                sanitized_arguments,
            )

        @retry(
            retry=retry_if_exception_type(anyio.ClosedResourceError),
            stop=stop_after_attempt(2),
            wait=wait_exponential(multiplier=1, min=1, max=3),
            before_sleep=before_sleep_log(TenacityLogger(logger), logging.WARNING),
            reraise=True,
        )
        async def _call_with_retry():
            async with self.subcapability_bridge.interactive_call(run_context):
                if not self.session:
                    raise ValueError(
                        "MCP session is not available for MCP function tools."
                    )

                try:
                    return await self.session.call_tool(
                        name=tool_name,
                        arguments=sanitized_arguments,
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

    async def read_resource_with_reconnect(
        self,
        uri: str,
        read_timeout_seconds: timedelta,
    ) -> mcp.types.ReadResourceResult:
        _ = read_timeout_seconds

        @retry(
            retry=retry_if_exception_type(anyio.ClosedResourceError),
            stop=stop_after_attempt(2),
            wait=wait_exponential(multiplier=1, min=1, max=3),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        async def _read_with_retry():
            if not self.session:
                raise ValueError("MCP session is not available for MCP resources.")

            try:
                return await self.session.read_resource(uri=uri)
            except anyio.ClosedResourceError:
                logger.warning(
                    "MCP resource read for %s failed (ClosedResourceError), attempting to reconnect...",
                    uri,
                )
                await self._reconnect()
                raise

        return await _read_with_retry()

    async def get_prompt_with_reconnect(
        self,
        name: str,
        arguments: dict[str, str] | None,
        read_timeout_seconds: timedelta,
    ) -> mcp.types.GetPromptResult:
        @retry(
            retry=retry_if_exception_type(anyio.ClosedResourceError),
            stop=stop_after_attempt(2),
            wait=wait_exponential(multiplier=1, min=1, max=3),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        async def _get_with_retry():
            if not self.session:
                raise ValueError("MCP session is not available for MCP prompts.")

            try:
                return await self.session.get_prompt(
                    name=name,
                    arguments=arguments,
                )
            except anyio.ClosedResourceError:
                logger.warning(
                    "MCP prompt read for %s failed (ClosedResourceError), attempting to reconnect...",
                    name,
                )
                await self._reconnect()
                raise

        _ = read_timeout_seconds
        return await _get_with_retry()

    async def cleanup(self) -> None:
        """Clean up resources by cancelling the connection owner task."""
        self.subcapability_bridge.clear_runtime_state()
        self._server_capabilities = None
        self.prompts = []
        self.prompt_bridge_tool_names = []
        self.resources = []
        self.resource_templates = []
        self.resource_templates_supported = False
        self.resource_bridge_tool_names = []

        # Cancel elicitation cleanup task
        if self._elicitation_cleanup_task:
            self._elicitation_cleanup_task.cancel()
            try:
                await self._elicitation_cleanup_task
            except asyncio.CancelledError:
                logger.debug("Elicitation cleanup task cancelled")

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
        self.process_pid = None


class MCPTool(FunctionTool, Generic[TContext]):
    """A function tool that calls an MCP service."""

    def __init__(
        self, mcp_tool: mcp.Tool, mcp_client: MCPClient, mcp_server_name: str, **kwargs
    ) -> None:
        normalized_server_name = quote(mcp_server_name, safe="")
        namespaced_name = f"mcp_{normalized_server_name}__{mcp_tool.name}"
        super().__init__(
            name=namespaced_name,
            description=mcp_tool.description or "",
            parameters=_normalize_mcp_input_schema(mcp_tool.inputSchema),
        )
        self.mcp_tool = mcp_tool
        self.mcp_client = mcp_client
        self.mcp_server_name = mcp_server_name
        self.original_tool_name = mcp_tool.name
        self.source = "mcp"

    async def call(
        self, context: ContextWrapper[TContext], **kwargs
    ) -> mcp.types.CallToolResult:
        return await self.mcp_client.call_tool_with_reconnect(
            tool_name=self.mcp_tool.name,
            arguments=kwargs,
            read_timeout_seconds=timedelta(seconds=context.tool_call_timeout),
            run_context=context,
        )
