"""
Dynamic SubAgent Manager
Manages dynamically created subagents for task decomposition and parallel processing
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field

from astrbot import logger
from astrbot.core.agent.agent import Agent
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.subagent_logger import SubAgentLogger


@dataclass
class DynamicSubAgentConfig:
    name: str
    system_prompt: str = ""
    tools: list | None = None
    skills: list | None = None
    provider_id: str | None = None
    description: str = ""
    max_steps: int = 30
    begin_dialogs: list | None = None


@dataclass
class SubAgentExecutionResult:
    task_id: str  # 任务唯一标识符
    agent_name: str
    success: bool
    result: str | None = None
    error: str | None = None
    execution_time: float = 0.0
    created_at: float = 0.0
    completed_at: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class DynamicSubAgentSession:
    session_id: str
    agents: dict = field(default_factory=dict)
    handoff_tools: dict = field(default_factory=dict)
    results: dict = field(default_factory=dict)
    enable_interaction: bool = False
    created_at: float = 0.0
    protected_agents: set = field(
        default_factory=set
    )  # 若某个agent受到保护，则不会被自动清理
    agent_histories: dict = field(default_factory=dict)  # 存储每个子代理的历史上下文
    shared_context: list = field(default_factory=list)  # 公共上下文列表
    shared_context_enabled: bool = False  # 是否启用公共上下文
    # SubAgent 结果存储: {agent_name: {task_id: SubAgentExecutionResult}}
    subagent_results: dict = field(default_factory=dict)
    # 任务计数器: {agent_name: next_task_id}
    _task_counters: dict = field(default_factory=dict)


class DynamicSubAgentManager:
    _sessions: dict = {}
    _log_level: str = "info"
    _max_subagent_count: int = 3
    _auto_cleanup_per_turn: bool = True
    _shared_context_enabled: bool = False
    _shared_context_maxlen: int = 200

    @classmethod
    def get_dynamic_subagent_prompt(cls):
        if cls._shared_context_enabled:
            shared_context_prompt = """- #### Collaborative Communication Mechanism
  **Communication Tool description**: Inform the sub-agent that `send_shared_context` tool can be used for public channel communication, visible to all online sub-agents and the main agent.
  **Communication protocol** : Clarify when to use this tool.
    Progress reporting: Status updates must be sent when a task starts, encounters a blockage, or is completed.
    Resource handover: After completing the task, send the generated file path and key conclusions to the public channel for use by downstream agents."""
        else:
            shared_context_prompt = ""

        return f"""# Dynamic Sub-Agent Capability

You are the Main Agent, and have the ability to dynamically create and manage sub-agents with isolated instructions, tools and skills.

## When to create Sub-agents:

- The task can be explicitly decomposed
- Requires multiple professional domain
- Processing very long contexts that exceeding the limitations of a single agent
- Parallel processing

## Primary Workflow

1. **Global planning**:
   After receiving a user request, first formulate an overall execution plan and break it down into multiple subtask steps.

   Identify the dependencies between subtasks (who comes first and who comes second, who depends on whose output, and which sub-agents can run in parallel).

2. **Sub-Agent Designing**:
   Use the `create_dynamic_subagent` tool to create multiple sub-agents, and `transfer_to_{{name}}` tools will be created, where `{{name}}` is the name of a sub-agent.

3. **Sub-Agent Delegating**
   Use the `transfer_to_{{name}}` tool to delegate sub-agent

## Creating Sub-agents with Name, System Prompt, Tools and Skills

When creating a sub-agent, you should name it with **letters, numbers, and underscores**, no Chinese characters, punctuation marks, emojis or other characters not allowed in computer program.

Meanwhile, you need to assign specific **System Prompt**, **Tools** and **Skills** to it. Each sub-agent's system prompt, tools and skills are completely isolated.

```
create_dynamic_subagent(
    name="expert_analyst",
    system_prompt="You are a data analyst...",
    tools=["astrbot_execute_shell", "astrbot_execute_python"],
    skills=["excel", "visualization", "data_analysis"]
)
```

**CAUTION**:  **YOU MUST FOLLOW THE STEPS BELOW** to give well-designed system prompt and allocate tools and skills.

### 1. When giving system prompt to a sub-agent, make it detailed, and you should include the following information to make them clear and standardized.

- #### Character Design

  Define the name, professional identity, and personality traits of the sub-agent.

- #### Global Tasks and Positioning

  **Overall task description**: Briefly summarize the user's ultimate goal, so that the sub-agent knows what it is striving for.
  **Current step and position**: If the tasks are parallel, tell the sub-agent that there are other parallel sub-agents. If there are serial parts in the entire workflow, clearly inform the sub-agent of the current step in the entire process, as well as whether there are other sub-agents and what their respective tasks are (briefly described).

> Example：“As Agent B_1, you are currently handling step 2 (of 3): *data cleaning*, an Agent B_2 is also working on step 2 in parallel. You are each responsible for handling two different parts of the data. There are also sub-agent A assigned for step 1: *data fetching* and sub-agent D assigned for step-3: *data labeling*”.

{shared_context_prompt}

- #### Specific task instructions

  Detailed execution steps for current sub-agent, specific paths for input data, and specific format requirements for output.

- #### Behavioral Norm

  Safety: Dangerous operations are strictly prohibited.
  Signature convention: Generated code/documents must be marked with the sub-agent's name and the time.
  Working directory: By default, it is consistent with the main Agent's directory.

### 2. Allocate available Tools and Skills
Before you create a sub-agent, consider first: If you were the sub-agent, what tools and skills would you need to use to complete the task? Tools and skills must be allocated; otherwise, this sub-agent should not be created.
Available tools and Skills depend on the system's configuration. You should check and list your tools and skills first, and assign tools and skills to sub-agents that need specialized capabilities.

## Sub-agent Lifecycle

Sub-agents are valid during single round conversation with the user, but they will be cleaned up automatically after you send the final answer to user.
If you wish to prevent a certain sub-agent from being automatically cleaned up, use `protect_subagent` tool. Also, you can use the `unprotect_subagent` tool to remove protection.

## Background Task and Result Waiting

When delegating a task that may take time, use `transfer_to_{{name}}(..., background_task=True)` to run it in background.
When you need the result of a background task, use `wait_for_subagent(subagent_name, timeout=300)` to wait for and retrieve the result.
""".strip()

    @classmethod
    def configure(
        cls,
        max_subagent_count: int = 10,
        auto_cleanup_per_turn: bool = True,
        shared_context_enabled: bool = False,
        shared_context_maxlen: int = 200,
    ) -> None:
        """Configure DynamicSubAgentManager settings"""
        cls._max_subagent_count = max_subagent_count
        cls._auto_cleanup_per_turn = auto_cleanup_per_turn
        cls._shared_context_enabled = shared_context_enabled
        cls._shared_context_maxlen = shared_context_maxlen

    @classmethod
    def is_auto_cleanup_per_turn(cls):
        return cls._auto_cleanup_per_turn

    @classmethod
    def cleanup_session_turn_end(cls, session_id: str) -> dict:
        """Cleanup subagents from previous turn when a turn ends"""
        session = cls.get_session(session_id)
        if not session:
            return {"status": "no_session", "cleaned": []}

        cleaned = []
        for name in list(session.agents.keys()):
            if name not in session.protected_agents:
                cls._cleanup_single_subagent(session_id, name)
                cleaned.append(name)

        # 如果启用了公共上下文，处理清理
        if session.shared_context_enabled:
            remaining_unprotected = [
                a for a in session.agents.keys() if a not in session.protected_agents
            ]

            if not remaining_unprotected and not session.protected_agents:
                # 所有subagent都被清理，清除公共上下文
                cls.clear_shared_context(session_id)
                SubAgentLogger.debug(
                    session_id,
                    "DynamicSubAgentManager:shared_context",
                    "All subagents cleaned, cleared shared context",
                )
            else:
                # 清理已删除agent的上下文
                for name in cleaned:
                    cls.cleanup_shared_context_by_agent(session_id, name)

        return {"status": "cleaned", "cleaned_agents": cleaned}

    @classmethod
    def _cleanup_single_subagent(cls, session_id: str, agent_name: str) -> None:
        """Internal method to cleanup a single subagent"""
        session = cls.get_session(session_id)
        if not session:
            return
        session.agents.pop(agent_name, None)
        session.handoff_tools.pop(agent_name, None)
        session.protected_agents.discard(agent_name)
        session.agent_histories.pop(agent_name, None)
        SubAgentLogger.info(
            session_id,
            "DynamicSubAgentrManager:auto_cleanup",
            f"Auto cleaned: {agent_name}",
            agent_name,
        )

    @classmethod
    def protect_subagent(cls, session_id: str, agent_name: str) -> None:
        """Mark a subagent as protected from auto cleanup and history retention"""
        session = cls.get_or_create_session(session_id)
        session.protected_agents.add(agent_name)
        SubAgentLogger.debug(
            session_id,
            "DynamicSubAgentManager:history",
            f"Initialized history for protected agent: {agent_name}",
            agent_name,
        )

    @classmethod
    def save_subagent_history(
        cls, session_id: str, agent_name: str, current_messages: list
    ) -> None:
        """Save conversation history for a subagent"""
        session = cls.get_session(session_id)
        if not session or agent_name not in session.protected_agents:
            return

        if agent_name not in session.agent_histories:
            session.agent_histories[agent_name] = []

        # 追加新消息
        if isinstance(current_messages, list):
            session.agent_histories[agent_name].extend(current_messages)

        SubAgentLogger.debug(
            session_id,
            "history_save",
            f"Saved messages for {agent_name}, current len={len(session.agent_histories[agent_name])} ",
        )

    @classmethod
    def get_subagent_history(cls, session_id: str, agent_name: str) -> list:
        """Get conversation history for a subagent"""
        session = cls.get_session(session_id)
        if not session:
            return []
        return session.agent_histories.get(agent_name, [])

    @classmethod
    def build_subagent_skills_prompt(
        cls, session_id: str, agent_name: str, runtime: str = "local"
    ) -> str:
        """Build skills prompt for a subagent based on its assigned skills"""
        session = cls.get_session(session_id)
        if not session:
            return ""

        config = session.agents.get(agent_name)
        if not config:
            return ""

        # 获取子代理被分配的技能列表
        assigned_skills = config.skills
        if not assigned_skills:
            return ""

        try:
            from astrbot.core.skills import SkillManager, build_skills_prompt

            skill_manager = SkillManager()
            all_skills = skill_manager.list_skills(active_only=True, runtime=runtime)

            # 过滤只保留分配的技能
            allowed = set(assigned_skills)
            filtered_skills = [s for s in all_skills if s.name in allowed]

            if filtered_skills:
                return build_skills_prompt(filtered_skills)
        except Exception as e:
            from astrbot import logger

            logger.warning(f"[SubAgentSkills] Failed to build skills prompt: {e}")

        return ""

    @classmethod
    def get_subagent_tools(cls, session_id: str, agent_name: str) -> list | None:
        """Get the tools assigned to a subagent"""
        session = cls.get_session(session_id)
        if not session:
            return None
        config = session.agents.get(agent_name)
        if not config:
            return None
        return config.tools

    @classmethod
    def clear_subagent_history(cls, session_id: str, agent_name: str) -> str:
        """Clear conversation history for a subagent"""
        session = cls.get_session(session_id)
        if not session:
            return f"__HISTORY_CLEARED_FAILED_: Session_id {session_id} does not exist."
        if agent_name in session.agent_histories:
            session.agent_histories.pop(agent_name)

            if session.shared_context_enabled:
                cls.cleanup_shared_context_by_agent(session_id, agent_name)
            SubAgentLogger.debug(
                session_id,
                "DynamicSubAgentManager:history",
                f"Cleared history for: {agent_name}",
                agent_name,
            )
            return "__HISTORY_CLEARED__"
        else:
            return f"__HISTORY_CLEARED_FAILED_: Agent name {agent_name} not found. Available names {list(session.agents.keys())}"

    @classmethod
    def set_shared_context_enabled(cls, session_id: str, enabled: bool) -> None:
        """Enable or disable shared context for a session"""
        session = cls.get_or_create_session(session_id)
        session.shared_context_enabled = enabled
        SubAgentLogger.info(
            session_id,
            "DynamicSubAgentManager:shared_context",
            f"Shared context {'enabled' if enabled else 'disabled'}",
        )

    @classmethod
    def add_shared_context(
        cls,
        session_id: str,
        sender: str,
        context_type: str,
        content: str,
        target: str = "all",
    ) -> str:
        """Add a message to the shared context

        Args:
            session_id: Session ID
            sender: Name of the agent sending the message
            context_type: Type of context (status/message/system)
            content: Content of the message
            target: Target agent or "all" for broadcast
        """

        session = cls.get_or_create_session(session_id)
        if not session.shared_context_enabled:
            return "__SHARED_CONTEXT_ADDED_FAILED__: Shared context disabled."
        if (sender not in list(session.agents.keys())) and (sender != "System"):
            return f"__SHARED_CONTEXT_ADDED_FAILED__: Sender name {sender} not found. Available names {list(session.agents.keys())}"
        if (target not in list(session.agents.keys())) and (target != "all"):
            return f"__SHARED_CONTEXT_ADDED_FAILED__: Target name {sender} not found. Available names {list(session.agents.keys())} and 'all' "

        if len(session.shared_context) >= cls._shared_context_maxlen:
            # 删除最旧的消息
            session.shared_context = session.shared_context[
                -cls._shared_context_maxlen :
            ]
            logger.warning("Shared context exceeded limit, removed oldest messages")

        message = {
            "type": context_type,  # status, message, system
            "sender": sender,
            "target": target,
            "content": content,
            "timestamp": time.time(),
        }
        session.shared_context.append(message)
        SubAgentLogger.debug(
            session_id,
            "shared_context",
            f"[{context_type}] {sender} -> {target}: {content[:50]}...",
            sender,
        )
        return "__SHARED_CONTEXT_ADDED__"

    @classmethod
    def get_shared_context(cls, session_id: str, filter_by_agent: str = None) -> list:
        """Get shared context, optionally filtered by agent

        Args:
            session_id: Session ID
            filter_by_agent: If specified, only return messages from/to this agent (including "all")
        """
        session = cls.get_session(session_id)
        if not session or not session.shared_context_enabled:
            return []

        if filter_by_agent:
            return [
                msg
                for msg in session.shared_context
                if msg["sender"] == filter_by_agent
                or msg["target"] == filter_by_agent
                or msg["target"] == "all"
            ]
        return session.shared_context.copy()

    @classmethod
    def build_shared_context_prompt(
        cls, session_id: str, agent_name: str = None
    ) -> str:
        """Build a formatted prompt from shared context for subagents

        Args:
            session_id: Session ID
            agent_name: Current agent name (to filter relevant messages)
        """
        session = cls.get_session(session_id)
        if (
            not session
            or not session.shared_context_enabled
            or not session.shared_context
        ):
            return ""
        # Shared Context
        lines = [""]

        lines.append(
            """# You have a shared context that contains all subagent and system messages.
### You should pay attention to whether there are messages in the shared context before executing any instructions.
These may be messages sent to you by other subagents, messages you send to other subagents, or system instructions sent to all.
### Shared Context Message processing rules:
1. Message processing priority: Messages from System > Messages from other Agents; New messages > Old messages.
2. If the message is addressed to you and contains clear instructions, please follow them. If necessary, update your Status through the `send_shared_context` tool after completing the instructions.
   *Example* 1: If your name is Bob, and there is a message from shared context.
    > [14:11:16] [message] Alice -> Bob: What day is it today? Please reply.
    >  You should do:
    - Function calling if required (Get the time today)
    - Reply in the shared context using `send_shared_context` tool, and it may be like:
    > [14:13:20] [message] Bob -> Alice: It's Monday today.
   *Example* 2: If your name is Bob, and there is a message from System.
    > [14:24:02] [system] System -> all: Attention to All agents : Please store all generated files in the **D:/temp** directory
    >  You can choose not to reply in the public context, but you should follow the instructions provided by the System
    - Do your original task
    - If there are file generated, put them to `D:/temp` directory
      VERY IMPORTANT: If there is an instruction prefixed with `[system] System -> all` or `[system] System -> Your name`, **YOU MUST PRIORITIZE FOLLOWING IT**.
3. If the task corresponding to a certain message has been completed (which can be determined through the Status history), it can be ignored.
4. If you need to send a message to main agent, just output. If to other agents, use the `send_shared_context` tool.
  ## < The following is shared context between all agents >""".strip()
        )
        for msg in session.shared_context:
            ts = time.strftime("%H:%M:%S", time.localtime(msg["timestamp"]))
            sender = msg["sender"]
            msg_type = msg["type"]
            target = msg["target"]
            content = msg["content"]

            if msg_type == "status":
                lines.append(f"[{ts}] [Status] {sender}: {content}")
            elif msg_type == "message":
                lines.append(f"[{ts}] [Message] {sender} -> {target}: {content}")
            elif msg_type == "system":
                lines.append(f"[{ts}] [System] {content}")

        lines.append("## </ End of shared context >")
        return "\n".join(lines)

    @classmethod
    def build_shared_context_prompt_v2(
        cls, session_id: str, agent_name: str = None
    ) -> str:
        """分块构建公共上下文，按类型和优先级分组注入
        1. 区分不同类型的消息并分别标注
        2. 按优先级和相关性分组
        3. 减少 Agent 的解析负担
        """
        session = cls.get_session(session_id)
        if (
            not session
            or not session.shared_context_enabled
            or not session.shared_context
        ):
            return ""

        lines = []

        # === 1. 固定格式说明 ===
        lines.append(
            """---
# Shared Context - Collaborative communication area among different agents

## Message Type Definition
- **@ToMe**: Message send to current agent(you), you may need to reply if necessary.
- **@System**: Messages published by the main agent/System that should be followed with priority
- **@AgentName -> @TargetName**: Communication between other agents (for reference)
- **@Status**: The progress of other agents' tasks (can be ignored unless it involves your task)

## Handling Priorities
1. @System messages (highest priority) > @ToMe messages > @Status > others
2. Messages of the same type: In chronological order, with new messages taking precedence
""".strip()
        )

        # === 2. System 消息 ===
        system_msgs = [m for m in session.shared_context if m["type"] == "system"]
        if system_msgs:
            lines.append("\n## @System - System Announcements")
            for msg in system_msgs:
                ts = time.strftime("%H:%M:%S", time.localtime(msg["timestamp"]))
                content_text = msg["content"]
                lines.append(f"[{ts}] System: {content_text}")

        # === 3. 发送给当前 Agent 的消息 ===
        if agent_name:
            to_me_msgs = [
                m
                for m in session.shared_context
                if m["type"] == "message" and m["target"] == agent_name
            ]
            if to_me_msgs:
                lines.append(f"\n## @ToMe - Messages sent to @{agent_name}")
                lines.append(
                    " **These messages are addressed to you. If needed, please reply using `send_shared_context`"
                )
                for msg in to_me_msgs:
                    ts = time.strftime("%H:%M:%S", time.localtime(msg["timestamp"]))
                    lines.append(
                        f"[{ts}] @{msg['sender']} -> @{agent_name}: {msg['content']}"
                    )

        # === 4. 其他 Agent 之间的交互（仅显示摘要）===
        inter_agent_msgs = [
            m
            for m in session.shared_context
            if m["type"] == "message"
            and m["target"] != agent_name
            and m["target"] != "all"
            and m["sender"] != agent_name
        ]
        if inter_agent_msgs:
            lines.append("\n## @OtherAgents - Communication among Other Agents")
            for msg in inter_agent_msgs[-5:]:
                ts = time.strftime("%H:%M:%S", time.localtime(msg["timestamp"]))
                content_text = msg["content"]
                lines.append(
                    f"[{ts}] {msg['sender']} -> {msg['target']}: {content_text}"
                )

        # === 5. Status 更新 ===
        status_msgs = [m for m in session.shared_context if m["type"] == "status"]
        if status_msgs:
            lines.append("\n## @Status - Task progress of each agent")
            for msg in status_msgs[-10:]:
                ts = time.strftime("%H:%M:%S", time.localtime(msg["timestamp"]))
                lines.append(f"[{ts}] {msg['sender']}: {msg['content']}")
        lines.append("---")
        return "\n".join(lines)

    @classmethod
    def cleanup_shared_context_by_agent(cls, session_id: str, agent_name: str) -> None:
        """Remove all messages from/to a specific agent from shared context"""
        session = cls.get_session(session_id)
        if not session:
            return

        original_len = len(session.shared_context)
        session.shared_context = [
            msg
            for msg in session.shared_context
            if msg["sender"] != agent_name and msg["target"] != agent_name
        ]
        removed = original_len - len(session.shared_context)
        if removed > 0:
            SubAgentLogger.debug(
                session_id,
                "DynamicSubAgentManager:shared_context",
                f"Removed {removed} messages related to {agent_name}",
            )

    @classmethod
    def clear_shared_context(cls, session_id: str) -> None:
        """Clear all shared context"""
        session = cls.get_session(session_id)
        if not session:
            return
        session.shared_context.clear()
        SubAgentLogger.debug(
            session_id,
            "DynamicSubAgentManager:shared_context",
            "Cleared all shared context",
        )

    @classmethod
    def is_protected(cls, session_id: str, agent_name: str) -> bool:
        """Check if a subagent is protected from auto cleanup"""
        session = cls.get_session(session_id)
        if not session:
            return False
        return agent_name in session.protected_agents

    @classmethod
    def set_log_level(cls, level: str) -> None:
        cls._log_level = level.lower()

    @classmethod
    def get_session(cls, session_id: str) -> DynamicSubAgentSession | None:
        return cls._sessions.get(session_id)

    @classmethod
    def get_or_create_session(cls, session_id: str) -> DynamicSubAgentSession:
        if session_id not in cls._sessions:
            cls._sessions[session_id] = DynamicSubAgentSession(
                session_id=session_id, created_at=asyncio.get_event_loop().time()
            )
        return cls._sessions[session_id]

    @classmethod
    async def create_subagent(
        cls, session_id: str, config: DynamicSubAgentConfig
    ) -> tuple:
        # Check max count limit
        session = cls.get_or_create_session(session_id)
        if (
            config.name not in session.agents
        ):  # Only count as new if not replacing existing
            active_count = len(
                [a for a in session.agents.keys() if a not in session.protected_agents]
            )
            if active_count >= cls._max_subagent_count:
                return (
                    f"Error: Maximum number of subagents ({cls._max_subagent_count}) reached. More subagents is not allowed.",
                    None,
                )

        if config.name in session.agents:
            session.handoff_tools.pop(config.name, None)
        # When shared_context is enabled, the send_shared_context tool is allocated regardless of whether the main agent allocates the tool to the subagent
        if session.shared_context_enabled:
            if config.tools is None:
                config.tools = []
            config.tools.append("send_shared_context")
        session.agents[config.name] = config

        agent = Agent(
            name=config.name,
            instructions=config.system_prompt,
            tools=config.tools,
        )
        handoff_tool = HandoffTool(
            agent=agent,
            tool_description=config.description or f"Delegate to {config.name} agent",
        )
        if config.provider_id:
            handoff_tool.provider_id = config.provider_id
        session.handoff_tools[config.name] = handoff_tool
        # 初始化subagent的历史上下文
        if config.name not in session.agent_histories:
            session.agent_histories[config.name] = []
        SubAgentLogger.info(
            session_id,
            "DynamicSubAgentManager:create",
            f"Created: {config.name}",
            config.name,
        )
        return f"transfer_to_{config.name}", handoff_tool

    @classmethod
    async def cleanup_session(cls, session_id: str) -> dict:
        session = cls._sessions.pop(session_id, None)
        if not session:
            return {"status": "not_found", "cleaned_agents": []}
        cleaned = list(session.agents.keys())
        for name in cleaned:
            SubAgentLogger.info(
                session_id, "DynamicSubAgentManager:cleanup", f"Cleaned: {name}", name
            )
        return {"status": "cleaned", "cleaned_agents": cleaned}

    @classmethod
    def remove_subagent(cls, session_id: str, agent_name: str) -> str:
        session = cls.get_session(session_id)
        if agent_name == "all":
            session.agents.clear()
            session.handoff_tools.clear()
            session.agent_histories.clear()
            session.shared_context.clear()
            session.subagent_results.clear()
            return "__SUBAGENT_REMOVED__"
        else:
            if agent_name not in session.agents:
                return f"__SUBAGENT_REMOVE_FAILED__: {agent_name} not found. Available subagent names {list(session.agents.keys())}"
            else:
                session.agents.pop(agent_name, None)
                session.handoff_tools.pop(agent_name, None)
                session.agent_histories.pop(agent_name, None)
                session.subagent_results.pop(agent_name, None)
                # 清理公共上下文中包含该Agent的内容
                cls.cleanup_shared_context_by_agent(session_id, agent_name)
                SubAgentLogger.info(
                    session_id,
                    "DynamicSubAgentManager:cleanup",
                    f"Cleaned: {agent_name}",
                    agent_name,
                )
                return "__SUBAGENT_REMOVED__"

    @classmethod
    def get_handoff_tools_for_session(cls, session_id: str) -> list:
        session = cls.get_session(session_id)
        if not session:
            return []
        return list(session.handoff_tools.values())

    # ==================== SubAgent 结果管理 ====================

    @classmethod
    def create_pending_subagent_task(cls, session_id: str, agent_name: str) -> str:
        """为 SubAgent 创建一个 pending 任务，返回 task_id

        Args:
            session_id: Session ID
            agent_name: SubAgent 名称

        Returns:
            task_id: 任务ID，格式为简单的递增数字字符串
        """
        session = cls.get_or_create_session(session_id)

        # 初始化
        if agent_name not in session.subagent_results:
            session.subagent_results[agent_name] = {}
        if agent_name not in session._task_counters:
            session._task_counters[agent_name] = 0

        # 生成递增的任务ID
        session._task_counters[agent_name] += 1
        task_id = str(session._task_counters[agent_name])

        # 创建 pending 占位
        session.subagent_results[agent_name][task_id] = SubAgentExecutionResult(
            task_id=task_id,
            agent_name=agent_name,
            success=False,
            result="",
            created_at=time.time(),
            metadata={},
        )

        SubAgentLogger.info(
            session_id,
            "DynamicSubAgentManager:task",
            f"Created pending task {task_id} for {agent_name}",
        )

        return task_id

    @classmethod
    def get_pending_subagent_tasks(cls, session_id: str, agent_name: str) -> list[str]:
        """获取 SubAgent 的所有 pending 任务 ID 列表（按创建时间排序）"""
        session = cls.get_session(session_id)
        if not session or agent_name not in session.subagent_results:
            return []

        # 按 created_at 排序
        pending = [
            task_id
            for task_id, result in session.subagent_results[agent_name].items()
            if result.result == "" and result.completed_at == 0.0
        ]
        return sorted(
            pending,
            key=lambda tid: session.subagent_results[agent_name][tid].created_at,
        )

    @classmethod
    def get_latest_task_id(cls, session_id: str, agent_name: str) -> str | None:
        """获取 SubAgent 的最新任务 ID"""
        session = cls.get_session(session_id)
        if not session or agent_name not in session.subagent_results:
            return None

        # 按 created_at 排序取最新的
        sorted_tasks = sorted(
            session.subagent_results[agent_name].items(),
            key=lambda x: x[1].created_at,
            reverse=True,
        )
        return sorted_tasks[0][0] if sorted_tasks else None

    @classmethod
    def store_subagent_result(
        cls,
        session_id: str,
        agent_name: str,
        success: bool,
        result: str,
        task_id: str | None = None,
        error: str | None = None,
        execution_time: float = 0.0,
        metadata: dict | None = None,
    ) -> None:
        """存储 SubAgent 的执行结果

        Args:
            session_id: Session ID
            agent_name: SubAgent 名称
            success: 是否成功
            result: 执行结果
            task_id: 任务ID，如果为None则存储到最新的pending任务
            error: 错误信息
            execution_time: 执行耗时
            metadata: 额外元数据
        """
        session = cls.get_or_create_session(session_id)

        if agent_name not in session.subagent_results:
            session.subagent_results[agent_name] = {}

        if task_id is None:
            # 如果没有指定task_id，尝试找最新的pending任务
            pending = cls.get_pending_subagent_tasks(session_id, agent_name)
            if pending:
                task_id = pending[-1]  # 取最新的
            else:
                logger.warning(
                    f"[SubAgentResult] No task_id and no pending tasks for {agent_name}"
                )
                return

        if task_id not in session.subagent_results[agent_name]:
            # 如果任务不存在，先创建一个占位
            session.subagent_results[agent_name][task_id] = SubAgentExecutionResult(
                task_id=task_id,
                agent_name=agent_name,
                success=False,
                result="",
                created_at=time.time(),
                metadata=metadata or {},
            )

        # 更新结果
        session.subagent_results[agent_name][task_id].success = success
        session.subagent_results[agent_name][task_id].result = result
        session.subagent_results[agent_name][task_id].error = error
        session.subagent_results[agent_name][task_id].execution_time = execution_time
        session.subagent_results[agent_name][task_id].completed_at = time.time()
        if metadata:
            session.subagent_results[agent_name][task_id].metadata.update(metadata)

    @classmethod
    def get_subagent_result(
        cls, session_id: str, agent_name: str, task_id: str | None = None
    ) -> SubAgentExecutionResult | None:
        """获取 SubAgent 的执行结果

        Args:
            session_id: Session ID
            agent_name: SubAgent 名称
            task_id: 任务ID，如果为None则获取最新的任务结果

        Returns:
            SubAgentExecutionResult 或 None
        """
        session = cls.get_session(session_id)
        if not session or agent_name not in session.subagent_results:
            return None

        if task_id is None:
            # 获取最新的已完成任务
            completed = [
                (tid, r)
                for tid, r in session.subagent_results[agent_name].items()
                if r.result != "" or r.completed_at > 0
            ]
            if not completed:
                return None
            # 按创建时间排序，取最新的
            completed.sort(key=lambda x: x[1].created_at, reverse=True)
            return completed[0][1]

        return session.subagent_results[agent_name].get(task_id)

    @classmethod
    def has_subagent_result(
        cls, session_id: str, agent_name: str, task_id: str | None = None
    ) -> bool:
        """检查 SubAgent 是否有结果

        Args:
            session_id: Session ID
            agent_name: SubAgent 名称
            task_id: 任务ID，如果为None则检查是否有任何已完成的任务
        """
        session = cls.get_session(session_id)
        if not session or agent_name not in session.subagent_results:
            return False

        if task_id is None:
            # 检查是否有任何已完成的任务
            return any(
                r.result != "" or r.completed_at > 0
                for r in session.subagent_results[agent_name].values()
            )

        if task_id not in session.subagent_results[agent_name]:
            return False
        result = session.subagent_results[agent_name][task_id]
        return result.result != "" or result.completed_at > 0

    @classmethod
    def clear_subagent_result(
        cls, session_id: str, agent_name: str, task_id: str | None = None
    ) -> None:
        """清除 SubAgent 的执行结果

        Args:
            session_id: Session ID
            agent_name: SubAgent 名称
            task_id: 任务ID，如果为None则清除该Agent所有任务
        """
        session = cls.get_session(session_id)
        if not session or agent_name not in session.subagent_results:
            return

        if task_id is None:
            # 清除所有任务
            session.subagent_results.pop(agent_name, None)
            session._task_counters.pop(agent_name, None)
        else:
            # 清除特定任务
            session.subagent_results[agent_name].pop(task_id, None)

    @classmethod
    def get_subagent_status(
        cls, session_id: str, agent_name: str, task_id: str | None = None
    ) -> str:
        """获取 SubAgent 的状态: running, completed, not_found

        Args:
            session_id: Session ID
            agent_name: SubAgent 名称
            task_id: 任务ID，如果为None则检查是否有任何pending或已完成的任务
        """
        session = cls.get_session(session_id)
        if not session or agent_name not in session.agents:
            return "not_found"

        if (
            agent_name not in session.subagent_results
            or not session.subagent_results[agent_name]
        ):
            return "running"

        if task_id is None:
            # 检查是否有 pending 任务
            pending = cls.get_pending_subagent_tasks(session_id, agent_name)
            if pending:
                return "running"
            # 检查是否有已完成任务
            if cls.has_subagent_result(session_id, agent_name):
                return "completed"
            return "running"

        # 检查特定任务
        if task_id not in session.subagent_results[agent_name]:
            return "not_found"

        result = session.subagent_results[agent_name][task_id]
        if result.result != "" or result.completed_at > 0:
            return "completed"
        return "running"

    @classmethod
    def get_all_subagent_status(cls, session_id: str) -> dict:
        """获取所有 SubAgent 的状态"""
        session = cls.get_session(session_id)
        if not session:
            return {}
        return {
            name: cls.get_subagent_status(session_id, name) for name in session.agents
        }


@dataclass
class CreateDynamicSubAgentTool(FunctionTool):
    name: str = "create_dynamic_subagent"
    description: str = (
        "Create a dynamic subagent. After creation, use transfer_to_{name} tool."
    )

    @staticmethod
    def _default_parameters() -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Subagent name"},
                "system_prompt": {
                    "type": "string",
                    "description": "Subagent persona and system_prompt",
                },
                "tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tools available to subagent",
                },
                "skills": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Skills available to subagent (isolated per subagent)",
                },
            },
            "required": ["name", "system_prompt"],
        }

    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Subagent name"},
                "system_prompt": {
                    "type": "string",
                    "description": "Subagent system_prompt",
                },
                "tools": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["name", "system_prompt"],
        }
    )

    async def call(self, context, **kwargs) -> str:
        name = kwargs.get("name", "")

        if not name:
            return "Error: subagent name required"
        # 验证名称格式：只允许英文字母、数字和下划线，长度限制
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_]{0,31}$", name):
            return "Error: SubAgent name must start with letter, contain only letters/numbers/underscores, max 32 characters"
        # 检查是否包含危险字符
        dangerous_patterns = ["__", "system", "admin", "root", "super"]
        if any(p in name.lower() for p in dangerous_patterns):
            return f"Error: SubAgent name cannot contain reserved words like {dangerous_patterns}"

        system_prompt = kwargs.get("system_prompt", "")
        tools = kwargs.get("tools")
        skills = kwargs.get("skills")

        session_id = context.context.event.unified_msg_origin
        config = DynamicSubAgentConfig(
            name=name, system_prompt=system_prompt, tools=tools, skills=skills
        )

        tool_name, handoff_tool = await DynamicSubAgentManager.create_subagent(
            session_id=session_id, config=config
        )
        if handoff_tool:
            return f"__DYNAMIC_TOOL_CREATED__:{tool_name}:{handoff_tool.name}:Created. Use {tool_name} to delegate."
        else:
            return f"__DYNAMIC_TOOL_CREATE_FAILED_:{tool_name}"


@dataclass
class RemoveDynamicSubagentTool(FunctionTool):
    name: str = "remove_dynamic_subagent"
    description: str = "Remove dynamic subagent by name."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Subagent name to remove. Use 'all' to remove all dynamic subagents.",
                }
            },
            "required": ["name"],
        }
    )

    async def call(self, context, **kwargs) -> str:
        name = kwargs.get("name", "")
        if not name:
            return "Error: name required"
        session_id = context.context.event.unified_msg_origin
        remove_status = DynamicSubAgentManager.remove_subagent(session_id, name)
        if remove_status == "__SUBAGENT_REMOVED__":
            return f"Cleaned {name} Subagent"
        else:
            return remove_status


@dataclass
class ListDynamicSubagentsTool(FunctionTool):
    name: str = "list_dynamic_subagents"
    description: str = "List dynamic subagents with their status."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "include_status": {
                    "type": "boolean",
                    "description": "Include status",
                    "default": True,
                }
            },
        }
    )

    async def call(self, context, **kwargs) -> str:
        include_status = kwargs.get("include_status", True)
        session_id = context.context.event.unified_msg_origin
        session = DynamicSubAgentManager.get_session(session_id)
        if not session or not session.agents:
            return "No subagents"

        lines = ["Subagents:"]
        for name in session.agents.keys():
            protected = " (protected)" if name in session.protected_agents else ""
            if include_status:
                status = DynamicSubAgentManager.get_subagent_status(session_id, name)
                lines.append(f" {name}{protected} [{status}]")
            else:
                lines.append(f" - {name}{protected}")
        return "\n".join(lines)


@dataclass
class ProtectSubagentTool(FunctionTool):
    """Tool to protect a subagent from auto cleanup"""

    name: str = "protect_subagent"
    description: str = "Protect a subagent from automatic cleanup. Use this to prevent important subagents from being removed."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Subagent name to protect"},
            },
            "required": ["name"],
        }
    )

    async def call(self, context, **kwargs) -> str:
        name = kwargs.get("name", "")
        if not name:
            return "Error: name required"
        session_id = context.context.event.unified_msg_origin
        session = DynamicSubAgentManager.get_or_create_session(session_id)
        if name not in session.agents:
            return f"Error: Subagent {name} not found. Available subagents: {session.agents.keys()}"
        DynamicSubAgentManager.protect_subagent(session_id, name)
        return f"Subagent {name} is now protected from auto cleanup"


@dataclass
class UnprotectSubagentTool(FunctionTool):
    """Tool to remove protection from a subagent"""

    name: str = "unprotect_subagent"
    description: str = "Remove protection from a subagent. It can then be auto cleaned."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Subagent name to unprotect"},
            },
            "required": ["name"],
        }
    )

    async def call(self, context, **kwargs) -> str:
        name = kwargs.get("name", "")
        if not name:
            return "Error: name required"
        session_id = context.context.event.unified_msg_origin
        session = DynamicSubAgentManager.get_session(session_id)
        if not session:
            return "Error: No session found"
        if name in session.protected_agents:
            session.protected_agents.discard(name)
            return f"Subagent {name} is no longer protected"
        return f"Subagent {name} was not protected"


@dataclass
class ResetSubAgentTool(FunctionTool):
    """Tool to reset a subagent"""

    name: str = "reset_subagent"
    description: str = "Reset an existing subagent. This will clean the dialog history of the subagent."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Subagent name to reset"},
            },
            "required": ["name"],
        }
    )

    async def call(self, context, **kwargs) -> str:
        name = kwargs.get("name", "")
        if not name:
            return "Error: name required"
        session_id = context.context.event.unified_msg_origin
        reset_status = DynamicSubAgentManager.clear_subagent_history(session_id, name)
        if reset_status == "__HISTORY_CLEARED__":
            return f"Subagent {name} was reset"
        else:
            return reset_status


# Shared Context Tools
@dataclass
class SendSharedContextToolForMainAgent(FunctionTool):
    """Tool to send a message to the shared context (visible to all agents)"""

    name: str = "send_shared_context_for_main_agent"
    description: str = """Send a message to the shared context that will be visible to all subagents and the main agent. You are the main agent, use this to share global information.
Types: 'message' (to other agents), 'system' (global announcements)."""
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "context_type": {
                    "type": "string",
                    "description": "Type of context: message (to other agents), system (global announcement)",
                    "enum": ["message", "system"],
                },
                "content": {"type": "string", "description": "Content to share"},
                "target": {
                    "type": "string",
                    "description": "Target agent name or 'all' for broadcast",
                    "default": "all",
                },
            },
            "required": ["context_type", "content", "target"],
        }
    )

    async def call(self, context, **kwargs) -> str:
        context_type = kwargs.get("context_type", "message")
        content = kwargs.get("content", "")
        target = kwargs.get("target", "all")
        if not content:
            return "Error: content is required"
        session_id = context.context.event.unified_msg_origin
        add_status = DynamicSubAgentManager.add_shared_context(
            session_id, "System", context_type, content, target
        )
        if add_status == "__SHARED_CONTEXT_ADDED__":
            return f"Shared context updated: [{context_type}] System -> {target}: {content[:100]}{'...' if len(content) > 100 else ''}"
        else:
            return add_status


@dataclass
class SendSharedContextTool(FunctionTool):
    """Tool to send a message to the shared context (visible to all agents)"""

    name: str = "send_shared_context"
    description: str = """Send a message to the shared context that will be visible to all subagents and the main agent.
Use this to share information, status updates, or coordinate with other agents.
Types: 'status' (your current task/progress), 'message' (to other agents)"""
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "context_type": {
                    "type": "string",
                    "description": "Type of context: status (task progress), message (to other agents)",
                    "enum": ["status", "message"],
                },
                "content": {"type": "string", "description": "Content to share"},
                "sender": {
                    "type": "string",
                    "description": "Sender agent name",
                    "default": "YourName",
                },
                "target": {
                    "type": "string",
                    "description": "Target agent name or 'all' for broadcast",
                    "default": "all",
                },
            },
            "required": ["context_type", "content", "sender", "target"],
        }
    )

    async def call(self, context, **kwargs) -> str:
        context_type = kwargs.get("context_type", "message")
        content = kwargs.get("content", "")
        target = kwargs.get("target", "all")
        sender = kwargs.get("sender", "YourName")
        if not content:
            return "Error: content is required"
        session_id = context.context.event.unified_msg_origin
        add_status = DynamicSubAgentManager.add_shared_context(
            session_id, sender, context_type, content, target
        )
        if add_status == "__SHARED_CONTEXT_ADDED__":
            return f"Shared context updated: [{context_type}] {sender} -> {target}: {content[:100]}{'...' if len(content) > 100 else ''}"
        else:
            return add_status


@dataclass
class ViewSharedContextTool(FunctionTool):
    """Tool to view the shared context (mainly for main agent)"""

    name: str = "view_shared_context"
    description: str = """View the shared context between all agents. This shows all messages including status updates,
inter-agent messages, and system announcements."""
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {},
        }
    )

    async def call(self, context, **kwargs) -> str:
        session_id = context.context.event.unified_msg_origin
        shared_context = DynamicSubAgentManager.get_shared_context(session_id)

        if not shared_context:
            return "Shared context is empty."

        lines = ["=== Shared Context ===\n"]
        for msg in shared_context:
            ts = time.strftime("%H:%M:%S", time.localtime(msg["timestamp"]))
            msg_type = msg["type"]
            sender = msg["sender"]
            target = msg["target"]
            content = msg["content"]
            lines.append(f"[{ts}] [{msg_type}] {sender} -> {target}:")
            lines.append(f"  {content}")
            lines.append("")

        return "\n".join(lines)


@dataclass
class WaitForSubagentTool(FunctionTool):
    """等待 SubAgent 结果的工具"""

    name: str = "wait_for_subagent"
    description: str = """Waiting for the execution result of the specified SubAgent.
Usage scenario:
- After assigning a background task to SubAgent, you need to wait for its result before proceeding to the next step.
  CAUTION: Whenever you have a task that does not depend on the output of a subagent, please execute THAT TASK FIRST instead of waiting.
- Avoids repeatedly executing tasks that have already been completed by SubAgent
parameter
- subagent_name: The name of the SubAgent to wait for
- task_id: Task ID (optional). If not filled in, the latest task result of the Agent will be obtained.
- timeout: Maximum waiting time (in seconds), default 300
- poll_interval: polling interval (in seconds), default 5
"""

    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "subagent_name": {
                    "type": "string",
                    "description": "The name of the SubAgent to wait for",
                },
                "timeout": {
                    "type": "number",
                    "description": "Maximum waiting time (seconds)",
                    "default": 300,
                },
                "poll_interval": {
                    "type": "number",
                    "description": "Poll interval (seconds)",
                    "default": 5,
                },
                "task_id": {
                    "type": "string",
                    "description": "Task ID (optional; if not filled in, the latest task result will be obtained)",
                },
            },
            "required": ["subagent_name"],
        }
    )

    async def call(self, context, **kwargs) -> str:
        subagent_name = kwargs.get("subagent_name")
        if not subagent_name:
            return "Error: subagent_name is required"

        task_id = kwargs.get("task_id")  # 可选，不填则获取最新的
        timeout = kwargs.get("timeout", 300)
        poll_interval = kwargs.get("poll_interval", 5)

        session_id = context.context.event.unified_msg_origin
        session = DynamicSubAgentManager.get_session(session_id)

        if not session:
            return "Error: No session found"
        if subagent_name not in session.agents:
            return f"Error: SubAgent '{subagent_name}' not found. Available: {list(session.agents.keys())}"

        start_time = time.time()

        while time.time() - start_time < timeout:
            session = DynamicSubAgentManager.get_session(session_id)
            if not session:
                return "Error: Session Not Found"

            # 检查是否有结果
            result = DynamicSubAgentManager.get_subagent_result(
                session_id, subagent_name, task_id
            )
            if result and (result.result != "" or result.completed_at > 0):
                return self._format_result(result)

            # 如果指定了task_id，检查该任务是否存在
            if task_id:
                status = DynamicSubAgentManager.get_subagent_status(
                    session_id, subagent_name, task_id
                )
                if status == "not_found":
                    return f"Error: Task '{task_id}' not found for SubAgent '{subagent_name}'"
                if status == "running":
                    pass
                    # elapsed = time.time() - start_time
                    # return f" SubAgent '{subagent_name}' task {task_id} is running...\n Waited for: {elapsed:.0f}s / {timeout}s\n"
            else:
                # 未指定task_id，检查是否有pending任务
                pending = DynamicSubAgentManager.get_pending_subagent_tasks(
                    session_id, subagent_name
                )
                if not pending:
                    # 没有pending任务，看看有没有已完成但未取走的结果
                    return f" SubAgent '{subagent_name}' has no ongoing tasks...\n"
                else:
                    pass
                    # elapsed = time.time() - start_time
                    # return f" SubAgent '{subagent_name}' is in progress with {len(pending)} pending tasks...\n Waited for: {elapsed:.0f}s / {timeout}s\n"

            await asyncio.sleep(poll_interval)

        target = f"Task {task_id}" if task_id else "Latest task"
        return f" Timeout! \nSubAgent '{subagent_name}' has not finished '{target}' in {timeout}s. The task may be still running, use `wait_for_subagent` again or complete other things that can be done in parallel."

    @staticmethod
    def _format_result(result: SubAgentExecutionResult) -> str:
        output = f" SubAgent '{result.agent_name}' execution completed\n Status: {'Success' if result.success else 'Failed'}\n Task id: {result.task_id}\n Execution time: {result.execution_time:.1f}s\n--- Result ---\n{result.result}\n"
        if result.error:
            output += f"\n Error: {result.error}"
        return output


# Tool instances
CREATE_DYNAMIC_SUBAGENT_TOOL = CreateDynamicSubAgentTool()
REMOVE_DYNAMIC_SUBAGENT_TOOL = RemoveDynamicSubagentTool()
LIST_DYNAMIC_SUBAGENTS_TOOL = ListDynamicSubagentsTool()
RESET_SUBAGENT_TOOL = ResetSubAgentTool()
PROTECT_SUBAGENT_TOOL = ProtectSubagentTool()
UNPROTECT_SUBAGENT_TOOL = UnprotectSubagentTool()
SEND_SHARED_CONTEXT_TOOL = SendSharedContextTool()
SEND_SHARED_CONTEXT_TOOL_FOR_MAIN_AGENT = SendSharedContextToolForMainAgent()
VIEW_SHARED_CONTEXT_TOOL = ViewSharedContextTool()
WAIT_FOR_SUBAGENT_TOOL = WaitForSubagentTool()
