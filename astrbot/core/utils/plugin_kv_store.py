from typing import Any, Protocol, TypeVar

SUPPORTED_VALUE_TYPES = int | float | str | bytes | bool | dict | list | None
_VT = TypeVar("_VT")


class PluginKVStorage(Protocol):
    """The narrow persistence capability required by plugin instances."""

    async def put(
        self,
        plugin_id: str,
        key: str,
        value: SUPPORTED_VALUE_TYPES,
    ) -> None: ...

    async def get(self, plugin_id: str, key: str, default: _VT) -> _VT | None: ...

    async def remove(self, plugin_id: str, key: str) -> None: ...


class PluginKVContext(Protocol):
    """A plugin context exposing only plugin-scoped key-value storage."""

    storage: PluginKVStorage


class PluginKVStoreMixin:
    """为插件提供键值存储功能的 Mixin 类"""

    plugin_id: str
    context: Any

    async def put_kv_data(
        self,
        key: str,
        value: SUPPORTED_VALUE_TYPES,
    ) -> None:
        """为指定插件存储一个键值对"""
        await self.context.storage.put(self.plugin_id, key, value)

    async def get_kv_data(self, key: str, default: _VT) -> _VT | None:
        """获取指定插件存储的键值对"""
        return await self.context.storage.get(self.plugin_id, key, default)

    async def delete_kv_data(self, key: str) -> None:
        """删除指定插件存储的键值对"""
        await self.context.storage.remove(self.plugin_id, key)
