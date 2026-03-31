import json
from pathlib import Path
from typing import TypeVar, overload

from astrbot.core.utils.astrbot_path import get_astrbot_data_path

_MISSING = object()
_T = TypeVar("_T")


class SharedPreferences:
    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            path = Path(get_astrbot_data_path()) / "shared_preferences.json"
        self.path = path
        self._data = self._load_preferences()

    def _load_preferences(self) -> dict[str, object]:
        if self.path.exists():
            try:
                with self.path.open(encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                self.path.unlink()
        return {}

    def _save_preferences(self) -> None:
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=4, ensure_ascii=False)
            f.flush()

    @overload
    def get(self, key: str) -> object | None: ...

    @overload
    def get(self, key: str, default: _T) -> object | _T: ...

    def get(self, key: str, default: object = _MISSING) -> object | None:
        if default is _MISSING:
            return self._data.get(key)
        return self._data.get(key, default)

    def put(self, key: str, value: object) -> None:
        self._data[key] = value
        self._save_preferences()

    def remove(self, key: str) -> None:
        if key in self._data:
            del self._data[key]
            self._save_preferences()

    def clear(self) -> None:
        self._data.clear()
        self._save_preferences()


sp = SharedPreferences()
