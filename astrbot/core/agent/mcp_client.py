import asyncio
import logging
from datetime import timedelta
from typing import Optional
from contextlib import AsyncExitStack
from astrbot import logger
from astrbot.core.utils.log_pipe import LogPipe

try:
    import mcp
    from mcp.client.sse import sse_client
except (ModuleNotFoundError, ImportError):
    logger.warning("警告: 缺少依赖库 'mcp'，将无法使用 MCP 服务。")

try:
    from mcp.client.streamable_http import streamablehttp_client
except (ModuleNotFoundError, ImportError):
    logger.warning(
        "警告: 缺少依赖库 'mcp' 或者 mcp 库版本过低，无法使用 Streamable HTTP 连接方式。"
    )


def _prepare_config(config: dict) -> dict:
    """准备配置，处理嵌套格式"""
    if "mcpServers" in config and config["mcpServers"]:
        first_key = next(iter(config["mcpServers"]))
        config = config["mcpServers"][first_key]
    config.pop("active", None)
    return config


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
                    else:
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
                    else:
                        return False, f"HTTP {response.status}: {response.reason}"

    except asyncio.TimeoutError:
        return False, f"连接超时: {timeout}秒"
    except Exception as e:
        return False, f"{e!s}"


class MCPClient:
    def __init__(self):
        # Initialize session and client objects
        self.session: Optional[mcp.ClientSession] = None
        self.exit_stack = AsyncExitStack()

        self.name = None
        self.active: bool = True
        self.tools: list[mcp.Tool] = []
        self.server_errlogs: list[str] = []
        self.running_event = asyncio.Event()

    async def connect_to_server(self, mcp_server_config: dict, name: str):
        """连接到 MCP 服务器

        如果 `url` 参数存在：
            1. 当 transport 指定为 `streamable_http` 时，使用 Streamable HTTP 连接方式。
            1. 当 transport 指定为 `sse` 时，使用 SSE 连接方式。
            2. 如果没有指定，默认使用 SSE 的方式连接到 MCP 服务。

        Args:
            mcp_server_config (dict): Configuration for the MCP server. See https://modelcontextprotocol.io/quickstart/server
        """
        cfg = _prepare_config(mcp_server_config.copy())

        def logging_callback(msg: str):
            # 处理 MCP 服务的错误日志
            print(f"MCP Server {name} Error: {msg}")
            self.server_errlogs.append(msg)

        if "url" in cfg:
            success, error_msg = await _quick_test_mcp_connection(cfg)
            if not success:
                raise Exception(error_msg)

            if cfg.get("transport") != "streamable_http":
                # SSE transport method
                self._streams_context = sse_client(
                    url=cfg["url"],
                    headers=cfg.get("headers", {}),
                    timeout=cfg.get("timeout", 5),
                    sse_read_timeout=cfg.get("sse_read_timeout", 60 * 5),
                )
                streams = await self.exit_stack.enter_async_context(
                    self._streams_context
                )

                # Create a new client session
                read_timeout = timedelta(seconds=cfg.get("session_read_timeout", 20))
                self.session = await self.exit_stack.enter_async_context(
                    mcp.ClientSession(
                        *streams,
                        read_timeout_seconds=read_timeout,
                        logging_callback=logging_callback,  # type: ignore
                    )
                )
            else:
                timeout = timedelta(seconds=cfg.get("timeout", 30))
                sse_read_timeout = timedelta(
                    seconds=cfg.get("sse_read_timeout", 60 * 5)
                )
                self._streams_context = streamablehttp_client(
                    url=cfg["url"],
                    headers=cfg.get("headers", {}),
                    timeout=timeout,
                    sse_read_timeout=sse_read_timeout,
                    terminate_on_close=cfg.get("terminate_on_close", True),
                )
                read_s, write_s, _ = await self.exit_stack.enter_async_context(
                    self._streams_context
                )

                # Create a new client session
                read_timeout = timedelta(seconds=cfg.get("session_read_timeout", 20))
                self.session = await self.exit_stack.enter_async_context(
                    mcp.ClientSession(
                        read_stream=read_s,
                        write_stream=write_s,
                        read_timeout_seconds=read_timeout,
                        logging_callback=logging_callback,  # type: ignore
                    )
                )

        else:
            server_params = mcp.StdioServerParameters(
                **cfg,
            )

            def callback(msg: str):
                # 处理 MCP 服务的错误日志
                self.server_errlogs.append(msg)

            stdio_transport = await self.exit_stack.enter_async_context(
                mcp.stdio_client(
                    server_params,
                    errlog=LogPipe(
                        level=logging.ERROR,
                        logger=logger,
                        identifier=f"MCPServer-{name}",
                        callback=callback,
                    ),  # type: ignore
                ),
            )

            # Create a new client session
            self.session = await self.exit_stack.enter_async_context(
                mcp.ClientSession(*stdio_transport)
            )
        await self.session.initialize()

    async def list_tools_and_save(self) -> mcp.ListToolsResult:
        """List all tools from the server and save them to self.tools"""
        response = await self.session.list_tools()
        self.tools = response.tools
        return response

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()
        self.running_event.set()  # Set the running event to indicate cleanup is done
