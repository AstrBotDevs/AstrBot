"""Plugin adapter registration is removable without affecting replacements."""

import pytest

from astrbot.core.provider.register import (
    provider_cls_map,
    provider_registry,
    register_provider_adapter,
    unregister_provider_adapter,
)


@pytest.fixture
def adapter_type():
    name = "test_plugin_oauth_registration"
    yield name
    metadata = provider_cls_map.get(name)
    if metadata is not None:
        unregister_provider_adapter(name, metadata.cls_type)


def test_unregister_removes_both_indexes_and_allows_reload(adapter_type):
    first = register_provider_adapter(adapter_type, "test")(type("First", (), {}))
    metadata = provider_cls_map[adapter_type]
    assert metadata in provider_registry
    assert unregister_provider_adapter(adapter_type, first)
    assert adapter_type not in provider_cls_map
    assert metadata not in provider_registry
    second = register_provider_adapter(adapter_type, "test")(type("Second", (), {}))
    assert provider_cls_map[adapter_type].cls_type is second


def test_old_plugin_cannot_remove_replacement(adapter_type):
    first = register_provider_adapter(adapter_type, "test")(type("First", (), {}))
    assert unregister_provider_adapter(adapter_type, first)
    second = register_provider_adapter(adapter_type, "test")(type("Second", (), {}))
    assert not unregister_provider_adapter(adapter_type, first)
    assert provider_cls_map[adapter_type].cls_type is second


def test_unregister_is_idempotent_and_collision_remains_an_error(adapter_type):
    first = register_provider_adapter(adapter_type, "test")(type("First", (), {}))
    with pytest.raises(ValueError):
        register_provider_adapter(adapter_type, "test")(type("Second", (), {}))
    assert provider_cls_map[adapter_type].cls_type is first
    assert unregister_provider_adapter(adapter_type, first)
    assert not unregister_provider_adapter(adapter_type, first)
