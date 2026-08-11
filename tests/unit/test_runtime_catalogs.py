"""Regression coverage for runtime-owned dynamic capability catalogs."""

from __future__ import annotations

import sys
from types import ModuleType

import pytest

from astrbot.core.platform.register import register_platform_adapter
from astrbot.core.provider.register import register_provider_adapter
from astrbot.core.runtime_catalogs import RuntimeCatalogs
from astrbot.core.star.star import StarMetadata
from astrbot.core.star.star_handler import EventType, StarHandlerMetadata


async def _catalog_handler(*_args: object) -> None:
    """Provide a concrete handler for registry isolation assertions."""


def _declared_provider_module(
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    provider_type: str,
) -> ModuleType:
    """Create an already-imported module with one provider declaration."""

    module = ModuleType(module_name)
    monkeypatch.setitem(sys.modules, module_name, module)

    @register_provider_adapter(provider_type, f"{provider_type} description")
    class DeclaredProvider:
        pass

    DeclaredProvider.__module__ = module_name
    module.DeclaredProvider = DeclaredProvider
    return module


def _declared_platform_module(
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    adapter_name: str,
) -> ModuleType:
    """Create an already-imported module with one platform declaration."""

    module = ModuleType(module_name)
    monkeypatch.setitem(sys.modules, module_name, module)

    @register_platform_adapter(adapter_name, f"{adapter_name} description")
    class DeclaredPlatform:
        pass

    DeclaredPlatform.__module__ = module_name
    module.DeclaredPlatform = DeclaredPlatform
    return module


def test_runtime_catalog_instances_do_not_share_mutable_registrations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = RuntimeCatalogs()
    second = RuntimeCatalogs()
    provider_module = _declared_provider_module(
        monkeypatch,
        "tests.runtime_catalogs.isolation.provider",
        "catalog-isolation-provider",
    )
    platform_module = _declared_platform_module(
        monkeypatch,
        "tests.runtime_catalogs.isolation.platform",
        "catalog-isolation-platform",
    )

    first.providers.register_module(provider_module)
    first.platforms.register_module(platform_module)
    first.plugins.publish(
        StarMetadata(
            name="Catalog isolation plugin",
            module_path="tests.runtime_catalogs.isolation.plugin",
        )
    )
    first.handlers.append(
        StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name="tests.runtime_catalogs.isolation.plugin.handler",
            handler_name="handler",
            handler_module_path="tests.runtime_catalogs.isolation.plugin",
            handler=_catalog_handler,
            event_filters=[],
        )
    )
    first.tools.add_tool(
        "catalog_isolation_tool",
        [],
        "Runtime-local test tool.",
        _catalog_handler,
    )

    assert first.providers.get("catalog-isolation-provider") is not None
    assert first.platforms.get("catalog-isolation-platform") is not None
    assert first.plugins.get_by_name("Catalog isolation plugin") is not None
    assert list(first.handlers)
    assert first.tools.get_tool("catalog_isolation_tool") is not None

    assert second.providers.registrations() == ()
    assert second.platforms.registrations() == ()
    assert second.plugins.all() == ()
    assert list(second.handlers) == []
    assert second.tools.func_list == []


def test_provider_catalog_scans_imported_module_and_unregisters_exact_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = RuntimeCatalogs().providers
    parent = _declared_provider_module(
        monkeypatch,
        "tests.runtime_catalogs.provider_source",
        "catalog-parent-provider",
    )
    child = _declared_provider_module(
        monkeypatch,
        "tests.runtime_catalogs.provider_source.child",
        "catalog-child-provider",
    )

    assert catalog.register_module(parent)[0].module_path == parent.__name__
    assert catalog.register_module(child)[0].module_path == child.__name__

    assert catalog.unregister_module(parent.__name__) == ("catalog-parent-provider",)
    assert catalog.get("catalog-parent-provider") is None
    assert catalog.get("catalog-child-provider") is not None


def test_platform_catalog_scans_imported_module_and_unregisters_exact_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = RuntimeCatalogs().platforms
    parent = _declared_platform_module(
        monkeypatch,
        "tests.runtime_catalogs.platform_source",
        "catalog-parent-platform",
    )
    child = _declared_platform_module(
        monkeypatch,
        "tests.runtime_catalogs.platform_source.child",
        "catalog-child-platform",
    )

    assert catalog.register_module(parent)[0].module_path == parent.__name__
    assert catalog.register_module(child)[0].module_path == child.__name__

    assert catalog.unregister_module(parent.__name__) == ("catalog-parent-platform",)
    assert catalog.get("catalog-parent-platform") is None
    assert catalog.get("catalog-child-platform") is not None


def test_builtin_pipeline_stage_order_is_a_fixed_tuple() -> None:
    from astrbot.core.pipeline.bootstrap import builtin_stage_classes

    stages = builtin_stage_classes()

    assert isinstance(stages, tuple)
    assert tuple(stage.__name__ for stage in stages) == (
        "WakingCheckStage",
        "WhitelistCheckStage",
        "SessionStatusCheckStage",
        "RateLimitStage",
        "ContentSafetyCheckStage",
        "PreProcessStage",
        "GroupMessageHistoryStage",
        "ProcessStage",
        "ResultDecorateStage",
        "RespondStage",
    )
