"""ConnectionInfoWriter - 连接信息写入器

将Socket连接信息写入JSON文件，供客户端读取。
遵循Unix哲学：原子化操作、显式I/O、无副作用。
"""

import json
import os
import tempfile
from typing import Any

from astrbot import logger


def write_connection_info(connection_info: dict[str, Any], data_dir: str) -> None:
    """写入连接信息到文件

    I/O契约:
        Input:
            connection_info: Socket连接信息
                - type: "unix" | "tcp"
                - path: str (Unix Socket)
                - host: str (TCP Socket)
                - port: int (TCP Socket)
            data_dir: 数据目录路径
        Output: None (副作用: 写入到 {data_dir}/.cli_connection)

    Args:
        connection_info: 连接信息字典
        data_dir: 数据目录路径

    Raises:
        ValueError: 连接信息格式无效
        OSError: 文件写入失败
    """
    logger.info(
        "[ENTRY] write_connection_info inputs={info=%s, dir=%s}",
        connection_info,
        data_dir,
    )

    # 验证输入
    _validate_connection_info(connection_info)

    # 目标文件路径
    target_path = os.path.join(data_dir, ".cli_connection")
    logger.debug("[PROCESS] Target file: %s", target_path)

    # 原子写入：先写临时文件，再重命名
    try:
        # 创建临时文件（同目录，确保原子重命名）
        fd, temp_path = tempfile.mkstemp(
            dir=data_dir, prefix=".cli_connection.", suffix=".tmp"
        )
        logger.debug("[PROCESS] Created temp file: %s", temp_path)

        try:
            # 写入JSON数据
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(connection_info, f, indent=2)
            logger.debug("[PROCESS] JSON data written to temp file")

            # 尝试设置文件权限（Windows下尽力而为）
            _set_file_permissions(temp_path)

            # 原子重命名
            os.replace(temp_path, target_path)
            logger.info("[PROCESS] Atomic rename completed: %s", target_path)

        except Exception:
            # 清理临时文件
            if os.path.exists(temp_path):
                os.remove(temp_path)
                logger.debug("[PROCESS] Cleaned up temp file: %s", temp_path)
            raise

    except Exception as e:
        logger.error("[ERROR] Failed to write connection info: %s", e)
        raise

    logger.info("[EXIT] write_connection_info return=None")


def _validate_connection_info(connection_info: dict[str, Any]) -> None:
    """验证连接信息格式

    Args:
        connection_info: 连接信息字典

    Raises:
        ValueError: 格式无效
    """
    if not isinstance(connection_info, dict):
        raise ValueError("connection_info must be a dict")

    conn_type = connection_info.get("type")
    if conn_type not in ("unix", "tcp"):
        raise ValueError(f"Invalid type: {conn_type}, must be 'unix' or 'tcp'")

    if conn_type == "unix":
        if "path" not in connection_info:
            raise ValueError("Unix socket requires 'path' field")
    elif conn_type == "tcp":
        if "host" not in connection_info or "port" not in connection_info:
            raise ValueError("TCP socket requires 'host' and 'port' fields")


def _set_file_permissions(file_path: str) -> None:
    """设置文件权限（Windows下尽力而为）

    Args:
        file_path: 文件路径
    """
    try:
        # Unix/Linux: 设置600权限
        os.chmod(file_path, 0o600)
        logger.debug("[SECURITY] File permissions set to 600: %s", file_path)
    except (OSError, NotImplementedError) as e:
        # Windows可能不支持chmod，记录警告但不失败
        logger.warning("[SECURITY] Failed to set file permissions (Windows?): %s", e)
