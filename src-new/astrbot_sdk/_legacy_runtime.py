"""legacy 运行时执行适配。

这个模块把 compat 执行细节从 runtime 主干中收口出来：

- 旧自定义过滤器执行
- 旧结果装饰与发送后 hook
- 旧插件错误 hook
- worker 生命周期中的 compat hook 调用

v4 主干只与这个适配层交互，不直接展开 legacy 事件包装和 hook 名称。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from .api.event import AstrMessageEvent
from .api.event.event_result import MessageEventResult
from .api.message.chain import MessageChain
from .context import Context
from .events import MessageEvent


@dataclass(slots=True)
class LegacyPreparedResult:
    item: Any
    compat_event: AstrMessageEvent | None = None
    stopped: bool = False


@dataclass(slots=True)
class LegacyRuntimeAdapter:
    legacy_context: Any
    filters: list[Any] = field(default_factory=list)

    @classmethod
    def from_handler(cls, legacy_context: Any, handler: Any) -> "LegacyRuntimeAdapter":
        from .api.event.filter import get_compat_custom_filters

        return cls(
            legacy_context=legacy_context,
            filters=list(get_compat_custom_filters(handler)),
        )

    @classmethod
    def from_capability(cls, legacy_context: Any) -> "LegacyRuntimeAdapter":
        return cls(legacy_context=legacy_context)

    def bind_runtime_context(self, runtime_context: Context) -> None:
        binder = getattr(self.legacy_context, "bind_runtime_context", None)
        if callable(binder):
            binder(runtime_context)

    def register_component(self, component: Any) -> None:
        register = getattr(self.legacy_context, "_register_compat_component", None)
        if callable(register):
            register(component)

    async def run_hook(self, hook_name: str, **kwargs: Any) -> list[Any]:
        runner = getattr(self.legacy_context, "_run_compat_hook", None)
        if not callable(runner):
            return []
        return await runner(
            hook_name,
            legacy_context=self.legacy_context,
            **kwargs,
        )

    def runtime_config(self) -> Any:
        config_getter = getattr(self.legacy_context, "_runtime_config", None)
        if callable(config_getter):
            return config_getter()
        return None

    async def passes_filters(self, event: MessageEvent) -> bool:
        if not self.filters:
            return True
        compat_event = AstrMessageEvent.from_message_event(event)
        cfg = self.runtime_config()
        for filter_obj in self.filters:
            if not filter_obj.filter(compat_event, cfg):
                return False
        return True

    async def prepare_result(
        self,
        item: Any,
        event: MessageEvent,
        ctx: Context | None,
    ) -> LegacyPreparedResult:
        compat_event = AstrMessageEvent.from_message_event(event)
        if isinstance(item, (MessageEventResult, MessageChain, str)):
            compat_event.set_result(item)
            await self.run_hook(
                "on_decorating_result",
                event=compat_event,
                context=ctx,
                result=compat_event.get_result(),
            )
            if compat_event.is_stopped():
                return LegacyPreparedResult(
                    item=item,
                    compat_event=compat_event,
                    stopped=True,
                )
            item = compat_event.get_result() or item
        return LegacyPreparedResult(item=item, compat_event=compat_event)

    async def after_send(
        self,
        compat_event: AstrMessageEvent | None,
        ctx: Context | None,
    ) -> None:
        if compat_event is None:
            return
        await self.run_hook(
            "after_message_sent",
            event=compat_event,
            context=ctx,
        )

    async def handle_error(
        self,
        *,
        plugin_id: str,
        handler_name: str,
        exc: Exception,
        event: MessageEvent,
        ctx: Context,
        traceback_text: str,
    ) -> None:
        await self.run_hook(
            "on_plugin_error",
            event=AstrMessageEvent.from_message_event(event),
            context=ctx,
            plugin_name=plugin_id,
            handler_name=handler_name,
            error=exc,
            traceback_text=traceback_text,
        )

    async def run_worker_startup_hooks(
        self,
        *,
        context: Context,
        metadata: dict[str, Any],
    ) -> None:
        await self.run_hook("on_astrbot_loaded", context=context)
        await self.run_hook("on_platform_loaded", context=context)
        await self.run_hook("on_plugin_loaded", context=context, metadata=metadata)

    async def run_worker_shutdown_hooks(
        self,
        *,
        context: Context,
        metadata: dict[str, Any],
    ) -> None:
        await self.run_hook("on_plugin_unloaded", context=context, metadata=metadata)


def build_handler_legacy_runtime(
    legacy_context: Any,
    handler: Any,
    *,
    compat_filters: list[Any] | None = None,
) -> LegacyRuntimeAdapter:
    if compat_filters is None:
        return LegacyRuntimeAdapter.from_handler(legacy_context, handler)
    return LegacyRuntimeAdapter(
        legacy_context=legacy_context,
        filters=list(compat_filters),
    )


def build_capability_legacy_runtime(legacy_context: Any) -> LegacyRuntimeAdapter:
    return LegacyRuntimeAdapter.from_capability(legacy_context)


def register_legacy_component(legacy_context: Any, component: Any) -> None:
    LegacyRuntimeAdapter.from_capability(legacy_context).register_component(component)


def get_legacy_runtime_adapter(loaded: Any) -> LegacyRuntimeAdapter | None:
    adapter = getattr(loaded, "legacy_runtime", None)
    if adapter is not None:
        return adapter
    legacy_context = getattr(loaded, "legacy_context", None)
    if legacy_context is None:
        return None
    filters = list(getattr(loaded, "compat_filters", ()))
    if hasattr(loaded, "compat_filters"):
        adapter = build_handler_legacy_runtime(
            legacy_context,
            getattr(loaded, "callable", None),
            compat_filters=filters,
        )
    else:
        adapter = build_capability_legacy_runtime(legacy_context)
    try:
        setattr(loaded, "legacy_runtime", adapter)
    except AttributeError:
        pass
    return adapter


def iter_unique_legacy_runtime_adapters(
    loaded_items: Iterable[Any],
) -> list[LegacyRuntimeAdapter]:
    seen_contexts: set[int] = set()
    adapters: list[LegacyRuntimeAdapter] = []
    for loaded in loaded_items:
        adapter = get_legacy_runtime_adapter(loaded)
        if adapter is None:
            continue
        marker = id(adapter.legacy_context)
        if marker in seen_contexts:
            continue
        seen_contexts.add(marker)
        adapters.append(adapter)
    return adapters


def bind_legacy_runtime_contexts(
    loaded_items: Iterable[Any],
    runtime_context: Context,
) -> None:
    for adapter in iter_unique_legacy_runtime_adapters(loaded_items):
        adapter.bind_runtime_context(runtime_context)


async def run_legacy_worker_startup_hooks(
    loaded_items: Iterable[Any],
    *,
    context: Context,
    metadata: dict[str, Any],
) -> None:
    for adapter in iter_unique_legacy_runtime_adapters(loaded_items):
        await adapter.run_worker_startup_hooks(
            context=context,
            metadata=metadata,
        )


async def run_legacy_worker_shutdown_hooks(
    loaded_items: Iterable[Any],
    *,
    context: Context,
    metadata: dict[str, Any],
) -> None:
    for adapter in iter_unique_legacy_runtime_adapters(loaded_items):
        await adapter.run_worker_shutdown_hooks(
            context=context,
            metadata=metadata,
        )
