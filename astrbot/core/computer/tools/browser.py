import json
from dataclasses import dataclass, field
from typing import Any

from astrbot.api import FunctionTool
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext

from ..computer_client import get_booter


def _to_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _ensure_admin(context: ContextWrapper[AstrAgentContext]) -> str | None:
    if context.context.event.role != "admin":
        return (
            "error: Permission denied. Browser and skill lifecycle tools are only allowed "
            "for admin users."
        )
    return None


async def _get_browser_component(context: ContextWrapper[AstrAgentContext]) -> Any:
    booter = await get_booter(
        context.context.context,
        context.context.event.unified_msg_origin,
    )
    browser = getattr(booter, "browser", None)
    if browser is None:
        raise RuntimeError(
            "Current sandbox booter does not support browser capability. "
            "Please switch to shipyard_neo."
        )
    return browser


@dataclass
class BrowserExecTool(FunctionTool):
    name: str = "astrbot_execute_browser"
    description: str = "Execute one browser automation command in the sandbox."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "cmd": {"type": "string", "description": "Browser command to execute."},
                "timeout": {"type": "integer", "default": 30},
                "description": {
                    "type": "string",
                    "description": "Optional execution description.",
                },
                "tags": {"type": "string", "description": "Optional tags."},
                "learn": {
                    "type": "boolean",
                    "description": "Whether to mark execution as learn evidence.",
                    "default": False,
                },
                "include_trace": {
                    "type": "boolean",
                    "description": "Whether to include trace_ref in response.",
                    "default": False,
                },
            },
            "required": ["cmd"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        cmd: str,
        timeout: int = 30,
        description: str | None = None,
        tags: str | None = None,
        learn: bool = False,
        include_trace: bool = False,
    ) -> ToolExecResult:
        if err := _ensure_admin(context):
            return err
        try:
            browser = await _get_browser_component(context)
            result = await browser.exec(
                cmd=cmd,
                timeout=timeout,
                description=description,
                tags=tags,
                learn=learn,
                include_trace=include_trace,
            )
            return _to_json(result)
        except Exception as e:
            return f"Error executing browser command: {str(e)}"


@dataclass
class BrowserBatchExecTool(FunctionTool):
    name: str = "astrbot_execute_browser_batch"
    description: str = "Execute a browser command batch in the sandbox."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "commands": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ordered browser commands.",
                },
                "timeout": {"type": "integer", "default": 60},
                "stop_on_error": {"type": "boolean", "default": True},
                "description": {
                    "type": "string",
                    "description": "Optional execution description.",
                },
                "tags": {"type": "string", "description": "Optional tags."},
                "learn": {
                    "type": "boolean",
                    "description": "Whether to mark execution as learn evidence.",
                    "default": False,
                },
                "include_trace": {
                    "type": "boolean",
                    "description": "Whether to include trace_ref in response.",
                    "default": False,
                },
            },
            "required": ["commands"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        commands: list[str],
        timeout: int = 60,
        stop_on_error: bool = True,
        description: str | None = None,
        tags: str | None = None,
        learn: bool = False,
        include_trace: bool = False,
    ) -> ToolExecResult:
        if err := _ensure_admin(context):
            return err
        try:
            browser = await _get_browser_component(context)
            result = await browser.exec_batch(
                commands=commands,
                timeout=timeout,
                stop_on_error=stop_on_error,
                description=description,
                tags=tags,
                learn=learn,
                include_trace=include_trace,
            )
            return _to_json(result)
        except Exception as e:
            return f"Error executing browser batch command: {str(e)}"


@dataclass
class RunBrowserSkillTool(FunctionTool):
    name: str = "astrbot_run_browser_skill"
    description: str = "Run a released browser skill in the sandbox by skill_key."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "skill_key": {"type": "string"},
                "timeout": {"type": "integer", "default": 60},
                "stop_on_error": {"type": "boolean", "default": True},
                "include_trace": {"type": "boolean", "default": False},
                "description": {"type": "string"},
                "tags": {"type": "string"},
            },
            "required": ["skill_key"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        skill_key: str,
        timeout: int = 60,
        stop_on_error: bool = True,
        include_trace: bool = False,
        description: str | None = None,
        tags: str | None = None,
    ) -> ToolExecResult:
        if err := _ensure_admin(context):
            return err
        try:
            browser = await _get_browser_component(context)
            result = await browser.run_skill(
                skill_key=skill_key,
                timeout=timeout,
                stop_on_error=stop_on_error,
                include_trace=include_trace,
                description=description,
                tags=tags,
            )
            return _to_json(result)
        except Exception as e:
            return f"Error running browser skill: {str(e)}"
