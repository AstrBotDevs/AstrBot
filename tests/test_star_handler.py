"""Import smoke tests for astrbot.core.star.star_handler."""
from astrbot.core.star.star_handler import (
    StarHandlerRegistry,
    StarHandlerMetadata,
    EventType,
    star_handlers_registry,
)


def test_star_handler_registry_class():
    """StarHandlerRegistry is importable and is a class."""
    assert isinstance(StarHandlerRegistry, type)


def test_star_handler_registry_default_instance():
    """star_handlers_registry is a module-level StarHandlerRegistry instance."""
    assert isinstance(star_handlers_registry, StarHandlerRegistry)


def test_star_handler_metadata_class():
    """StarHandlerMetadata is importable and is a dataclass."""
    assert isinstance(StarHandlerMetadata, type)


def test_event_type_enum():
    """EventType is an enum with expected members."""
    assert hasattr(EventType, "AdapterMessageEvent")
    assert hasattr(EventType, "OnLLMRequestEvent")
    assert hasattr(EventType, "OnLLMResponseEvent")
    assert hasattr(EventType, "OnAstrBotLoadedEvent")
    assert hasattr(EventType, "OnPluginLoadedEvent")
    assert hasattr(EventType, "OnPluginUnloadedEvent")
