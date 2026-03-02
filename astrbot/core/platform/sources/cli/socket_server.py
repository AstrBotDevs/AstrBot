"""Socket服务器模块

提供Unix Socket和TCP Socket服务器实现，以及平台检测和工厂函数。
"""

import asyncio
import os
import platform as platform_mod
import socket
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

# ------------------------------------------------------------------
# 平台检测
# ------------------------------------------------------------------


@dataclass
class PlatformInfo:
    """平台信息"""

    os_type: Literal["windows", "linux", "darwin"]
    python_version: tuple[int, int, int]
    supports_unix_socket: bool


def detect_platform() -> PlatformInfo:
    """检测当前平台信息"""
    system = platform_mod.system()
    if system == "Windows":
        os_type = "windows"
    elif system == "Linux":
        os_type = "linux"
    elif system == "Darwin":
        os_type = "darwin"
    else:
        os_type = "linux"

    vi = sys.version_info
    python_version = (
        (vi.major, vi.minor, vi.micro)
        if hasattr(vi, "major")
        else (vi[0], vi[1], vi[2])
    )

    supports_unix = os_type in ("linux", "darwin")
    if os_type == "windows" and python_version >= (3, 9, 0):
        try:
            if hasattr(socket, "AF_UNIX"):
                test_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                test_sock.close()
                supports_unix = True
        except (OSError, AttributeError):
            pass

    info = PlatformInfo(
        os_type=os_type,
        python_version=python_version,
        supports_unix_socket=supports_unix,
    )
    logger.info(
        f"[CLI] Platform: {info.os_type}, Python {info.python_version}, unix_socket={info.supports_unix_socket}"
    )
    return info


# ------------------------------------------------------------------
# Socket服务器抽象基类
# ------------------------------------------------------------------


class AbstractSocketServer(ABC):
    """Socket服务器抽象基类"""

    @abstractmethod
    async def start(self) -> None:
        pass

    @abstractmethod
    async def stop(self) -> None:
        pass

    @abstractmethod
    async def accept_connection(self) -> tuple[Any, Any]:
        pass

    @abstractmethod
    def get_connection_info(self) -> dict:
        pass


# ------------------------------------------------------------------
# TCP Socket服务器
# ------------------------------------------------------------------


class TCPSocketServer(AbstractSocketServer):
    """TCP Socket服务器，用于Windows或显式指定TCP的场景"""

    def __init__(
        self, host: str = "127.0.0.1", port: int = 0, auth_token: str | None = None
    ):
        self.host = host
        self.port = port
        self.auth_token = auth_token
        self.server_socket: socket.socket | None = None
        self.actual_port: int = port
        self._is_running = False

    async def start(self) -> None:
        if self._is_running:
            raise RuntimeError("Server is already running")

        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.actual_port = self.server_socket.getsockname()[1]
            self.server_socket.listen(5)
            self.server_socket.setblocking(False)
            self._is_running = True
            logger.info(f"[CLI] TCP server listening on {self.host}:{self.actual_port}")
        except Exception:
            if self.server_socket:
                self.server_socket.close()
                self.server_socket = None
            raise

    async def stop(self) -> None:
        if not self._is_running and self.server_socket is None:
            return
        if self.server_socket:
            self.server_socket.close()
            self.server_socket = None
        self._is_running = False
        logger.info("[CLI] TCP server stopped")

    async def accept_connection(self) -> tuple[Any, Any]:
        if not self._is_running or self.server_socket is None:
            raise RuntimeError("Server is not running")
        loop = asyncio.get_running_loop()
        return await loop.sock_accept(self.server_socket)

    def get_connection_info(self) -> dict:
        return {"type": "tcp", "host": self.host, "port": self.actual_port}


# ------------------------------------------------------------------
# Unix Socket服务器
# ------------------------------------------------------------------


class UnixSocketServer(AbstractSocketServer):
    """Unix Domain Socket服务器"""

    def __init__(self, socket_path: str, auth_token: str | None = None) -> None:
        if not socket_path:
            raise ValueError("socket_path cannot be empty")
        self.socket_path = socket_path
        self.auth_token = auth_token
        self._server_socket: socket.socket | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            raise RuntimeError("Server is already running")

        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

        self._server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_socket.bind(self.socket_path)
        os.chmod(self.socket_path, 0o600)
        self._server_socket.listen(5)
        self._server_socket.setblocking(False)
        self._running = True
        logger.info(f"[CLI] Unix socket server listening on {self.socket_path}")

    async def stop(self) -> None:
        self._running = False
        if self._server_socket is not None:
            try:
                self._server_socket.close()
            except Exception as e:
                logger.error(f"[CLI] Failed to close socket: {e}")
        if os.path.exists(self.socket_path):
            try:
                os.remove(self.socket_path)
            except Exception as e:
                logger.error(f"[CLI] Failed to remove socket file: {e}")
        self._server_socket = None
        logger.info("[CLI] Unix socket server stopped")

    async def accept_connection(self) -> tuple[Any, Any]:
        if not self._running or self._server_socket is None:
            raise RuntimeError("Server is not started")
        loop = asyncio.get_running_loop()
        return await loop.sock_accept(self._server_socket)

    def get_connection_info(self) -> dict:
        return {"type": "unix", "path": self.socket_path}


# ------------------------------------------------------------------
# 工厂函数
# ------------------------------------------------------------------


def create_socket_server(
    platform_info: PlatformInfo, config: dict, auth_token: str | None
) -> AbstractSocketServer:
    """根据平台和配置创建Socket服务器"""
    socket_type = config.get("socket_type", "auto")

    if socket_type == "tcp":
        use_tcp = True
    elif socket_type == "unix":
        use_tcp = False
    elif socket_type == "auto":
        use_tcp = (
            platform_info.os_type == "windows"
            and not platform_info.supports_unix_socket
        )
    else:
        logger.warning(
            f"[CLI] Invalid socket_type '{socket_type}', falling back to auto"
        )
        use_tcp = (
            platform_info.os_type == "windows"
            and not platform_info.supports_unix_socket
        )

    if use_tcp:
        host = config.get("tcp_host", "127.0.0.1")
        port = config.get("tcp_port", 0)
        server = TCPSocketServer(host=host, port=port, auth_token=auth_token)
    else:
        socket_path = config.get("socket_path") or os.path.join(
            get_astrbot_temp_path(), "astrbot.sock"
        )
        server = UnixSocketServer(socket_path=socket_path, auth_token=auth_token)

    logger.info(f"[CLI] Created {server.__class__.__name__}")
    return server
