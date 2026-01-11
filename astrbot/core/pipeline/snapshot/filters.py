from __future__ import annotations

from typing import Any

from astrbot.core.pipeline.snapshot.utils import compose_command
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.filter.permission import PermissionTypeFilter
from astrbot.core.star.filter.regex import RegexFilter
from astrbot.core.star.star_handler import StarHandlerMetadata


def _permission_from_filters(handler: StarHandlerMetadata) -> str | None:
    for f in handler.event_filters:
        if isinstance(f, PermissionTypeFilter):
            # PermissionTypeFilter.permission_type 是 enum.Flag；以字符串末尾判断避免引入更多枚举依赖
            return (
                "admin"
                if str(getattr(f, "permission_type", "")).endswith("ADMIN")
                else "member"
            )
    return None


def summarize_filters(
    handler: StarHandlerMetadata,
) -> tuple[str | None, dict[str, Any] | None, str | None, str | None]:
    """
    Returns:
      - cmd: str | None
      - trigger: HandlerTrigger | None
      - filters_summary: str | None
      - permission: 'everyone' | 'member' | 'admin' | None
    """
    cmd: str | None = None
    trigger: dict[str, Any] | None = None
    parts: list[str] = []

    permission = _permission_from_filters(handler)

    for f in handler.event_filters:
        if isinstance(f, CommandFilter):
            parent = (f.parent_command_names or [""])[0].strip()
            cmd = compose_command(parent, f.command_name).strip()
            trigger_type = (
                "sub_command"
                if bool(handler.extras_configs.get("sub_command"))
                else "command"
            )
            trigger = {
                "type": trigger_type,
                "signature": cmd,
                "extra": {
                    "aliases": sorted(getattr(f, "alias", set())),
                },
            }
            parts.append(f"command={cmd}")
            aliases = sorted(getattr(f, "alias", set()))
            if aliases:
                parts.append(f"alias={','.join(aliases)}")
        elif isinstance(f, CommandGroupFilter):
            names = f.get_complete_command_names()
            cmd = (names[0] if names else f.group_name).strip()
            trigger = {
                "type": "command_group",
                "signature": cmd,
                "extra": {
                    "aliases": sorted(getattr(f, "alias", set())),
                },
            }
            parts.append(f"command_group={cmd}")
        elif isinstance(f, RegexFilter):
            cmd = f.regex_str
            trigger = {"type": "regex", "signature": cmd}
            parts.append(f"regex={f.regex_str}")
        elif isinstance(f, PermissionTypeFilter):
            continue
        else:
            parts.append(type(f).__name__)

    if permission:
        parts.append(f"permission={permission}")

    summary = ", ".join([p for p in parts if p])
    return cmd, trigger, summary or None, permission


__all__ = ["summarize_filters"]
