"""
Unix Socket Server Implementation

This module provides Unix Socket server implementation for Linux/Unix environments.
It handles socket creation, permission management, and connection acceptance.

Design Pattern: Concrete implementation of AbstractSocketServer
I/O Contract: Implements all abstract methods defined in AbstractSocketServer
"""

import asyncio
import os
import socket
from typing import Any

from astrbot import logger

from .socket_abstract import AbstractSocketServer


class UnixSocketServer(AbstractSocketServer):
    """Unix Socket服务器实现

    职责：
        - 创建和管理Unix Domain Socket
        - 设置严格的文件权限(0o600)
        - 接受客户端连接
        - 清理资源

    I/O契约：
        Input: socket_path (str), auth_token (str | None)
        Output: AbstractSocketServer实例

    设计原则：
        - Single Responsibility: 仅处理Unix Socket相关逻辑
        - Explicit I/O: 所有输入通过构造函数，输出通过方法返回
        - Stateless where possible: 最小化内部状态

    Usage:
        server = UnixSocketServer(socket_path="/tmp/app.sock")
        await server.start()
        client, addr = await server.accept_connection()
        await server.stop()
    """

    def __init__(self, socket_path: str, auth_token: str | None = None) -> None:
        """初始化Unix Socket服务器

        Args:
            socket_path: Socket文件路径
            auth_token: 认证Token（可选，用于上层验证）

        Raises:
            ValueError: 如果socket_path为空
        """
        logger.info(
            "[ENTRY] UnixSocketServer.__init__ inputs={socket_path=%s, has_token=%s}",
            socket_path,
            auth_token is not None,
        )

        if not socket_path:
            raise ValueError("socket_path cannot be empty")

        self.socket_path = socket_path
        self.auth_token = auth_token
        self._server_socket: socket.socket | None = None
        self._running = False

        logger.info("[EXIT] UnixSocketServer.__init__ return=None")

    async def start(self) -> None:
        """启动Unix Socket服务器

        创建socket文件，设置权限，开始监听连接。

        I/O契约：
            Input: None
            Output: None (副作用：创建socket文件，开始监听)

        Raises:
            RuntimeError: 如果服务器已经在运行
            OSError: 如果无法创建socket或设置权限

        Implementation:
            1. 检查是否已启动
            2. 删除旧的socket文件（如果存在）
            3. 创建AF_UNIX socket
            4. 绑定到socket_path
            5. 设置0o600权限
            6. 开始监听（backlog=5）
            7. 设置非阻塞模式
        """
        logger.info("[ENTRY] UnixSocketServer.start inputs=None")

        if self._running:
            raise RuntimeError("Server is already running")

        # 删除旧的socket文件
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
            logger.info("[PROCESS] Removed old socket file: %s", self.socket_path)

        # 创建Unix socket
        self._server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_socket.bind(self.socket_path)
        logger.info("[PROCESS] Socket bound to: %s", self.socket_path)

        # 设置严格权限(仅所有者可访问)
        os.chmod(self.socket_path, 0o600)
        logger.info("[SECURITY] Socket permissions set to 600: %s", self.socket_path)

        # 开始监听
        self._server_socket.listen(5)
        self._server_socket.setblocking(False)
        self._running = True

        logger.info("[EXIT] UnixSocketServer.start return=None")

    async def stop(self) -> None:
        """停止Unix Socket服务器

        关闭socket连接，删除socket文件，清理资源。

        I/O契约：
            Input: None
            Output: None (副作用：关闭socket，删除文件)

        Implementation:
            1. 标记为非运行状态
            2. 关闭server socket
            3. 删除socket文件
            4. 清理内部状态
        """
        logger.info("[ENTRY] UnixSocketServer.stop inputs=None")

        self._running = False

        # 关闭socket
        if self._server_socket is not None:
            try:
                self._server_socket.close()
                logger.info("[PROCESS] Server socket closed")
            except Exception as e:
                logger.error("[ERROR] Failed to close socket: %s", e)

        # 删除socket文件
        if os.path.exists(self.socket_path):
            try:
                os.remove(self.socket_path)
                logger.info("[PROCESS] Socket file removed: %s", self.socket_path)
            except Exception as e:
                logger.error("[ERROR] Failed to remove socket file: %s", e)

        self._server_socket = None
        logger.info("[EXIT] UnixSocketServer.stop return=None")

    async def accept_connection(self) -> tuple[Any, Any]:
        """接受客户端连接

        等待并接受一个客户端连接。使用asyncio事件循环实现非阻塞等待。

        I/O契约：
            Input: None
            Output: (client_socket, client_address)
                - client_socket: 客户端socket对象
                - client_address: 客户端地址（Unix Socket为空字符串）

        Raises:
            RuntimeError: 如果服务器未启动
            OSError: 如果socket已关闭或发生网络错误

        Implementation:
            1. 检查服务器是否已启动
            2. 使用asyncio.loop.sock_accept()非阻塞等待连接
            3. 返回客户端socket和地址
        """
        logger.debug("[ENTRY] UnixSocketServer.accept_connection inputs=None")

        if not self._running or self._server_socket is None:
            raise RuntimeError("Server is not started")

        # 使用asyncio事件循环接受连接（非阻塞）
        loop = asyncio.get_running_loop()
        client_socket, client_addr = await loop.sock_accept(self._server_socket)

        logger.debug(
            "[EXIT] UnixSocketServer.accept_connection return=(socket, %s)", client_addr
        )
        return client_socket, client_addr

    def get_connection_info(self) -> dict:
        """获取连接信息

        返回客户端连接到此服务器所需的信息。

        I/O契约：
            Input: None
            Output: dict - 连接信息字典
                {
                    "type": "unix",
                    "path": "/path/to/socket"
                }

        Implementation:
            返回包含socket类型和路径的字典
        """
        logger.debug("[ENTRY] UnixSocketServer.get_connection_info inputs=None")

        info = {"type": "unix", "path": self.socket_path}

        logger.debug("[EXIT] UnixSocketServer.get_connection_info return=%s", info)
        return info
