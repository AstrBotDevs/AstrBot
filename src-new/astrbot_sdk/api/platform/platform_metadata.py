"""旧版平台元数据兼容类型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PlatformMetadata:
    name: str
    description: str
    id: str
    default_config_tmpl: dict | None = None
    adapter_display_name: str | None = None
    logo_path: str | None = None
