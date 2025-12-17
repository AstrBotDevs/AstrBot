from typing import TypeVar

from astrbot.core import sp

SUPPORTED_VALUE_TYPES = int | float | str | bytes | bool | dict | list | None
_VT = TypeVar("_VT")


class PluginKVStoreMixin:
    """为插件提供键值存储功能的 Mixin 类"""

    plugin_id: str

    async def put_kv_data(
        self,
        key: str,
        value: SUPPORTED_VALUE_TYPES,
    ) -> None:
        """为指定插件存储一个键值对"""
        await sp.put_async("plugin", self.plugin_id, key, value)

    async def get_kv_data(self, key: str, default: _VT) -> _VT | None:
        """获取指定插件存储的键值对"""
        return await sp.get_async("plugin", self.plugin_id, key, default)

    async def delete_kv_data(self, key: str) -> None:
        """删除指定插件存储的键值对"""
        await sp.remove_async("plugin", self.plugin_id, key)
