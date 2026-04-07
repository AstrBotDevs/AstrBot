"""
AstrBot core tools - DEPRECATED

.. deprecated::
    This module has been moved to :mod:`astrbot._internal.tools.builtin`.
    Please update your imports accordingly.

    Old import (deprecated):
        from astrbot.core.tools import cron_tools, send_message, kb_query

    New import:
        from astrbot._internal.tools.builtin import (
            CreateActiveCronTool,
            DeleteCronJobTool,
            ListCronJobsTool,
            SendMessageToUserTool,
            KnowledgeBaseQueryTool,
        )

This file exists solely for backward compatibility and will be removed in a future version.
"""

import warnings

warnings.warn(
    "astrbot.core.tools has been moved to astrbot._internal.tools.builtin. "
    "Please update your imports.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export from new location for backward compatibility
from astrbot._internal.tools.builtin import (
    CREATE_CRON_JOB_TOOL,
    DELETE_CRON_JOB_TOOL,
    KNOWLEDGE_BASE_QUERY_TOOL,
    LIST_CRON_JOBS_TOOL,
    SEND_MESSAGE_TO_USER_TOOL,
)

__all__ = [
    "CREATE_CRON_JOB_TOOL",
    "DELETE_CRON_JOB_TOOL",
    "KNOWLEDGE_BASE_QUERY_TOOL",
    "LIST_CRON_JOBS_TOOL",
    "SEND_MESSAGE_TO_USER_TOOL",
]
