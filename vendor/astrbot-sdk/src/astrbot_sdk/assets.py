from __future__ import annotations

from dataclasses import dataclass

from .protocol_registry import register_protocol_dataclass


@register_protocol_dataclass
@dataclass(frozen=True, slots=True)
class AssetRef:
    id: str
    filename: str | None = None
    media_type: str | None = None
    size: int | None = None
