from dataclasses import dataclass


@dataclass
class Emotion:
    """描述了一个情绪状态"""

    energy: float
    valence: float
    arousal: float


@dataclass
class EmotionLog:
    """描述了一条情绪维度变化的日志"""

    timestamp: int
    field: str
    value: float
    reason: str = ""
