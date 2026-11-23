from __future__ import annotations

import asyncio
import copy
import hashlib
import inspect
import json
import os
import threading
import urllib.parse
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import aiohttp
from deprecated import deprecated

from astrbot import logger
from astrbot.core import sp
from astrbot.core.agent.mcp_client import MCPClient, MCPTool, _prepare_config
from astrbot.core.agent.tool import FunctionTool, ToolSchema, ToolSet
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

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


class _MCPClientDictView(Mapping[str, MCPClient]):
    """Read-only view of MCP clients derived from runtime state."""

    def __init__(self, runtime: dict[str, _MCPServerRuntime]) -> None:
        self._runtime = runtime

    def __getitem__(self, key: str) -> MCPClient:
        return self._runtime[key].client

    def __iter__(self):
        return iter(self._runtime)

    def __len__(self) -> int:
        return len(self._runtime)


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
    except (TypeError, ValueError):
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
# alias
FuncTool = FunctionTool


async def _quick_test_mcp_connection(config: dict) -> tuple[bool, str]:
    """快速测试 MCP 服务器可达性"""
    import aiohttp

    cfg = _prepare_config(config.copy())

    url = cfg["url"]
    headers = cfg.get("headers", {})
    timeout = cfg.get("timeout", 10)

    try:
        async with aiohttp.ClientSession() as session:
            if cfg.get("transport") == "streamable_http":
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

    except TimeoutError:
        return False, f"连接超时: {timeout}秒"
    except Exception as e:
        return False, f"{e!s}"


class _PermissionGuardedTool(FunctionTool):
    """Transparent proxy that checks per-tool permissions before delegating.

    Only wraps tools contributed to the manager by plugins and MCP servers.

    The ``handler`` field is intentionally kept ``None`` so that
    ``FunctionToolExecutor._execute_local`` falls through to the
    ``is_override_call`` branch and invokes our ``call()`` instead of
    calling the raw handler directly.  This ensures the permission
    check runs for *every* invocation path.
    """

    def __init__(
        self,
        tool: FunctionTool,
        manager: FunctionToolManager,
    ) -> None:
        # Do NOT pass handler to the parent — keep self.handler = None
        # so the tool executor always routes through our call().
        super().__init__(
            name=tool.name,
            description=tool.description,
            parameters=getattr(tool, "parameters", {}),
            execution_timeout=tool.execution_timeout,
        )
        self._wrapped = tool
        self._mgr = manager
        # Mirror mutable state from the underlying tool
        self.active = getattr(tool, "active", True)
        self.handler_module_path = getattr(tool, "handler_module_path", None)

    @staticmethod
    async def _invoke_handler(
        handler: Callable[..., Any], event: Any, /, **kwargs: Any
    ) -> Any:
        """Complete synchronous, awaitable, or streamed legacy handler results."""
        result = handler(event, **kwargs)
        if inspect.isasyncgen(result):
            last: Any = None
            async for item in result:
                last = item
            return last
        if inspect.isawaitable(result):
            return await result
        return result

    async def call(self, context: Any, **kwargs: Any) -> Any:
        error = await self._mgr._check_tool_permission(
            self.name, context, tool_key=self._mgr.get_tool_key(self._wrapped)
        )
        if error is not None:
            return error

        # @filter.llm_tool decorated tools have a handler attribute, which is the actual callable.
        if self._wrapped.handler is not None:
            return await self._invoke_handler(
                self._wrapped.handler, context.context.event, **kwargs
            )

        # If the tool has a "call" method that is not the default FunctionTool.call, invoke it.
        call_override = getattr(type(self._wrapped), "call", None)
        if call_override is not None and call_override is not FunctionTool.call:
            return await self._wrapped.call(context, **kwargs)

        # Compatibility fallback: if the tool has a "run" method, invoke it. This is for legacy tools that don't use the new handler/call interface.
        run = getattr(self._wrapped, "run", None)
        if run is not None:
            return await self._invoke_handler(run, context.context.event, **kwargs)

        return "error: tool has no callable handler"


class FunctionToolManager:
    def __init__(self) -> None:
        self.func_list: list[FuncTool] = []
        """Tools contributed by plugins and MCP servers."""

        self._mcp_server_runtime: dict[str, _MCPServerRuntime] = {}
        """MCP runtime metadata, keyed by server name. Updated atomically on MCP lifecycle changes."""
        self._mcp_server_runtime_view = MappingProxyType(self._mcp_server_runtime)
        self._mcp_client_dict_view = _MCPClientDictView(self._mcp_server_runtime)
        self._timeout_mismatch_warned = False
        self._timeout_warn_lock = threading.Lock()
        self._runtime_lock = asyncio.Lock()
        self._tool_state_lock = asyncio.Lock()
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
    def mcp_client_dict(self) -> Mapping[str, MCPClient]:
        """Read-only compatibility view for external callers that still read mcp_client_dict.

        Note: Mutating this mapping is unsupported and will raise TypeError.
        """
        return self._mcp_client_dict_view

    @property
    def mcp_server_runtime_view(self) -> Mapping[str, _MCPServerRuntime]:
        """Read-only view of MCP runtime metadata for external callers."""
        return self._mcp_server_runtime_view

    @property
    @deprecated(reason="Use mcp_server_runtime_view instead.")
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
        handler: Callable[..., Awaitable[Any] | AsyncGenerator[Any]],
    ) -> FuncTool:
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
        handler: Callable[..., Awaitable[Any] | AsyncGenerator[Any]],
    ) -> None:
        """添加函数调用工具

        @param name: 函数名
        @param func_args: 函数参数列表，格式为 [{"type": "string", "name": "arg_name", "description": "arg_description"}, ...]
        @param desc: 函数描述
        @param func_obj: 处理函数
        """
        # check if the tool has been added before
        self.remove_func(name)

        self.func_list.append(
            self.spec_to_func(
                name=name,
                func_args=func_args,
                desc=desc,
                handler=handler,
            ),
        )
        logger.info(f"Added llm tool: {name}")

    def remove_func(self, name: str) -> None:
        """删除一个函数调用工具。"""
        for i, f in enumerate(self.func_list):
            if f.name == name:
                self.func_list.pop(i)
                break

    def get_func(self, name) -> FuncTool | None:
        # 优先返回已激活的工具（后加载的覆盖前面的，与 ToolSet.add_tool 保持一致）
        # 使用 getattr(..., True) 与 ToolSet.add_tool 保持一致：没有 active 属性的工具视为已激活
        for f in reversed(self.func_list):
            if f.name == name and getattr(f, "active", True):
                return f
        # 退化则拿最后一个同名工具
        for f in reversed(self.func_list):
            if f.name == name:
                return f
        return None

    @staticmethod
    def get_tool_key(tool: FuncTool) -> str:
        """Build a stable identity from the registered tool's source and owner."""
        source = "mcp" if isinstance(tool, MCPTool) else tool.source
        if isinstance(tool, MCPTool):
            owner = tool.mcp_server_name
        else:
            owner = (
                tool.handler_module_path
                or getattr(tool.handler, "__module__", None)
                or f"{type(tool).__module__}.{type(tool).__qualname__}"
            )
        identity = json.dumps(
            [source, owner, tool.name], ensure_ascii=False, separators=(",", ":")
        )
        return "tool:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def resolve_tool(
        self, name: str | None = None, *, tool_key: str | None = None
    ) -> FuncTool | None:
        """Resolve a management selector without runtime name precedence."""
        if name and name.startswith("tool:") and tool_key is None:
            tool_key, name = name, None
        if not name and not tool_key:
            return None
        matches = [
            tool
            for tool in self.func_list
            if (name is None or tool.name == name)
            and (tool_key is None or self.get_tool_key(tool) == tool_key)
        ]
        if len(matches) > 1:
            raise ValueError("Ambiguous tool identity; provide a unique tool_key")
        return matches[0] if matches else None

    @classmethod
    def is_tool_active(
        cls, tool: FuncTool, inactivated_llm_tools: list, tool_states: object
    ) -> bool:
        """Apply exact state overrides before the legacy name blacklist."""
        override = (
            tool_states.get(cls.get_tool_key(tool))
            if isinstance(tool_states, dict)
            else None
        )
        if isinstance(override, bool):
            return override
        return tool.name not in inactivated_llm_tools

    async def set_tool_active(
        self, tool_key: str, active: bool, star_map: dict
    ) -> bool:
        """Persist an exact tool state before changing the registered object."""
        async with self._tool_state_lock:
            tool = self.resolve_tool(tool_key=tool_key)
            if tool is None:
                return False
            if tool.source in ("native", "internal"):
                raise ValueError("Native and internal tools are managed by the runtime")
            plugin = star_map.get(tool.handler_module_path)
            if active and plugin is not None and not plugin.activated:
                raise ValueError(
                    f"Plugin {plugin.name} is disabled; enable it before its tool"
                )
            stored = await sp.global_get("llm_tool_states", {})
            states = dict(stored) if isinstance(stored, dict) else {}
            states[tool_key] = active
            await sp.global_put("llm_tool_states", states)
            tool.active = active
            return True

    def _default_permission(self, tool_name: str) -> str:
        """Compute the fallback permission for a plugin or MCP tool.

        Tools default to ``"member"`` when no restriction is configured."""
        return "member"

    async def _check_tool_permission(
        self,
        tool_name: str,
        context: Any,
        *,
        tool_key: str | None = None,
    ) -> str | None:
        """Return an error string if the caller lacks permission, or None.

        Permission is resolved from
        ``tool_permissions`` in SharedPreferences (``_default`` key). When
        no explicit entry exists the tool inherits the fallback
        ``_default_permission``."""
        try:
            perms_raw = await sp.global_get("tool_permissions", {})
        except Exception:
            perms_raw = {}
        defaults = perms_raw.get("_default", {}) if isinstance(perms_raw, dict) else {}
        if not isinstance(defaults, dict):
            defaults = {}
        effective = defaults.get(tool_key, defaults.get(tool_name))
        if effective is None:
            effective = self._default_permission(tool_name)

        if effective != "admin":
            return None  # member or unknown → pass

        try:
            event = context.context.event
        except AttributeError:
            event = None
        from astrbot.core.agent.runtime import get_agent_permissions

        if event is None or not get_agent_permissions(context).is_admin:
            sender_id = getattr(event, "get_sender_id", lambda: "unknown")()
            return (
                f"error: Permission denied. The tool '{tool_name}' requires admin "
                f"privileges. Your ID: {sender_id}. "
                "Ask admin to configure in WebUI → Extension → Components."
            )
        return None

    def get_full_tool_set(self) -> ToolSet:
        """Return the registered plugin and MCP tools with permission checks.

        Returns:
            A tool set that prefers active tools and uses the latest registration
            when tools with the same name have the same active state.
        """
        tool_set = ToolSet()
        for tool in self.func_list:
            tool_set.add_tool(_PermissionGuardedTool(tool, self))
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

        mcp_client = MCPClient()
        mcp_client.name = name

        connect_done = asyncio.Event()
        connect_error: BaseException | None = None

        async def connect_and_lifecycle() -> None:
            # Single task that handles connect, lifecycle, and cleanup.

            nonlocal connect_error
            try:
                await mcp_client.connect_to_server(cfg, name)
                await mcp_client.list_tools_and_save()
            except asyncio.CancelledError:
                # cleanup on cancellation
                try:
                    await mcp_client.cleanup()
                except BaseException:
                    pass
                raise
            except Exception as e:
                connect_error = e
                try:
                    await mcp_client.cleanup()
                except Exception:
                    pass
                connect_done.set()
                return

            # Register tools
            self.func_list = [
                f
                for f in self.func_list
                if not (isinstance(f, MCPTool) and f.mcp_server_name == name)
            ]
            inactivated = await sp.global_get("inactivated_llm_tools", [])
            if not isinstance(inactivated, list):
                inactivated = []
            tool_states = await sp.global_get("llm_tool_states", {})
            for tool in mcp_client.tools:
                func_tool = MCPTool(
                    mcp_tool=tool,
                    mcp_client=mcp_client,
                    mcp_server_name=name,
                )
                func_tool.active = self.is_tool_active(
                    func_tool, inactivated, tool_states
                )
                self.func_list.append(func_tool)

            logger.info(
                f"Connected to MCP server {name}, "
                f"Tools: {[t.name for t in mcp_client.tools]}"
            )

            connect_done.set()

            try:
                await shutdown_event.wait()
                logger.info(f"Received shutdown signal for MCP client {name}")
            except asyncio.CancelledError:
                logger.debug(f"MCP client {name} task was cancelled")
                raise
            finally:
                # Cleanup in the same task that entered the anyio contexts:
                # asyncio.shield() would schedule the coroutine as a separate
                # Task, and anyio cancel scopes cannot exit across tasks (#9068).
                # Absorb late cancellations so a forced shutdown cannot abort
                # the cleanup halfway.
                task = asyncio.current_task()
                while True:
                    try:
                        await self._terminate_mcp_client(name)
                        break
                    except asyncio.CancelledError:
                        # Task.uncancel() is 3.11+; on 3.10 absorbing the
                        # cancellation is sufficient.
                        if task is not None and hasattr(task, "uncancel"):
                            task.uncancel()

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
                    logger.debug("MCP lifecycle task was cancelled during shutdown.")
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
            # 关闭MCP连接
            await self._cleanup_mcp_client_safely(client, name)
            # 移除关联的FuncTool
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
        if "url" in config:
            success, error_msg = await _quick_test_mcp_connection(config)
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
        timeout: float | int | str | None = None,  # noqa: ASYNC109 - Preserve the public MCP timeout keyword.
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
            timeout_seconds=timeout_value,
        )

    async def disable_mcp_server(
        self,
        name: str | None = None,
        timeout: float = 10,  # noqa: ASYNC109 - Preserve the public MCP timeout keyword.
    ) -> None:
        """Disable an MCP server by its name.

        Args:
            name (str): The name of the MCP server to disable. If None, ALL MCP servers will be disabled.
            timeout (int): Timeout.

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
                "检测到 MCP 初始化超时与动态启用超时配置不同："
                "初始化使用 %s 秒，动态启用使用 %s 秒。如需一致，请设置相同值。",
                f"{init_timeout:g}",
                f"{enable_timeout:g}",
            )
            self._timeout_mismatch_warned = True

    def get_func_desc_openai_style(self, omit_empty_parameter_field=False) -> list:
        """获得 OpenAI API 风格的**已经激活**的工具描述"""
        tools: list[ToolSchema] = [f for f in self.func_list if f.active]
        toolset = ToolSet(tools)
        return toolset.openai_schema(
            omit_empty_parameter_field=omit_empty_parameter_field,
        )

    def get_func_desc_anthropic_style(self) -> list:
        """获得 Anthropic API 风格的**已经激活**的工具描述"""
        tools: list[ToolSchema] = [f for f in self.func_list if f.active]
        toolset = ToolSet(tools)
        return toolset.anthropic_schema()

    def get_func_desc_google_genai_style(self) -> dict:
        """获得 Google GenAI API 风格的**已经激活**的工具描述"""
        tools: list[ToolSchema] = [f for f in self.func_list if f.active]
        toolset = ToolSet(tools)
        return toolset.google_schema()

    @deprecated(reason="Use deactivate_llm_tool_async() instead.")
    def deactivate_llm_tool(self, name: str) -> bool:
        """停用一个已经注册的函数调用工具。

        Returns:
            如果没找到，会返回 False

        """
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

    async def deactivate_llm_tool_async(self, name: str) -> bool:
        """Asynchronously deactivate a registered function-calling tool.

        Args:
            name: Tool name.

        Returns:
            True when the tool was deactivated, or False when it was not found.
        """
        func_tool = self.get_func(name)
        if func_tool is not None:
            func_tool.active = False

            inactivated_llm_tools: list = await sp.get_async(
                "global",
                "global",
                "inactivated_llm_tools",
                [],
            )
            if name not in inactivated_llm_tools:
                inactivated_llm_tools.append(name)
                await sp.put_async(
                    "global",
                    "global",
                    "inactivated_llm_tools",
                    inactivated_llm_tools,
                )

            return True
        return False

    # 因为不想解决循环引用，所以这里直接传入 star_map 先了...
    @deprecated(reason="Use activate_llm_tool_async() instead.")
    def activate_llm_tool(self, name: str, star_map: dict) -> bool:
        func_tool = self.get_func(name)
        if func_tool is not None:
            if func_tool.handler_module_path in star_map:
                if not star_map[func_tool.handler_module_path].activated:
                    raise ValueError(
                        f"此函数调用工具所属的插件 {star_map[func_tool.handler_module_path].name} 已被禁用，请先在管理面板启用再激活此工具。",
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

    async def activate_llm_tool_async(self, name: str, star_map: dict) -> bool:
        """Asynchronously activate a registered function-calling tool.

        Args:
            name: Tool name.
            star_map: Loaded plugins indexed by module path.

        Returns:
            True when the tool was activated, or False when it was not found.

        Raises:
            ValueError: If the plugin that owns the tool is disabled.
        """
        func_tool = self.get_func(name)
        if func_tool is not None:
            if func_tool.handler_module_path in star_map:
                if not star_map[func_tool.handler_module_path].activated:
                    raise ValueError(
                        f"此函数调用工具所属的插件 {star_map[func_tool.handler_module_path].name} 已被禁用，请先在管理面板启用再激活此工具。",
                    )

            func_tool.active = True

            inactivated_llm_tools: list = await sp.get_async(
                "global",
                "global",
                "inactivated_llm_tools",
                [],
            )
            if name in inactivated_llm_tools:
                inactivated_llm_tools.remove(name)
                await sp.put_async(
                    "global",
                    "global",
                    "inactivated_llm_tools",
                    inactivated_llm_tools,
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
                        for server in mcp_server_list:
                            server_name = server.get("name")
                            if not server_name:
                                continue
                            operational_urls = server.get("operational_urls", [])
                            if not operational_urls:
                                continue
                            url_info = operational_urls[0]
                            server_url = url_info.get("url")
                            if not server_url:
                                continue
                            # 添加到配置中(同名会覆盖)
                            server_config = {
                                "url": server_url,
                                "transport": "sse",
                                "active": True,
                                "provider": "modelscope",
                            }
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


# alias
FuncCall = FunctionToolManager
