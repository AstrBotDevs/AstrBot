from __future__ import annotations

import pytest

from astrbot.core.platform.register import (
    platform_cls_map,
    platform_registry,
    register_platform_adapter,
)


@pytest.mark.unit
def test_register_platform_adapter_is_idempotent_for_same_module_and_class_name() -> (
    None
):
    adapter_name = "test_repeatable_platform"
    original_registry = list(platform_registry)
    original_cls_map = dict(platform_cls_map)

    try:
        def _build_adapter():
            class RepeatablePlatform:
                pass

            RepeatablePlatform.__module__ = "tests.repeatable_platform"
            RepeatablePlatform.__qualname__ = "RepeatablePlatform"
            return register_platform_adapter(adapter_name, "repeatable")(RepeatablePlatform)

        first = _build_adapter()
        second = _build_adapter()

        assert first.__module__ == second.__module__
        assert first.__qualname__ == second.__qualname__
        assert platform_cls_map[adapter_name] is second
        assert [item.name for item in platform_registry].count(adapter_name) == 1
    finally:
        platform_registry[:] = original_registry
        platform_cls_map.clear()
        platform_cls_map.update(original_cls_map)


@pytest.mark.unit
def test_register_platform_adapter_still_rejects_real_name_conflicts() -> None:
    adapter_name = "test_conflicting_platform"
    original_registry = list(platform_registry)
    original_cls_map = dict(platform_cls_map)

    try:
        class FirstPlatform:
            pass

        FirstPlatform.__module__ = "tests.first_platform"
        FirstPlatform.__qualname__ = "FirstPlatform"
        register_platform_adapter(adapter_name, "first")(FirstPlatform)

        class SecondPlatform:
            pass

        SecondPlatform.__module__ = "tests.second_platform"
        SecondPlatform.__qualname__ = "SecondPlatform"

        with pytest.raises(ValueError, match=adapter_name):
            register_platform_adapter(adapter_name, "second")(SecondPlatform)
    finally:
        platform_registry[:] = original_registry
        platform_cls_map.clear()
        platform_cls_map.update(original_cls_map)
