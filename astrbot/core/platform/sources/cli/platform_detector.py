"""
Platform Detector Module

Detects the current operating system, Python version, and Unix Socket support.
Follows Unix philosophy: single responsibility, pure function, explicit I/O.

Architecture:
    Input: None
    Output: PlatformInfo(os_type, python_version, supports_unix_socket)

Data Flow:
    [Start] -> detect_platform()
        -> [Detect OS] platform.system()
        -> [Detect Python Version] sys.version_info
        -> [Check Unix Socket Support]
        -> [Return] PlatformInfo
"""

import platform
import sys
import time
from dataclasses import dataclass
from typing import Literal

from astrbot import logger


@dataclass
class PlatformInfo:
    """Platform information dataclass

    Attributes:
        os_type: Operating system type (windows, linux, darwin)
        python_version: Python version tuple (major, minor, micro)
        supports_unix_socket: Whether Unix Socket is supported
    """

    os_type: Literal["windows", "linux", "darwin"]
    python_version: tuple[int, int, int]
    supports_unix_socket: bool


def _detect_os_type() -> Literal["windows", "linux", "darwin"]:
    """Detect operating system type

    Returns:
        OS type string: "windows", "linux", or "darwin"
        Unknown systems default to "linux" (Unix-like fallback)
    """
    start_time = time.time()
    logger.debug("[ENTRY] _detect_os_type inputs={}")

    system = platform.system()
    logger.debug(f"[PROCESS] platform.system() returned: {system}")

    # Normalize OS type
    if system == "Windows":
        os_type = "windows"
    elif system == "Linux":
        os_type = "linux"
    elif system == "Darwin":
        os_type = "darwin"
    else:
        # Unknown OS, default to linux (Unix-like fallback)
        logger.warning(f"[PROCESS] Unknown OS type: {system}, defaulting to linux")
        os_type = "linux"

    duration_ms = (time.time() - start_time) * 1000
    logger.debug(f"[EXIT] _detect_os_type return={os_type} time_ms={duration_ms:.2f}")

    return os_type


def _detect_python_version() -> tuple[int, int, int]:
    """Detect Python version

    Returns:
        Python version tuple (major, minor, micro)
    """
    start_time = time.time()
    logger.debug("[ENTRY] _detect_python_version inputs={}")

    # Handle both sys.version_info object and tuple (for testing)
    version_info = sys.version_info
    if hasattr(version_info, "major"):
        # Normal sys.version_info object
        version = (version_info.major, version_info.minor, version_info.micro)
    else:
        # Tuple (used in tests with mock.patch)
        version = (version_info[0], version_info[1], version_info[2])

    duration_ms = (time.time() - start_time) * 1000
    logger.debug(
        f"[EXIT] _detect_python_version return={version} time_ms={duration_ms:.2f}"
    )

    return version


def _check_windows_unix_socket_support(python_version: tuple[int, int, int]) -> bool:
    """Check if Windows supports Unix Socket

    Requirements:
        - Python 3.9+
        - Windows 10 build 17063+

    Args:
        python_version: Python version tuple

    Returns:
        True if Unix Socket is supported, False otherwise
    """
    start_time = time.time()
    logger.debug(
        f"[ENTRY] _check_windows_unix_socket_support inputs={{python_version={python_version}}}"
    )

    # Check Python version (must be 3.9+)
    if python_version < (3, 9, 0):
        logger.debug(
            f"[PROCESS] Python version {python_version} < 3.9.0, Unix Socket not supported"
        )
        duration_ms = (time.time() - start_time) * 1000
        logger.debug(
            f"[EXIT] _check_windows_unix_socket_support return=False time_ms={duration_ms:.2f}"
        )
        return False

    # Check Windows build version
    try:
        win_ver = platform.win32_ver()
        logger.debug(f"[PROCESS] platform.win32_ver() returned: {win_ver}")

        # win_ver returns: (release, version, csd, ptype)
        # version format: "10.0.19041"
        version_str = win_ver[1]

        if not version_str:
            logger.warning("[PROCESS] Unable to determine Windows build version")
            duration_ms = (time.time() - start_time) * 1000
            logger.debug(
                f"[EXIT] _check_windows_unix_socket_support return=False time_ms={duration_ms:.2f}"
            )
            return False

        # Parse build number from version string
        # Format: "major.minor.build"
        parts = version_str.split(".")
        if len(parts) >= 3:
            build = int(parts[2])
            logger.debug(f"[PROCESS] Windows build number: {build}")

            # Unix Socket support requires build 17063+
            if build >= 17063:
                logger.debug(f"[PROCESS] Build {build} >= 17063, Unix Socket supported")
                supports = True
            else:
                logger.debug(
                    f"[PROCESS] Build {build} < 17063, Unix Socket not supported"
                )
                supports = False
        else:
            logger.warning(
                f"[PROCESS] Unable to parse build number from version: {version_str}"
            )
            supports = False

    except Exception as e:
        logger.error(f"[ERROR] Failed to check Windows version: {e}", exc_info=True)
        supports = False

    duration_ms = (time.time() - start_time) * 1000
    logger.debug(
        f"[EXIT] _check_windows_unix_socket_support return={supports} time_ms={duration_ms:.2f}"
    )

    return supports


def _check_unix_socket_support(
    os_type: Literal["windows", "linux", "darwin"], python_version: tuple[int, int, int]
) -> bool:
    """Check if Unix Socket is supported on current platform

    Logic:
        - Linux/Darwin: Always supported
        - Windows: Requires Python 3.9+ and Windows 10 build 17063+

    Args:
        os_type: Operating system type
        python_version: Python version tuple

    Returns:
        True if Unix Socket is supported, False otherwise
    """
    start_time = time.time()
    logger.debug(
        f"[ENTRY] _check_unix_socket_support inputs={{os_type={os_type}, python_version={python_version}}}"
    )

    if os_type in ("linux", "darwin"):
        logger.debug(f"[PROCESS] OS type {os_type} always supports Unix Socket")
        supports = True
    elif os_type == "windows":
        logger.debug("[PROCESS] Checking Windows Unix Socket support")
        supports = _check_windows_unix_socket_support(python_version)
    else:
        # Unknown OS, assume Unix Socket support (Unix-like fallback)
        logger.warning(
            f"[PROCESS] Unknown OS type {os_type}, assuming Unix Socket support"
        )
        supports = True

    duration_ms = (time.time() - start_time) * 1000
    logger.debug(
        f"[EXIT] _check_unix_socket_support return={supports} time_ms={duration_ms:.2f}"
    )

    return supports


def detect_platform() -> PlatformInfo:
    """Detect platform information

    Pure function with no side effects (except logging).
    Detects OS type, Python version, and Unix Socket support.

    Returns:
        PlatformInfo: Platform information dataclass

    Example:
        >>> info = detect_platform()
        >>> print(f"OS: {info.os_type}, Python: {info.python_version}")
        OS: windows, Python: (3, 10, 0)
    """
    start_time = time.time()
    logger.info("[ENTRY] detect_platform inputs={}")

    # Step 1: Detect OS type
    os_type = _detect_os_type()
    logger.info(f"[PROCESS] Detected OS type: {os_type}")

    # Step 2: Detect Python version
    python_version = _detect_python_version()
    logger.info(f"[PROCESS] Detected Python version: {python_version}")

    # Step 3: Check Unix Socket support
    supports_unix_socket = _check_unix_socket_support(os_type, python_version)
    logger.info(f"[PROCESS] Unix Socket support: {supports_unix_socket}")

    # Step 4: Create PlatformInfo
    platform_info = PlatformInfo(
        os_type=os_type,
        python_version=python_version,
        supports_unix_socket=supports_unix_socket,
    )

    duration_ms = (time.time() - start_time) * 1000
    logger.info(
        f"[EXIT] detect_platform return={platform_info} time_ms={duration_ms:.2f}"
    )

    return platform_info
