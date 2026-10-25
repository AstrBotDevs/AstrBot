from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SessionEnumResult:
    """Result of a platform session enumeration.

    Each entry in ``groups``/``friends`` has the shape
    ``{"id": str, "name": str}``. A non-empty ``error`` means enumeration failed
    completely or partially, and callers should degrade gracefully.
    """

    groups: list[dict] = field(default_factory=list)
    friends: list[dict] = field(default_factory=list)
    error: str = ""


class SessionEnumerator:
    """Optional protocol for platform adapters that can enumerate sessions.

    Supporting platforms (e.g. aiocqhttp) implement ``enumerate_sessions()`` so the
    session management page can list groups/private chats that have never talked to
    the bot.
    """

    async def enumerate_sessions(self) -> SessionEnumResult:
        raise NotImplementedError
