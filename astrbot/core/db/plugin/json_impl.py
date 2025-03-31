import json
import os
import aiofiles
from typing import Any, Dict, Optional
from .plugin_storage import PluginStorage

DIR = "data/plugin_data/json"


class JSONPluginStorage(PluginStorage):
    """插件数据的 JSON 文件存储实现类。

    该类提供异步方式将插件数据存储到 JSON 文件中，每个插件对应一个独立的 JSON 文件。
    支持数据的增删改查操作。
    """

    _instance: Optional["JSONPluginStorage"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """
        初始化 JSON 存储对象。数据存储在 `data/plugin_data/json` 目录下。
        """
        # 避免重复初始化
        if getattr(self, "_initialized", False):
            return

        self.data_dir = DIR
        self._data_cache: Dict[str, Dict[str, Any]] = {}
        self._initialized = True

    async def _ensure_dir_exists(self):
        """确保数据目录存在。"""
        os.makedirs(self.data_dir, exist_ok=True)

    def _get_plugin_file_path(self, plugin: str) -> str:
        """获取指定插件的 JSON 文件路径。"""
        return os.path.join(self.data_dir, f"{plugin}.json")

    async def _load_plugin_data(self, plugin: str) -> Dict[str, Any]:
        """从文件加载插件数据。"""
        if plugin in self._data_cache:
            return self._data_cache[plugin]

        file_path = self._get_plugin_file_path(plugin)

        try:
            if os.path.exists(file_path):
                async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                    content = await f.read()
                    data = json.loads(content)
                    self._data_cache[plugin] = data
                    return data
        except (json.JSONDecodeError, IOError):
            # 文件损坏或读取失败，返回空字典
            pass

        # 文件不存在或读取失败，返回空字典
        self._data_cache[plugin] = {}
        return {}

    async def _save_plugin_data(self, plugin: str, data: Dict[str, Any]):
        """保存插件数据到文件。"""
        await self._ensure_dir_exists()
        file_path = self._get_plugin_file_path(plugin)

        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))
            await f.flush()

        # 更新缓存
        self._data_cache[plugin] = data

    async def set(self, plugin: str, key: str, value: Any):
        """
        异步存储数据。

        将指定插件的键值对存入 JSON 文件，如果键已存在则更新值。

        Args:
            plugin: 插件标识符，将用作独立JSON文件的文件名
            key: 数据键名
            value: 要存储的数据值（任意可JSON序列化的类型）
        """
        data = await self._load_plugin_data(plugin)
        data[key] = value
        await self._save_plugin_data(plugin, data)

    async def get(self, plugin: str, key: str) -> Any:
        """
        异步获取数据。

        从指定插件的 JSON 文件中获取键名对应的值。

        Args:
            plugin: 插件标识符
            key: 数据键名

        Returns:
            Any: 存储的数据值，如果未找到则返回 None
        """
        data = await self._load_plugin_data(plugin)
        return data.get(key)

    async def delete(self, plugin: str, key: str):
        """
        异步删除数据。

        从指定插件的 JSON 文件中删除键名对应的数据项。

        Args:
            plugin: 插件标识符
            key: 要删除的数据键名
        """
        data = await self._load_plugin_data(plugin)
        if key in data:
            del data[key]
            await self._save_plugin_data(plugin, data)

    async def clear_plugin(self, plugin: str):
        """
        清空指定插件的所有数据。

        Args:
            plugin: 插件标识符
        """
        await self._save_plugin_data(plugin, {})

        # 从缓存中移除
        if plugin in self._data_cache:
            del self._data_cache[plugin]
