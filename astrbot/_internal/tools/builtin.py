"""
Builtin tools for AstrBot - re-exports from core.tools for backward compatibility.

This module re-exports the builtin tools (cron, send_message, kb_query) from
the deprecated core.tools module for backward compatibility.

TODO: These tools should be fully migrated to _internal and core.tools
should be removed once all consumers update their imports.
"""

from __future__ import annotations

# Re-export cron tools
from astrbot.core.tools.cron_tools import (
    CREATE_CRON_JOB_TOOL,
    DELETE_CRON_JOB_TOOL,
    LIST_CRON_JOBS_TOOL,
    CreateActiveCronTool,
    DeleteCronJobTool,
    ListCronJobsTool,
)

# Re-export knowledge_base_query tool
from astrbot.core.tools.kb_query import (
    KNOWLEDGE_BASE_QUERY_TOOL,
    KnowledgeBaseQueryTool,
)

# Re-export send_message tool
from astrbot.core.tools.send_message import (
    SEND_MESSAGE_TO_USER_TOOL,
    SendMessageToUserTool,
)

__all__ = [
    # Cron tools
    "CREATE_CRON_JOB_TOOL",
    "DELETE_CRON_JOB_TOOL",
    "KNOWLEDGE_BASE_QUERY_TOOL",
    "LIST_CRON_JOBS_TOOL",
    "SEND_MESSAGE_TO_USER_TOOL",
    # Classes
    "CreateActiveCronTool",
    "DeleteCronJobTool",
    "KnowledgeBaseQueryTool",
    "ListCronJobsTool",
    "SendMessageToUserTool",
]
