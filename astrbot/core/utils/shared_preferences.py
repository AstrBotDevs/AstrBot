import json
import os
from .astrbot_path import get_astrbot_data_path


class SharedPreferences:
    def __init__(self, path=None):
        if path is None:
            path = os.path.join(get_astrbot_data_path(), "shared_preferences.json")
        self.path = path
        self._data = self._load_preferences()

    def _load_preferences(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                os.remove(self.path)
        return {}

    def _save_preferences(self):
        with open(self.path, "w") as f:
            json.dump(self._data, f, indent=4, ensure_ascii=False)
            f.flush()

    def get(self, key, default=None):
        return self._data.get(key, default)

    def put(self, key, value):
        self._data[key] = value
        self._save_preferences()

    def remove(self, key):
        if key in self._data:
            del self._data[key]
            self._save_preferences()

    def clear(self):
        self._data.clear()
        self._save_preferences()
