"""
AstrBot Public API.

This package exposes the public interface for extending and integrating with
AstrBot. All exports from this module are guaranteed to be stable across
minor version updates.

Modules:
    tools: Tool registration and management API
    mcp: Model Context Protocol server and tool API
    skills: Skill management and conversion API
"""

from astrbot import logger

# MCP API
from astrbot.api.mcp import (
    MCPClient,
    MCPTool,
    get_mcp_servers,
    register_mcp_server,
    unregister_mcp_server,
)

# Skills API
from astrbot.api.skills import (
    SkillInfo,
    SkillManager,
    get_skill_manager,
    skill_to_tool,
)

# Tools API
from astrbot.api.tools import ToolRegistry, get_registry, tool
from astrbot.core import html_renderer, sp
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.agent.tool_executor import BaseFunctionToolExecutor
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.star.register import register_agent as agent
from astrbot.core.star.register import register_llm_tool as llm_tool

__all__ = [
    "AstrBotConfig",
    "BaseFunctionToolExecutor",
    "FunctionTool",
    "MCPClient",
    "MCPTool",
    "SkillInfo",
    "SkillManager",
    "ToolRegistry",
    "ToolSet",
    "agent",
    "get_mcp_servers",
    "get_registry",
    "get_skill_manager",
    "html_renderer",
    "llm_tool",
    "logger",
    "register_mcp_server",
    "skill_to_tool",
    "sp",
    "tool",
    "unregister_mcp_server",
]
