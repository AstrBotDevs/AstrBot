"""Commands from disabled plugins should not look enabled in the dashboard."""

from types import SimpleNamespace

from astrbot.core.star.command_management import (
    CommandDescriptor,
    _descriptor_to_dict,
    _group_conflicts,
    _is_plugin_activated,
    star_map,
)


def _descriptor(module_path: str, *, enabled: bool = True) -> CommandDescriptor:
    return CommandDescriptor(
        handler=SimpleNamespace(),  # type: ignore[arg-type]
        module_path=module_path,
        enabled=enabled,
        effective_command="demo",
    )


def test_plugin_activation_is_serialized_without_mutating_enabled():
    original = dict(star_map)
    try:
        star_map.clear()
        star_map["data.plugins.foo.main"] = SimpleNamespace(activated=True)
        star_map["data.plugins.bar.main"] = SimpleNamespace(activated=False)

        active = _descriptor("data.plugins.foo.main", enabled=True)
        inactive = _descriptor("data.plugins.bar.main", enabled=True)
        unknown = _descriptor("data.plugins.missing.main", enabled=True)

        assert _is_plugin_activated(active) is True
        assert _is_plugin_activated(inactive) is False
        assert _is_plugin_activated(unknown) is True
        assert active.enabled is True
        assert inactive.enabled is True
        assert unknown.enabled is True

        active_dict = _descriptor_to_dict(active)
        inactive_dict = _descriptor_to_dict(inactive)
        unknown_dict = _descriptor_to_dict(unknown)

        assert active_dict["enabled"] is True
        assert inactive_dict["enabled"] is True
        assert unknown_dict["enabled"] is True
        assert active_dict["plugin_activated"] is True
        assert inactive_dict["plugin_activated"] is False
        assert unknown_dict["plugin_activated"] is True
    finally:
        star_map.clear()
        star_map.update(original)


def test_inactive_plugin_commands_are_excluded_from_conflicts():
    original = dict(star_map)
    try:
        star_map.clear()
        star_map["data.plugins.foo.main"] = SimpleNamespace(activated=True)
        star_map["data.plugins.bar.main"] = SimpleNamespace(activated=False)

        live = _descriptor("data.plugins.foo.main")
        off = _descriptor("data.plugins.bar.main")
        conflicts = _group_conflicts([live, off])

        assert conflicts == {}
    finally:
        star_map.clear()
        star_map.update(original)
