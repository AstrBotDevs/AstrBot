"""旧版基础实体兼容类型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Conversation:
    """兼容旧版对话实体。"""

    platform_id: str
    user_id: str
    cid: str
    history: list[dict[str, Any]] = field(default_factory=list)
    title: str | None = ""
    persona_id: str | None = ""
    created_at: int = 0
    updated_at: int = 0
