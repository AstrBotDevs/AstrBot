"""配置定义

集中管理工具执行系统的配置常量。
"""

from dataclasses import dataclass

# 后台任务管理工具名称（不应用超时）
BACKGROUND_TOOL_NAMES = frozenset(
    {
        "wait_tool_result",
        "get_tool_output",
        "stop_tool",
        "list_running_tools",
    }
)


@dataclass(frozen=True)
class BackgroundToolConfig:
    """后台工具执行配置

    所有配置项的默认值集中定义在此，便于统一管理。
    """

    # 清理间隔（秒）
    cleanup_interval_seconds: int = 600

    # 已完成任务保留时间（秒）
    task_max_age_seconds: int = 3600

    # 后台任务默认超时（秒）
    default_timeout_seconds: int = 600

    # 错误预览最大长度
    error_preview_max_length: int = 500

    # 输出日志默认行数
    default_output_lines: int = 50


# 默认配置实例
DEFAULT_CONFIG = BackgroundToolConfig()
