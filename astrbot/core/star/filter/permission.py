import enum

from astrbot.core.config import AstrBotConfig
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from . import HandlerFilter


class PermissionType(enum.Flag):
    """Legacy declaration vocabulary retained only for introspection."""

    ADMIN = enum.auto()
    MEMBER = enum.auto()


class PermissionTypeFilter(HandlerFilter):
    """Deprecated declaration adapter for plugins not yet action-migrated."""

    def __init__(
        self, permission_type: PermissionType, raise_error: bool = True
    ) -> None:
        self.permission_type = permission_type
        self.raise_error = raise_error

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        del event, cfg
        return self.permission_type == PermissionType.MEMBER

    @property
    def action(self) -> str:
        return (
            "session.manage"
            if self.permission_type == PermissionType.ADMIN
            else "session.read"
        )


class ActionPermissionFilter(PermissionTypeFilter):
    """Declarative command action gate resolved asynchronously by the pipeline."""

    def __init__(self, action: str, raise_error: bool = True) -> None:
        self._action = action
        self.raise_error = raise_error

    @property
    def permission_type(self) -> PermissionType:
        """Read-only migration view for callers inspecting old declarations."""
        return (
            PermissionType.ADMIN
            if self._action == "session.manage"
            else PermissionType.MEMBER
        )

    @property
    def action(self) -> str:
        return self._action

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        """Synchronous callers must fail closed; pipeline resolves this filter."""

        del event, cfg
        return False
