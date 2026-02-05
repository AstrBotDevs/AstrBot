"""Socket客户端处理器

负责处理单个Socket客户端连接。
"""

import asyncio
import json
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING

from astrbot import logger

from ..interfaces import IHandler, IMessageConverter, ISessionManager, ITokenValidator
from ..message.response_builder import ResponseBuilder

if TYPE_CHECKING:
    from astrbot.core.platform.platform_metadata import PlatformMetadata

    from ..cli_event import CLIMessageEvent


class SocketClientHandler:
    """Socket客户端处理器

    处理单个客户端连接，不实现IHandler（因为它不是独立运行的模式）。

    I/O契约:
        Input: socket连接
        Output: None (发送JSON响应到客户端)
    """

    RECV_BUFFER_SIZE = 4096
    MAX_REQUEST_SIZE = 1024 * 1024  # 1MB 最大请求大小
    RESPONSE_TIMEOUT = 30.0

    def __init__(
        self,
        token_manager: ITokenValidator,
        message_converter: IMessageConverter,
        session_manager: ISessionManager,
        platform_meta: "PlatformMetadata",
        output_queue: asyncio.Queue,
        event_committer: Callable[["CLIMessageEvent"], None],
        use_isolated_sessions: bool = False,
    ):
        """初始化Socket客户端处理器"""
        self.token_manager = token_manager
        self.message_converter = message_converter
        self.session_manager = session_manager
        self.platform_meta = platform_meta
        self.output_queue = output_queue
        self.event_committer = event_committer
        self.use_isolated_sessions = use_isolated_sessions

    async def handle(self, client_socket) -> None:
        """处理单个客户端连接"""
        try:
            loop = asyncio.get_running_loop()

            # 接收请求（带大小限制）
            data = await self._recv_with_limit(loop, client_socket)
            if not data:
                return

            # 解析并验证请求
            request = self._parse_request(data)
            if request is None:
                await self._send_response(
                    loop,
                    client_socket,
                    ResponseBuilder.build_error("Invalid JSON format"),
                )
                return

            message_text = request.get("message", "")
            request_id = request.get("request_id", str(uuid.uuid4()))
            auth_token = request.get("auth_token", "")

            # Token验证
            if not self.token_manager.validate(auth_token):
                error_msg = (
                    "Unauthorized: missing token"
                    if not auth_token
                    else "Unauthorized: invalid token"
                )
                await self._send_response(
                    loop,
                    client_socket,
                    ResponseBuilder.build_error(error_msg, request_id, "AUTH_FAILED"),
                )
                return

            # 处理消息
            response = await self._process_message(message_text, request_id)
            await self._send_response(loop, client_socket, response)

        except Exception as e:
            logger.error("Socket handler error: %s", e, exc_info=True)
        finally:
            try:
                client_socket.close()
            except Exception as e:
                logger.warning("Failed to close socket: %s", e)

    async def _recv_with_limit(self, loop, client_socket) -> bytes:
        """接收数据，带大小限制防止DoS攻击"""
        chunks = []
        total_size = 0

        while True:
            chunk = await loop.sock_recv(client_socket, self.RECV_BUFFER_SIZE)
            if not chunk:
                break

            total_size += len(chunk)
            if total_size > self.MAX_REQUEST_SIZE:
                logger.warning(
                    "Request too large: %d bytes, limit: %d",
                    total_size,
                    self.MAX_REQUEST_SIZE,
                )
                return b""

            chunks.append(chunk)

            # 检查是否接收完整（JSON以}结尾）
            if chunk.rstrip().endswith(b"}"):
                break

        return b"".join(chunks)

    def _parse_request(self, data: bytes) -> dict | None:
        """解析JSON请求"""
        try:
            return json.loads(data.decode("utf-8"))
        except json.JSONDecodeError:
            return None

    async def _send_response(self, loop, client_socket, response: str) -> None:
        """发送响应"""
        await loop.sock_sendall(client_socket, response.encode("utf-8"))

    async def _process_message(self, message_text: str, request_id: str) -> str:
        """处理消息并返回JSON响应"""
        from ..cli_event import CLIMessageEvent

        response_future = asyncio.Future()

        message = self.message_converter.convert(
            message_text,
            request_id=request_id,
            use_isolated_session=self.use_isolated_sessions,
        )

        self.session_manager.register(message.session_id)

        message_event = CLIMessageEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.platform_meta,
            session_id=message.session_id,
            output_queue=self.output_queue,
            response_future=response_future,
        )

        self.event_committer(message_event)

        try:
            message_chain = await asyncio.wait_for(
                response_future, timeout=self.RESPONSE_TIMEOUT
            )
            return ResponseBuilder.build_success(message_chain, request_id)
        except asyncio.TimeoutError:
            # 超时时取消延迟响应任务，防止资源泄露
            if (
                hasattr(message_event, "_response_delay_task")
                and message_event._response_delay_task
            ):
                message_event._response_delay_task.cancel()
            return ResponseBuilder.build_error("Request timeout", request_id, "TIMEOUT")


class SocketModeHandler(IHandler):
    """Socket模式处理器

    管理Socket服务器的生命周期，实现IHandler接口。
    """

    def __init__(
        self,
        server,
        client_handler: SocketClientHandler,
        connection_info_writer: Callable[[dict, str], None],
        data_path: str,
    ):
        """初始化Socket模式处理器

        Args:
            server: Socket服务器实例
            client_handler: 客户端处理器
            connection_info_writer: 连接信息写入函数
            data_path: 数据目录路径
        """
        self.server = server
        self.client_handler = client_handler
        self.connection_info_writer = connection_info_writer
        self.data_path = data_path
        self._running = False

    async def run(self) -> None:
        """运行Socket服务器"""
        self._running = True

        try:
            await self.server.start()
            logger.info("Socket server started: %s", type(self.server).__name__)

            # 写入连接信息
            connection_info = self.server.get_connection_info()
            self.connection_info_writer(connection_info, self.data_path)

            # 接受连接循环
            while self._running:
                try:
                    client_socket, _ = await self.server.accept_connection()
                    asyncio.create_task(self.client_handler.handle(client_socket))
                except Exception as e:
                    if self._running:
                        logger.error("Socket accept error: %s", e)
                    await asyncio.sleep(0.1)

        finally:
            await self.server.stop()

    def stop(self) -> None:
        """停止Socket服务器"""
        self._running = False
