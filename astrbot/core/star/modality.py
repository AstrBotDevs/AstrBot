from __future__ import annotations

import enum

from astrbot.core.message.components import BaseMessageComponent, ComponentType


class Modality(enum.Enum):
    """单一模态类型"""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    FILE = "file"


# 组件类型到模态的映射
_COMPONENT_TYPE_TO_MODALITY: dict[ComponentType, Modality] = {
    ComponentType.Plain: Modality.TEXT,
    ComponentType.Image: Modality.IMAGE,
    ComponentType.Record: Modality.AUDIO,
    ComponentType.Video: Modality.VIDEO,
    ComponentType.File: Modality.FILE,
}


def extract_modalities(components: list[BaseMessageComponent]) -> set[Modality]:
    """从消息组件列表提取实际模态集合"""
    result: set[Modality] = set()
    for comp in components:
        modality = _COMPONENT_TYPE_TO_MODALITY.get(comp.type)
        if modality is not None:
            result.add(modality)
    return result or {Modality.TEXT}  # 默认 TEXT
