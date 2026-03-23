"""Computer tools provider for AstrBot.

This provider wraps the ComputerToolProvider from the computer module
to ensure computer tools are available through the unified provider interface.
"""

from typing import TYPE_CHECKING

from astrbot._internal.tools.base import FunctionTool

if TYPE_CHECKING:
    pass


class ComputerToolProvider:
    """Provider for computer-use tools (local/sandbox).

    This class wraps the existing ``ComputerToolProvider`` from
    ``astrbot.core.computer.computer_tool_provider`` to integrate
    computer tools into the unified provider interface.

    The computer tools include shell execution, Python code execution,
    file operations, browser automation, and skill management tools.
    """

    @staticmethod
    def get_all_tools() -> list[FunctionTool]:
        """Return all computer-use tools across all runtimes.

        Delegates to ``ComputerToolProvider.get_all_tools()`` which
        collects tools from all runtimes (local, sandbox, browser, neo).

        Creates **fresh instances** separate from the runtime caches so
        that setting ``active=False`` on them does not affect runtime
        behaviour. These registration-only instances let the WebUI display
        and assign tools without injecting them into actual LLM requests.

        Returns:
            list[FunctionTool]: A list of all computer FunctionTool instances.
        """
        from astrbot.core.computer.computer_tool_provider import (
            ComputerToolProvider as CoreComputerToolProvider,
        )

        return CoreComputerToolProvider.get_all_tools()
