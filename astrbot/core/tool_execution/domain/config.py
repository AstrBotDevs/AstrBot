"""配置定义"""

# 后台任务管理工具名称（不应用超时）
BACKGROUND_TOOL_NAMES = frozenset(
    {
        "wait_tool_result",
        "get_tool_output",
        "stop_tool",
        "list_running_tools",
    }
)
