import json
from dataclasses import dataclass, field
from typing import Any

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.tools.computer_tools.util import check_admin_permission
from astrbot.core.tools.registry import builtin_tool

_SHIPYARD_NEO_TOOL_CONFIG = {
    "provider_settings.computer_use_runtime": "sandbox",
    "provider_settings.sandbox.booter": "shipyard_neo",
}


def _to_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


async def _get_browser_component(context: ContextWrapper[AstrAgentContext]) -> Any:
    booter = await context.context.context.computer_runtime.get_booter(
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


@builtin_tool(
    config=_SHIPYARD_NEO_TOOL_CONFIG, required_actions=("tool.browser_control",)
)
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
        **kwargs: Any,
    ) -> ToolExecResult:
        cmd: str = kwargs["cmd"]
        timeout_seconds: int = kwargs.get("timeout_seconds", 30)
        description: str | None = kwargs.get("description", None)
        tags: str | None = kwargs.get("tags", None)
        learn: bool = kwargs.get("learn", False)
        include_trace: bool = kwargs.get("include_trace", False)
        if err := await check_admin_permission(context, "Using browser tools"):
            return err
        try:
            browser = await _get_browser_component(context)
            result = await browser.exec(
                cmd=cmd,
                timeout_seconds=timeout_seconds,
                description=description,
                tags=tags,
                learn=learn,
                include_trace=include_trace,
            )
            return _to_json(result)
        except Exception as e:
            return f"Error executing browser command: {str(e)}"


@builtin_tool(
    config=_SHIPYARD_NEO_TOOL_CONFIG, required_actions=("tool.browser_control",)
)
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
        **kwargs: Any,
    ) -> ToolExecResult:
        commands: list[str] = kwargs["commands"]
        timeout_seconds: int = kwargs.get("timeout_seconds", 60)
        stop_on_error: bool = kwargs.get("stop_on_error", True)
        description: str | None = kwargs.get("description", None)
        tags: str | None = kwargs.get("tags", None)
        learn: bool = kwargs.get("learn", False)
        include_trace: bool = kwargs.get("include_trace", False)
        if err := await check_admin_permission(context, "Using browser tools"):
            return err
        try:
            browser = await _get_browser_component(context)
            result = await browser.exec_batch(
                commands=commands,
                timeout_seconds=timeout_seconds,
                stop_on_error=stop_on_error,
                description=description,
                tags=tags,
                learn=learn,
                include_trace=include_trace,
            )
            return _to_json(result)
        except Exception as e:
            return f"Error executing browser batch command: {str(e)}"


@builtin_tool(
    config=_SHIPYARD_NEO_TOOL_CONFIG, required_actions=("tool.browser_control",)
)
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
        **kwargs: Any,
    ) -> ToolExecResult:
        skill_key: str = kwargs["skill_key"]
        timeout_seconds: int = kwargs.get("timeout_seconds", 60)
        stop_on_error: bool = kwargs.get("stop_on_error", True)
        include_trace: bool = kwargs.get("include_trace", False)
        description: str | None = kwargs.get("description", None)
        tags: str | None = kwargs.get("tags", None)
        if err := await check_admin_permission(context, "Using browser tools"):
            return err
        try:
            browser = await _get_browser_component(context)
            result = await browser.run_skill(
                skill_key=skill_key,
                timeout_seconds=timeout_seconds,
                stop_on_error=stop_on_error,
                include_trace=include_trace,
                description=description,
                tags=tags,
            )
            return _to_json(result)
        except Exception as e:
            return f"Error running browser skill: {str(e)}"
