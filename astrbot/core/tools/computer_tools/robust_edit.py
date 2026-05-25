"""
Enhanced FileEditTool for AstrBot with robust multi-strategy matching.

This tool registers as `astrbot_robust_file_edit_tool` (distinct from the
default `astrbot_file_edit_tool`), and is inspired by opencode's edit tool.
It features:
- 9-layer fuzzy replacer chain (exact → escape-normalized → line-trimmed → block-anchor → whitespace-normalized → indentation-flexible → trimmed-boundary → context-aware → multi-occurrence)
- File-level asyncio locks to prevent concurrent edits
- BOM and line-ending preservation
- Unified diff output for transparency

Author: AstrBot Agent Harness Development Expert
Date: 2026-05-18 (refactored)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from astrbot.api import FunctionTool, logger
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext

from .fs import (
    _is_restricted_env,
    _normalize_rw_path,
    _COMPUTER_RUNTIME_TOOL_CONFIG,
)
from .util import is_local_runtime
from ..registry import builtin_tool
from .robust_edit_engine import edit_file


@builtin_tool(config=_COMPUTER_RUNTIME_TOOL_CONFIG)
@dataclass
class RobustFileEditTool(FunctionTool):
    """
    Enhanced file editing tool with robust fuzzy matching.

    This tool is designed to handle LLM-generated edits that may have minor
    whitespace, indentation, or escape sequence differences from the actual
    file content. It tries 9 different matching strategies in order of
    specificity before giving up.
    """

    name: str = "robust_file_edit_tool"
    description: str = (
        "Editing files with robust fuzzy matching. "
        "Supports exact match, escape-normalized match, line-trimmed match, block-anchor match, "
        "whitespace-normalized match, indentation-flexible match, "
        "trimmed-boundary match, context-aware match, "
        "and multi-occurrence replacement. "
        "When editing text from Read tool output, preserve the exact indentation "
        "(tabs/spaces) as it appears AFTER the line number prefix. "
        "The line number prefix format is: line number + colon + space (e.g., '1: '). "
        "Everything after that space is the actual file content to match. "
        "Never include any part of the line number prefix in oldString or newString. "
        "The edit will FAIL if oldString is not found. "
        "The edit will FAIL if oldString is found multiple times and replace_all is false. "
        "Use replace_all for renaming variables or strings across the file."
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Path of the file to edit. If relative, will be in workspace root."
                    ),
                },
                "old": {
                    "type": "string",
                    "description": (
                        "The text to replace. Must be an exact substring of the file content, "
                        "but the tool will try multiple matching strategies if exact match fails. "
                        "Include sufficient surrounding context (3-5 lines) to make the match unique."
                    ),
                },
                "new": {
                    "type": "string",
                    "description": "The replacement text.",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": (
                        "Whether to replace all matches. Defaults to false. "
                        "Useful for renaming variables or strings across the file."
                    ),
                },
            },
            "required": ["path", "old", "new"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        path: str,
        old: str,
        new: str,
        replace_all: bool = False,
    ) -> ToolExecResult:
        umo = str(context.context.event.unified_msg_origin)
        local_env = is_local_runtime(context)
        restricted = _is_restricted_env(context)

        try:
            # Resolve path
            if local_env:
                normalized_path = _normalize_rw_path(
                    path,
                    restricted=restricted,
                    local_env=local_env,
                    umo=umo,
                    write=True,
                )
            else:
                normalized_path = path.strip()

            if not normalized_path:
                raise ValueError("`path` must be a non-empty string.")

            # Note: We do NOT call _decode_escaped_text here anymore.
            # The robust_edit_engine now handles escape sequences internally
            # via its _escape_normalized_replacer, which avoids double-decoding
            # issues and provides more comprehensive escape handling.

            # Use robust edit engine
            result = await edit_file(
                path=normalized_path,
                old_string=old,
                new_string=new,
                replace_all=replace_all,
                encoding="utf-8",
            )

            if not result.success:
                return f"Error editing file: {result.error}"

            mode_text = "all matches" if replace_all else "first match"
            replacements = result.replacements

            # Build response with diff preview
            lines = [
                f"Edited {normalized_path}.",
                f"Replaced {replacements} occurrence(s) using {mode_text} mode.",
            ]

            if result.diff:
                lines.append("")
                lines.append("Diff:")
                lines.append("```diff")
                # Truncate diff if too long for token efficiency
                diff_preview = result.diff
                if len(diff_preview) > 2000:
                    diff_preview = diff_preview[:2000] + "\n... (diff truncated)"
                lines.append(diff_preview)
                lines.append("```")

            return "\n".join(lines)

        except PermissionError as exc:
            return f"Error: {exc}"
        except Exception as exc:
            logger.error(f"Error editing file: {exc}")
            return f"Error editing file: {exc}"
