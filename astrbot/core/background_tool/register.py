"""后台工具注册

将后台任务管理工具注册到AstrBot的LLM工具系统。
"""

from astrbot import logger
from astrbot.core.provider.func_tool_manager import FuncCall


def register_background_tools(llm_tools: FuncCall) -> None:
    """注册后台任务管理工具

    Args:
        llm_tools: LLM工具管理器实例
    """
    from .llm_tools import (
        get_tool_output,
        wait_tool_result,
        stop_tool,
        list_running_tools,
    )

    # 注册 get_tool_output 工具
    llm_tools.add_func(
        name="get_tool_output",
        func_args=[
            {
                "name": "task_id",
                "type": "string",
                "description": "The ID of the background task",
            },
            {
                "name": "lines",
                "type": "integer",
                "description": "Number of recent lines to return (default: 50)",
            },
        ],
        desc="View the output logs of a background tool. Use this to check the progress of a long-running task.",
        handler=get_tool_output,
    )
    logger.info("[PROCESS] Registered LLM tool: get_tool_output")

    # 注册 wait_tool_result 工具
    llm_tools.add_func(
        name="wait_tool_result",
        func_args=[
            {
                "name": "task_id",
                "type": "string",
                "description": "The ID of the background task",
            },
        ],
        desc="Wait for a background tool to complete. The wait can be interrupted by new user messages. No timeout - waits until task finishes or is terminated.",
        handler=wait_tool_result,
    )
    logger.info("[PROCESS] Registered LLM tool: wait_tool_result")

    # 注册 stop_tool 工具
    llm_tools.add_func(
        name="stop_tool",
        func_args=[
            {
                "name": "task_id",
                "type": "string",
                "description": "The ID of the background task to stop",
            },
        ],
        desc="Stop a running background tool.",
        handler=stop_tool,
    )
    logger.info("[PROCESS] Registered LLM tool: stop_tool")

    # 注册 list_running_tools 工具
    llm_tools.add_func(
        name="list_running_tools",
        func_args=[],
        desc="List all currently running background tools in this session.",
        handler=list_running_tools,
    )
    logger.info("[PROCESS] Registered LLM tool: list_running_tools")

    logger.info("[PROCESS] All background tool management tools registered")
