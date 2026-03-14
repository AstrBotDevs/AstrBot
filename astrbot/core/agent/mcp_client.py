import asyncio
import logging
from contextlib import AsyncExitStack
from datetime import timedelta
from typing import Any, Generic

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from astrbot import logger
from astrbot.core.agent.mcp_prompt_bridge import build_mcp_prompt_tool_names
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.utils.log_pipe import LogPipe

from .mcp_resource_bridge import build_mcp_resource_tool_names
from .mcp_stdio_client import tolerant_stdio_client
from .mcp_subcapability_bridge import (
    MCPClientSubCapabilityBridge,
    normalize_mcp_server_config,
)
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
    config = normalize_mcp_server_config(config)
    config.pop("active", None)
    config.pop("client_capabilities", None)
    config.pop("provider", None)
    return config


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
        self.prompts: list[mcp.types.Prompt] = []
        self.prompt_bridge_tool_names: list[str] = []
        self.resources: list[mcp.types.Resource] = []
        self.resource_templates: list[mcp.types.ResourceTemplate] = []
        self.resource_templates_supported: bool = False
        self.resource_bridge_tool_names: list[str] = []
        self.server_errlogs: list[str] = []
        self.running_event = asyncio.Event()

        # Store connection config for reconnection
        self._mcp_server_config: dict | None = None
        self._server_name: str | None = None
        self._server_capabilities: mcp.types.ServerCapabilities | None = None
        self._reconnect_lock = asyncio.Lock()  # Lock for thread-safe reconnection
        self._reconnecting: bool = False  # For logging and debugging
        self.subcapability_bridge = MCPClientSubCapabilityBridge[Any]()

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
        self.subcapability_bridge.set_server_name(name)
        self.subcapability_bridge.configure_from_server_config(mcp_server_config)

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
                tolerant_stdio_client(
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
                self.subcapability_bridge.clear_runtime_state()

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
        run_context: ContextWrapper[Any] | None = None,
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
            async with self.subcapability_bridge.interactive_call(run_context):
                if not self.session:
                    raise ValueError(
                        "MCP session is not available for MCP function tools."
                    )

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
        """Clean up resources including old exit stacks from reconnections"""
        self.subcapability_bridge.clear_runtime_state()
        self._server_capabilities = None
        self.prompts = []
        self.prompt_bridge_tool_names = []
        self.resources = []
        self.resource_templates = []
        self.resource_templates_supported = False
        self.resource_bridge_tool_names = []
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
            run_context=context,
        )
