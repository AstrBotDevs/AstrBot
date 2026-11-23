"""String-valued enums with the SDK's established display behavior."""

from enum import Enum, StrEnum


class StringEnum(StrEnum):
    """Keep Enum display/formatting alongside string equality and JSON values."""

    __str__ = Enum.__str__

    def __format__(self, format_spec: str, /) -> str:
        """Apply Enum formatting while retaining the string format signature."""
        return Enum.__format__(self, format_spec)
