"""Filesystem tool audit.

Tool exposure from the main agent:
- Local runtime exposes `astrbot_read_file_tool`, `astrbot_file_edit_tool`,
  and `astrbot_grep_tool`.
- Sandbox runtime exposes `astrbot_upload_file`, `astrbot_download_file`,
  `astrbot_read_file_tool`, `astrbot_file_edit_tool`, and `astrbot_grep_tool`.

Behavior when `provider_settings.computer_use_require_admin=True`:
- Admin + local: read/edit/grep are not path-restricted by this module; access
  depends on the local runtime implementation and host OS permissions. Upload
  and download tools are defined here, but `LocalBooter` does not implement
  them and the main agent does not expose them in local mode.
- Member + local: read/edit/grep are restricted to `data/skills`,
  `data/workspaces/{normalized_umo}`, and `/tmp/.astrbot`. Upload/download are
  denied by `check_admin_permission` if invoked.
- Admin + sandbox: read/edit/grep are not path-restricted by this module;
  sandbox filesystem boundaries are enforced by the sandbox runtime. Upload and
  download are allowed.
- Member + sandbox: read/edit/grep are also not path-restricted by this module.
  Upload/download are denied by `check_admin_permission` if invoked.

When `computer_use_require_admin=False`, member behavior in this module matches
admin behavior.
"""

import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from astrbot.api import FunctionTool, logger
from astrbot.api.event import MessageChain
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.message.components import File
from astrbot.core.utils.astrbot_path import (
    get_astrbot_skills_path,
    get_astrbot_temp_path,
    get_astrbot_workspaces_path,
)

from ..computer_client import get_booter
from .permissions import check_admin_permission


def _normalize_umo_for_workspace(umo: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", umo.strip())
    return normalized or "unknown"


def _restricted_env_path_labels(umo: str) -> list[str]:
    """Labels for the allowed directories in a local(not sandbox) and restricted(not admin) environment"""
    normalized_umo = _normalize_umo_for_workspace(umo)
    return [
        "data/skills",
        f"data/workspaces/{normalized_umo}",
        "/tmp/.astrbot",
    ]


def _read_allowed_roots(umo: str) -> tuple[Path, ...]:
    """Non-admin users can only read files within these directories (and their subdirectories)"""
    normalized_umo = _normalize_umo_for_workspace(umo)
    return (
        Path(get_astrbot_skills_path()).resolve(strict=False),
        (Path(get_astrbot_workspaces_path()) / normalized_umo).resolve(strict=False),
        Path("/tmp/.astrbot").resolve(strict=False),
    )


def _is_restricted_env(context: ContextWrapper[AstrAgentContext]) -> bool:
    cfg = context.context.context.get_config(
        umo=context.context.event.unified_msg_origin
    )
    provider_settings = cfg.get("provider_settings", {})
    runtime = str(provider_settings.get("computer_use_runtime", "local"))
    if runtime != "local":
        return False
    require_admin = provider_settings.get("computer_use_require_admin", True)
    return require_admin and context.context.event.role != "admin"


def _resolve_user_path(path: str) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve(strict=False)
    return (Path.cwd() / candidate).resolve(strict=False)


def _is_path_within_allowed_roots(path: str, umo: str) -> bool:
    resolved = _resolve_user_path(path)
    return any(
        resolved == allowed_root or resolved.is_relative_to(allowed_root)
        for allowed_root in _read_allowed_roots(umo)
    )


def _normalize_search_paths(
    path: str | None,
    *,
    restricted: bool,
    umo: str,
) -> list[str]:
    normalized = [path] if path else []
    if not normalized:
        return _restricted_env_path_labels(umo) if restricted else ["."]

    if restricted:
        disallowed = [
            path for path in normalized if not _is_path_within_allowed_roots(path, umo)
        ]
        if disallowed:
            allowed = ", ".join(_restricted_env_path_labels(umo))
            blocked = ", ".join(disallowed)
            raise PermissionError(
                "Read access is restricted for this user. "
                f"Allowed directories: {allowed}. Blocked paths: {blocked}."
            )

    return normalized


def _normalize_read_path(
    path: str,
    *,
    restricted: bool,
    umo: str,
) -> str:
    normalized_path = path.strip()
    if not normalized_path:
        raise ValueError("`path` must be a non-empty string.")
    if restricted and not _is_path_within_allowed_roots(normalized_path, umo):
        allowed = ", ".join(_restricted_env_path_labels(umo))
        raise PermissionError(
            "Read access is restricted for this user. "
            f"Allowed directories: {allowed}. Blocked path: {normalized_path}."
        )
    return normalized_path


def _resolve_context_options(
    after_context: int | None,
    before_context: int | None,
    context: int | None,
) -> tuple[int | None, int | None]:
    if context is not None and context < 0:
        raise ValueError("`-C` must be greater than or equal to 0.")
    if after_context is not None and after_context < 0:
        raise ValueError("`-A` must be greater than or equal to 0.")
    if before_context is not None and before_context < 0:
        raise ValueError("`-B` must be greater than or equal to 0.")

    resolved_after = context if after_context is None else after_context
    resolved_before = context if before_context is None else before_context
    return resolved_after, resolved_before


def _split_output_groups(output: str, *, has_context: bool) -> list[str]:
    if not output.strip():
        return []

    if not has_context:
        return [f"{line}\n" for line in output.splitlines() if line.strip()]

    groups: list[str] = []
    current: list[str] = []

    for line in output.splitlines(keepends=True):
        if line.strip() == "--":
            if current:
                groups.append("".join(current))
                current = []
            continue
        if not line.strip():
            continue
        current.append(line)

    if current:
        groups.append("".join(current))
    return groups


def _apply_result_limit(
    output: str,
    *,
    result_limit: int,
    has_context: bool,
) -> str:
    if result_limit < 1:
        raise ValueError("`result_limit` must be greater than or equal to 1.")

    groups = _split_output_groups(output, has_context=has_context)
    if len(groups) <= result_limit:
        return output if output.strip() else "No matches found."

    limited_output = "".join(groups[:result_limit]).rstrip()
    return f"{limited_output}\n\n[Truncated to first {result_limit} result groups.]"


def _validate_read_window(
    offset: int | None,
    limit: int | None,
) -> tuple[int | None, int | None]:
    if offset is not None and offset < 0:
        raise ValueError("`offset` must be greater than or equal to 0.")
    if limit is not None and limit < 1:
        raise ValueError("`limit` must be greater than or equal to 1.")
    return offset, limit


@dataclass
class ReadFileTool(FunctionTool):
    name: str = "astrbot_read_file_tool"
    description: str = "read file content."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path of the file to read.",
                },
                "offset": {
                    "type": "integer",
                    "description": "Character offset to start reading from. Defaults to 0.",
                    "minimum": 0,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of characters to read. Defaults to 4000.",
                    "minimum": 1,
                },
            },
            "required": ["path"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        path: str,
        offset: int | None = None,
        limit: int | None = None,
    ) -> ToolExecResult:
        restricted = _is_restricted_env(context)
        try:
            normalized_path = _normalize_read_path(
                path,
                restricted=restricted,
                umo=context.context.event.unified_msg_origin,
            )
            offset, limit = _validate_read_window(offset, limit)
            sb = await get_booter(
                context.context.context,
                context.context.event.unified_msg_origin,
            )
            result = await sb.fs.read_file(
                path=normalized_path,
                encoding="utf-8",
                offset=offset,
                limit=limit,
            )
            if not result.get("success", False):
                error_detail = str(result.get("error", "") or "").strip()
                return (
                    "Error reading file: "
                    f"{error_detail or 'unknown filesystem read error'}"
                )

            content = str(result.get("content", "") or "")
            if not content:
                return "No content found at the requested offset."
            return content or ""
        except PermissionError as exc:
            return f"Error: {exc}"
        except Exception as exc:
            logger.error(f"Error reading file: {exc}")
            return f"Error reading file: {exc}"


@dataclass
class FileEditTool(FunctionTool):
    name: str = "astrbot_file_edit_tool"
    description: str = "Editing files."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path of the file to edit.",
                },
                "old": {
                    "type": "string",
                    "description": "The exact old text to replace.",
                },
                "new": {
                    "type": "string",
                    "description": "The replacement text.",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Whether to replace all matches. Defaults to false.",
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
        restricted = _is_restricted_env(context)
        try:
            normalized_path = _normalize_read_path(
                path,
                restricted=restricted,
                umo=umo,
            )
            sb = await get_booter(
                context.context.context,
                context.context.event.unified_msg_origin,
            )
            result = await sb.fs.edit_file(
                path=normalized_path,
                old_string=old,
                new_string=new,
                replace_all=replace_all,
                encoding="utf-8",
            )
            if not result.get("success", False):
                error_detail = str(result.get("error", "") or "").strip()
                return (
                    "Error editing file: "
                    f"{error_detail or 'unknown filesystem edit error'}"
                )
            replacements = int(result.get("replacements", 0) or 0)
            mode_text = "all matches" if replace_all else "first match"
            return (
                f"Edited {normalized_path}. "
                f"Replaced {replacements} occurrence(s) using {mode_text} mode."
            )
        except PermissionError as exc:
            return f"Error: {exc}"
        except Exception as exc:
            logger.error(f"Error editing file: {exc}")
            return f"Error editing file: {exc}"


@dataclass
class GrepTool(FunctionTool):
    name: str = "astrbot_grep_tool"
    description: str = "Search and read file contents using ripgrep."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "The expression pattern to search for in file contents.",
                },
                "path": {
                    "type": "string",
                    "description": "File or directory to search in (rg PATH).",
                },
                "glob": {
                    "type": "string",
                    "description": "Optional glob filter such as `*.py`, `*.{ts,tsx}`.",
                },
                "-A": {
                    "type": "integer",
                    "description": "Number of trailing context lines to include after each match.",
                    "minimum": 0,
                },
                "-B": {
                    "type": "integer",
                    "description": "Number of leading context lines to include before each match.",
                    "minimum": 0,
                },
                "-C": {
                    "type": "integer",
                    "description": "Number of leading and trailing context lines to include around each match.",
                    "minimum": 0,
                },
                "result_limit": {
                    "type": "integer",
                    "description": "Maximum number of result groups returned by the tool. Defaults to 50.",
                    "minimum": 1,
                },
            },
            "required": ["pattern"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        result_limit: int = 50,
        **kwargs,
    ) -> ToolExecResult:
        normalized_pattern = pattern.strip()
        if not normalized_pattern:
            return "Error: `pattern` must be a non-empty string."

        restricted = _is_restricted_env(context)
        try:
            search_paths = _normalize_search_paths(
                path,
                restricted=restricted,
                umo=context.context.event.unified_msg_origin,
            )
            after_context, before_context = _resolve_context_options(
                kwargs.get("-A"),
                kwargs.get("-B"),
                kwargs.get("-C"),
            )
            has_context = (after_context or 0) > 0 or (before_context or 0) > 0
            sb = await get_booter(
                context.context.context,
                context.context.event.unified_msg_origin,
            )
            contents: list[str] = []
            for search_path in search_paths:
                result = await sb.fs.search_files(
                    pattern=normalized_pattern,
                    path=search_path,
                    glob=glob,
                    after_context=after_context,
                    before_context=before_context,
                )
                if not result.get("success", False):
                    error_detail = str(result.get("error", "") or "").strip()
                    logger.error("GrepTool search failed: %s", error_detail)
                    return (
                        "Error searching files: "
                        f"{error_detail or 'unknown filesystem search error'}"
                    )
                content = str(result.get("content", "") or "")
                if content:
                    contents.append(content)

            return _apply_result_limit(
                "".join(contents),
                result_limit=result_limit,
                has_context=has_context,
            )
        except PermissionError as exc:
            return f"Error: {exc}"
        except Exception as exc:
            logger.error(f"Error searching files: {exc}")
            return f"Error searching files: {exc}"


@dataclass
class FileUploadTool(FunctionTool):
    name: str = "astrbot_upload_file"
    description: str = (
        "Transfer a file FROM the host machine INTO the sandbox so that sandbox "
        "code can access it. Use this when the user sends/attaches a file and you "
        "need to process it inside the sandbox. The local_path must point to an "
        "existing file on the host filesystem."
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "local_path": {
                    "type": "string",
                    "description": "Absolute path to the file on the host filesystem that will be copied into the sandbox.",
                },
                # "remote_path": {
                #     "type": "string",
                #     "description": "The filename to use in the sandbox. If not provided, file will be saved to the working directory with the same name as the local file.",
                # },
            },
            "required": ["local_path"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        local_path: str,
    ) -> str | None:
        if permission_error := check_admin_permission(context, "File upload/download"):
            return permission_error
        sb = await get_booter(
            context.context.context,
            context.context.event.unified_msg_origin,
        )
        try:
            # Check if file exists
            if not os.path.exists(local_path):
                return f"Error: File does not exist: {local_path}"

            if not os.path.isfile(local_path):
                return f"Error: Path is not a file: {local_path}"

            # Use basename if sandbox_filename is not provided
            remote_path = os.path.basename(local_path)

            # Upload file to sandbox
            result = await sb.upload_file(local_path, remote_path)
            logger.debug(f"Upload result: {result}")
            success = result.get("success", False)

            if not success:
                return f"Error uploading file: {result.get('message', 'Unknown error')}"

            file_path = result.get("file_path", "")
            logger.info(f"File {local_path} uploaded to sandbox at {file_path}")

            return f"File uploaded successfully to {file_path}"
        except Exception as e:
            logger.error(f"Error uploading file {local_path}: {e}")
            return f"Error uploading file: {str(e)}"


@dataclass
class FileDownloadTool(FunctionTool):
    name: str = "astrbot_download_file"
    description: str = (
        "Transfer a file FROM the sandbox OUT to the host and optionally send it "
        "to the user. Use this ONLY when the user asks to retrieve/export a file "
        "that was created or modified inside the sandbox."
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "remote_path": {
                    "type": "string",
                    "description": "Path of the file inside the sandbox to copy out to the host.",
                },
                "also_send_to_user": {
                    "type": "boolean",
                    "description": "Whether to also send the downloaded file to the user via message. Defaults to true.",
                },
            },
            "required": ["remote_path"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        remote_path: str,
        also_send_to_user: bool = True,
    ) -> ToolExecResult:
        if permission_error := check_admin_permission(context, "File upload/download"):
            return permission_error
        sb = await get_booter(
            context.context.context,
            context.context.event.unified_msg_origin,
        )
        try:
            name = os.path.basename(remote_path)

            local_path = os.path.join(
                get_astrbot_temp_path(), f"sandbox_{uuid.uuid4().hex[:4]}_{name}"
            )

            # Download file from sandbox
            await sb.download_file(remote_path, local_path)
            logger.info(f"File {remote_path} downloaded from sandbox to {local_path}")

            if also_send_to_user:
                try:
                    name = os.path.basename(local_path)
                    await context.context.event.send(
                        MessageChain(chain=[File(name=name, file=local_path)])
                    )
                except Exception as e:
                    logger.error(f"Error sending file message: {e}")

                # remove
                # try:
                #     os.remove(local_path)
                # except Exception as e:
                #     logger.error(f"Error removing temp file {local_path}: {e}")

                return f"File downloaded successfully to {local_path} and sent to user."

            return f"File downloaded successfully to {local_path}"
        except Exception as e:
            logger.error(f"Error downloading file {remote_path}: {e}")
            return f"Error downloading file: {str(e)}"
