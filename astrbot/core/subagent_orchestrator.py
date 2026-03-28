from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

from astrbot import logger
from astrbot.core.agent.agent import Agent
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.provider.func_tool_manager import FunctionToolManager

if TYPE_CHECKING:
    from astrbot.core.persona_mgr import PersonaManager


class SubAgentOrchestrator:
    """Loads subagent definitions from config and registers handoff tools.

    This is intentionally lightweight: it does not execute agents itself.
    Execution happens via HandoffTool in FunctionToolExecutor.

    """

    def __init__(
        self, tool_mgr: FunctionToolManager, persona_mgr: PersonaManager
    ) -> None:
        self._tool_mgr = tool_mgr
        self._persona_mgr = persona_mgr
        self.handoffs: list[HandoffTool] = []
        self._dynamic_manager = None  # 动态SubAgent管理器引用
        self._enhanced_enabled = False
        self._log_level = "info"

    async def reload_from_config(self, cfg: dict[str, Any]) -> None:
        """从配置重新加载子代理定义"""
        from astrbot.core.astr_agent_context import AstrAgentContext

        agents = cfg.get("agents", [])
        if not isinstance(agents, list):
            logger.warning("subagent_orchestrator.agents must be a list")
            return

        handoffs: list[HandoffTool] = []
        for item in agents:
            if not isinstance(item, dict):
                continue
            if not item.get("enabled", True):
                continue

            name = str(item.get("name", "")).strip()
            if not name:
                continue

            persona_id = item.get("persona_id")
            if persona_id is not None:
                persona_id = str(persona_id).strip() or None
            persona_data = self._persona_mgr.get_persona_v3_by_id(persona_id)
            if persona_id and persona_data is None:
                logger.warning(
                    "SubAgent persona %s not found, fallback to inline prompt.",
                    persona_id,
                )

            instructions = str(item.get("system_prompt", "")).strip()
            public_description = str(item.get("public_description", "")).strip()
            provider_id = item.get("provider_id")
            if provider_id is not None:
                provider_id = str(provider_id).strip() or None
            tools = item.get("tools", [])
            begin_dialogs = None

            if persona_data:
                prompt = str(persona_data.get("prompt", "")).strip()
                if prompt:
                    instructions = prompt
                begin_dialogs = copy.deepcopy(
                    persona_data.get("_begin_dialogs_processed")
                )
                tools = persona_data.get("tools")
                if public_description == "" and prompt:
                    public_description = prompt[:120]
            if tools is None:
                tools = None
            elif not isinstance(tools, list):
                tools = []
            else:
                tools = [str(t).strip() for t in tools if str(t).strip()]

            agent = Agent[AstrAgentContext](
                name=name,
                instructions=instructions,
                tools=tools,  # type: ignore
            )
            agent.begin_dialogs = begin_dialogs
            handoff = HandoffTool(
                agent=agent,
                tool_description=public_description or None,
            )

            handoff.provider_id = provider_id

            handoffs.append(handoff)

        for handoff in handoffs:
            logger.info(f"Registered subagent handoff tool: {handoff.name}")

        self.handoffs = handoffs

        # 检查是否启用增强模式
        main_enable = cfg.get("main_enable", False)
        if main_enable:
            self._enhanced_enabled = True
            self._log_level = cfg.get("log_level", "info")
            logger.info("[SubAgentOrchestrator] Dynamic SubAgent mode enabled")

    def set_dynamic_manager(self, manager) -> None:
        """设置动态SubAgent管理器"""
        self._dynamic_manager = manager

    def get_dynamic_manager(self):
        """获取动态SubAgent管理器"""
        return self._dynamic_manager

    def is_enhanced_enabled(self) -> bool:
        """检查增强模式是否启用"""
        return self._enhanced_enabled

    def get_enhanced_prompt(self) -> str:
        """获取增强版系统提示词"""
        if not self._enhanced_enabled:
            return ""

        return """# Enhanced SubAgent Capability

You have the ability to dynamically create and manage subagents with isolated skills.

## Creating Subagents with Skills

When creating a subagent, you can assign specific skills to it:

```
create_dynamic_subagent(
    name="expert_analyst",
    instructions="You are a data analyst...",
    skills=["data_analysis", "visualization"]
)
```

**CAUTION**: Each subagent's skills are completely isolated. Subagent A with skills ["analysis"] cannot access Subagent B's skills ["coding"]. Skills are not shared between subagents.

## Skills Available

Available skills depend on the system's configuration. You should specify skills when creating subagents that need specialized capabilities.
When tasks are complex or require parallel processing, you can create specialized subagents to complete them.

## When to create subagents:

- The task can be explicitly decomposed
- Requires professional domain
- Processing very long contexts
- Parallel processing

## How to create subagents

Use `create_dynamic_subagent` tool

## How to delegate subagents ##

Use `transfer_to_{name}` tool if the subagent is created successfully.

## Subagent Lifecycle

Subagents are valid during session, but they will be cleaned up once you send the final answer to user.
If you wish to prevent a certain subagent from being automatically cleaned up, use `protect_subagent` tool.
Also, you can use the `unprotect_subagent` tool to remove protection.

## IMPORTANT ##

Since `transfer_to_{name}` corresponds to a function in a computer program，The name of subagents **MUSE BE ENGLISH**, no Chinese characters, punctuation marks, emojis or other characters not allowed in computer program.
    """.strip()
