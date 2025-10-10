from dataclasses import dataclass

from .emotion import Emotion


@dataclass
class Soul:
    emotion: Emotion
    emotion_logs: list[Emotion] | None = None
