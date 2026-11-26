"""Legacy persistent-object shapes (astrbot.core.db.po) as plain classes."""

from __future__ import annotations

import json
from typing import Any


class Personality(dict):
    """Legacy personality record."""


class Conversation:
    """Legacy conversation record; history is a JSON string of messages."""

    def __init__(
        self,
        cid: str = "",
        history: str = "[]",
        persona_id: str | None = None,
        created_at: Any = None,
        updated_at: Any = None,
        title: str | None = None,
        **_: Any,
    ) -> None:
        self.cid = cid
        self.history = history
        self.persona_id = persona_id
        self.created_at = created_at
        self.updated_at = updated_at
        self.title = title

    def messages(self) -> list[dict]:
        """Return the decoded message history."""
        try:
            return json.loads(self.history or "[]")
        except json.JSONDecodeError:
            return []


class CronJob:
    """Legacy cron job record (type-only facade; scheduling is deferred)."""

    def __init__(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)
