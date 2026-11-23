"""Plugin metadata has stable identifiers and isolated mutable fields."""

import pytest

from astrbot.core.star.star import StarMetadata


@pytest.mark.parametrize(
    ("name", "author", "expected"),
    [
        ("Weather", "Alice", "alice/weather"),
        ("team/plugin", "ORG/Owner", "org_owner/team_plugin"),
        (None, None, "unknown/unknown"),
        ("", "", "unknown/unknown"),
    ],
)
def test_plugin_id_is_normalized(name, author, expected: str) -> None:
    assert StarMetadata(name=name, author=author).plugin_id == expected


def test_metadata_collections_are_owned_by_each_plugin() -> None:
    first, second = StarMetadata(), StarMetadata()
    first.star_handler_full_names.append("plugin.handle")
    first.support_platforms.append("telegram")
    first.i18n["en-US"] = {"hello": "Hello"}
    first.views.append(object())
    assert second.star_handler_full_names == []
    assert second.support_platforms == []
    assert second.i18n == {}
    assert second.views == []


def test_metadata_description_contains_identity_and_version() -> None:
    metadata = StarMetadata(
        name="Weather", author="Alice", version="1.2.3", desc="Forecast"
    )
    assert str(metadata) == "Plugin Weather (1.2.3) by Alice: Forecast"
    assert repr(metadata) == str(metadata)
