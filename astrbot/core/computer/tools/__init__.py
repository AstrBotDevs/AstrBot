"""Backward-compatible computer tool exports.

Concrete sandbox provider implementations live in plugins. Core keeps only
generic local/sandbox tools plus inactive provider-specific placeholders for
legacy imports and WebUI registration.
"""

from dataclasses import dataclass, field

from astrbot.api import FunctionTool
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.tools.computer_tools.fs import (
    FileDownloadTool,
    FileEditTool,
    FileReadTool,
    FileUploadTool,
    FileWriteTool,
    GrepTool,
)
from astrbot.core.tools.computer_tools.python import LocalPythonTool, PythonTool
from astrbot.core.tools.computer_tools.sandbox import (
    CopyFileBetweenSandboxesTool,
    CreateSandboxTool,
    DestroySandboxTool,
    GetCurrentSandboxTool,
    KeepAliveSandboxTool,
    ListSandboxesTool,
    ListSandboxProvidersTool,
    ReleaseSandboxTool,
    ScreenshotSandboxTool,
    SetSandboxRetentionPolicyTool,
    SwitchSandboxTool,
    TakeoverSandboxTool,
)
from astrbot.core.tools.computer_tools.shell import ExecuteShellTool


@dataclass
class _ProviderSpecificPlaceholderTool(FunctionTool[AstrAgentContext]):
    active: bool = False
    sandbox_provider_id: str = "shipyard_neo"
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {},
        },
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        **kwargs,
    ) -> ToolExecResult:
        return (
            f"Tool '{self.name}' is provided by sandbox provider plugin "
            f"'{self.sandbox_provider_id}', but that plugin is not loaded."
        )


@dataclass
class BrowserExecTool(_ProviderSpecificPlaceholderTool):
    name: str = "astrbot_execute_browser"
    description: str = "Execute one browser automation command in a provider sandbox."


@dataclass
class BrowserBatchExecTool(_ProviderSpecificPlaceholderTool):
    name: str = "astrbot_execute_browser_batch"
    description: str = "Execute browser automation commands in a provider sandbox."


@dataclass
class RunBrowserSkillTool(_ProviderSpecificPlaceholderTool):
    name: str = "astrbot_run_browser_skill"
    description: str = "Run a browser skill in a provider sandbox."


@dataclass
class GetExecutionHistoryTool(_ProviderSpecificPlaceholderTool):
    name: str = "astrbot_get_execution_history"
    description: str = "Get execution history from a provider sandbox."


@dataclass
class AnnotateExecutionTool(_ProviderSpecificPlaceholderTool):
    name: str = "astrbot_annotate_execution"
    description: str = "Annotate execution history in a provider sandbox."


@dataclass
class CreateSkillPayloadTool(_ProviderSpecificPlaceholderTool):
    name: str = "astrbot_create_skill_payload"
    description: str = "Create a skill payload in a provider sandbox."


@dataclass
class GetSkillPayloadTool(_ProviderSpecificPlaceholderTool):
    name: str = "astrbot_get_skill_payload"
    description: str = "Get a skill payload from a provider sandbox."


@dataclass
class CreateSkillCandidateTool(_ProviderSpecificPlaceholderTool):
    name: str = "astrbot_create_skill_candidate"
    description: str = "Create a skill candidate in a provider sandbox."


@dataclass
class ListSkillCandidatesTool(_ProviderSpecificPlaceholderTool):
    name: str = "astrbot_list_skill_candidates"
    description: str = "List skill candidates in a provider sandbox."


@dataclass
class EvaluateSkillCandidateTool(_ProviderSpecificPlaceholderTool):
    name: str = "astrbot_evaluate_skill_candidate"
    description: str = "Evaluate a skill candidate in a provider sandbox."


@dataclass
class PromoteSkillCandidateTool(_ProviderSpecificPlaceholderTool):
    name: str = "astrbot_promote_skill_candidate"
    description: str = "Promote a skill candidate in a provider sandbox."


@dataclass
class ListSkillReleasesTool(_ProviderSpecificPlaceholderTool):
    name: str = "astrbot_list_skill_releases"
    description: str = "List skill releases in a provider sandbox."


@dataclass
class RollbackSkillReleaseTool(_ProviderSpecificPlaceholderTool):
    name: str = "astrbot_rollback_skill_release"
    description: str = "Rollback a skill release in a provider sandbox."


@dataclass
class SyncSkillReleaseTool(_ProviderSpecificPlaceholderTool):
    name: str = "astrbot_sync_skill_release"
    description: str = "Sync a skill release in a provider sandbox."


__all__ = [
    "AnnotateExecutionTool",
    "BrowserBatchExecTool",
    "BrowserExecTool",
    "CopyFileBetweenSandboxesTool",
    "CreateSandboxTool",
    "CreateSkillCandidateTool",
    "CreateSkillPayloadTool",
    "DestroySandboxTool",
    "EvaluateSkillCandidateTool",
    "ExecuteShellTool",
    "FileDownloadTool",
    "FileEditTool",
    "FileReadTool",
    "FileUploadTool",
    "FileWriteTool",
    "GetCurrentSandboxTool",
    "GetExecutionHistoryTool",
    "GetSkillPayloadTool",
    "GrepTool",
    "KeepAliveSandboxTool",
    "ListSandboxProvidersTool",
    "ListSandboxesTool",
    "ListSkillCandidatesTool",
    "ListSkillReleasesTool",
    "LocalPythonTool",
    "PromoteSkillCandidateTool",
    "PythonTool",
    "ReleaseSandboxTool",
    "RollbackSkillReleaseTool",
    "RunBrowserSkillTool",
    "ScreenshotSandboxTool",
    "SetSandboxRetentionPolicyTool",
    "SwitchSandboxTool",
    "SyncSkillReleaseTool",
    "TakeoverSandboxTool",
]
