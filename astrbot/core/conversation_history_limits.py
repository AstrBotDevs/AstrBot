"""Limits for loading persisted conversation history into Python."""

from sqlalchemy import LargeBinary, cast, func

MAX_ONLINE_HISTORY_BYTES = 16 * 1024 * 1024
"""Maximum UTF-8 byte size of one conversation history loaded online."""


class HistoryTooLargeError(ValueError):
    """Raised when a stored conversation history exceeds the online read limit.

    Attributes:
        cid: Conversation identity, when known.
        byte_size: Stored history size measured by SQLite in bytes.
        limit_bytes: Maximum permitted online history size.
    """

    def __init__(self, cid: str, byte_size: int, limit_bytes: int) -> None:
        self.cid = cid
        self.byte_size = byte_size
        self.limit_bytes = limit_bytes
        super().__init__(
            f"Conversation history is {byte_size} bytes and exceeds the "
            f"{limit_bytes}-byte online limit; the history remains stored "
            "but cannot be processed online."
        )


def history_size_bytes(content_column):
    """Build a SQLite expression measuring the stored JSON as UTF-8 bytes.

    Args:
        content_column: SQLAlchemy expression for the persisted JSON content.

    Returns:
        A SQL expression equivalent to ``length(CAST(content AS BLOB))``,
        treating SQL NULL as an empty history.
    """
    return func.coalesce(func.length(cast(content_column, LargeBinary)), 0)
