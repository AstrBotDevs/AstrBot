from __future__ import annotations

import asyncio
import copy
import json
import os
import threading
import urllib.parse
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from astrbot import logger
from astrbot.core import sp
from astrbot.core.agent.mcp_client import (
    MCPClient,
    MCPTool,
    _quick_test_mcp_connection,
)
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .mcp_sync_providers import SyncedMcpServer, get_mcp_sync_provider

DEFAULT_MCP_CONFIG = {"mcpServers": {}}

DEFAULT_MCP_INIT_TIMEOUT_SECONDS = 20.0
DEFAULT_ENABLE_MCP_TIMEOUT_SECONDS = 30.0
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


class FunctionToolManager:
    def __init__(self) -> None:
        self.func_list: list[FuncTool] = []
        self._mcp_server_runtime: dict[str, _MCPServerRuntime] = {}
        """MCP 服务运行时状态（唯一事实来源）"""
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
        logger.info(f"添加函数调用工具: {name}")

    def remove_func(self, name: str) -> None:
        """删除一个函数调用工具。"""
        for i, f in enumerate(self.func_list):
            if f.name == name:
                self.func_list.pop(i)
                break

    def get_func(self, name) -> FuncTool | None:
        for f in self.func_list:
            if f.name == name:
                return f

    def get_full_tool_set(self) -> ToolSet:
        """获取完整工具集"""
        tool_set = ToolSet(self.func_list.copy())
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
        self,
        raise_on_all_failed: bool = False,
        *,
        init_timeout: float | int | str | None = None,
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
        - 显式 `init_timeout` 参数优先（用于测试或调用方覆盖）。
        - 初始化超时使用环境变量 ASTRBOT_MCP_INIT_TIMEOUT 或默认值。
        - 动态启用超时使用 ASTRBOT_MCP_ENABLE_TIMEOUT（独立于初始化超时）。
        """
        data_dir = get_astrbot_data_path()

        mcp_json_file = os.path.join(data_dir, "mcp_server.json")
        if not await asyncio.to_thread(os.path.exists, mcp_json_file):
            # 配置文件不存在错误处理
            config_text = json.dumps(DEFAULT_MCP_CONFIG, ensure_ascii=False, indent=4)
            await asyncio.to_thread(
                Path(mcp_json_file).write_text,
                config_text,
                encoding="utf-8",
            )
            logger.info(f"未找到 MCP 服务配置文件，已创建默认配置文件 {mcp_json_file}")
            return MCPInitSummary(total=0, success=0, failed=[])

        mcp_json_content = await asyncio.to_thread(
            Path(mcp_json_file).read_text,
            encoding="utf-8",
        )
        mcp_server_json_obj: dict[str, dict] = json.loads(mcp_json_content)[
            "mcpServers"
        ]

        init_timeout_value = _resolve_timeout(
            timeout=init_timeout,
            env_name=MCP_INIT_TIMEOUT_ENV,
            default=self._init_timeout_default,
        )
        timeout_display = f"{init_timeout_value:g}"

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
                    timeout_seconds=init_timeout_value,
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
                    logger.error(f"MCP 服务 {name} 初始化超时（{timeout_display}秒）")
                else:
                    logger.error(f"MCP 服务 {name} 初始化失败: {result}")
                self._log_safe_mcp_debug_config(cfg)
                failed_services.append(name)
                async with self._runtime_lock:
                    self._mcp_server_runtime.pop(name, None)
                continue

            success_count += 1

        if failed_services:
            logger.warning(
                f"以下 MCP 服务初始化失败: {', '.join(failed_services)}。"
                f"请检查配置文件 mcp_server.json 和服务器可用性。"
            )

        summary = MCPInitSummary(
            total=len(active_configs), success=success_count, failed=failed_services
        )
        logger.info(f"MCP 服务初始化完成: {summary.success}/{summary.total} 成功")
        if summary.total > 0 and summary.success == 0:
            msg = "全部 MCP 服务初始化失败，请检查 mcp_server.json 配置和服务器可用性。"
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
                    f"MCP 服务 {name} 已在运行，忽略本次启用请求（timeout={timeout_seconds:g}）。"
                )
                self._log_safe_mcp_debug_config(cfg)
                return
            self._mcp_starting.add(name)

        if shutdown_event is None:
            shutdown_event = asyncio.Event()

        mcp_client: MCPClient | None = None
        try:
            mcp_client = await asyncio.wait_for(
                self._init_mcp_client(name, cfg),
                timeout=timeout_seconds,
            )
        except TimeoutError as exc:
            raise MCPInitTimeoutError(
                f"MCP 服务 {name} 初始化超时（{timeout_seconds:g} 秒）"
            ) from exc
        except Exception as e:
            msg = str(e).lower()
            is_invalid_key = (
                "invalid apikey" in msg or "invalid authorization key" in msg
            )
            if is_invalid_key and str(cfg.get("provider", "")).lower() == "mcprouter":
                logger.warning(
                    f"初始化 MCP 客户端 {name} 失败：MCPRouter API Key 无效（请重新同步/更新 API Key）: {e!s}",
                )
            elif is_invalid_key:
                logger.warning(f"初始化 MCP 客户端 {name} 失败: {e!s}")
            else:
                logger.error(f"初始化 MCP 客户端 {name} 失败", exc_info=True)
            raise
        finally:
            if mcp_client is None:
                async with self._runtime_lock:
                    self._mcp_starting.discard(name)

        async def lifecycle() -> None:
            try:
                await shutdown_event.wait()
                logger.info(f"收到 MCP 客户端 {name} 终止信号")
            except asyncio.CancelledError:
                logger.debug(f"MCP 客户端 {name} 任务被取消")
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
                "MCP 服务关闭超时（%s 秒），以下服务未完全关闭：%s",
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
            logger.error(f"清理 MCP 客户端资源 {name} 失败: {cleanup_exc}")

    async def _init_mcp_client(self, name: str, config: dict) -> MCPClient:
        """初始化单个MCP客户端"""
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

        # 移除该MCP服务之前的工具（如有）
        self.func_list = [
            f
            for f in self.func_list
            if not (isinstance(f, MCPTool) and f.mcp_server_name == name)
        ]

        # 将 MCP 工具转换为 FuncTool 并添加到 func_list
        for tool in mcp_client.tools:
            func_tool = MCPTool(
                mcp_tool=tool,
                mcp_client=mcp_client,
                mcp_server_name=name,
            )
            self.func_list.append(func_tool)

        logger.info(f"已连接 MCP 服务 {name}, Tools: {tool_names}")
        return mcp_client

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
            logger.info(f"已关闭 MCP 服务 {name}")
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
        timeout_seconds: float | int | str | None = None,
        **kwargs: Any,
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
        legacy_timeout = kwargs.pop("timeout", None)
        if legacy_timeout is not None:
            timeout_seconds = legacy_timeout

        if timeout_seconds is None:
            timeout_value = self._enable_timeout_default
        else:
            timeout_value = _resolve_timeout(
                timeout=timeout_seconds,
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
        timeout_seconds: float = 10,
        **kwargs: Any,
    ) -> None:
        """Disable an MCP server by its name.

        Args:
            name (str): The name of the MCP server to disable. If None, ALL MCP servers will be disabled.
            timeout_seconds (int): Timeout.

        Raises:
            MCPShutdownTimeoutError: If shutdown does not complete within timeout.
                Only raised when disabling a specific server (name is not None).

        """
        legacy_timeout = kwargs.pop("timeout", None)
        if legacy_timeout is not None:
            timeout_seconds = float(legacy_timeout)

        if name:
            async with self._runtime_lock:
                runtime = self._mcp_server_runtime.get(name)
            if runtime is None:
                return

            await self._shutdown_runtimes(
                [runtime], timeout_seconds=timeout_seconds, strict=True
            )
        else:
            async with self._runtime_lock:
                runtimes = list(self._mcp_server_runtime.values())
            await self._shutdown_runtimes(
                runtimes, timeout_seconds=timeout_seconds, strict=False
            )

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
        tools = [f for f in self.func_list if f.active]
        toolset = ToolSet(tools)
        return toolset.openai_schema(
            omit_empty_parameter_field=omit_empty_parameter_field,
        )

    def get_func_desc_anthropic_style(self) -> list:
        """获得 Anthropic API 风格的**已经激活**的工具描述"""
        tools = [f for f in self.func_list if f.active]
        toolset = ToolSet(tools)
        return toolset.anthropic_schema()

    def get_func_desc_google_genai_style(self) -> dict:
        """获得 Google GenAI API 风格的**已经激活**的工具描述"""
        tools = [f for f in self.func_list if f.active]
        toolset = ToolSet(tools)
        return toolset.google_schema()

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

    # 因为不想解决循环引用，所以这里直接传入 star_map 先了...
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

    async def _enable_mcp_servers_with_concurrency_limit(
        self,
        server_names: list[str],
        config: dict,
        *,
        max_concurrency: int = 5,
        timeout_seconds: int = 30,
    ) -> tuple[int, dict[str, str]]:
        sem = asyncio.Semaphore(max_concurrency)
        failures: dict[str, str] = {}

        async def _enable_one(name: str) -> bool:
            async with sem:
                try:
                    if name in self.mcp_client_dict:
                        await self.disable_mcp_server(name, timeout=10)
                    await self.enable_mcp_server(
                        name=name,
                        config=config["mcpServers"][name],
                        timeout=timeout_seconds,
                    )
                    return True
                except Exception as e:
                    failures[name] = str(e)
                    logger.warning(f"启用 MCP 服务器失败: {name}, err={e!s}")
                    return False

        results = await asyncio.gather(*[_enable_one(n) for n in server_names])
        enabled_count = sum(1 for ok in results if ok)
        return enabled_count, failures

    async def sync_mcp_servers_from_provider(
        self,
        provider_name: str,
        payload: dict[str, Any],
        *,
        max_concurrency: int = 5,
    ) -> dict[str, Any]:
        provider = get_mcp_sync_provider(provider_name)
        servers: list[SyncedMcpServer] = await provider.fetch(payload)
        if not servers:
            return {
                "provider": provider_name,
                "synced": 0,
                "enabled": 0,
                "failed": 0,
                "failed_servers": [],
            }

        local_mcp_config = self.load_mcp_config()
        local_mcp_config.setdefault("mcpServers", {})

        for item in servers:
            local_mcp_config["mcpServers"][item.name] = item.config

        if not self.save_mcp_config(local_mcp_config):
            raise RuntimeError("保存 MCP 配置失败，已取消同步启用")

        enabled_count, failures = await self._enable_mcp_servers_with_concurrency_limit(
            [item.name for item in servers],
            local_mcp_config,
            max_concurrency=max_concurrency,
        )

        return {
            "provider": provider_name,
            "synced": len(servers),
            "enabled": enabled_count,
            "failed": len(failures),
            "failed_servers": sorted(failures.keys()),
        }

    async def list_mcp_servers_from_provider(
        self,
        provider_name: str,
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        provider = get_mcp_sync_provider(provider_name)
        return await provider.list_servers(payload)

    async def sync_modelscope_mcp_servers(self, access_token: str) -> None:
        await self.sync_mcp_servers_from_provider(
            "modelscope",
            {"access_token": access_token},
        )

    async def sync_mcprouter_mcp_servers(
        self,
        api_key: str,
        *,
        app_url: str = "",
        app_name: str = "AstrBot",
        api_base: str = "https://api.mcprouter.to/v1",
        limit: int = 100,
        max_servers: int = 30,
        query: str = "",
        server_keys: str | list[str] | None = None,
    ) -> dict[str, Any]:
        return await self.sync_mcp_servers_from_provider(
            "mcprouter",
            {
                "api_key": api_key,
                "app_url": app_url,
                "app_name": app_name,
                "api_base": api_base,
                "limit": limit,
                "max_servers": max_servers,
                "query": query,
                "server_keys": server_keys,
            },
        )

    def __str__(self) -> str:
        return str(self.func_list)

    def __repr__(self) -> str:
        return str(self.func_list)


# alias
FuncCall = FunctionToolManager
