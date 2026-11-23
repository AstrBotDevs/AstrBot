"""Legacy registration preserves class identity and existing plugin metadata."""

import importlib

import pytest

from astrbot.core.star.star import StarMetadata

registration = importlib.import_module("astrbot.core.star.register.star")


def test_legacy_registration_creates_metadata_and_warns(monkeypatch) -> None:
    monkeypatch.setattr(registration, "star_map", {})
    monkeypatch.setattr(registration, "_warned_register_star", False)

    class Plugin:
        pass

    with pytest.warns(DeprecationWarning, match="deprecated"):
        decorate = registration.register_star(
            "weather", "author", "forecast", "1.0", "https://example.invalid/repo"
        )
    assert decorate(Plugin) is Plugin
    metadata = registration.star_map[Plugin.__module__]
    assert (
        metadata.name,
        metadata.author,
        metadata.desc,
        metadata.version,
        metadata.repo,
    ) == ("weather", "author", "forecast", "1.0", "https://example.invalid/repo")


def test_legacy_registration_updates_metadata_without_replacing_runtime_state(
    monkeypatch,
) -> None:
    class Plugin:
        pass

    metadata = StarMetadata(star_cls_type=Plugin, activated=False, reserved=True)
    monkeypatch.setattr(registration, "star_map", {Plugin.__module__: metadata})
    monkeypatch.setattr(registration, "_warned_register_star", True)
    assert (
        registration.register_star("new-name", "author", "description", "2.0")(Plugin)
        is Plugin
    )
    assert registration.star_map[Plugin.__module__] is metadata
    assert metadata.name == "new-name" and metadata.version == "2.0"
    assert metadata.star_cls_type is Plugin
    assert metadata.activated is False and metadata.reserved is True
