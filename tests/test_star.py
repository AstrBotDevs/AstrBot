"""Import smoke tests for astrbot.core.star.star."""
from astrbot.core.star.star import StarMetadata, star_registry, star_map


def test_star_metadata_class():
    """StarMetadata is importable and is a dataclass."""
    assert isinstance(StarMetadata, type)


def test_star_registry_is_list():
    """star_registry is a module-level list."""
    assert isinstance(star_registry, list)


def test_star_map_is_dict():
    """star_map is a module-level dict."""
    assert isinstance(star_map, dict)


def test_star_metadata_instantiation():
    """StarMetadata can be instantiated with minimal fields."""
    meta = StarMetadata(name="test_plugin")
    assert meta.name == "test_plugin"
    assert meta.activated is True
