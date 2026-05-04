"""
SubAgent Tools
Tool definitions for SubAgent management.
These tools are used by the main agent to create, manage, and interact with subagents.
"""

from __future__ import annotations

import asyncio
import os
import platform
import re
import time
from dataclasses import dataclass, field

from astrbot.core.agent.tool import FunctionTool
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from astrbot.core.subagent_manager import (
    SubAgentConfig,
    SubAgentManager,
)

@dataclass
class CreateSubAgentTool(FunctionTool):
    name: str = "create_subagent"
    description: str = "Create a subagent. After creation, use transfer_to_{name} tool."

    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Subagent name"},
                "system_prompt": {
                    "type": "string",
                    "description": "Subagent system_prompt",
                },
                "tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tools available to subagent, can be empty.",
                },
                "skills": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Skills available to subagent, can be empty",
                },
                "workdir": {
                    "type": "string",
                    "description": "Subagent working directory(absolute path), can be empty(same to main agent). Fill only when the user has clearly specified the path.",
                },
            },
            "required": ["name", "system_prompt"],
        }
    )

    def _check_path_safety(self, path_str: str) -> bool:
        """
        检查路径是否合法、安全
        """
        if not path_str or not isinstance(path_str, str):
            return False

        if not os.path.isabs(path_str):
            return False

        try:
            resolved = os.path.realpath(path_str)
        except (OSError, ValueError):
            return False

        # 使用路径组件匹配而非子字符串匹配
        path_parts = {part.lower() for part in os.path.normpath(resolved).split(os.sep)}

        # Windows 特殊目录检查（作为独立的路径组件）
        windows_dangerous_components = {
            "windows",
            "system32",
            "syswow64",
            "boot",
            "recovery",
            "programdata",
            "$recycle.bin",
            "system volume information",
        }

        system = platform.system().lower()
        if system == "windows":
            if path_parts & windows_dangerous_components:
                return False
        elif system == "linux":
            # 检查是否在危险目录下（前缀匹配）
            linux_dangerous_prefixes = [
                "/etc",
                "/bin",
                "/sbin",
                "/lib",
                "/lib64",
                "/boot",
                "/dev",
                "/proc",
                "/sys",
                "/root",
            ]
            resolved_norm = os.path.normpath(resolved)
            for prefix in linux_dangerous_prefixes:
                if resolved_norm.startswith(prefix + "/") or resolved_norm == prefix:
                    return False
        elif system == "darwin":
            darwin_dangerous_prefixes = [
                "/System",
                "/Library",
                "/private/var",
                "/usr",
            ]
            resolved_norm = os.path.normpath(resolved)
            for prefix in darwin_dangerous_prefixes:
                if resolved_norm.startswith(prefix + "/") or resolved_norm == prefix:
                    return False

        # 通用检查：父目录跳转
        if ".." in path_str:
            return False

        if not os.path.exists(resolved):
            return False

        return True

    async def call(self, context, **kwargs) -> str:
        name = kwargs.get("name", "")

        if not name:
            return "Error: subagent name required"
        # 验证名称格式：只允许英文字母、数字和下划线，长度限制
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_]{0,31}$", name):
            return "Error: SubAgent name must start with letter, contain only letters/numbers/underscores, max 32 characters"

        if name.startswith("__") and name.endswith("__"):
            return "Error: SubAgent name cannot start and end with double underscores"

        system_prompt = kwargs.get("system_prompt", "")
        tools = kwargs.get("tools", {})
        skills = kwargs.get("skills", {})
        workdir = kwargs.get("workdir")

        session_id = context.context.event.unified_msg_origin
        # 工作路径如果非法，回退到该session的默认工作路径
        if workdir is None or (not self._check_path_safety(workdir)):
            workdir = get_astrbot_temp_path()
        config = SubAgentConfig(
            name=name,
            system_prompt=system_prompt,
            tools=set(tools),
            skills=set(skills),
            workdir=workdir,
        )

        tool_name, handoff_tool = await SubAgentManager.create_subagent(
            session_id=session_id, config=config
        )
        if handoff_tool:
            return f"__DYNAMIC_TOOL_CREATED__:{tool_name}:{handoff_tool.name}:Created. Use {tool_name} to delegate."
        else:
            return f"__DYNAMIC_TOOL_CREATE_FAILED__:{tool_name}"


@dataclass
class RemoveSubagentTool(FunctionTool):
    name: str = "remove_subagent"
    description: str = "Remove subagent by name. Use 'all' to remove all subagents."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Subagent name to remove. Use 'all' to remove all subagents.",
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
        remove_status = SubAgentManager.remove_subagent(session_id, name)
        if remove_status == "__SUBAGENT_REMOVED__":
            return f"Cleaned {name} Subagent"
        else:
            return remove_status


@dataclass
class ListSubagentsTool(FunctionTool):
    name: str = "list_subagents"
    description: str = "List subagents with their status."
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
        session = SubAgentManager.get_session(session_id)
        if not session or not session.subagents:
            return "No subagents"

        lines = ["Subagents:"]
        for name, config in session.subagents.items():
            protected = " (protected)" if name in session.protected_agents else ""
            if include_status:
                status = SubAgentManager.get_subagent_status(session_id, name)
                lines.append(f" {name}{protected} [{status}]\ttools:{config.tools}")
            else:
                lines.append(f" - {name}{protected}\ttools:{config.tools}")
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
        session = SubAgentManager._get_or_create_session(session_id)
        if name not in session.subagents:
            return f"Error: Subagent {name} not found. Available subagents: {session.subagents.keys()}"
        SubAgentManager.protect_subagent(session_id, name)
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
        session = SubAgentManager.get_session(session_id)
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
        reset_status = SubAgentManager.clear_subagent_history(session_id, name)
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
        add_status = SubAgentManager.add_shared_context(
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
    description: str = """Send a message to the shared context that will be visible to all subagents.
Use this to share information, status updates, or coordinate with other agents.
If you want to send a result to the main agent, do not use this tool, just return the results directly.
"""
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "context_type": {
                    "type": "string",
                    "description": "Type of context: `status` (your current task progress), `message` (to other agents)",
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
                    "description": "Target agent name or 'all' for broadcast.",
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
        add_status = SubAgentManager.add_shared_context(
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
        shared_context = SubAgentManager.get_shared_context(session_id)

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
- timeout: Maximum waiting time (in seconds), default 60
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
                    "default": 60,
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
        timeout = kwargs.get("timeout", 60)
        poll_interval = kwargs.get("poll_interval", 5)

        session_id = context.context.event.unified_msg_origin
        session = SubAgentManager.get_session(session_id)

        if not session:
            return "Error: No session found"
        if subagent_name not in session.subagents:
            return f"Error: SubAgent '{subagent_name}' not found. Available: {list(session.subagents.keys())}"

        # 如果没有指定 task_id，尝试获取最新创建的 pending 任务
        if not task_id:
            pending_tasks = SubAgentManager.get_pending_subagent_tasks(
                session_id, subagent_name
            )
            if pending_tasks:
                # 使用最新的 pending 任务
                task_id = pending_tasks[-1]
            else:
                # 没有 pending 任务，检查是否有已完成的最新任务
                latest = SubAgentManager.get_subagent_result(session_id, subagent_name)
                if latest:
                    return f"SubAgent '{subagent_name}' has no pending tasks. Latest completed task id: {latest.task_id}. Task id {latest.task_id} Results:\n{latest.result}"
                return f"Error: SubAgent '{subagent_name}' has no tasks."
        start_time = time.time()

        while time.time() - start_time < timeout:
            session = SubAgentManager.get_session(session_id)
            if not session:
                return "Error: Session Not Found"
            if subagent_name not in session.subagents:
                return (
                    f"Error: SubAgent '{subagent_name}' not found. It may be removed."
                )

            status = SubAgentManager.get_subagent_status(session_id, subagent_name)

            if status == "IDLE":
                return f"Error: SubAgent '{subagent_name}' is running no tasks."
            elif status == "COMPLETED":
                result = SubAgentManager.get_subagent_result(
                    session_id, subagent_name, task_id
                )
                if result and (result.result != "" or result.completed_at > 0):
                    return f"SubAgent '{result.agent_name}' execution completed\n Task id: {result.task_id}\n Execution time: {result.execution_time:.1f}s\n--- Result ---\n{result.result}\n"
                else:
                    return f"SubAgent '{subagent_name}' task {task_id} execution completed with empty results."
            elif status == "FAILED":
                result = SubAgentManager.get_subagent_result(
                    session_id, subagent_name, task_id
                )
                if result and (result.result != "" or result.completed_at > 0):
                    return (
                        f"SubAgent '{result.agent_name}' execution failed\n"
                        f"Task id: {result.task_id}\n"
                        f"Execution time: {result.execution_time:.1f}s\n"
                        f"Error: {result.error or 'Unknown error'}\n"
                    )
                else:
                    return f"SubAgent '{subagent_name}' failed task {task_id} with empty results. Error: {result.error or 'Unknown error'}"
            else:
                pass

            await asyncio.sleep(poll_interval)

        target = f"Task {task_id}"
        return f" Timeout! \nSubAgent '{subagent_name}' has not finished '{target}' in {timeout}s. The task may be still running. You can continue waiting by `wait_for_subagent` again."


# Tool instances
CREATE_SUBAGENT_TOOL = CreateSubAgentTool()
REMOVE_SUBAGENT_TOOL = RemoveSubagentTool()
LIST_SUBAGENTS_TOOL = ListSubagentsTool()
RESET_SUBAGENT_TOOL = ResetSubAgentTool()
PROTECT_SUBAGENT_TOOL = ProtectSubagentTool()
UNPROTECT_SUBAGENT_TOOL = UnprotectSubagentTool()
SEND_SHARED_CONTEXT_TOOL = SendSharedContextTool()
SEND_SHARED_CONTEXT_TOOL_FOR_MAIN_AGENT = SendSharedContextToolForMainAgent()
VIEW_SHARED_CONTEXT_TOOL = ViewSharedContextTool()
WAIT_FOR_SUBAGENT_TOOL = WaitForSubagentTool()
