"""Tool providers for AstrBot.

This module provides different tool providers that supply tools
through a unified interface:

- InternalToolProvider: Provides built-in AstrBot tools (cron, kb_query, send_message)
- PluginToolProvider: Provides tools registered by star plugins
- ComputerToolProvider: Provides computer-use tools (shell, Python, file ops, etc.)
"""

from astrbot._internal.tools.providers.computer import (
    ComputerToolProvider,
)
from astrbot._internal.tools.providers.internal import (
    InternalToolProvider,
)
from astrbot._internal.tools.providers.plugin import (
    PluginToolProvider,
)

__all__ = [
    "ComputerToolProvider",
    "InternalToolProvider",
    "PluginToolProvider",
]
