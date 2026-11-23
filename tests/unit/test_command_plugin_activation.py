"""Dashboard command state distinguishes handler enablement from plugin activation."""

import pytest

from astrbot.core.star import command_management as management
from astrbot.core.star.star import StarMetadata
from astrbot.core.star.star_handler import EventType, StarHandlerMetadata


@pytest.fixture
def plugins(monkeypatch):
    metadata = {
        "data.plugins.active.main": StarMetadata(name="active", activated=True),
        "data.plugins.inactive.main": StarMetadata(name="inactive", activated=False),
    }
    monkeypatch.setattr(management, "star_map", metadata)
    return metadata


def descriptor(module_path, *, enabled=True):
    async def handler(event):
        return event

    metadata = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        f"{module_path}_demo",
        "demo",
        module_path,
        handler,
        [],
    )
    return management.CommandDescriptor(
        handler=metadata,
        module_path=module_path,
        enabled=enabled,
        effective_command="demo",
    )


@pytest.mark.parametrize(
    ("plugin", "activated"), [("active", True), ("inactive", False), ("missing", True)]
)
@pytest.mark.parametrize("enabled", [True, False])
def test_activation_serialization_preserves_handler_enablement(
    plugins, plugin, activated, enabled
):
    command = descriptor(f"data.plugins.{plugin}.main", enabled=enabled)
    assert management._is_plugin_activated(command) is activated
    serialized = management._descriptor_to_dict(command)
    assert serialized["enabled"] is enabled
    assert serialized["plugin_activated"] is activated
    assert command.enabled is enabled


def test_disabled_plugin_and_disabled_command_do_not_create_conflicts(plugins):
    live = descriptor("data.plugins.active.main")
    inactive = descriptor("data.plugins.inactive.main")
    disabled = descriptor("data.plugins.active.main", enabled=False)
    assert management._group_conflicts([live, inactive, disabled]) == {}
    second = descriptor("data.plugins.active.main")
    assert management._group_conflicts([live, second, inactive, disabled]) == {
        "demo": [live, second]
    }
