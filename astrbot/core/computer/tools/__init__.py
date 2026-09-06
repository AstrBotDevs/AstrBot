"""Stub module for backward compatibility.

The canonical computer tools are now in:
- astrbot.core.tools.computer_tools.shell (ExecuteShellTool)
- astrbot.core.tools.computer_tools.python (PythonTool, LocalPythonTool)
- astrbot.core.tools.computer_tools.fs (FileUploadTool, FileDownloadTool)
- astrbot.core.tools.computer_tools.shipyard_neo.browser (BrowserExecTool, etc.)
- astrbot.core.tools.computer_tools.shipyard_neo.neo_skills (Neo skill tools)

This module exists only for any legacy imports that may still reference it.
"""

from astrbot.core.tools.computer_tools.fs import FileDownloadTool, FileUploadTool
from astrbot.core.tools.computer_tools.python import LocalPythonTool, PythonTool
from astrbot.core.tools.computer_tools.shell import ExecuteShellTool
from astrbot.core.tools.computer_tools.shipyard_neo.browser import (
    BrowserBatchExecTool,
    BrowserExecTool,
    RunBrowserSkillTool,
)
from astrbot.core.tools.computer_tools.shipyard_neo.neo_skills import (
    AnnotateExecutionTool,
    CreateSkillCandidateTool,
    CreateSkillPayloadTool,
    EvaluateSkillCandidateTool,
    GetExecutionHistoryTool,
    GetSkillPayloadTool,
    ListSkillCandidatesTool,
    ListSkillReleasesTool,
    PromoteSkillCandidateTool,
    RollbackSkillReleaseTool,
    SyncSkillReleaseTool,
)

__all__ = [
    "AnnotateExecutionTool",
    "BrowserBatchExecTool",
    "BrowserExecTool",
    "CreateSkillCandidateTool",
    "CreateSkillPayloadTool",
    "EvaluateSkillCandidateTool",
    "ExecuteShellTool",
    "FileDownloadTool",
    "FileUploadTool",
    "GetExecutionHistoryTool",
    "GetSkillPayloadTool",
    "ListSkillCandidatesTool",
    "ListSkillReleasesTool",
    "LocalPythonTool",
    "PromoteSkillCandidateTool",
    "PythonTool",
    "RollbackSkillReleaseTool",
    "RunBrowserSkillTool",
    "SyncSkillReleaseTool",
]
