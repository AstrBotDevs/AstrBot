"""Commands from disabled plugins should not look enabled in the dashboard."""

from types import SimpleNamespace


def test_inactive_plugin_commands_are_not_effectively_enabled():
    from astrbot.core.star.command_management import (
        _apply_plugin_activation_to_descriptors,
        _is_plugin_activated,
        star_map,
    )

    original = dict(star_map)
    try:
        star_map.clear()
        star_map["data.plugins.foo.main"] = SimpleNamespace(activated=True)
        star_map["data.plugins.bar.main"] = SimpleNamespace(activated=False)

        active = SimpleNamespace(module_path="data.plugins.foo.main", enabled=True)
        inactive = SimpleNamespace(module_path="data.plugins.bar.main", enabled=True)
        unknown = SimpleNamespace(module_path="data.plugins.missing.main", enabled=True)

        _apply_plugin_activation_to_descriptors([active, inactive, unknown])

        assert _is_plugin_activated(active) is True
        assert _is_plugin_activated(inactive) is False
        assert _is_plugin_activated(unknown) is True
        assert active.enabled is True
        assert inactive.enabled is False
        assert unknown.enabled is True
    finally:
        star_map.clear()
        star_map.update(original)
