from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from ..context import PluginContext

_STORAGE_CAPABILITY = "storage.kv"


class PluginStorage:
    """Access plugin-scoped persistent storage provided by the Host.

    The KV store is namespaced per plugin on the Host side. ``data_dir`` is a
    Runner-local directory for larger files; the Host cannot read it.
    """

    def __init__(self, ctx: PluginContext, data_dir: Path) -> None:
        """Initialize the storage service.

        Args:
            ctx: Owning plugin context used for Host invocation.
            data_dir: Runner-local persistent directory for this plugin.
        """
        self._ctx = ctx
        self.data_dir = data_dir

    async def get(self, key: str, default: Any = None) -> Any:
        """Read one value from the plugin KV store.

        Args:
            key: Storage key.
            default: Value returned when the key is missing.

        Returns:
            Stored JSON value or ``default``.
        """
        result = await self._ctx._invoke_capability(
            _STORAGE_CAPABILITY,
            "get",
            {"key": key, "default": default},
        )
        return result.get("value", default)

    async def set(self, key: str, value: Any) -> None:
        """Write one JSON value into the plugin KV store.

        Args:
            key: Storage key.
            value: JSON-compatible value to store.
        """
        await self._ctx._invoke_capability(
            _STORAGE_CAPABILITY,
            "set",
            {"key": key, "value": value},
        )

    async def delete(self, key: str) -> None:
        """Remove one key from the plugin KV store.

        Args:
            key: Storage key.
        """
        await self._ctx._invoke_capability(
            _STORAGE_CAPABILITY,
            "delete",
            {"key": key},
        )
