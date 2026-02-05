"""CLI配置模块

拆分为单一职责的小组件：
- CLIConfig: 纯数据结构
- PathResolver: 路径解析
- ConfigFileReader: 配置文件读取
- ConfigLoader: 组合门面
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path, get_astrbot_temp_path

# ============================================================
# 原子组件：路径解析器
# ============================================================


class PathResolver:
    """路径解析器

    单一职责：解析和生成默认路径
    """

    @staticmethod
    def get_socket_path(custom_path: str = "") -> str:
        """获取Socket路径"""
        if custom_path:
            return custom_path
        return os.path.join(get_astrbot_temp_path(), "astrbot.sock")

    @staticmethod
    def get_input_file(custom_path: str = "") -> str:
        """获取输入文件路径"""
        if custom_path:
            return custom_path
        return os.path.join(get_astrbot_temp_path(), "astrbot_cli", "input.txt")

    @staticmethod
    def get_output_file(custom_path: str = "") -> str:
        """获取输出文件路径"""
        if custom_path:
            return custom_path
        return os.path.join(get_astrbot_temp_path(), "astrbot_cli", "output.txt")

    @staticmethod
    def get_config_file_path(filename: str = "cli_config.json") -> str:
        """获取配置文件路径"""
        return os.path.join(get_astrbot_data_path(), filename)


# ============================================================
# 原子组件：配置文件读取器
# ============================================================


class ConfigFileReader:
    """配置文件读取器

    单一职责：读取JSON配置文件
    """

    @staticmethod
    def read(file_path: str) -> dict | None:
        """读取配置文件

        Args:
            file_path: 配置文件路径

        Returns:
            配置字典或None
        """
        if not os.path.exists(file_path):
            return None

        try:
            with open(file_path, encoding="utf-8") as f:
                config = json.load(f)
            logger.info("Loaded config from %s", file_path)
            return config
        except Exception as e:
            logger.warning("Failed to load config from %s: %s", file_path, e)
            return None


# ============================================================
# 数据结构：CLI配置
# ============================================================


@dataclass
class CLIConfig:
    """CLI配置数据类

    纯数据结构，不包含业务逻辑
    """

    # 运行模式
    mode: str = "socket"
    socket_type: str = "auto"
    socket_path: str = ""
    tcp_host: str = "127.0.0.1"
    tcp_port: int = 0

    # 文件模式配置
    input_file: str = ""
    output_file: str = ""
    poll_interval: float = 1.0

    # 会话配置
    use_isolated_sessions: bool = False
    session_ttl: int = 30

    # 其他
    whitelist: list[str] = field(default_factory=list)
    platform_id: str = "cli"


# ============================================================
# 组合组件：配置构建器
# ============================================================


class ConfigBuilder:
    """配置构建器

    从字典构建CLIConfig，处理默认值
    """

    @staticmethod
    def build(config_dict: dict[str, Any]) -> CLIConfig:
        """从字典构建配置"""
        return CLIConfig(
            mode=config_dict.get("mode", "socket"),
            socket_type=config_dict.get("socket_type", "auto"),
            socket_path=PathResolver.get_socket_path(
                config_dict.get("socket_path", "")
            ),
            tcp_host=config_dict.get("tcp_host", "127.0.0.1"),
            tcp_port=config_dict.get("tcp_port", 0),
            input_file=PathResolver.get_input_file(config_dict.get("input_file", "")),
            output_file=PathResolver.get_output_file(
                config_dict.get("output_file", "")
            ),
            poll_interval=config_dict.get("poll_interval", 1.0),
            use_isolated_sessions=config_dict.get("use_isolated_sessions", False),
            session_ttl=config_dict.get("session_ttl", 30),
            whitelist=config_dict.get("whitelist", []),
            platform_id=config_dict.get("id", "cli"),
        )


# ============================================================
# 组合组件：配置合并器
# ============================================================


class ConfigMerger:
    """配置合并器

    合并多个配置源
    """

    @staticmethod
    def merge(base: dict, override: dict | None) -> dict:
        """合并配置，override优先"""
        if override is None:
            return base.copy()

        result = base.copy()
        result.update(override)
        return result


# ============================================================
# 门面：配置加载器
# ============================================================


class ConfigLoader:
    """配置加载器门面

    组合所有小组件，提供统一接口

    I/O契约:
        Input: platform_config (dict), platform_settings (dict)
        Output: CLIConfig
    """

    @staticmethod
    def load(
        platform_config: dict[str, Any],
        platform_settings: dict[str, Any] | None = None,
    ) -> CLIConfig:
        """加载CLI配置

        优先级: 独立配置文件 > platform_config > 默认值

        Args:
            platform_config: 平台配置字典
            platform_settings: 平台设置字典

        Returns:
            CLIConfig实例
        """
        # 尝试从独立配置文件加载
        config_filename = platform_config.get("config_file", "cli_config.json")
        config_path = PathResolver.get_config_file_path(config_filename)

        file_config = ConfigFileReader.read(config_path)

        # 合并配置
        if file_config:
            if "platform_config" in file_config:
                platform_config = ConfigMerger.merge(
                    platform_config, file_config["platform_config"]
                )

        # 构建最终配置
        return ConfigBuilder.build(platform_config)
