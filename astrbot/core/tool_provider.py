"""ToolProvider protocol for decoupled tool injection.

ToolProviders supply tools and system-prompt addons to the main agent
without the agent builder knowing about specific tool implementations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from astrbot.core.agent.tool import FunctionTool


class ToolProviderContext:
    """Session-level context passed to ToolProvider methods.

    Wraps the information a provider needs to decide which tools to offer.
    """

    __slots__ = ("computer_use_runtime", "sandbox_cfg", "session_id")

    def __init__(
        self,
        *,
        computer_use_runtime: str = "none",
        sandbox_cfg: dict | None = None,
        session_id: str = "",
    ) -> None:
        self.computer_use_runtime = computer_use_runtime
        self.sandbox_cfg = sandbox_cfg or {}
        self.session_id = session_id


class ToolProvider(Protocol):
    """Protocol for pluggable tool providers.

    Each provider returns its tools and an optional system-prompt addon
    based on the current session context.
    """

    def get_tools(self, ctx: ToolProviderContext) -> list[FunctionTool]:
        """Return tools available for this session."""
        ...

    def get_system_prompt_addon(self, ctx: ToolProviderContext) -> str:
        """Return text to append to the system prompt, or empty string."""
        ...
