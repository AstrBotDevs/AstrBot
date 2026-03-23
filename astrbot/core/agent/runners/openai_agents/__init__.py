"""OpenAI Agents SDK integration for AstrBot.

This module provides integration with the openai-agents library,
allowing AstrBot to leverage the openai-agents Agent implementation
while using its existing tool and provider infrastructure.

Usage:
    from astrbot.core.agent.runners.openai_agents import OpenAIAgentsRunner

    runner = OpenAIAgentsRunner(agent_config)
    async for response in runner.run():
        print(response)
"""

from .runner import OpenAIAgentsRunner
from .tool_adapter import astrbot_tool_to_agents_tool

__all__ = [
    "OpenAIAgentsRunner",
    "astrbot_tool_to_agents_tool",
]
