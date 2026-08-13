import enum

from astrbot.core.config import AstrBotConfig
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from . import HandlerFilter


class ActionPermissionFilter(HandlerFilter):
    """Declarative command action gate resolved asynchronously by the pipeline."""

    def __init__(self, action: str, raise_error: bool = True) -> None:
        self.action = action
        self.raise_error = raise_error

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        """Synchronous callers must fail closed; pipeline resolves this filter."""

        del event, cfg
        return False


class PermissionType(enum.Flag):
    """权限类型。当选择 MEMBER，ADMIN 也可以通过。"""

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
        """Fail closed outside the action-aware pipeline."""

        del event, cfg
        return self.permission_type == PermissionType.MEMBER

    @property
    def action(self) -> str:
        """Map legacy plugin ADMIN input to a scoped session capability."""

        return "session.manage" if self.permission_type == PermissionType.ADMIN else "session.read"
