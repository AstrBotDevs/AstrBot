"""Socket处理器模块

处理Socket客户端连接和Socket模式的生命周期管理。
"""

import asyncio
import json
import os
import re
import tempfile
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from astrbot import logger
from astrbot.core.message.message_event_result import MessageChain

if TYPE_CHECKING:
    from astrbot.core.platform.platform_metadata import PlatformMetadata

    from .cli_event import CLIMessageEvent


# ------------------------------------------------------------------
# 连接信息写入
# ------------------------------------------------------------------


def write_connection_info(connection_info: dict[str, Any], data_dir: str) -> None:
    """写入连接信息到文件，供客户端读取"""
    if not isinstance(connection_info, dict):
        raise ValueError("connection_info must be a dict")

    conn_type = connection_info.get("type")
    if conn_type not in ("unix", "tcp"):
        raise ValueError(f"Invalid type: {conn_type}, must be 'unix' or 'tcp'")
    if conn_type == "unix" and "path" not in connection_info:
        raise ValueError("Unix socket requires 'path' field")
    if conn_type == "tcp" and (
        "host" not in connection_info or "port" not in connection_info
    ):
        raise ValueError("TCP socket requires 'host' and 'port' fields")

    target_path = os.path.join(data_dir, ".cli_connection")

    try:
        fd, temp_path = tempfile.mkstemp(
            dir=data_dir, prefix=".cli_connection.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(connection_info, f, indent=2)
            try:
                os.chmod(temp_path, 0o600)
            except OSError:
                pass
            os.replace(temp_path, target_path)
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise
    except Exception as e:
        logger.error(f"[CLI] Failed to write connection info: {e}")
        raise


# ------------------------------------------------------------------
# 响应构建（从message/response_builder.py内联）
# ------------------------------------------------------------------


def _build_success_response(
    message_chain: MessageChain,
    request_id: str,
    images: list[dict],
    extra: dict[str, Any] | None = None,
) -> str:
    """构建成功响应JSON"""
    result = {
        "status": "success",
        "response": message_chain.get_plain_text(),
        "images": images,
        "request_id": request_id,
    }
    if extra:
        result.update(extra)
    return json.dumps(result, ensure_ascii=False)


def _build_error_response(
    error_msg: str,
    request_id: str | None = None,
    error_code: str | None = None,
) -> str:
    """构建错误响应JSON"""
    result: dict[str, Any] = {"status": "error", "error": error_msg}
    if request_id:
        result["request_id"] = request_id
    if error_code:
        result["error_code"] = error_code
    return json.dumps(result, ensure_ascii=False)


# ------------------------------------------------------------------
# Socket客户端处理器
# ------------------------------------------------------------------


class SocketClientHandler:
    """处理单个Socket客户端连接"""

    RECV_BUFFER_SIZE = 4096
    MAX_REQUEST_SIZE = 1024 * 1024  # 1MB
    RESPONSE_TIMEOUT = 120.0

    def __init__(
        self,
        token_manager,
        message_converter,
        session_manager,
        platform_meta: "PlatformMetadata",
        output_queue: asyncio.Queue,
        event_committer: Callable[["CLIMessageEvent"], None],
        use_isolated_sessions: bool = False,
        data_path: str | None = None,
    ):
        self.token_manager = token_manager
        self.message_converter = message_converter
        self.session_manager = session_manager
        self.platform_meta = platform_meta
        self.output_queue = output_queue
        self.event_committer = event_committer
        self.use_isolated_sessions = use_isolated_sessions
        self.data_path = data_path or os.path.join(os.getcwd(), "data")

    async def handle(self, client_socket) -> None:
        """处理单个客户端连接"""
        try:
            loop = asyncio.get_running_loop()

            data = await self._recv_with_limit(loop, client_socket)
            if not data:
                return

            request = self._parse_request(data)
            if request is None:
                await self._send_response(
                    loop, client_socket, _build_error_response("Invalid JSON format")
                )
                return

            request_id = request.get("request_id", str(uuid.uuid4()))
            auth_token = request.get("auth_token", "")
            action = request.get("action", "")

            if not self.token_manager.validate(auth_token):
                error_msg = (
                    "Unauthorized: missing token"
                    if not auth_token
                    else "Unauthorized: invalid token"
                )
                await self._send_response(
                    loop,
                    client_socket,
                    _build_error_response(error_msg, request_id, "AUTH_FAILED"),
                )
                return

            if action == "get_logs":
                response = await self._get_logs(request, request_id)
            else:
                message_text = request.get("message", "")
                response = await self._process_message(message_text, request_id)

            await self._send_response(loop, client_socket, response)

        except Exception as e:
            logger.error(f"[CLI] Socket handler error: {e}", exc_info=True)
        finally:
            try:
                client_socket.close()
            except Exception as e:
                logger.warning(f"[CLI] Failed to close socket: {e}")

    async def _recv_with_limit(self, loop, client_socket) -> bytes:
        """接收数据，带大小限制"""
        chunks = []
        total_size = 0

        while True:
            chunk = await loop.sock_recv(client_socket, self.RECV_BUFFER_SIZE)
            if not chunk:
                break

            total_size += len(chunk)
            if total_size > self.MAX_REQUEST_SIZE:
                logger.warning(f"[CLI] Request too large: {total_size} bytes")
                return b""

            chunks.append(chunk)
            if chunk.rstrip().endswith(b"}"):
                break

        return b"".join(chunks)

    def _parse_request(self, data: bytes) -> dict | None:
        try:
            return json.loads(data.decode("utf-8"))
        except json.JSONDecodeError:
            return None

    async def _send_response(self, loop, client_socket, response: str) -> None:
        await loop.sock_sendall(client_socket, response.encode("utf-8"))

    async def _process_message(self, message_text: str, request_id: str) -> str:
        """处理消息并返回JSON响应"""
        from .cli_event import CLIMessageEvent, extract_images

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
            if message_chain is None:
                return _build_success_response(MessageChain([]), request_id, [])
            images = extract_images(message_chain)
            return _build_success_response(message_chain, request_id, images)
        except asyncio.TimeoutError:
            return _build_error_response("Request timeout", request_id, "TIMEOUT")

    async def _get_logs(self, request: dict, request_id: str) -> str:
        """获取日志"""
        LEVEL_MAP = {
            "DEBUG": "DEBUG",
            "INFO": "INFO",
            "WARNING": "WARN",
            "WARN": "WARN",
            "ERROR": "ERRO",
            "CRITICAL": "CRIT",
        }

        try:
            lines = min(request.get("lines", 100), 1000)
            level_filter = request.get("level", "").upper()
            level_filter = LEVEL_MAP.get(level_filter, level_filter)
            pattern = request.get("pattern", "")
            use_regex = request.get("regex", False)

            log_path = os.path.join(self.data_path, "logs", "astrbot.log")

            if not os.path.exists(log_path):  # noqa: ASYNC240
                return json.dumps(
                    {
                        "status": "success",
                        "response": "",
                        "message": "日志文件未找到。请在配置中启用 log_file_enable 来记录日志到文件。",
                        "request_id": request_id,
                    },
                    ensure_ascii=False,
                )

            logs = []
            try:
                with open(log_path, encoding="utf-8", errors="ignore") as f:
                    all_lines = f.readlines()

                for line in reversed(all_lines):
                    if not line.strip():
                        continue
                    if level_filter and not re.search(rf"\[{level_filter}\]", line):
                        continue
                    if pattern:
                        if use_regex:
                            try:
                                if not re.search(pattern, line):
                                    continue
                            except re.error:
                                if pattern not in line:
                                    continue
                        else:
                            if pattern not in line:
                                continue
                    logs.append(line.rstrip())
                    if len(logs) >= lines:
                        break
            except OSError as e:
                logger.warning(f"[CLI] Failed to read log file: {e}")
                return _build_error_response(
                    f"Failed to read log file: {e}", request_id
                )

            logs.reverse()
            log_text = "\n".join(logs)
            return json.dumps(
                {
                    "status": "success",
                    "response": log_text,
                    "message": f"Retrieved {len(logs)} log lines",
                    "request_id": request_id,
                },
                ensure_ascii=False,
            )

        except Exception as e:
            logger.exception("[CLI] Error getting logs")
            return _build_error_response(f"Error getting logs: {e}", request_id)


# ------------------------------------------------------------------
# Socket模式处理器
# ------------------------------------------------------------------


class SocketModeHandler:
    """管理Socket服务器的生命周期"""

    def __init__(
        self,
        server,
        client_handler: SocketClientHandler,
        connection_info_writer: Callable[[dict, str], None],
        data_path: str,
    ):
        self.server = server
        self.client_handler = client_handler
        self.connection_info_writer = connection_info_writer
        self.data_path = data_path
        self._running = False

    async def run(self) -> None:
        self._running = True
        try:
            await self.server.start()
            logger.info(f"[CLI] Socket server started: {type(self.server).__name__}")

            connection_info = self.server.get_connection_info()
            self.connection_info_writer(connection_info, self.data_path)

            while self._running:
                try:
                    client_socket, _ = await self.server.accept_connection()
                    asyncio.create_task(self.client_handler.handle(client_socket))
                except Exception as e:
                    if self._running:
                        logger.error(f"[CLI] Socket accept error: {e}")
                    await asyncio.sleep(0.1)
        finally:
            await self.server.stop()

    def stop(self) -> None:
        self._running = False
