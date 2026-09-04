from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, TypeVar, cast

if TYPE_CHECKING:
    from .context import Context

_VT = TypeVar("_VT")


class _HasRuntimeContext(Protocol):
    def _require_runtime_context(self) -> Context: ...


class PluginKVStoreMixin:
    """Plugin-scoped KV helpers backed by the runtime db client."""

    def _runtime_context(self) -> Context:
        owner = cast(_HasRuntimeContext, self)
        return owner._require_runtime_context()

    @property
    def plugin_id(self) -> str:
        ctx = self._runtime_context()
        return ctx.plugin_id

    async def put_kv_data(self, key: str, value: Any) -> None:
        ctx = self._runtime_context()
        await ctx.db.set(str(key), value)

    async def get_kv_data(self, key: str, default: _VT) -> _VT:
        ctx = self._runtime_context()
        value = await ctx.db.get(str(key))
        return default if value is None else value

    async def delete_kv_data(self, key: str) -> None:
        ctx = self._runtime_context()
        await ctx.db.delete(str(key))
