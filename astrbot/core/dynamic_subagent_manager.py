"""
Dynamic SubAgent Manager
Manages dynamically created subagents for task decomposition and parallel processing
"""

from __future__ import annotations
import asyncio
import re
from dataclasses import dataclass, field
from astrbot import logger
from astrbot.core.agent.agent import Agent
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.subagent_logger import SubAgentLogger
import time


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
    agent_name: str
    success: bool
    result: str
    error: str | None = None
    execution_time: float = 0.0


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

Available tools and Skills depend on the system's configuration. You should check and list tools and skills, and assign tools and skills when creating sub-agents that need specialized capabilities.

## Sub-agent Lifecycle

Sub-agents are valid during single round conversation with the user, but they will be cleaned up automatically after you send the final answer to user.
If you wish to prevent a certain sub-agent from being automatically cleaned up, use `protect_subagent` tool. Also, you can use the `unprotect_subagent` tool to remove protection.
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
    def cleanup_session_turn_start(cls, session_id: str) -> dict:
        """Cleanup subagents from previous turn when a new turn starts"""
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
            "DynamicSubAgentManager:auto_cleanup",
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
    def clear_subagent_history(cls, session_id: str, agent_name: str) -> None:
        """Clear conversation history for a subagent"""
        session = cls.get_session(session_id)
        if not session:
            return
        if agent_name in session.agent_histories:
            session.agent_histories.pop(agent_name)
            SubAgentLogger.debug(
                session_id,
                "DynamicSubAgentManager:history",
                f"Cleared history for: {agent_name}",
                agent_name,
            )

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
    ) -> None:
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
            return

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
    async def cleanup_subagent(cls, session_id: str, agent_name: str) -> bool:
        session = cls.get_session(session_id)
        if not session or agent_name not in session.agents:
            return False
        session.agents.pop(agent_name, None)
        session.handoff_tools.pop(agent_name, None)
        session.agent_histories.pop(agent_name, None)
        # 清理公共上下文中包含该Agent的内容
        cls.cleanup_shared_context_by_agent(session_id, agent_name)
        SubAgentLogger.info(
            session_id,
            "DynamicSubAgentManager:cleanup",
            f"Cleaned: {agent_name}",
            agent_name,
        )
        return True

    @classmethod
    def get_handoff_tools_for_session(cls, session_id: str) -> list:
        session = cls.get_session(session_id)
        if not session:
            return []
        return list(session.handoff_tools.values())


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
        if "Error: Maximum number of subagents" not in tool_name:
            return f"__DYNAMIC_TOOL_CREATED__:{tool_name}:{handoff_tool.name}:Created. Use {tool_name} to delegate."
        else:
            return f"__FAILED_TO_CREATE_DYNAMIC_TOOL__:{tool_name}"


@dataclass
class CleanupDynamicSubagentTool(FunctionTool):
    name: str = "cleanup_dynamic_subagent"
    description: str = "Clean up dynamic subagent."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
    )

    async def call(self, context, **kwargs) -> str:
        name = kwargs.get("name", "")
        if not name:
            return "Error: name required"
        session_id = context.context.event.unified_msg_origin
        success = await DynamicSubAgentManager.cleanup_subagent(session_id, name)
        return f"Cleaned {name}" if success else f"Not found: {name}"


@dataclass
class ListDynamicSubagentsTool(FunctionTool):
    name: str = "list_dynamic_subagents"
    description: str = "List dynamic subagents."
    parameters: dict = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )

    async def call(self, context, **kwargs) -> str:
        session_id = context.context.event.unified_msg_origin
        session = DynamicSubAgentManager.get_session(session_id)
        if not session or not session.agents:
            return "No subagents"
        lines = []
        for name in session.agents.keys():
            protected = "(protected)" if name in session.protected_agents else ""
            lines.append(f"  - {name} {protected}")
        return "Subagents:\n" + "\n".join(lines)


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
            return f"Error: Subagent {name} not found"
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


# Tool instances
CREATE_DYNAMIC_SUBAGENT_TOOL = CreateDynamicSubAgentTool()
CLEANUP_DYNAMIC_SUBAGENT_TOOL = CleanupDynamicSubagentTool()
LIST_DYNAMIC_SUBAGENTS_TOOL = ListDynamicSubagentsTool()
PROTECT_SUBAGENT_TOOL = ProtectSubagentTool()
UNPROTECT_SUBAGENT_TOOL = UnprotectSubagentTool()


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
        DynamicSubAgentManager.add_shared_context(
            session_id, "System", context_type, content, target
        )
        return f"Shared context updated: [{context_type}] System -> {target}: {content[:100]}{'...' if len(content) > 100 else ''}"


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
        DynamicSubAgentManager.add_shared_context(
            session_id, sender, context_type, content, target
        )
        return f"Shared context updated: [{context_type}] {sender} -> {target}: {content[:100]}{'...' if len(content) > 100 else ''}"


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


# Shared context tool instances
SEND_SHARED_CONTEXT_TOOL = SendSharedContextTool()
SEND_SHARED_CONTEXT_TOOL_FOR_MAIN_AGENT = SendSharedContextToolForMainAgent()
VIEW_SHARED_CONTEXT_TOOL = ViewSharedContextTool()
