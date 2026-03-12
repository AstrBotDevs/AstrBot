"""旧版配置对象兼容类型。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class AstrBotConfig(dict):
    """兼容旧版 ``AstrBotConfig``。

    旧版实现本身就是 ``dict`` 的薄封装。compat 层额外补上
    ``save_config()``，以支持文档里的插件配置用法。
    """

    def __init__(
        self,
        *args: Any,
        save_path: str | Path | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._save_path = Path(save_path) if save_path is not None else None

    @property
    def save_path(self) -> Path | None:
        return self._save_path

    def bind_save_path(self, save_path: str | Path | None) -> "AstrBotConfig":
        self._save_path = Path(save_path) if save_path is not None else None
        return self

    def save_config(self, save_path: str | Path | None = None) -> None:
        path = Path(save_path) if save_path is not None else self._save_path
        if path is None:
            raise RuntimeError("AstrBotConfig 未绑定保存路径")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        self._save_path = path
