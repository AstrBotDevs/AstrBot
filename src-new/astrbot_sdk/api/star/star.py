"""旧版插件元数据兼容类型。"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..basic.astrbot_config import AstrBotConfig


@dataclass(slots=True)
class StarMetadata:
    name: str | None = None
    author: str | None = None
    desc: str | None = None
    version: str | None = None
    repo: str | None = None
    module_path: str | None = None
    root_dir_name: str | None = None
    reserved: bool = False
    activated: bool = True
    config: AstrBotConfig | None = None
    star_handler_full_names: list[str] = field(default_factory=list)
    display_name: str | None = None
    logo_path: str | None = None

    def __str__(self) -> str:
        return f"Plugin {self.name} ({self.version}) by {self.author}: {self.desc}"

    def __repr__(self) -> str:
        return str(self)
