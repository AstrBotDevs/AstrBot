"""Tests for the private legacy runtime boundary helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from astrbot_sdk._legacy_api import LegacyContext
from astrbot_sdk._legacy_runtime import (
    LegacyComponentConstruction,
    LegacyRuntimeAdapter,
    bind_loaded_legacy_runtime,
    build_legacy_worker_runtime_bridge,
    create_legacy_component_context,
    finalize_legacy_component_instance,
    is_new_star_component,
    legacy_constructor_accepts_config,
    plan_legacy_component_construction,
    prepare_legacy_handler_runtime,
    resolve_plugin_lifecycle_hook,
    select_legacy_constructor_args,
)
from astrbot_sdk.api.event import AstrMessageEvent
from astrbot_sdk.api.event.filter import (
    CustomFilter,
    after_message_sent,
    on_decorating_result,
    on_plugin_loaded,
)
from astrbot_sdk.context import Context
from astrbot_sdk.events import MessageEvent
from astrbot_sdk.protocol.descriptors import CommandTrigger, HandlerDescriptor
from astrbot_sdk.runtime.loader import LoadedHandler
from astrbot_sdk.star import Star


class _DummyPeer:
    def __init__(self) -> None:
        self.remote_capability_map: dict[str, object] = {}


class _RejectAll(CustomFilter):
    def filter(self, event: AstrMessageEvent, cfg) -> bool:
        return False


def _runtime_context() -> Context:
    return Context(peer=_DummyPeer(), plugin_id="compat-plugin")


def _record_sender(bucket: list[str]):
    async def sender(item) -> bool:
        get_plain_text = getattr(item, "get_plain_text", None)
        if callable(get_plain_text):
            bucket.append(get_plain_text())
        else:
            bucket.append(str(item))
        return True

    return sender


async def _ignore_sender(item) -> bool:
    return False


def _loaded_handler(legacy_context: LegacyContext) -> LoadedHandler:
    async def handler_func(event):
        return event

    return LoadedHandler(
        descriptor=HandlerDescriptor(
            id="compat.handler",
            trigger=CommandTrigger(command="compat"),
        ),
        callable=handler_func,
        owner=MagicMock(),
        legacy_context=None,
    )


@pytest.mark.asyncio
async def test_prepare_legacy_handler_runtime_binds_context_and_applies_filters():
    legacy_context = LegacyContext("compat-plugin")
    loaded = _loaded_handler(legacy_context)
    loaded.legacy_runtime = LegacyRuntimeAdapter(
        legacy_context=legacy_context,
        filters=[_RejectAll()],
    )
    runtime_context = _runtime_context()
    event = MessageEvent(text="compat", session_id="session-1", context=runtime_context)

    prepared = await prepare_legacy_handler_runtime(
        loaded,
        runtime_context=runtime_context,
        event=event,
    )

    assert prepared.adapter is loaded.legacy_runtime
    assert prepared.should_run is False
    assert legacy_context.require_runtime_context() is runtime_context


def test_bind_loaded_legacy_runtime_binds_runtime_context():
    legacy_context = LegacyContext("compat-plugin")
    adapter = LegacyRuntimeAdapter(legacy_context=legacy_context)
    loaded = SimpleNamespace(legacy_runtime=adapter, legacy_context=legacy_context)
    runtime_context = _runtime_context()

    bound = bind_loaded_legacy_runtime(loaded, runtime_context)

    assert bound is adapter
    assert legacy_context.require_runtime_context() is runtime_context


def test_create_legacy_component_context_uses_factory_method_when_available():
    expected = object()

    class LegacyComponent:
        @classmethod
        def _astrbot_create_legacy_context(cls, plugin_name):
            return expected

    assert create_legacy_component_context(LegacyComponent, "compat-plugin") is expected


def test_is_new_star_component_detects_legacy_marker():
    class NotAStar:
        pass

    class LegacyCompat(Star):
        @classmethod
        def __astrbot_is_new_star__(cls) -> bool:
            return False

    assert is_new_star_component("nope") is False
    assert is_new_star_component(NotAStar) is False
    assert is_new_star_component(LegacyCompat) is False


def test_legacy_constructor_helpers_follow_legacy_context_config_rules():
    class NeedsContextOnly:
        def __init__(self, context):
            self.context = context

    class NeedsContextAndConfig:
        def __init__(self, context, config):
            self.context = context
            self.config = config

    legacy_context = object()
    config = {"token": "secret"}

    assert legacy_constructor_accepts_config(NeedsContextOnly) is False
    assert legacy_constructor_accepts_config(NeedsContextAndConfig) is True
    assert select_legacy_constructor_args(NeedsContextOnly, legacy_context, config) == (
        legacy_context,
    )
    assert select_legacy_constructor_args(
        NeedsContextAndConfig,
        legacy_context,
        config,
    ) == (legacy_context, config)


def test_plan_legacy_component_construction_reuses_shared_context_and_default_config():
    class NeedsContextAndConfig:
        def __init__(self, context, config):
            self.context = context
            self.config = config

    shared_context = object()
    created_configs: list[dict[str, str]] = []

    def build_default_config():
        config = {"token": "default"}
        created_configs.append(config)
        return config

    planned = plan_legacy_component_construction(
        NeedsContextAndConfig,
        plugin_name="compat-plugin",
        shared_legacy_context=shared_context,
        plugin_config=None,
        default_config_factory=build_default_config,
    )

    assert isinstance(planned, LegacyComponentConstruction)
    assert planned.legacy_context is shared_context
    assert planned.shared_legacy_context is shared_context
    assert planned.component_config == {"token": "default"}
    assert planned.constructor_args == (shared_context, {"token": "default"})
    assert created_configs == [{"token": "default"}]


def test_finalize_legacy_component_instance_binds_context_config_and_registers():
    legacy_context = LegacyContext("compat-plugin")
    component_config = {"token": "secret"}

    class CompatComponent:
        @on_plugin_loaded()
        async def on_loaded(self, metadata):
            return metadata

    instance = CompatComponent()

    finalize_legacy_component_instance(
        instance,
        legacy_context=legacy_context,
        component_config=component_config,
    )

    assert instance.context is legacy_context
    assert instance.config == component_config
    assert "on_plugin_loaded" in legacy_context._compat_hooks


@pytest.mark.asyncio
async def test_legacy_worker_runtime_bridge_deduplicates_shared_context_hooks():
    legacy_context = LegacyContext("compat-plugin")
    observed_metadata: list[str] = []

    class CompatHooks:
        @on_plugin_loaded()
        async def on_loaded(self, metadata):
            observed_metadata.append(str(metadata["name"]))

    legacy_context._register_compat_component(CompatHooks())
    loaded_items = [
        SimpleNamespace(
            legacy_runtime=LegacyRuntimeAdapter(legacy_context=legacy_context),
            legacy_context=legacy_context,
        ),
        SimpleNamespace(
            legacy_runtime=LegacyRuntimeAdapter(legacy_context=legacy_context),
            legacy_context=legacy_context,
        ),
    ]
    bridge = build_legacy_worker_runtime_bridge(loaded_items)

    await bridge.run_startup_hooks(
        context=_runtime_context(),
        metadata={"name": "compat-plugin"},
    )

    assert observed_metadata == ["compat-plugin"]


@pytest.mark.asyncio
async def test_legacy_runtime_dispatch_result_runs_after_send_only_for_sent_output():
    legacy_context = LegacyContext("compat-plugin")
    observed_results: list[str] = []

    class CompatHooks:
        @on_plugin_loaded()
        async def noop(self, metadata):
            return metadata

        @on_decorating_result()
        async def decorate(self, event: AstrMessageEvent):
            event.set_result("decorated")

        @after_message_sent()
        async def after_send(self, event: AstrMessageEvent):
            result = event.get_result()
            observed_results.append(result.get_plain_text() if result else "")

    legacy_context._register_compat_component(CompatHooks())
    adapter = LegacyRuntimeAdapter(legacy_context=legacy_context)
    runtime_context = _runtime_context()
    adapter.bind_runtime_context(runtime_context)
    event = MessageEvent(
        text="compat",
        session_id="session-1",
        user_id="user-1",
        platform="test",
        context=runtime_context,
    )
    seen_items: list[str] = []

    handled = await adapter.dispatch_result(
        "raw",
        event,
        runtime_context,
        sender=_record_sender(seen_items),
    )

    assert handled is True
    assert seen_items == ["decorated"]
    assert observed_results == ["decorated"]

    ignored = await adapter.dispatch_result(
        "raw",
        event,
        runtime_context,
        sender=_ignore_sender,
    )

    assert ignored is False
    assert observed_results == ["decorated"]


def test_resolve_plugin_lifecycle_hook_prefers_legacy_initialize_alias():
    calls: list[str] = []

    class LegacyComponent(Star):
        @classmethod
        def __astrbot_is_new_star__(cls) -> bool:
            return False

        async def initialize(self, ctx):
            calls.append(ctx.plugin_id)

    instance = LegacyComponent()

    hook = resolve_plugin_lifecycle_hook(instance, "on_start")

    assert hook is not None
    assert getattr(hook, "__name__", "") == "initialize"


def test_resolve_plugin_lifecycle_hook_keeps_overridden_new_star_hook():
    class NewComponent(Star):
        async def on_start(self, ctx):
            return ctx

    instance = NewComponent()

    hook = resolve_plugin_lifecycle_hook(instance, "on_start")

    assert hook is not None
    assert getattr(hook, "__name__", "") == "on_start"
