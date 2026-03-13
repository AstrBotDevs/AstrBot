"""旧版 ``astrbot.core.agent.message`` 兼容入口。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TextPart:
    text: str


__all__ = ["TextPart"]
