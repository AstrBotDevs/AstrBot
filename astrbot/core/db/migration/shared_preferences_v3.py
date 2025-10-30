import json
import os
from typing import TypeVar
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

_VT = TypeVar("_VT")


class SharedPreferences:
    def __init__(self, path: str | None = None) -> None:
        if path is None:
            path = os.path.join(get_astrbot_data_path(), "shared_preferences.json")
        self.path = path
        self._data = self._load_preferences()

    def _load_preferences(self) -> dict:
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    return json.load(f)
            except json.JSONDecodeError:
                os.remove(self.path)
        return {}

    def _save_preferences(self) -> None:
        with open(self.path, "w") as f:
            json.dump(self._data, f, indent=4, ensure_ascii=False)
            f.flush()

    def get(self, key: str, default: _VT = None) -> _VT:
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
