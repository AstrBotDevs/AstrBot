"""Public types for QQ Official callback-button interactions."""

from enum import IntEnum


class QQOfficialInteractionResultCode(IntEnum):
    """QQ Official callback-button acknowledgement result codes."""

    SUCCESS = 0
    FAILED = 1
    RATE_LIMITED = 2
    DUPLICATE = 3
    FORBIDDEN = 4
    ADMIN_ONLY = 5
