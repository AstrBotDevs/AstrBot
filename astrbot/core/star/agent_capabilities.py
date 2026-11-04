"""Session plugin availability for registered tools and skills."""

from astrbot.core.agent.mcp_client import MCPTool
from astrbot.core.agent.tool import ToolSet
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.skills.skill_manager import SkillInfo
from astrbot.core.star.star import star_registry
from astrbot.core.star.star_handler import star_map


def filter_skills(
    skills: list[SkillInfo],
    cfg: dict,
) -> list[SkillInfo]:
    """Keep skills belonging to active plugins enabled by this session.

    Args:
        skills: Skills available in the selected runtime.
        cfg: Session provider settings, including the enabled plugin list.

    Returns:
        Local skills and skills from available plugins.
    """
    plugin_set = cfg.get("plugin_set", ["*"])
    allowed_plugins = (
        None
        if not isinstance(plugin_set, list) or "*" in plugin_set
        else {str(name) for name in plugin_set}
    )
    plugin_by_root_dir = {
        metadata.root_dir_name: metadata
        for metadata in star_registry
        if metadata.root_dir_name
    }
    filtered: list[SkillInfo] = []
    for skill in skills:
        if skill.source_type != "plugin":
            filtered.append(skill)
            continue

        plugin = plugin_by_root_dir.get(skill.plugin_name)
        if not plugin or not plugin.activated:
            continue
        if plugin.reserved or allowed_plugins is None:
            filtered.append(skill)
            continue
        if plugin.name is not None and plugin.name in allowed_plugins:
            filtered.append(skill)
    return filtered


def filter_tools(event: AstrMessageEvent, tools: ToolSet) -> ToolSet:
    """Filter plugin-owned tools using the session's enabled-plugin list.

    Args:
        event: Event carrying the session plugin selection.
        tools: Available tools. MCP tools, handoffs,
            and tools with unknown ownership retain their existing availability.

    Returns:
        The tool set restricted to the caller's enabled plugins.
    """
    if event.plugins_name is not None:
        new_tool_set = ToolSet()
        for tool in tools.tools:
            if isinstance(tool, MCPTool):
                # MCP tools are not owned by plugins.
                new_tool_set.add_tool(tool)
                continue
            mp = tool.handler_module_path
            if not mp:
                # Tools without plugin ownership include subagent handoffs.
                new_tool_set.add_tool(tool)
                continue
            plugin = star_map.get(mp)
            if not plugin:
                # Preserve tools when their plugin ownership cannot be resolved.
                new_tool_set.add_tool(tool)
                continue
            if plugin.name in event.plugins_name or plugin.reserved:
                new_tool_set.add_tool(tool)
        return new_tool_set
    return tools
