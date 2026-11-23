"""Plugin session settings use persisted, isolated configuration overrides."""

import asyncio

import pytest

from astrbot.core import session_overrides as overrides
from astrbot.core.config_bindings import BINDING_KEY


@pytest.fixture
def plugin_preferences(monkeypatch, shared_preferences):
    monkeypatch.setattr(overrides, "sp", shared_preferences)
    monkeypatch.setattr(overrides, "_locks", [asyncio.Lock() for _ in range(64)])
    return shared_preferences


def test_plugin_lists_replace_profile_values_without_mutating_the_profile():
    profile = {"plugin_set": ["default"], "disabled_plugins": ["disabled"]}
    values = {"plugin_set": [], "disabled_plugins": ["private"]}
    resolved = overrides.apply_overrides(profile, values)

    assert resolved == {"plugin_set": [], "disabled_plugins": ["private"]}
    resolved["disabled_plugins"].append("extra")
    assert profile == {"plugin_set": ["default"], "disabled_plugins": ["disabled"]}
    assert values == {"plugin_set": [], "disabled_plugins": ["private"]}


@pytest.mark.asyncio
async def test_plugin_selection_persists_only_for_its_exact_session(plugin_preferences):
    umo = "test:GroupMessage:room-a"
    expected = {"plugin_set": ["weather"], "disabled_plugins": ["admin"]}
    assert await overrides.update_overrides(umo, expected) == expected
    assert await overrides.get_overrides(umo) == expected
    assert await overrides.get_overrides("test:GroupMessage:room-b") == {}
    binding = await plugin_preferences.session_get(umo, BINDING_KEY)
    assert binding == {"profile_id": None, "overrides": expected}


@pytest.mark.asyncio
async def test_removing_plugin_override_restores_inheritance_and_keeps_profile(
    plugin_preferences,
):
    umo = "test:FriendMessage:user"
    await overrides.update_overrides(
        umo,
        {"plugin_set": ["weather"], "disabled_plugins": ["admin"]},
        profile_id="profile-a",
        update_profile=True,
    )
    assert await overrides.update_overrides(umo, {"plugin_set": None}) == {
        "disabled_plugins": ["admin"]
    }
    assert await plugin_preferences.session_get(umo, BINDING_KEY) == {
        "profile_id": "profile-a",
        "overrides": {"disabled_plugins": ["admin"]},
    }
    await overrides.update_overrides(
        umo, {}, profile_id=None, update_profile=True, clear_overrides=True
    )
    assert await plugin_preferences.session_get(umo, BINDING_KEY) is None


@pytest.mark.asyncio
async def test_concurrent_plugin_patches_preserve_both_changes(plugin_preferences):
    umo = "test:GroupMessage:shared"
    await asyncio.gather(
        overrides.update_overrides(umo, {"plugin_set": ["weather"]}),
        overrides.update_overrides(umo, {"disabled_plugins": ["admin"]}),
    )
    assert await overrides.get_overrides(umo) == {
        "plugin_set": ["weather"],
        "disabled_plugins": ["admin"],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [True, "weather", [1], {"weather": True}])
async def test_invalid_plugin_selection_does_not_replace_persisted_settings(
    plugin_preferences, value
):
    umo = "test:FriendMessage:user"
    await overrides.update_overrides(umo, {"plugin_set": ["weather"]})
    with pytest.raises(ValueError):
        await overrides.update_overrides(umo, {"plugin_set": value})
    assert await overrides.get_overrides(umo) == {"plugin_set": ["weather"]}
