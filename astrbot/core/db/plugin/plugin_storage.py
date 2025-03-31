import abc
from typing import Any

class PluginStorage(abc.ABC):
    @abc.abstractmethod
    async def set(self, plugin: str, key: str, value: Any):
        """存储插件数据"""
        raise NotImplementedError

    @abc.abstractmethod
    async def get(self, plugin: str, key: str) -> Any:
        """获取插件数据"""
        raise NotImplementedError

    @abc.abstractmethod
    async def delete(self, plugin: str, key: str):
        """删除插件数据"""
        raise NotImplementedError
