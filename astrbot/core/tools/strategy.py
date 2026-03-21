"""Abstract base class for tool search strategies.

ToolSearchStrategy defines the contract that all provider-specific strategies
must implement. Phase 6 (generic path) and Phase 7 (Claude-native path) each
provide a concrete implementation.

The ABC is deliberately minimal -- two methods only -- following the project's
existing ContentSafetyStrategy ABC pattern.
"""

from __future__ import annotations

import abc

from astrbot.core.agent.tool import FunctionTool, ToolSet


class ToolSearchStrategy(abc.ABC):
    """Abstract strategy for tool search behavior.

    Concrete implementations decide how to build the tools parameter for each
    LLM request and how to expose the tool_search tool.
    """

    @abc.abstractmethod
    def build_tool_set(self) -> ToolSet:
        """Build the tools parameter for the current LLM request.

        Returns:
            A :class:`ToolSet` containing the tools to send to the LLM.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def get_tool_search_tool(self) -> FunctionTool:
        """Return the tool_search FunctionTool instance.

        Returns:
            The :class:`FunctionTool` (or subclass) that performs tool search.
        """
        raise NotImplementedError
