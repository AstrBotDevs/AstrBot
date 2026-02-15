"""
Socket Factory Module

Creates appropriate socket server instances based on platform information
and configuration. Follows the Factory Pattern to encapsulate creation logic.

Architecture:
    Input: PlatformInfo + config dict + auth_token
    Output: AbstractSocketServer instance (UnixSocketServer or TCPSocketServer)

Data Flow:
    [Platform Info] + [Config] + [Auth Token]
         |
         v
    [Decision Logic]
         |
    +----+----+
    |         |
    v         v
  Unix      TCP
  Socket    Socket
  Server    Server
"""

import os
import time
from typing import Literal

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from .platform_detector import PlatformInfo
from .socket_abstract import AbstractSocketServer
from .tcp_socket_server import TCPSocketServer
from .unix_socket_server import UnixSocketServer


def _determine_socket_type(
    platform_info: PlatformInfo, config: dict
) -> Literal["unix", "tcp"]:
    """Determine which socket type to use

    Decision Logic:
        1. Check explicit user specification
        2. Auto-detect based on platform
        3. Fallback to auto-detection for invalid values

    Args:
        platform_info: Platform detection result
        config: Configuration dictionary

    Returns:
        Socket type: "unix" or "tcp"
    """
    start_time = time.time()
    logger.debug(
        f"[ENTRY] _determine_socket_type inputs={{platform_info={platform_info}, config={config}}}"
    )

    socket_type_config = config.get("socket_type", "auto")
    logger.debug(f"[PROCESS] socket_type from config: {socket_type_config}")

    # Step 1: Handle explicit specification
    if socket_type_config == "tcp":
        logger.info("[PROCESS] Explicitly specified socket_type=tcp")
        result = "tcp"
    elif socket_type_config == "unix":
        logger.info("[PROCESS] Explicitly specified socket_type=unix")
        result = "unix"
    elif socket_type_config == "auto":
        # Step 2: Auto-detection
        logger.debug("[PROCESS] Auto-detection mode")
        if (
            platform_info.os_type == "windows"
            and not platform_info.supports_unix_socket
        ):
            logger.info(
                "[PROCESS] Auto-detected: Windows without Unix Socket support, using TCP"
            )
            result = "tcp"
        else:
            logger.info(
                f"[PROCESS] Auto-detected: {platform_info.os_type} with Unix Socket support, using Unix"
            )
            result = "unix"
    else:
        # Step 3: Invalid value, fallback to auto-detection
        logger.warning(
            f"[PROCESS] Invalid socket_type '{socket_type_config}', falling back to auto-detection"
        )
        if (
            platform_info.os_type == "windows"
            and not platform_info.supports_unix_socket
        ):
            result = "tcp"
        else:
            result = "unix"

    duration_ms = (time.time() - start_time) * 1000
    logger.debug(
        f"[EXIT] _determine_socket_type return={result} time_ms={duration_ms:.2f}"
    )

    return result


def _create_unix_socket_server(
    config: dict, auth_token: str | None
) -> AbstractSocketServer:
    """Create Unix Socket server instance

    Args:
        config: Configuration dictionary
        auth_token: Authentication token

    Returns:
        UnixSocketServer instance
    """
    start_time = time.time()
    logger.debug(
        f"[ENTRY] _create_unix_socket_server inputs={{config={config}, auth_token={'***' if auth_token else None}}}"
    )

    # Get socket path from config or use default (handle None values)
    socket_path = config.get("socket_path") or os.path.join(
        get_astrbot_temp_path(), "astrbot.sock"
    )
    logger.debug(f"[PROCESS] Using Unix Socket path: {socket_path}")

    # Create Unix Socket server
    server = UnixSocketServer(socket_path=socket_path, auth_token=auth_token)

    duration_ms = (time.time() - start_time) * 1000
    logger.debug(
        f"[EXIT] _create_unix_socket_server return=UnixSocketServer time_ms={duration_ms:.2f}"
    )

    return server


def _create_tcp_socket_server(
    config: dict, auth_token: str | None
) -> AbstractSocketServer:
    """Create TCP Socket server instance

    Args:
        config: Configuration dictionary
        auth_token: Authentication token

    Returns:
        TCPSocketServer instance
    """
    start_time = time.time()
    logger.debug(
        f"[ENTRY] _create_tcp_socket_server inputs={{config={config}, auth_token={'***' if auth_token else None}}}"
    )

    # Get TCP configuration from config or use defaults
    tcp_host = config.get("tcp_host", "127.0.0.1")
    tcp_port = config.get("tcp_port", 0)
    logger.debug(f"[PROCESS] Using TCP host: {tcp_host}, port: {tcp_port}")

    # Create TCP Socket server
    server = TCPSocketServer(host=tcp_host, port=tcp_port, auth_token=auth_token)

    duration_ms = (time.time() - start_time) * 1000
    logger.debug(
        f"[EXIT] _create_tcp_socket_server return=TCPSocketServer time_ms={duration_ms:.2f}"
    )

    return server


def create_socket_server(
    platform_info: PlatformInfo, config: dict, auth_token: str | None
) -> AbstractSocketServer:
    """Create socket server based on platform and configuration

    Decision Logic:
        1. User explicitly specifies socket_type ("unix" or "tcp")
        2. Auto-detection mode: Windows without Unix Socket support uses TCP
        3. Fallback strategy: Invalid config falls back to auto-detection

    Args:
        platform_info: Platform detection result
        config: Configuration dictionary containing socket_type, paths, etc.
        auth_token: Authentication token (optional)

    Returns:
        AbstractSocketServer instance (UnixSocketServer or TCPSocketServer)

    Example:
        >>> platform_info = detect_platform()
        >>> config = {"socket_type": "auto"}
        >>> server = create_socket_server(platform_info, config, "token123")
    """
    start_time = time.time()
    logger.info(
        f"[ENTRY] create_socket_server inputs={{platform_info={platform_info}, "
        f"socket_type={config.get('socket_type', 'auto')}, auth_token={'***' if auth_token else None}}}"
    )

    # Step 1: Determine socket type
    socket_type = _determine_socket_type(platform_info, config)
    logger.info(f"[PROCESS] Selected socket type: {socket_type}")

    # Step 2: Create appropriate server
    if socket_type == "tcp":
        server = _create_tcp_socket_server(config, auth_token)
    else:  # socket_type == "unix"
        server = _create_unix_socket_server(config, auth_token)

    duration_ms = (time.time() - start_time) * 1000
    logger.info(
        f"[EXIT] create_socket_server return={server.__class__.__name__} time_ms={duration_ms:.2f}"
    )

    return server
