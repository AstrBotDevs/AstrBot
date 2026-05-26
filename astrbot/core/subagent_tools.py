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
import uuid
from dataclasses import dataclass, field

from astrbot import logger
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.subagent_dag import (
    DAGExecutionContext,
    DAGNodeStatus,
    DAGTaskNode,
    SubAgentDAGEngine,
)
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
        # 验证名称格式：只允许英文字母、数字和下划线，长度限制；避免Windows保留名
        SAFE_IDENTIFIER = re.compile(
            r"^(?!^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$)[a-zA-Z][a-zA-Z0-9_]{0,32}$",
            re.IGNORECASE,
        )
        if not bool(SAFE_IDENTIFIER.match(name)):
            return "Error: SubAgent name must start with letter, contain only letters/numbers/underscores, max 32 characters"

        system_prompt = kwargs.get("system_prompt", "")
        tools = kwargs.get("tools", {})
        skills = kwargs.get("skills", {})
        workdir = kwargs.get("workdir")

        session_id = context.context.event.unified_msg_origin
        if not self._check_path_safety(workdir):
            workdir = None
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
class ManageSubagentProtectionTool(FunctionTool):
    """Tool to protect or unprotect a subagent from auto cleanup"""

    name: str = "manage_subagent_protection"
    description: str = "Protect or unprotect a subagent from automatic cleanup. Use this to prevent important subagents from being removed, or to allow them to be auto cleaned."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Subagent name to manage"},
                "protected": {
                    "type": "boolean",
                    "description": "Whether to protect (true) or unprotect (false) the subagent",
                },
            },
            "required": ["name", "protected"],
        }
    )

    async def call(self, context, **kwargs) -> str:
        name = kwargs.get("name", "")
        protected = kwargs.get("protected", True)
        if not name:
            return "Error: name required"
        session_id = context.context.event.unified_msg_origin
        session = SubAgentManager._get_or_create_session(session_id)
        if name not in session.subagents:
            return f"Error: Subagent {name} not found. Available subagents: {session.subagents.keys()}"
        if protected:
            SubAgentManager.protect_subagent(session_id, name)
            return f"Subagent {name} is now protected from auto cleanup"
        else:
            if name in session.protected_agents:
                session.protected_agents.discard(name)
                return f"Subagent {name} is no longer protected"
            return f"Subagent {name} was not protected"


@dataclass
class ResetSubAgentTool(FunctionTool):
    """Tool to reset a subagent"""

    name: str = "reset_subagent"
    description: str = "Reset an existing subagent. This will clean the dialog history of the subagent. Used before assigning a new task to an existing subagent."
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
class BroadCastSharedContextTool(FunctionTool):
    """Tool to send a message to the shared context (visible to all agents)"""

    name: str = "broadcast_shared_context"
    description: str = (
        """Send a message to one or all subagents when they are running."""
    )
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
    description: str = """Send a message to the shared context that will be visible to other subagents.
Use this to share information, status updates, or coordinate with other subagents.
Not used for informing the main agent, return the results directly instead.
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
        if timeout > 3600 or timeout <= 0:
            return "Error: timeout is invalid. Must be between 1 and 3600"
        poll_interval = kwargs.get("poll_interval", 5)
        if poll_interval > 60 or poll_interval <= 0:
            return "Error: poll_interval is invalid. Must be between 1 and 60"
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
        return f"Timeout! SubAgent '{subagent_name}' has not finished '{target}' in {timeout}s. The task may be still running. You can continue waiting by `wait_for_subagent` again."


@dataclass
class OrchestrateTasksTool(FunctionTool):
    """Orchestrate multiple subagent tasks with DAG dependency management."""

    name: str = "orchestrate_tasks"
    description: str = (
        "Orchestrate multiple subagent tasks with automatic dependency management."
        "  Define tasks with their dependencies and the orchestrator will:"
        " (1) Automatically determine which tasks can run in parallel,"
        " (2) Execute dependent tasks sequentially in waves,"
        " (3) Auto-inject predecessor results as context for successor tasks,"
        " (4) Aggregate all results into a single summary."
        "  Use this when you have 2+ subtasks where some produce output that others"
        " consume. For simple single-agent delegation, use transfer_to_* directly."
    )

    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "description": "List of tasks to orchestrate with dependencies",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": "Unique task ID, e.g. 'step1'",
                            },
                            "agent": {
                                "type": "string",
                                "description": "Target subagent name",
                            },
                            "prompt": {
                                "type": "string",
                                "description": "Task description for the subagent",
                            },
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": (
                                    "IDs of tasks that must complete first. "
                                    "Results auto-injected as context."
                                ),
                            },
                        },
                        "required": ["id", "agent", "prompt"],
                    },
                },
                "max_parallel": {
                    "type": "integer",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 10,
                    "description": "Maximum concurrent subagents",
                },
            },
            "required": ["tasks"],
        }
    )

    async def call(self, context, **kwargs) -> str:
        tasks_data = kwargs.get("tasks", [])
        max_parallel = kwargs.get("max_parallel", 5)
        session_id = context.context.event.unified_msg_origin

        if not tasks_data:
            return "Error: At least one task is required."

        cfg = self._get_dag_config(context)
        max_nodes = cfg.get("dag_max_nodes", 10)
        cfg_max_parallel = cfg.get("dag_max_parallel", 5)

        if len(tasks_data) > max_nodes:
            return f"Error: Maximum {max_nodes} tasks per DAG. Got {len(tasks_data)}."

        max_parallel = min(max_parallel, cfg_max_parallel)

        active_dag = SubAgentManager.get_active_dag(session_id)
        if active_dag and active_dag.status == "RUNNING":
            completed = sum(
                1
                for n in active_dag.nodes.values()
                if n.status == DAGNodeStatus.COMPLETED
            )
            return (
                f"Error: A DAG is already running for this session "
                f"(dag_id={active_dag.dag_id[:8]}..., "
                f"{completed}/{len(active_dag.nodes)} completed)."
            )

        session = SubAgentManager.get_session(session_id)
        if not session:
            return "Error: No session found. Create subagents first."

        nodes: list[DAGTaskNode] = []
        for t in tasks_data:
            agent_name = t.get("agent", "")
            if agent_name not in session.subagents:
                available = list(session.subagents.keys())
                return (
                    f"Error: SubAgent '{agent_name}' not found. Available: {available}"
                )
            node = DAGTaskNode(
                id=t["id"],
                agent_name=agent_name,
                prompt=t["prompt"],
                depends_on=t.get("depends_on", []),
            )
            nodes.append(node)

        valid, error = SubAgentDAGEngine.validate_dag(nodes)
        if not valid:
            return f"Error: Invalid DAG — {error}"

        topo_layers = SubAgentDAGEngine._kahn_sort(nodes)

        node_map = {n.id: n for n in nodes}
        adj: dict[str, set[str]] = {n.id: set() for n in nodes}
        rev_adj: dict[str, set[str]] = {n.id: set() for n in nodes}
        for n in nodes:
            for dep in n.depends_on:
                adj[dep].add(n.id)
                rev_adj[n.id].add(dep)

        dag_ctx = DAGExecutionContext(
            dag_id=uuid.uuid4().hex[:12],
            session_id=session_id,
            nodes=node_map,
            adjacency=adj,
            reverse_adjacency=rev_adj,
            topo_layers=topo_layers,
            fail_fast=True,
            max_parallel=max_parallel,
            created_at=time.time(),
        )

        SubAgentManager.register_dag(session_id, dag_ctx)

        # Build launch callback that actually triggers subagent execution
        tool_context = context  # ContextWrapper[AstrAgentContext]

        async def _launch_dag_node(node, _sid, injected_context, task_id):
            import mcp.types as _mcp_types

            session = SubAgentManager.get_session(_sid)
            if not session or node.agent_name not in session.handoff_tools:
                logger.error(f"[SubAgent:DAG] No handoff tool for {node.agent_name}")
                SubAgentManager.store_subagent_result(
                    _sid,
                    node.agent_name,
                    False,
                    "",
                    task_id=task_id,
                    error=f"No handoff for {node.agent_name}",
                    execution_time=0.0,
                )
                return

            handoff = session.handoff_tools[node.agent_name]
            prompt = node.prompt
            if injected_context:
                ctx_text = injected_context[0]["content"]
                prompt = ctx_text + "Your task:" + chr(10) + prompt

            try:
                from astrbot.core.astr_agent_tool_exec import (
                    FunctionToolExecutor,
                )

                result_text = ""
                async for r in FunctionToolExecutor._execute_handoff(
                    tool=handoff,
                    run_context=tool_context,
                    input=prompt,
                ):
                    if isinstance(r, _mcp_types.CallToolResult):
                        for c in r.content:
                            if isinstance(c, _mcp_types.TextContent):
                                result_text += c.text + chr(10)

                # Detect task status from subagent output.
                # Priority: 1) [TASK RESULT: ...] marker  2) error: prefix  3) empty
                success = True
                error_reason = None
                stripped = result_text.strip()
                status_match = re.search(
                    r"\[TASK\s*RESULT\s*:\s*(SUCCESS|FAILURE)\]",
                    stripped,
                    re.IGNORECASE,
                )
                if status_match:
                    success = status_match.group(1).upper() == "SUCCESS"
                    if not success:
                        # Extract failure reason for concise error reporting
                        reason_match = re.search(
                            r"\[FAILURE\s*REASON\s*:\s*(.+?)\]",
                            stripped,
                            re.IGNORECASE,
                        )
                        if reason_match:
                            error_reason = reason_match.group(1).strip()
                        else:
                            error_reason = "No reason provided"
                elif not stripped or stripped.lower().startswith("error:"):
                    success = False

                SubAgentManager.store_subagent_result(
                    _sid,
                    node.agent_name,
                    success,
                    result_text,
                    task_id=task_id,
                    execution_time=0.0,
                    error=error_reason,
                )
            except Exception as e:
                logger.error(f"[SubAgent:DAG] Launch error for {node.agent_name}: {e}")
                SubAgentManager.store_subagent_result(
                    _sid,
                    node.agent_name,
                    False,
                    "",
                    task_id=task_id,
                    error=str(e),
                    execution_time=0.0,
                )

        try:
            result = await SubAgentDAGEngine.execute_dag(
                ctx=dag_ctx,
                session_id=session_id,
                max_inject_length=cfg.get("dag_max_inject_length", 4000),
                launch_fn=_launch_dag_node,
            )
            dag_ctx.status = "COMPLETED" if result["failed"] == 0 else "FAILED"
            dag_ctx.completed_at = time.time()

            session = SubAgentManager.get_session(session_id)
            if session:
                session.dag_history.append(dag_ctx)
                session.active_dag = None

            return result["formatted"]

        except Exception as e:
            logger.error(f"[SubAgent:DAG] Execution error: {e}", exc_info=True)
            dag_ctx.status = "FAILED"
            dag_ctx.completed_at = time.time()
            session = SubAgentManager.get_session(session_id)
            if session:
                session.dag_history.append(dag_ctx)
                session.active_dag = None
            return f"Error: DAG execution failed — {e}"

    @staticmethod
    def _get_dag_config(context) -> dict:
        try:
            ctx = context.context.context
            cfg = ctx.get_config(umo=context.context.event.unified_msg_origin)
            orch_cfg = cfg.get("subagent_orchestrator", {})
            return {
                "dag_max_nodes": orch_cfg.get("dag_max_nodes", 10),
                "dag_max_parallel": orch_cfg.get("dag_max_parallel", 5),
                "dag_max_inject_length": orch_cfg.get("dag_max_inject_length", 4000),
            }
        except Exception:
            return {
                "dag_max_nodes": 10,
                "dag_max_parallel": 5,
                "dag_max_inject_length": 4000,
            }


ORCHESTRATE_TASKS_TOOL = OrchestrateTasksTool()


# Tool instances
CREATE_SUBAGENT_TOOL = CreateSubAgentTool()
REMOVE_SUBAGENT_TOOL = RemoveSubagentTool()
LIST_SUBAGENTS_TOOL = ListSubagentsTool()
RESET_SUBAGENT_TOOL = ResetSubAgentTool()
MANAGE_SUBAGENT_PROTECTION_TOOL = ManageSubagentProtectionTool()
SEND_SHARED_CONTEXT_TOOL = SendSharedContextTool()
BROADCAST_SHARED_CONTEXT_TOOL = BroadCastSharedContextTool()
VIEW_SHARED_CONTEXT_TOOL = ViewSharedContextTool()
WAIT_FOR_SUBAGENT_TOOL = WaitForSubagentTool()
