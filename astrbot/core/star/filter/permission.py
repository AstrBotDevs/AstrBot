import enum

from astrbot.core.config import AstrBotConfig
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from . import HandlerFilter


class PermissionType(enum.Flag):
    """Command permissions; MEMBER also allows administrators."""

    ADMIN = enum.auto()
    MEMBER = enum.auto()
    GROUP_ADMIN = enum.auto()


COMMAND_PERMISSION_TYPES = {
    "admin": PermissionType.ADMIN,
    "member": PermissionType.MEMBER,
    "group_admin": PermissionType.GROUP_ADMIN,
}


class PermissionTypeFilter(HandlerFilter):
    def __init__(
        self, permission_type: PermissionType, raise_error: bool = True
    ) -> None:
        self.permission_type = permission_type
        self.raise_error = raise_error

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        """Check the sender's permission in the current chat.

        Args:
            event: Incoming command event.
            cfg: Active AstrBot configuration.

        Returns:
            Whether the sender may run the command.
        """
        if self.permission_type == PermissionType.ADMIN or (
            self.permission_type == PermissionType.GROUP_ADMIN and event.get_group_id()
        ):
            return event.is_admin()
        return True
