"""Built-in tools for AstrBot.

This module provides access to all AstrBot built-in tools that are part of
the internal tool providers system.
"""

from astrbot._internal.tools.base import FunctionTool
from astrbot._internal.tools.builtin.cron import (
    CREATE_CRON_JOB_TOOL,
    DELETE_CRON_JOB_TOOL,
    LIST_CRON_JOBS_TOOL,
)
from astrbot._internal.tools.builtin.cron import (
    get_all_tools as cron_get_all_tools,
)
from astrbot._internal.tools.builtin.kb_query import (
    KNOWLEDGE_BASE_QUERY_TOOL,
)
from astrbot._internal.tools.builtin.kb_query import (
    get_all_tools as kb_query_get_all_tools,
)
from astrbot._internal.tools.builtin.send_message import (
    SEND_MESSAGE_TO_USER_TOOL,
)
from astrbot._internal.tools.builtin.send_message import (
    get_all_tools as send_message_get_all_tools,
)


def get_all_tools() -> list[FunctionTool]:
    """Return all built-in tools for registration.

    This aggregates tools from all built-in tool modules:
    - cron tools (create/delete/list future tasks)
    - knowledge base query tool
    - send message tool
    """
    tools: list[FunctionTool] = []
    tools.extend(cron_get_all_tools())
    tools.extend(kb_query_get_all_tools())
    tools.extend(send_message_get_all_tools())
    return tools


__all__ = [
    "CREATE_CRON_JOB_TOOL",
    "DELETE_CRON_JOB_TOOL",
    "KNOWLEDGE_BASE_QUERY_TOOL",
    "LIST_CRON_JOBS_TOOL",
    "SEND_MESSAGE_TO_USER_TOOL",
    "get_all_tools",
]
