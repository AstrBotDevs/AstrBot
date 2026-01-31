"""
CLI Platform Adapter Module

命令行模拟器平台适配器，用于快速测试AstrBot插件。
"""

from .cli_adapter import CLIPlatformAdapter
from .cli_event import CLIMessageEvent

__all__ = ["CLIPlatformAdapter", "CLIMessageEvent"]
