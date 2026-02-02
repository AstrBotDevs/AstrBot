"""
TCP Socket Server Implementation

This module provides a TCP Socket server implementation for Windows compatibility.
It implements the AbstractSocketServer interface using TCP sockets (AF_INET).

Design Pattern: Strategy Pattern (implements AbstractSocketServer)
Security: Localhost-only binding + Token authentication

I/O Contract:
    Input: host (str), port (int), auth_token (str | None)
    Output: AbstractSocketServer instance with TCP socket functionality
"""

import asyncio
import socket
import time
from typing import Any

from astrbot import logger

from .socket_abstract import AbstractSocketServer


class TCPSocketServer(AbstractSocketServer):
    """TCP Socket服务器实现

    用于Windows环境的Socket服务器，使用TCP协议（AF_INET）。
    仅监听localhost（127.0.0.1），通过Token认证保证安全性。

    Attributes:
        host: 监听地址（默认127.0.0.1）
        port: 监听端口（0表示随机端口）
        auth_token: 认证Token（可选但强烈推荐）
        server_socket: TCP socket对象
        actual_port: 实际绑定的端口号

    Security:
        - 仅监听localhost，不暴露到网络
        - 支持Token认证（应用层安全）
        - 记录所有连接尝试

    Example:
        server = TCPSocketServer(port=0, auth_token="secret")
        await server.start()
        client, addr = await server.accept_connection()
        await server.stop()
    """

    def __init__(
        self, host: str = "127.0.0.1", port: int = 0, auth_token: str | None = None
    ):
        """初始化TCP Socket服务器

        Args:
            host: 监听地址，默认127.0.0.1（仅本地访问）
            port: 监听端口，0表示随机端口
            auth_token: 认证Token，用于验证客户端身份

        Note:
            强烈建议设置auth_token，因为TCP Socket无文件权限保护
        """
        self.host = host
        self.port = port
        self.auth_token = auth_token
        self.server_socket: socket.socket | None = None
        self.actual_port: int = port
        self._is_running = False

    async def start(self) -> None:
        """启动TCP Socket服务器

        创建TCP socket，绑定到指定地址和端口，开始监听连接。
        使用非阻塞模式，与asyncio事件循环集成。

        Input: None
        Output: None (副作用：启动服务器，开始监听)

        Raises:
            RuntimeError: 如果服务器已经在运行
            OSError: 如果端口已被占用或权限不足

        Logging:
            [ENTRY] start inputs={host, port}
            [PROCESS] Socket created and bound
            [EXIT] start return=None time_ms={duration}
        """
        start_time = time.time()
        logger.debug(
            f"[ENTRY] TCPSocketServer.start inputs={{host={self.host}, port={self.port}}}"
        )

        if self._is_running:
            logger.error("[ERROR] TCPSocketServer.start: Server already running")
            raise RuntimeError("Server is already running")

        try:
            # Create TCP socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            logger.debug("[PROCESS] TCP socket created")

            # Bind to localhost only (security)
            self.server_socket.bind((self.host, self.port))
            self.actual_port = self.server_socket.getsockname()[1]
            logger.debug(f"[PROCESS] Socket bound to {self.host}:{self.actual_port}")

            # Start listening
            self.server_socket.listen(5)
            self.server_socket.setblocking(False)
            logger.debug("[PROCESS] Socket listening (non-blocking mode)")

            self._is_running = True

            duration_ms = (time.time() - start_time) * 1000
            logger.info(
                f"[EXIT] TCPSocketServer.start return=None time_ms={duration_ms:.2f} "
                f"actual_port={self.actual_port}"
            )

        except Exception as e:
            logger.error(
                f"[ERROR] TCPSocketServer.start failed: {type(e).__name__}: {e}",
                exc_info=True,
            )
            # Cleanup on failure
            if self.server_socket:
                self.server_socket.close()
                self.server_socket = None
            raise

    async def stop(self) -> None:
        """停止TCP Socket服务器

        关闭socket连接并清理所有资源。
        此方法是幂等的，可以安全地多次调用。

        Input: None
        Output: None (副作用：停止服务器，清理资源)

        Logging:
            [ENTRY] stop inputs={}
            [PROCESS] Closing socket
            [EXIT] stop return=None time_ms={duration}
        """
        start_time = time.time()
        logger.debug("[ENTRY] TCPSocketServer.stop inputs={}")

        if not self._is_running and self.server_socket is None:
            logger.debug("[PROCESS] Server not running, nothing to stop")
            return

        try:
            if self.server_socket:
                logger.debug("[PROCESS] Closing TCP socket")
                self.server_socket.close()
                self.server_socket = None

            self._is_running = False

            duration_ms = (time.time() - start_time) * 1000
            logger.info(
                f"[EXIT] TCPSocketServer.stop return=None time_ms={duration_ms:.2f}"
            )

        except Exception as e:
            logger.error(
                f"[ERROR] TCPSocketServer.stop failed: {type(e).__name__}: {e}",
                exc_info=True,
            )
            # Ensure cleanup even on error
            self.server_socket = None
            self._is_running = False
            raise

    async def accept_connection(self) -> tuple[Any, Any]:
        """接受客户端连接

        等待并接受一个客户端连接。使用asyncio事件循环实现非阻塞等待。

        Input: None
        Output: (client_socket, client_address)
            - client_socket: 客户端socket对象
            - client_address: 客户端地址元组 (host, port)

        Raises:
            OSError: 如果socket已关闭或发生网络错误
            RuntimeError: 如果服务器未启动

        Logging:
            [ENTRY] accept_connection inputs={}
            [PROCESS] Waiting for connection
            [PROCESS] Connection accepted from {address}
            [EXIT] accept_connection return=(socket, address) time_ms={duration}
        """
        start_time = time.time()
        logger.debug("[ENTRY] TCPSocketServer.accept_connection inputs={}")

        if not self._is_running or self.server_socket is None:
            logger.error(
                "[ERROR] TCPSocketServer.accept_connection: Server not started"
            )
            raise RuntimeError("Server is not running")

        try:
            logger.debug("[PROCESS] Waiting for client connection")

            # Use asyncio event loop for non-blocking accept
            loop = asyncio.get_event_loop()
            client_socket, client_address = await loop.sock_accept(self.server_socket)

            logger.debug(f"[PROCESS] Connection accepted from {client_address}")

            duration_ms = (time.time() - start_time) * 1000
            logger.info(
                f"[EXIT] TCPSocketServer.accept_connection "
                f"return=(socket, {client_address}) time_ms={duration_ms:.2f}"
            )

            return client_socket, client_address

        except Exception as e:
            logger.error(
                f"[ERROR] TCPSocketServer.accept_connection failed: {type(e).__name__}: {e}",
                exc_info=True,
            )
            raise

    def get_connection_info(self) -> dict:
        """获取连接信息

        返回客户端连接到此服务器所需的信息。
        包含socket类型、主机地址和端口号。

        Input: None
        Output: dict - 连接信息字典
            {
                "type": "tcp",
                "host": "127.0.0.1",
                "port": 12345
            }

        Example:
            info = server.get_connection_info()
            print(f"Connect to: {info['host']}:{info['port']}")
        """
        return {"type": "tcp", "host": self.host, "port": self.actual_port}
