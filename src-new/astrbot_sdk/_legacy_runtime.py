"""legacy 运行时执行适配。

这个模块把 compat 执行细节从 runtime 主干中收口出来：

- 旧自定义过滤器执行
- 旧结果装饰与发送后 hook
- 旧插件错误 hook
- worker 生命周期中的 compat hook 调用

v4 主干只与这个适配层交互，不直接展开 legacy 事件包装和 hook 名称。
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from .api.event import AstrMessageEvent
from .api.event.event_result import MessageEventResult
from .api.message.chain import MessageChain
from .context import Context
from .events import MessageEvent
from .star import Star


@dataclass(slots=True)
class LegacyPreparedResult:
    item: Any
    compat_event: AstrMessageEvent | None = None
    stopped: bool = False


@dataclass(slots=True)
class LegacyHandlerPreparation:
    adapter: LegacyRuntimeAdapter | None
    should_run: bool = True


@dataclass(slots=True)
class LegacyComponentConstruction:
    legacy_context: Any
    shared_legacy_context: Any
    component_config: Any | None
    constructor_args: tuple[Any, ...]


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

    async def dispatch_result(
        self,
        item: Any,
        event: MessageEvent,
        ctx: Context | None,
        *,
        sender: Callable[[Any], Any],
    ) -> bool:
        prepared = await self.prepare_result(item, event, ctx)
        if prepared.stopped:
            return False
        handled = sender(prepared.item)
        if inspect.isawaitable(handled):
            handled = await handled
        sent = bool(handled)
        if sent:
            await self.after_send(prepared.compat_event, ctx)
        return sent

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


def bind_loaded_legacy_runtime(
    loaded: Any,
    runtime_context: Context,
) -> LegacyRuntimeAdapter | None:
    adapter = get_legacy_runtime_adapter(loaded)
    if adapter is None:
        return None
    adapter.bind_runtime_context(runtime_context)
    return adapter


async def prepare_legacy_handler_runtime(
    loaded: Any,
    *,
    runtime_context: Context,
    event: MessageEvent,
) -> LegacyHandlerPreparation:
    adapter = bind_loaded_legacy_runtime(loaded, runtime_context)
    if adapter is None:
        return LegacyHandlerPreparation(adapter=None, should_run=True)
    should_run = await adapter.passes_filters(event)
    return LegacyHandlerPreparation(adapter=adapter, should_run=should_run)


class LegacyWorkerRuntimeBridge:
    def __init__(self, loaded_items: Callable[[], list[Any]] | Iterable[Any]) -> None:
        self._loaded_items = loaded_items

    def _items(self) -> list[Any]:
        if callable(self._loaded_items):
            return list(self._loaded_items())
        return list(self._loaded_items)

    def bind_runtime_contexts(self, runtime_context: Context) -> None:
        bind_legacy_runtime_contexts(self._items(), runtime_context)

    async def run_startup_hooks(
        self,
        *,
        context: Context,
        metadata: dict[str, Any],
    ) -> None:
        await run_legacy_worker_startup_hooks(
            self._items(),
            context=context,
            metadata=metadata,
        )

    async def run_shutdown_hooks(
        self,
        *,
        context: Context,
        metadata: dict[str, Any],
    ) -> None:
        await run_legacy_worker_shutdown_hooks(
            self._items(),
            context=context,
            metadata=metadata,
        )


def build_legacy_worker_runtime_bridge(
    loaded_items: Callable[[], list[Any]] | Iterable[Any],
) -> LegacyWorkerRuntimeBridge:
    return LegacyWorkerRuntimeBridge(loaded_items)


def create_legacy_component_context(component_cls: Any, plugin_name: str) -> Any:
    factory = getattr(component_cls, "_astrbot_create_legacy_context", None)
    if callable(factory):
        return factory(plugin_name)
    from .api.star.context import Context as LegacyContext

    return LegacyContext(plugin_name)


def is_new_star_component(component_cls: Any) -> bool:
    if not isinstance(component_cls, type):
        return False
    if not issubclass(component_cls, Star):
        return False
    marker = getattr(component_cls, "__astrbot_is_new_star__", None)
    if callable(marker):
        return bool(marker())
    return True


def legacy_constructor_accepts_config(component_cls: Any) -> bool:
    try:
        signature = inspect.signature(component_cls.__init__)
    except (TypeError, ValueError):
        return False
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    ]
    if positional and positional[0].name == "self":
        positional = positional[1:]
    return len(positional) >= 2


def select_legacy_constructor_args(
    component_cls: Any,
    legacy_context: Any,
    component_config: Any | None,
) -> tuple[Any, ...]:
    if legacy_constructor_accepts_config(component_cls):
        return (legacy_context, component_config)
    return (legacy_context,)


def plan_legacy_component_construction(
    component_cls: Any,
    *,
    plugin_name: str,
    shared_legacy_context: Any | None,
    plugin_config: Any | None,
    default_config_factory: Callable[[], Any],
) -> LegacyComponentConstruction:
    legacy_context = shared_legacy_context or create_legacy_component_context(
        component_cls,
        plugin_name,
    )
    component_config = plugin_config
    if component_config is None and legacy_constructor_accepts_config(component_cls):
        component_config = default_config_factory()
    return LegacyComponentConstruction(
        legacy_context=legacy_context,
        shared_legacy_context=shared_legacy_context or legacy_context,
        component_config=component_config,
        constructor_args=select_legacy_constructor_args(
            component_cls,
            legacy_context,
            component_config,
        ),
    )


def finalize_legacy_component_instance(
    instance: Any,
    *,
    legacy_context: Any,
    component_config: Any | None,
) -> None:
    setattr(instance, "context", legacy_context)
    if component_config is not None:
        setattr(instance, "config", component_config)
    register_legacy_component(legacy_context, instance)


def resolve_plugin_lifecycle_hook(
    instance: Any, method_name: str
) -> Callable[..., Any] | None:
    direct = getattr(type(instance), method_name, None)
    inherited = getattr(Star, method_name, None)
    if direct is not None and direct is not inherited:
        return getattr(instance, method_name)
    if not is_new_star_component(type(instance)):
        alias = {
            "on_start": "initialize",
            "on_stop": "terminate",
        }.get(method_name)
        if alias:
            hook = getattr(instance, alias, None)
            if callable(hook):
                return hook
    return None
