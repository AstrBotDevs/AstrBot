"""
SubAgent Manager
Manages subagents for task decomposition and parallel processing.
Supports both statically configured subagents (from subagent_orchestrator) and
dynamically created subagents at runtime.
"""

from __future__ import annotations

import os.path
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from astrbot import logger
from astrbot.core.agent.agent import Agent
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.astr_main_agent_resources import LLM_SAFETY_MODE_SYSTEM_PROMPT
from astrbot.core.utils.astrbot_path import get_astrbot_workspaces_path
from astrbot.core.star.star import star_registry

@dataclass
class SubAgentConfig:
    name: str
    system_prompt: str = ""
    tools: set[str] | None = None
    skills: set[str] | None = None
    provider_id: str | None = None
    description: str = ""
    workdir: str | None = None
    execution_timeout: float = 600.0


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
class SubAgentSession:
    session_id: str
    subagents: dict = field(default_factory=dict)  # 存储SubAgentConfig对象
    handoff_tools: dict = field(default_factory=dict)
    subagent_status: dict = field(
        default_factory=dict
    )  # 工作状态 "IDLE" "RUNNING" "COMPLETED" "FAILED"
    protected_agents: set = field(
        default_factory=set
    )  # 若某个agent受到保护，则不会被自动清理
    history_enabled: bool = True  # 是否保存子代理历史
    subagent_histories: dict = field(default_factory=dict)  # 存储每个子代理的历史上下文
    shared_context: list = field(default_factory=list)  # 公共上下文列表
    shared_context_enabled: bool = False  # 是否启用公共上下文
    subagent_background_results: dict = field(
        default_factory=dict
    )  # 后台subagent结果存储: {agent_name: {task_id: SubAgentExecutionResult}}
    # 任务计数器: {agent_name: next_task_id}
    background_task_counters: dict = field(default_factory=dict)
    last_activity_at: float = field(default_factory=time.time)  # 最后活跃时间戳


class SubAgentManager:
    _sessions: dict = {}
    _max_subagent_count: int = 3
    _auto_cleanup_per_turn: bool = True
    _shared_context_enabled: bool = False
    _history_enabled: bool = True  # 是否启用子代理历史记忆功能
    _shared_context_maxlen: int = 300  # 公共上下文保留的历史消息条数
    _subagent_history_maxlen: int = 300  # 每个subagent最多保留的历史消息条数
    _execution_timeout: float = 1200.0  # SubAgent 执行超时时间（秒） 总时长
    _rule_prompt: str = ""  # 动态子代理的固定行为约束prompt
    _time_prompt_enabled: bool = True  # 是否启用时间prompt注入
    _timezone: str | None = None  # 时区设置
    _tools_blacklist: set[str] = {
        "broadcast_shared_context",
        "create_subagent",
        "manage_subagent_protection",
        "remove_subagent",
        "list_subagents",
        "wait_for_subagent",
        "view_shared_context",
    }
    _tools_inherent: set[str] = {
        "astrbot_execute_shell",
        "astrbot_execute_python",
    }
    _session_timeout_seconds = (
        1800  # 会话存活时间。若有会话的subagent闲置时间超过该值，自动清理
    )

    _HEADER_TEMPLATE = f"""# Sub-Agent Orchestration
You can manage sub-agents with isolated instructions, tools and skills. Maximum {_max_subagent_count} subagents.

## When to Use
Create sub-agents ONLY when:
- Task has ≥2 independent workstreams with clear inputs/outputs
- Context exceeds your effective processing window"""
    _SUBAGENT_AUTOCLEAN_PROMPT = (
        "- Sub-agents auto-destroy per turn; use `manage_subagent_protection(name, protected=true/false)` for multi-turn stateful tasks"
        if _auto_cleanup_per_turn
        else ""
    )
    _CREATE_GUIDE_PROMPT = f"""## Workflow: Plan → Create → Delegate → Collect → Cleanup
### 1. Create Sub-agent
**Name**: 1 to 32 characters (letters, numbers, or underscores), starting with a letter.
**Required fields:**
| Field | Description |
|-------|-------------|
| Role | Expertise + work style |
| Context | Parent goal, this step, sibling agents |
| Instruction | Input → Process → Output (step-by-step) |
| Tools | **Minimum necessary only** |

### 2. Delegate
- Sequential: `transfer_to_*(...)` — block until return
- Parallel: `transfer_to_*(..., background_task=True)` → `wait_for_subagent(name, timeout=secs)`

### 3. Collect & Cleanup
- Merge independent outputs by concatenation
- Resolve conflicts by preferring explicit data over inference
{_SUBAGENT_AUTOCLEAN_PROMPT}"""

    @classmethod
    def build_task_router_prompt(cls, session_id: str):
        session = cls.get_session(session_id)
        if not session:
            return ""

        parts = [
            cls._HEADER_TEMPLATE,
            cls._CREATE_GUIDE_PROMPT,
        ]
        return "\n".join(parts) + "\n"

    @classmethod
    def configure(
        cls,
        max_subagent_count: int = 10,
        auto_cleanup_per_turn: bool = True,
        shared_context_enabled: bool = False,
        shared_context_maxlen: int = 300,
        subagent_history_maxlen: int = 300,
        tools_blacklist: list[str] = None,
        tools_inherent: list[str] = None,
        execution_timeout: float = 1200.0,
        history_enabled: bool = True,
        rule_prompt: str = "",
        time_prompt_enabled: bool = True,
        timezone: str | None = None,
        **kwargs,
    ) -> None:
        """Configure SubAgentManager settings"""
        cls._max_subagent_count = max_subagent_count
        cls._auto_cleanup_per_turn = auto_cleanup_per_turn
        cls._shared_context_enabled = shared_context_enabled
        cls._history_enabled = history_enabled
        cls._shared_context_maxlen = shared_context_maxlen
        cls._subagent_history_maxlen = subagent_history_maxlen
        cls._execution_timeout = execution_timeout
        cls._rule_prompt = rule_prompt
        cls._time_prompt_enabled = time_prompt_enabled
        cls._timezone = timezone
        if tools_inherent is None:
            cls._tools_inherent = {
                "astrbot_execute_shell",
                "astrbot_execute_python",
            }
        else:
            cls._tools_inherent = set(tools_inherent)
        if tools_blacklist is None:
            cls._tools_blacklist = {
                "broadcast_shared_context",
                "create_subagent",
                "protect_subagent",
                "manage_subagent_protection",
                "remove_subagent",
                "list_subagents",
                "wait_for_subagent",
                "view_shared_context",
            }
        else:
            cls._tools_blacklist = set(tools_blacklist)

    @classmethod
    def get_execution_timeout(cls) -> float:
        return cls._execution_timeout

    @classmethod
    def is_auto_cleanup_per_turn(cls) -> bool:
        return cls._auto_cleanup_per_turn

    @classmethod
    def is_shared_context_enabled(cls) -> bool:
        return cls._shared_context_enabled

    @classmethod
    def is_history_enabled(cls) -> bool:
        return cls._history_enabled

    @classmethod
    def register_blacklisted_tool(cls, tool_name: str) -> None:
        """注册不应被子 Agent 使用的工具"""
        cls._tools_blacklist.add(tool_name)

    @classmethod
    def register_inherent_tool(cls, tool_name: str) -> None:
        """注册子 Agent 默认拥有的工具"""
        cls._tools_inherent.add(tool_name)

    @classmethod
    def cleanup_session_turn_end(cls, session_id: str) -> dict:
        """Cleanup subagents from previous turn when a turn ends"""
        session = cls.get_session(session_id)
        if not session:
            return {"status": "no_session", "cleaned": []}

        cleaned = []
        for name in list(session.subagents.keys()):
            if name not in session.protected_agents:
                cls.remove_subagent(session_id, name)
                cleaned.append(name)

        # 如果启用了公共上下文，处理清理
        if session.shared_context_enabled:
            if not session.subagents and not session.protected_agents:
                # 所有subagent都被清理，清除公共上下文
                cls.clear_shared_context(session_id)
                logger.debug(
                    "[SubAgent:SharedContext] All subagents cleaned, cleared shared context"
                )
            else:
                # 清理已删除agent的上下文
                for name in cleaned:
                    cls.cleanup_shared_context_by_agent(session_id, name)

        # 清理后若没有subagent，清理整个session
        if not session.subagents and not session.protected_agents:
            cls._sessions.pop(session_id, None)

        # 每轮结束时顺便清理全局过期会话
        cls.cleanup_expired_sessions()

        return {"status": "cleaned", "cleaned_agents": cleaned}

    @classmethod
    def protect_subagent(cls, session_id: str, agent_name: str) -> None:
        """Mark a subagent as protected from auto cleanup and history retention"""
        session = cls._get_or_create_session(session_id)
        session.protected_agents.add(agent_name)
        logger.debug(
            "[SubAgent:History] Initialized history for protected agent: %s",
            agent_name,
        )

    @classmethod
    def update_subagent_history(
        cls, session_id: str, agent_name: str, current_messages: list
    ) -> None:
        """Update conversation history for a subagent"""
        if not cls._history_enabled:
            return

        session = cls.get_session(session_id)

        if not session:
            return

        if agent_name not in session.subagent_histories:
            session.subagent_histories[agent_name] = []

        filtered_messages = []
        if isinstance(current_messages, list):
            _MAX_TOOL_RESULT_LEN = 2000
            for msg in current_messages:
                if (
                    isinstance(msg, dict) and msg.get("role") == "system"
                ):  # 移除system消息
                    continue
                # 对过长的 tool 结果做截断，避免单条消息占用过多空间
                if (
                    isinstance(msg, dict)
                    and msg.get("role") == "tool"
                    and isinstance(msg.get("content"), str)
                    and len(msg["content"]) > _MAX_TOOL_RESULT_LEN
                ):
                    msg["content"] = (
                        msg["content"][:_MAX_TOOL_RESULT_LEN] + "\n...[truncated]"
                    )
                filtered_messages.append(msg)

        session.subagent_histories[agent_name].extend(filtered_messages)
        if len(session.subagent_histories[agent_name]) > cls._subagent_history_maxlen:
            session.subagent_histories[agent_name] = session.subagent_histories[
                agent_name
            ][-cls._subagent_history_maxlen :]

        logger.debug(
            "[SubAgent:History] Saved messages for %s, current len=%d",
            agent_name,
            len(session.subagent_histories[agent_name]),
        )

    @classmethod
    def get_subagent_history(cls, session_id: str, agent_name: str) -> list:
        """Get conversation history for a subagent"""
        if not cls._history_enabled:
            return []
        session = cls.get_session(session_id)
        if not session:
            return []
        return session.subagent_histories.get(agent_name, [])

    @classmethod
    def build_subagent_system_prompt(
        cls, session_id: str, agent_name: str, runtime: str
    ) -> str:
        parts = []
        rule = cls._build_rule_prompt()
        workdir = cls._build_workdir_prompt(session_id, agent_name)
        if rule:
            parts.append(rule)
        if workdir:
            parts.append(workdir)
        skills = cls._build_subagent_skills_prompt(session_id, agent_name, runtime)
        if skills:
            parts.append(skills)
        return "\n".join(parts)

    @classmethod
    def build_subagent_extra_content_parts(
        cls, session_id: str, agent_name: str
    ) -> list:
        """构建子代理的追加内容部分（extra_user_content_parts）。

        将共享上下文和时间信息作为追加内容返回，它们将被注入到用户消息中，

        Returns:
            list[TextPart]: 追加内容部分列表
        """
        from astrbot.core.agent.message import TextPart

        parts = []

        # 1. 共享上下文
        shared_context = cls._build_shared_context_prompt(session_id, agent_name)
        if shared_context:
            parts.append(TextPart(text=shared_context).mark_as_temp())

        # 2. 时间信息
        time_prompt = cls._build_time_prompt()
        if time_prompt:
            parts.append(TextPart(text=time_prompt).mark_as_temp())

        return parts

    @classmethod
    def _filter_skills_for_current_config(cls, skills: list) -> list:
        """Filter skills based on plugin activation status and plugin_set config.

        Mirrors the logic in astr_main_agent._filter_skills_for_current_config
        but avoids circular imports by accessing config directly.
        """
        try:
            from astrbot.core.star.context import Context
            ctx = Context.get_instance() if hasattr(Context, 'get_instance') else None
            cfg = ctx.get_config() if ctx else {}
        except Exception:
            return skills

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

        filtered = []
        for skill in skills:
            if getattr(skill, 'source_type', '') != "plugin":
                filtered.append(skill)
                continue

            plugin_name = getattr(skill, 'plugin_name', '')
            plugin = plugin_by_root_dir.get(plugin_name)
            if not plugin or not plugin.activated:
                continue
            if plugin.reserved or allowed_plugins is None:
                filtered.append(skill)
                continue
            if plugin.name is not None and plugin.name in allowed_plugins:
                filtered.append(skill)

        return filtered

    @classmethod
    def _build_subagent_skills_prompt(
        cls, session_id: str, agent_name: str, runtime: str = "local"
    ) -> str:
        """Build skills prompt for a subagent based on its assigned skills"""
        session = cls.get_session(session_id)
        if not session:
            return ""

        config = session.subagents.get(agent_name)
        if not config:
            return ""

        # 获取子代理被分配的技能列表
        assigned_skills = config.skills

        from astrbot.core.skills import SkillManager, build_skills_prompt

        skill_manager = SkillManager()
        all_skills = skill_manager.list_skills(active_only=True, runtime=runtime)
        all_skills = cls._filter_skills_for_current_config(all_skills)
        if all_skills:
            if assigned_skills is None:
                filtered_skills = all_skills
            else:
                # 过滤只保留分配的技能
                filtered_skills = [
                    s for s in all_skills if s.name in set(assigned_skills)
                ]
        else:
            return ""
        if filtered_skills:
            return build_skills_prompt(filtered_skills)
        else:
            return ""

    @classmethod
    def get_subagent_tools(cls, session_id: str, agent_name: str) -> list | None:
        """Get the tools assigned to a subagent"""
        session = cls.get_session(session_id)
        if not session:
            return None
        config = session.subagents.get(agent_name)
        if not config:
            return None
        return config.tools

    @classmethod
    def clear_subagent_history(cls, session_id: str, agent_name: str) -> str:
        """Clear conversation history for a subagent"""
        session = cls.get_session(session_id)
        if not session:
            return (
                f"__HISTORY_CLEARED_FAILED__: Session_id {session_id} does not exist."
            )
        if agent_name in session.subagents:
            if agent_name in session.subagent_histories:
                session.subagent_histories.pop(agent_name, None)
                if session.shared_context_enabled:
                    cls.cleanup_shared_context_by_agent(session_id, agent_name)
                logger.debug("[SubAgent:History] Cleared history for: %s", agent_name)
            return "__HISTORY_CLEARED__"
        else:
            return f"__HISTORY_CLEARED_FAILED__: Agent name {agent_name} not found. Available names {list(session.subagents.keys())}"

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

        session = cls._get_or_create_session(session_id)
        if not session.shared_context_enabled:
            return "__SHARED_CONTEXT_ADDED_FAILED__: Shared context disabled."
        if (sender not in list(session.subagents.keys())) and (sender != "System"):
            return f"__SHARED_CONTEXT_ADDED_FAILED__: Sender name {sender} not found. Available names {list(session.subagents.keys())}"
        if (target not in list(session.subagents.keys())) and (target != "all"):
            return f"__SHARED_CONTEXT_ADDED_FAILED__: Target name {target} not found. Available names {list(session.subagents.keys())} and 'all' "

        if len(session.shared_context) >= cls._shared_context_maxlen:
            keep_count = int(cls._shared_context_maxlen * 0.9)
            session.shared_context = session.shared_context[-keep_count:]
            logger.warning(
                "Shared context exceeded limit (%d), trimmed to %d",
                cls._shared_context_maxlen,
                keep_count,
            )

        message = {
            "type": context_type,  # status, message, system
            "sender": sender,
            "target": target,
            "content": content,
            "timestamp": time.time(),
        }
        session.shared_context.append(message)
        logger.debug(
            "[SubAgent:SharedContext] [%s] %s -> %s: %s...",
            context_type,
            sender,
            target,
            content[:50],
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
    def _build_shared_context_prompt(
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
1. @System messages (highest priority) > @ToMe messages > @Status > @OtherAgents
2. Messages of the same type: In chronological order, with new messages taking precedence
"""
        )

        # === 2. System 消息 ===
        system_msgs = [m for m in session.shared_context if m["type"] == "system"]
        if system_msgs:
            lines.append("\n## @System - System Announcements")
            for msg in system_msgs:
                if cls._timezone:
                    import zoneinfo

                    ts = datetime.fromtimestamp(
                        msg["timestamp"], tz=zoneinfo.ZoneInfo(cls._timezone)
                    ).strftime("%H:%M:%S")
                else:
                    ts = time.strftime("%H:%M:%S", time.localtime(msg["timestamp"]))
                content_text = msg["content"]
                lines.append(f"[{ts}] System: {content_text}")

        if agent_name:
            # === 3. 发送给当前 Agent 的消息 ===
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

            # === 4. 其他 Agent 之间的交互（仅显示最近10条）===
            inter_agent_msgs = [
                m
                for m in session.shared_context
                if m["type"] == "message"
                and m["target"] != agent_name
                and m["target"] != "all"
                and m["sender"] != agent_name
            ]
            if inter_agent_msgs:
                lines.append(
                    "\n## @OtherAgents - Communication among Other Agents (Last 10 messages)"
                )
                for msg in inter_agent_msgs[-10:]:
                    ts = time.strftime("%H:%M:%S", time.localtime(msg["timestamp"]))
                    content_text = msg["content"]
                    lines.append(
                        f"[{ts}] {msg['sender']} -> {msg['target']}: {content_text}"
                    )

            # === 5. Status 更新 ===
            status_msgs = [m for m in session.shared_context if m["type"] == "status"]
            if status_msgs:
                lines.append(
                    "\n## @Status - Task progress of each agent (Last 10 messages)"
                )
                for msg in status_msgs[-10:]:
                    ts = time.strftime("%H:%M:%S", time.localtime(msg["timestamp"]))
                    lines.append(f"[{ts}] {msg['sender']}: {msg['content']}")

        lines.append("---")
        return "\n".join(lines)

    @classmethod
    def _build_workdir_prompt(cls, session_id: str, agent_name: str = None) -> str:
        """为subagent注入工作目录信息"""
        session = cls.get_session(session_id)
        normalized_umo = (
            re.sub(r"[^A-Za-z0-9._-]+", "_", session_id.strip()) or "unknown"
        )

        if not session:
            return ""
        try:
            workdir = session.subagents[agent_name].workdir
            if workdir is None:
                workdir = (
                    Path(get_astrbot_workspaces_path()) / normalized_umo / agent_name
                ).resolve(strict=False)

        except Exception:
            workdir = (
                Path(get_astrbot_workspaces_path()) / normalized_umo / agent_name
            ).resolve(strict=False)

        if not os.path.exists(workdir):
            os.makedirs(workdir)
        workdir_prompt = (
            "# Working Directory\n"
            + f"Your working directory is `{workdir}`. Unless specified by the user, all generated files are saved by default in this directory.\n"
        )
        return workdir_prompt

    @classmethod
    def _build_time_prompt(cls) -> str:
        if not cls._time_prompt_enabled:
            return ""
        try:
            if cls._timezone:
                import zoneinfo

                current_time = datetime.now(zoneinfo.ZoneInfo(cls._timezone)).strftime(
                    "%Y-%m-%d %H:%M (%Z)"
                )
            else:
                current_time = (
                    datetime.now().astimezone().strftime("%Y-%m-%d %H:%M (%Z)")
                )
        except Exception:
            current_time = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M (%Z)")
        time_prompt = f"# Current Time\n{current_time}\n"
        return time_prompt

    @classmethod
    def _build_rule_prompt(cls) -> str:
        if cls._rule_prompt:
            return cls._rule_prompt
        return (
            "# Behavior Rules\n"
            "## Safety\n"
            f"{LLM_SAFETY_MODE_SYSTEM_PROMPT}"
            "## Output Guidelines\n"
            "- If output is long, save it to file. Summarize in your response and provide the file path.\n"
            "- Mark all generated code/documents with your name and timestamp (if given).\n"
        )

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
            logger.debug(
                "[SubAgent:SharedContext] Removed %d messages related to %s",
                removed,
                agent_name,
            )

    @classmethod
    def clear_shared_context(cls, session_id: str) -> None:
        """Clear all shared context"""
        session = cls.get_session(session_id)
        if not session:
            return
        session.shared_context.clear()
        logger.debug("[SubAgent:SharedContext] Cleared all shared context")

    @classmethod
    def is_protected(cls, session_id: str, agent_name: str) -> bool:
        """Check if a subagent is protected from auto cleanup"""
        session = cls.get_session(session_id)
        if not session:
            return False
        return agent_name in session.protected_agents

    @classmethod
    def set_history_enabled(cls, session_id: str, enabled: bool) -> None:
        """Enable or disable history for subagents"""
        session = cls._get_or_create_session(session_id)
        session.history_enabled = enabled
        logger.info(
            "[SubAgent:History] Subagent history %s",
            "enabled" if enabled else "disabled",
        )

    @classmethod
    def set_shared_context_enabled(cls, session_id: str, enabled: bool) -> None:
        """Enable or disable shared context for a session"""
        session = cls._get_or_create_session(session_id)
        session.shared_context_enabled = enabled
        logger.info(
            "[SubAgent:SharedContext] Shared context %s",
            "enabled" if enabled else "disabled",
        )

    @classmethod
    def set_subagent_status(cls, session_id: str, agent_name: str, status: str) -> None:
        session = cls._get_or_create_session(session_id)
        if agent_name in session.subagents:
            session.subagent_status[agent_name] = status

    # for read-only operations
    @classmethod
    def get_session(cls, session_id: str) -> SubAgentSession | None:
        return cls._sessions.get(session_id, None)

    # ensure the existence of a session before writing operations
    @classmethod
    def _get_or_create_session(cls, session_id: str) -> SubAgentSession:
        if session_id not in cls._sessions:
            cls._sessions[session_id] = SubAgentSession(session_id=session_id)
        else:
            cls._sessions[session_id].last_activity_at = time.time()
        return cls._sessions[session_id]

    @classmethod
    def _touch_session(cls, session_id: str) -> None:
        """更新会话的最后活跃时间"""
        session = cls._sessions.get(session_id)
        if session:
            session.last_activity_at = time.time()

    @classmethod
    def cleanup_expired_sessions(cls) -> dict:
        """清理超过超时时间未活跃的会话，防止内存泄漏

        Returns:
            dict: 包含被清理的会话ID列表和数量
        """
        now = time.time()
        expired_session_ids = [
            sid
            for sid, session in cls._sessions.items()
            if now - session.last_activity_at > cls._session_timeout_seconds
        ]
        cleaned_agents_count = 0
        for sid in expired_session_ids:
            session = cls._sessions.get(sid)
            if session:
                agent_names = list(session.subagents.keys())
                cleaned_agents_count += len(agent_names)
                cls._sessions.pop(sid, None)
                logger.info(
                    "[SubAgent:Timeout] Session %s expired (inactive for >%.0f minutes). Cleaned %d subagents.",
                    sid,
                    cls._session_timeout_seconds / 60,
                    len(agent_names),
                )
        return {
            "cleaned_sessions": expired_session_ids,
            "cleaned_count": len(expired_session_ids),
            "cleaned_agents_count": cleaned_agents_count,
        }

    @classmethod
    async def create_subagent(
        cls, session_id: str, config: SubAgentConfig, protected: bool = False
    ) -> tuple:
        """Create a subagent (dynamic or static).

        Args:
            session_id: Session ID
            config: SubAgent configuration
            protected: If True, the subagent will not be auto-cleaned per turn.
                       Static subagents from config should be protected.
        """
        session = cls._get_or_create_session(session_id)
        if config.name not in session.subagents:
            # Check max count limit
            active_count = len(session.subagents.keys())
            if active_count >= cls._max_subagent_count:
                return (
                    f"Error: Maximum number of subagents ({cls._max_subagent_count}) reached. More subagents is not allowed.",
                    None,
                )

        if config.name in session.subagents:
            session.handoff_tools.pop(config.name, None)
        # When shared_context is enabled, the send_shared_context tool is allocated regardless of whether the main agent allocates the tool to the subagent
        if config.tools is None:
            config.tools = set()
        # When shared_context is enabled, the send_shared_context tool is allocated regardless of whether the main agent allocates the tool to the subagent
        if session.shared_context_enabled:
            config.tools.add("send_shared_context")
        # remove tools in backlist
        for tool_bl in cls._tools_blacklist:
            config.tools.discard(tool_bl)

        # add tools in inherent list
        for tool_ih in cls._tools_inherent:
            config.tools.add(tool_ih)

        session.subagents[config.name] = config
        agent = Agent(
            name=config.name,
            instructions=config.system_prompt,
            tools=list(config.tools),
        )
        handoff_tool = HandoffTool(
            agent=agent,
            tool_description=config.description or f"Delegate to {config.name} agent",
        )
        if config.provider_id:
            handoff_tool.provider_id = config.provider_id
        session.handoff_tools[config.name] = handoff_tool
        # 初始化subagent的历史上下文（仅当历史功能启用时）
        if cls._history_enabled:
            session.subagent_histories[config.name] = []
        # 初始化subagent状态
        cls.set_subagent_status(session_id, config.name, "IDLE")
        # 如果标记为protected，则加入protected集合
        if protected:
            session.protected_agents.add(config.name)
        logger.info(
            "[SubAgent:Create] Created subagent: %s (protected=%s)",
            config.name,
            protected,
        )
        return f"transfer_to_{config.name}", handoff_tool

    @classmethod
    def register_static_subagent(
        cls,
        session_id: str,
        handoff_tool: HandoffTool,
        skills: set[str] | None = None,
        workdir: str | None = None,
    ) -> tuple:
        """Register a static subagent (from subagent_orchestrator config) into SubAgentManager.

        Static subagents are always protected from auto-cleanup.
        Returns (tool_name, handoff_tool) same as create_subagent.
        """
        agent = handoff_tool.agent
        config = SubAgentConfig(
            name=agent.name,
            system_prompt=agent.instructions or "",
            tools=agent.tools,
            skills=skills,
            provider_id=getattr(handoff_tool, "provider_id", None),
            description=f"Delegate to {agent.name} agent",
            workdir=workdir,
        )

        session = cls._get_or_create_session(session_id)
        if (
            config.name not in session.subagents
        ):  # if the static agent already exists, pass
            if config.tools is None:
                config.tools = None
            if config.tools is not None and not config.tools:
                config.tools = set()
            if session.shared_context_enabled:
                config.tools.add("send_shared_context")
            session.subagents[config.name] = config
            agent = Agent(
                name=config.name,
                instructions=config.system_prompt,
                tools=config.tools,
            )
            handoff_tool = HandoffTool(
                agent=agent,
                tool_description=config.description
                or f"Delegate to {config.name} agent",
            )
            if config.provider_id:
                handoff_tool.provider_id = config.provider_id
            session.handoff_tools[config.name] = handoff_tool

            if cls._history_enabled and config.name not in session.subagent_histories:
                session.subagent_histories[config.name] = []

            cls.set_subagent_status(session_id, config.name, "IDLE")
            session.protected_agents.add(config.name)
        else:
            pass
        return f"transfer_to_{config.name}", handoff_tool

    @classmethod
    async def cleanup_session(cls, session_id: str) -> dict:
        session = cls._sessions.pop(session_id, None)
        if not session:
            return {"status": "not_found", "cleaned_agents": []}
        else:
            cleaned = list(session.subagents.keys())
            for name in cleaned:
                logger.info("[SubAgent:Cleanup] Cleaned: %s", name)
            return {"status": "cleaned", "cleaned_agents": cleaned}

    @classmethod
    def remove_subagent(cls, session_id: str, agent_name: str) -> str:
        cls._touch_session(session_id)
        session = cls.get_session(session_id)
        if not session:
            return f"__SUBAGENT_REMOVE_FAILED__: Session {session_id} does not exist."
        if session.subagent_status.get(agent_name) == "RUNNING":
            return f"__SUBAGENT_REMOVE_FAILED__: {agent_name} is still RUNNING. Waiting for finish first."

        def _remove_by_name(name):
            session.subagents.pop(name, None)
            session.protected_agents.discard(name)
            session.handoff_tools.pop(name, None)
            session.subagent_histories.pop(name, None)
            session.subagent_background_results.pop(name, None)
            session.background_task_counters.pop(name, None)
            # 清理公共上下文中包含该Agent的内容
            cls.cleanup_shared_context_by_agent(session_id, name)

        if agent_name == "all":
            if "RUNNING" in session.subagent_status.values():
                removed = 0
                for subagent_name in list(session.subagents.keys()):
                    if session.subagent_status.get(subagent_name) == "RUNNING":
                        continue
                    _remove_by_name(subagent_name)
                    removed += 1
                return f"__SUBAGENT_REMOVED__: Removed {removed} subagents. {len(session.subagents.keys())} subagents are reserved because they are still running."
            else:
                session.subagents.clear()
                session.handoff_tools.clear()
                session.protected_agents.clear()
                session.subagent_histories.clear()
                session.shared_context.clear()
                session.subagent_background_results.clear()
                session.background_task_counters.clear()
                logger.info("[SubAgent:Cleanup] All subagents cleaned.")
                return "__SUBAGENT_REMOVED__: All subagents have been removed."
        else:
            if agent_name not in session.subagents:
                return f"__SUBAGENT_REMOVE_FAILED__: {agent_name} not found. Available subagent names {list(session.subagents.keys())}"
            else:
                _remove_by_name(agent_name)
                logger.info("[SubAgent:Cleanup] Cleaned: %s", agent_name)
                return f"__SUBAGENT_REMOVED__: Subagent {agent_name} has been removed."

    @classmethod
    def get_handoff_tools_for_session(cls, session_id: str) -> list:
        session = cls.get_session(session_id)
        if not session:
            return []
        return list(session.handoff_tools.values())

    @classmethod
    def create_pending_subagent_task(cls, session_id: str, agent_name: str) -> str:
        """为 SubAgent 创建一个 pending 任务，返回 task_id

        Args:
            session_id: Session ID
            agent_name: SubAgent 名称

        Returns:
            task_id: 任务ID，格式为简单的递增数字字符串
        """
        session = cls._get_or_create_session(session_id)

        # 初始化
        if agent_name not in session.subagent_background_results:
            session.subagent_background_results[agent_name] = {}
        if agent_name not in session.background_task_counters:
            session.background_task_counters[agent_name] = 0

        if (
            session.subagent_status[agent_name] == "RUNNING"
        ):  # 若当前有任务在运行，不允许创建
            return (
                f"__PENDING_TASK_CREATE_FAILED__: Subagent {agent_name} already running"
            )

        # 生成递增的任务ID
        session.background_task_counters[agent_name] += 1
        task_id = str(session.background_task_counters[agent_name])

        # 创建 pending 占位
        session.subagent_background_results[agent_name][task_id] = (
            SubAgentExecutionResult(
                task_id=task_id,
                agent_name=agent_name,
                success=False,
                result=None,
                created_at=time.time(),
                metadata={},
            )
        )

        return task_id

    @classmethod
    def _ensure_task_store(
        cls, session: SubAgentSession, agent_name: str
    ) -> dict[str, SubAgentExecutionResult]:
        if agent_name not in session.subagent_background_results:
            session.subagent_background_results[agent_name] = {}
        return session.subagent_background_results[agent_name]

    @staticmethod
    def _is_task_completed(result: SubAgentExecutionResult) -> bool:
        return result.completed_at > 0 or result.error is not None

    @classmethod
    def get_pending_subagent_tasks(cls, session_id: str, agent_name: str) -> list[str]:
        """获取 SubAgent 的所有 pending 任务 ID 列表（按创建时间排序）"""
        session = cls.get_session(session_id)
        if not session:
            return []

        store = session.subagent_background_results.get(agent_name)
        if not store:
            return []

        pending = [tid for tid, res in store.items() if not cls._is_task_completed(res)]
        return sorted(pending, key=lambda tid: store[tid].created_at)

    @classmethod
    def get_latest_task_id(cls, session_id: str, agent_name: str) -> str | None:
        """获取 SubAgent 的最新任务 ID"""
        session = cls.get_session(session_id)
        if not session or agent_name not in session.subagent_background_results:
            return None

        # 按 created_at 排序取最新的
        sorted_tasks = sorted(
            session.subagent_background_results[agent_name].items(),
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
        session = cls._get_or_create_session(session_id)

        task_store = cls._ensure_task_store(session, agent_name)

        if task_id is None:
            # 如果没有指定task_id，尝试找最新的pending任务
            pending = cls.get_pending_subagent_tasks(session_id, agent_name)
            if pending:
                task_id = pending[-1]
            else:
                logger.warning(
                    f"[SubAgentResult] No task_id and no pending tasks for {agent_name}"
                )
                return

        if task_id not in task_store:
            # 如果任务不存在，先创建一个占位
            task_store[task_id] = SubAgentExecutionResult(
                task_id=task_id,
                agent_name=agent_name,
                success=False,
                result="",
                created_at=time.time(),
                metadata=metadata or {},
            )

        # 更新结果
        task_store[task_id].success = success
        task_store[task_id].result = result
        task_store[task_id].error = error
        task_store[task_id].execution_time = execution_time
        task_store[task_id].completed_at = time.time()
        if metadata:
            task_store[task_id].metadata.update(metadata)

    @classmethod
    def get_subagent_result(
        cls, session_id: str, agent_name: str, task_id: str | None = None
    ) -> SubAgentExecutionResult | None:
        """获取 SubAgent 的执行结果

        Args:
            session_id: Session ID
            agent_name: SubAgent 名称
            task_id: 任务ID，如果为None则获取最新完成的任务结果

        Returns:
            SubAgentExecutionResult 或 None
        """
        session = cls.get_session(session_id)
        if not session or agent_name not in session.subagent_background_results:
            return None

        if task_id is None:
            # 获取最新的已完成任务
            completed = [
                (tid, r)
                for tid, r in session.subagent_background_results[agent_name].items()
                if r.result != "" or r.completed_at > 0
            ]
            if not completed:
                return None
            # 按创建时间排序，取最新的
            completed.sort(key=lambda x: x[1].created_at, reverse=True)
            return completed[0][1]

        return session.subagent_background_results[agent_name].get(task_id, None)

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
        task_store = cls._ensure_task_store(session, agent_name)
        if not session or not task_store:
            return False

        if task_id is None:
            # 检查是否有任何已完成的任务
            return any(
                r.result != "" or r.completed_at > 0 for r in task_store.values()
            )

        if task_id not in task_store:
            return False
        result = task_store[task_id]
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
        task_store = cls._ensure_task_store(session, agent_name)
        if not session or not task_store:
            return

        if task_id is None:
            # 清除所有任务
            session.subagent_background_results.pop(agent_name, None)
            session.background_task_counters.pop(agent_name, None)
        else:
            # 清除特定任务
            task_store.pop(task_id, None)

    @classmethod
    def get_subagent_status(cls, session_id: str, agent_name: str) -> str:
        """获取 SubAgent 的状态: IDLE, RUNNING, COMPLETED, FAILED

        Args:
            session_id: Session ID
            agent_name: SubAgent 名称
        """
        session = cls.get_session(session_id)
        if not session:
            return "UNKNOWN"
        return session.subagent_status.get(agent_name, "UNKNOWN")

    @classmethod
    def get_all_subagent_status(cls, session_id: str) -> dict:
        """获取所有 SubAgent 的状态"""
        session = cls.get_session(session_id)
        if not session:
            return {}
        return {
            name: cls.get_subagent_status(session_id, name)
            for name in session.subagents
        }
