"""Session workspace resolution and workspace-provided instructions."""

from __future__ import annotations

from pathlib import Path

from astrbot.core import logger
from astrbot.core.db import BaseDatabase
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.context import Context
from astrbot.core.utils.astrbot_path import get_astrbot_workspaces_path
from astrbot.core.workspace import (
    normalize_umo_for_workspace,
    resolve_workspace_root_for_umo,
)


async def resolve_workspace_path(umo: str, plugin_context: Context) -> Path:
    """Resolve the workspace path for the current request.

    Args:
        umo: Unified message origin.
        plugin_context: Star context containing the database instance.

    Returns:
        Workspace path used as cwd.
    """
    fallback_root = (
        Path(get_astrbot_workspaces_path()) / normalize_umo_for_workspace(umo)
    ).resolve(strict=False)
    db = getattr(plugin_context, "_db", None)
    if not isinstance(db, BaseDatabase):
        return fallback_root
    try:
        return await resolve_workspace_root_for_umo(umo, db)
    except Exception:
        return fallback_root


async def apply_workspace_instructions(
    event: AstrMessageEvent,
    req: ProviderRequest,
    plugin_context: Context,
) -> None:
    """Append the current workspace's EXTRA_PROMPT.md instructions when present.

    Args:
        event: Event identifying the workspace's session.
        req: Request receiving the workspace instructions.
        plugin_context: Workspace resolution services.
    """
    workspace_root = await resolve_workspace_path(
        event.unified_msg_origin,
        plugin_context,
    )
    extra_prompts: list[str] = []
    extra_prompt_path = workspace_root / "EXTRA_PROMPT.md"
    if extra_prompt_path.is_file():
        try:
            extra_prompt = extra_prompt_path.read_text(encoding="utf-8").strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to read workspace extra prompt for umo=%s from %s: %s",
                event.unified_msg_origin,
                extra_prompt_path,
                exc,
            )
        else:
            if extra_prompt:
                extra_prompts.append(f"From `{extra_prompt_path}`:\n{extra_prompt}")

    if not extra_prompts:
        return

    extra_prompt_text = "\n\n".join(extra_prompts)
    req.system_prompt = (
        f"{req.system_prompt or ''}\n"
        "[Workspace Extra Prompt]\n"
        "The following instructions are loaded from the current workspace "
        "`EXTRA_PROMPT.md` file.\n"
        f"{extra_prompt_text}\n"
    )
