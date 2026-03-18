"""Provider discovery and provider-management clients."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict

from ..llm.entities import ProviderMeta, ProviderType
from ..llm.providers import (
    ProviderProxy,
    STTProvider,
    TTSProvider,
    provider_proxy_from_meta,
)
from ._proxy import CapabilityProxy


class _ProviderModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class ManagedProviderRecord(_ProviderModel):
    id: str
    model: str | None = None
    type: str
    provider_type: ProviderType
    loaded: bool
    enabled: bool
    provider_source_id: str | None = None

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> ManagedProviderRecord | None:
        if not isinstance(payload, dict):
            return None
        return cls.model_validate(payload)


class ProviderChangeEvent(_ProviderModel):
    provider_id: str
    provider_type: ProviderType
    umo: str | None = None

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> ProviderChangeEvent | None:
        if not isinstance(payload, dict):
            return None
        return cls.model_validate(payload)


class ProviderClient:
    def __init__(self, proxy: CapabilityProxy) -> None:
        self._proxy = proxy

    @staticmethod
    def _provider_meta_list(items: Any) -> list[ProviderMeta]:
        if not isinstance(items, list):
            return []
        providers: list[ProviderMeta] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            provider = ProviderMeta.from_payload(item)
            if provider is not None:
                providers.append(provider)
        return providers

    async def list_all(self) -> list[ProviderMeta]:
        output = await self._proxy.call("provider.list_all", {})
        return self._provider_meta_list(output.get("providers"))

    async def list_tts(self) -> list[ProviderMeta]:
        output = await self._proxy.call("provider.list_all_tts", {})
        return self._provider_meta_list(output.get("providers"))

    async def list_stt(self) -> list[ProviderMeta]:
        output = await self._proxy.call("provider.list_all_stt", {})
        return self._provider_meta_list(output.get("providers"))

    async def list_embedding(self) -> list[ProviderMeta]:
        output = await self._proxy.call("provider.list_all_embedding", {})
        return self._provider_meta_list(output.get("providers"))

    async def list_rerank(self) -> list[ProviderMeta]:
        output = await self._proxy.call("provider.list_all_rerank", {})
        return self._provider_meta_list(output.get("providers"))

    async def _get_tts_support_stream(self, provider_id: str) -> bool:
        output = await self._proxy.call(
            "provider.tts.support_stream",
            {"provider_id": str(provider_id)},
        )
        return bool(output.get("supported", False))

    async def _build_proxy(self, meta: ProviderMeta | None) -> ProviderProxy | None:
        if meta is None:
            return None
        tts_supports_stream = None
        if meta.provider_type == ProviderType.TEXT_TO_SPEECH:
            tts_supports_stream = await self._get_tts_support_stream(meta.id)
        return provider_proxy_from_meta(
            self._proxy,
            meta,
            tts_supports_stream=tts_supports_stream,
        )

    async def get(self, provider_id: str) -> ProviderProxy | None:
        output = await self._proxy.call(
            "provider.get_by_id",
            {"provider_id": str(provider_id)},
        )
        return await self._build_proxy(
            ProviderMeta.from_payload(output.get("provider"))
        )

    async def get_using_chat(self, umo: str | None = None) -> ProviderMeta | None:
        output = await self._proxy.call("provider.get_using", {"umo": umo})
        return ProviderMeta.from_payload(output.get("provider"))

    async def get_using_tts(self, umo: str | None = None) -> TTSProvider | None:
        output = await self._proxy.call("provider.get_using_tts", {"umo": umo})
        provider = await self._build_proxy(
            ProviderMeta.from_payload(output.get("provider"))
        )
        return provider if isinstance(provider, TTSProvider) else None

    async def get_using_stt(self, umo: str | None = None) -> STTProvider | None:
        output = await self._proxy.call("provider.get_using_stt", {"umo": umo})
        provider = await self._build_proxy(
            ProviderMeta.from_payload(output.get("provider"))
        )
        return provider if isinstance(provider, STTProvider) else None


class ProviderManagerClient:
    def __init__(
        self,
        proxy: CapabilityProxy,
        *,
        plugin_id: str | None = None,
        logger: Any | None = None,
    ) -> None:
        self._proxy = proxy
        self._plugin_id = plugin_id
        self._logger = logger
        self._change_hook_tasks: set[asyncio.Task[None]] = set()

    @staticmethod
    def _provider_type_value(provider_type: ProviderType | str) -> str:
        if isinstance(provider_type, ProviderType):
            return provider_type.value
        return str(provider_type).strip()

    @staticmethod
    def _record_from_output(output: dict[str, Any]) -> ManagedProviderRecord | None:
        return ManagedProviderRecord.from_payload(output.get("provider"))

    async def set_provider(
        self,
        provider_id: str,
        provider_type: ProviderType | str,
        umo: str | None = None,
    ) -> None:
        await self._proxy.call(
            "provider.manager.set",
            {
                "provider_id": str(provider_id),
                "provider_type": self._provider_type_value(provider_type),
                "umo": umo,
            },
        )

    async def get_provider_by_id(
        self,
        provider_id: str,
    ) -> ManagedProviderRecord | None:
        output = await self._proxy.call(
            "provider.manager.get_by_id",
            {"provider_id": str(provider_id)},
        )
        return self._record_from_output(output)

    async def load_provider(
        self,
        provider_config: dict[str, Any],
    ) -> ManagedProviderRecord | None:
        output = await self._proxy.call(
            "provider.manager.load",
            {"provider_config": dict(provider_config)},
        )
        return self._record_from_output(output)

    async def terminate_provider(self, provider_id: str) -> None:
        await self._proxy.call(
            "provider.manager.terminate",
            {"provider_id": str(provider_id)},
        )

    async def create_provider(
        self,
        provider_config: dict[str, Any],
    ) -> ManagedProviderRecord | None:
        output = await self._proxy.call(
            "provider.manager.create",
            {"provider_config": dict(provider_config)},
        )
        return self._record_from_output(output)

    async def update_provider(
        self,
        origin_provider_id: str,
        new_config: dict[str, Any],
    ) -> ManagedProviderRecord | None:
        output = await self._proxy.call(
            "provider.manager.update",
            {
                "origin_provider_id": str(origin_provider_id),
                "new_config": dict(new_config),
            },
        )
        return self._record_from_output(output)

    async def delete_provider(
        self,
        provider_id: str | None = None,
        provider_source_id: str | None = None,
    ) -> None:
        await self._proxy.call(
            "provider.manager.delete",
            {
                "provider_id": provider_id,
                "provider_source_id": provider_source_id,
            },
        )

    async def get_insts(self) -> list[ManagedProviderRecord]:
        output = await self._proxy.call("provider.manager.get_insts", {})
        items = output.get("providers")
        if not isinstance(items, list):
            return []
        return [
            record
            for record in (
                ManagedProviderRecord.from_payload(item)
                if isinstance(item, dict)
                else None
                for item in items
            )
            if record is not None
        ]

    async def watch_changes(self) -> AsyncIterator[ProviderChangeEvent]:
        async for chunk in self._proxy.stream("provider.manager.watch_changes", {}):
            event = ProviderChangeEvent.from_payload(chunk)
            if event is not None:
                yield event

    async def register_provider_change_hook(
        self,
        callback: Callable[
            [str, ProviderType, str | None],
            Awaitable[None] | None,
        ],
    ) -> asyncio.Task[None]:
        async def runner() -> None:
            async for event in self.watch_changes():
                result = callback(
                    event.provider_id,
                    event.provider_type,
                    event.umo,
                )
                if inspect.isawaitable(result):
                    await result

        task = asyncio.create_task(runner())
        self._change_hook_tasks.add(task)
        task.add_done_callback(self._log_change_hook_result)
        return task

    async def unregister_provider_change_hook(
        self,
        task: asyncio.Task[None],
    ) -> None:
        if task not in self._change_hook_tasks:
            return
        self._change_hook_tasks.discard(task)
        if not task.done():
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    def _log_change_hook_result(self, task: asyncio.Task[None]) -> None:
        self._change_hook_tasks.discard(task)
        if task.cancelled():
            debug_logger = getattr(self._logger, "debug", None)
            if callable(debug_logger):
                debug_logger(
                    "Provider change hook cancelled: plugin_id={}",
                    self._plugin_id,
                )
            return
        try:
            task.result()
        except asyncio.CancelledError:
            debug_logger = getattr(self._logger, "debug", None)
            if callable(debug_logger):
                debug_logger(
                    "Provider change hook cancelled: plugin_id={}",
                    self._plugin_id,
                )
        except Exception:
            exception_logger = getattr(self._logger, "exception", None)
            if callable(exception_logger):
                exception_logger(
                    "Provider change hook failed: plugin_id={}",
                    self._plugin_id,
                )


__all__ = [
    "ManagedProviderRecord",
    "ProviderChangeEvent",
    "ProviderClient",
    "ProviderManagerClient",
]
