"""
Abstract Socket Server Interface

This module defines the abstract base class for socket server implementations.
It provides a unified interface for both Unix Socket and TCP Socket servers,
enabling platform-independent socket communication.

Design Pattern: Abstract Factory Pattern
I/O Contract: Defines abstract methods that must be implemented by concrete classes
"""

from abc import ABC, abstractmethod
from typing import Any


class AbstractSocketServer(ABC):
    """Socket服务器抽象基类

    定义统一的Socket服务器接口，供UnixSocketServer和TCPSocketServer实现。
    所有子类必须实现全部抽象方法。

    Design Principles:
        - Single Responsibility: 仅定义接口契约
        - Open/Closed: 对扩展开放，对修改封闭
        - Liskov Substitution: 子类可替换父类

    Usage:
        class MySocketServer(AbstractSocketServer):
            async def start(self) -> None:
                # Implementation
                pass

            async def stop(self) -> None:
                # Implementation
                pass

            async def accept_connection(self) -> tuple[Any, Any]:
                # Implementation
                return (client_socket, client_address)

            def get_connection_info(self) -> dict:
                # Implementation
                return {"type": "unix", "path": "/tmp/socket"}
    """

    @abstractmethod
    async def start(self) -> None:
        """启动服务器

        启动Socket服务器并开始监听连接。此方法应该是非阻塞的，
        使用asyncio事件循环处理连接。

        Input: None
        Output: None (副作用：启动服务器，开始监听)

        Raises:
            OSError: 如果端口已被占用或权限不足
            RuntimeError: 如果服务器已经在运行

        Example:
            server = MySocketServer()
            await server.start()
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """停止服务器

        停止Socket服务器并清理所有资源（关闭socket、删除文件等）。
        此方法应该优雅地关闭所有活动连接。

        Input: None
        Output: None (副作用：停止服务器，清理资源)

        Example:
            await server.stop()
        """
        pass

    @abstractmethod
    async def accept_connection(self) -> tuple[Any, Any]:
        """接受客户端连接

        等待并接受一个客户端连接。此方法应该是非阻塞的，
        使用asyncio事件循环等待连接。

        Input: None
        Output: (client_socket, client_address)
            - client_socket: 客户端socket对象
            - client_address: 客户端地址（Unix Socket为空字符串，TCP为(host, port)）

        Raises:
            OSError: 如果socket已关闭或发生网络错误

        Example:
            client, addr = await server.accept_connection()
        """
        pass

    @abstractmethod
    def get_connection_info(self) -> dict:
        """获取连接信息

        返回客户端连接到此服务器所需的信息。
        不同类型的socket返回不同的字段。

        Input: None
        Output: dict - 连接信息字典
            Unix Socket: {"type": "unix", "path": "/path/to/socket"}
            TCP Socket: {"type": "tcp", "host": "127.0.0.1", "port": 12345}

        Example:
            info = server.get_connection_info()
            if info["type"] == "unix":
                print(f"Connect to: {info['path']}")
            elif info["type"] == "tcp":
                print(f"Connect to: {info['host']}:{info['port']}")
        """
        pass
