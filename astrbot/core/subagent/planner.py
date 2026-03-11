from __future__ import annotations

from typing import Any

from astrbot import logger
from astrbot.core.agent.agent import Agent
from astrbot.core.agent.handoff import HandoffTool

from .models import (
    SubagentAgentSpec,
    SubagentConfig,
    SubagentMountPlan,
    ToolsScope,
    build_safe_handoff_agent_name,
)


class SubagentPlanner:
    """Build a deterministic mount plan from canonical subagent configuration."""

    def __init__(
        self,
        tool_mgr: Any,
        persona_mgr: Any,
    ) -> None:
        self._tool_mgr = tool_mgr
        self._persona_mgr = persona_mgr

    async def build_mount_plan(self, config: SubagentConfig) -> SubagentMountPlan:
        diagnostics: list[str] = []
        handoffs: list[HandoffTool] = []
        handoff_map: dict[str, HandoffTool] = {}
        exclude_set: set[str] = set()

        all_active_tools = {
            tool.name
            for tool in self._tool_mgr.func_list
            if getattr(tool, "active", True) and not isinstance(tool, HandoffTool)
        }
        seen_agent_names: set[str] = set()

        for spec in config.agents:
            if not spec.enabled:
                continue

            safe_agent_name = spec.handoff_agent_name
            resolved_agent_name = safe_agent_name
            if resolved_agent_name in seen_agent_names:
                suffix = 2
                while suffix <= 99 and resolved_agent_name in seen_agent_names:
                    resolved_agent_name = build_safe_handoff_agent_name(
                        f"{spec.name}-{suffix}"
                    )
                    suffix += 1
                if resolved_agent_name in seen_agent_names:
                    diagnostics.append(
                        f"ERROR: duplicate subagent tool name generated from `{spec.name}`."
                    )
                    continue
                diagnostics.append(
                    "WARN: duplicate subagent tool name generated from "
                    f"`{spec.name}`, renamed to `{resolved_agent_name}`."
                )
            seen_agent_names.add(resolved_agent_name)

            persona = await self._resolve_persona(spec, diagnostics)
            instructions = self._resolve_instructions(spec, persona)
            public_description = self._resolve_public_description(spec, persona)
            tools = self._resolve_tools(spec, persona, all_active_tools, diagnostics)
            begin_dialogs = getattr(persona, "begin_dialogs", None) if persona else None

            agent = Agent[Any](
                name=resolved_agent_name,
                instructions=instructions,
                tools=tools,  # type: ignore[arg-type]
            )
            agent.begin_dialogs = begin_dialogs

            handoff = HandoffTool(
                agent=agent,
                tool_description=public_description or None,
            )
            handoff.provider_id = spec.provider_id
            handoff.agent_display_name = spec.name  # type: ignore[attr-defined]
            handoff.max_steps = spec.max_steps  # type: ignore[attr-defined]
            handoff.max_steps_unlimited = spec.max_steps is None  # type: ignore[attr-defined]
            handoffs.append(handoff)
            handoff_map[handoff.name] = handoff

            if config.remove_main_duplicate_tools:
                if tools is None:
                    exclude_set.update(all_active_tools)
                else:
                    exclude_set.update(
                        {name for name in tools if name in all_active_tools}
                    )

        for handoff in handoffs:
            logger.info("Registered subagent handoff tool: %s", handoff.name)

        return SubagentMountPlan(
            handoffs=handoffs,
            handoff_by_tool_name=handoff_map,
            main_tool_exclude_set=exclude_set,
            router_prompt=(config.router_system_prompt or "").strip() or None,
            diagnostics=diagnostics,
        )

    async def _resolve_persona(
        self,
        spec: SubagentAgentSpec,
        diagnostics: list[str],
    ) -> Any | None:
        if not spec.persona_id:
            return None
        try:
            return await self._persona_mgr.get_persona(spec.persona_id)
        except (ValueError, StopIteration):
            diagnostics.append(
                f"WARN: subagent `{spec.name}` persona `{spec.persona_id}` not found, fallback to inline settings."
            )
            return None

    @staticmethod
    def _resolve_instructions(spec: SubagentAgentSpec, persona: Any | None) -> str:
        if persona and getattr(persona, "system_prompt", None):
            return str(persona.system_prompt)
        return spec.instructions

    @staticmethod
    def _resolve_public_description(
        spec: SubagentAgentSpec, persona: Any | None
    ) -> str:
        if spec.public_description:
            return spec.public_description
        if persona and getattr(persona, "system_prompt", None):
            return str(persona.system_prompt)[:120]
        return ""

    @staticmethod
    def _resolve_tools(
        spec: SubagentAgentSpec,
        persona: Any | None,
        all_active_tools: set[str],
        diagnostics: list[str],
    ) -> list[str] | None:
        if spec.tools_scope == ToolsScope.ALL:
            return None
        if spec.tools_scope == ToolsScope.NONE:
            return []
        if spec.tools_scope == ToolsScope.PERSONA:
            if persona is None:
                diagnostics.append(
                    f"WARN: subagent `{spec.name}` uses tools_scope=persona but persona is missing."
                )
                return []
            tools = getattr(persona, "tools", None)
            if tools is None:
                return None
            if not isinstance(tools, list):
                return []
            return [str(t).strip() for t in tools if str(t).strip() in all_active_tools]

        tools = spec.tools or []
        filtered: list[str] = []
        for name in tools:
            tool_name = str(name).strip()
            if not tool_name:
                continue
            if tool_name.startswith("transfer_to_"):
                diagnostics.append(
                    f"WARN: subagent `{spec.name}` tool `{tool_name}` ignored to prevent recursive handoff."
                )
                continue
            if tool_name in all_active_tools:
                filtered.append(tool_name)
        return filtered
