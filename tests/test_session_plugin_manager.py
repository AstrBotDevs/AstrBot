"""Import smoke tests for astrbot.core.star.session_plugin_manager."""
from astrbot.core.star.session_plugin_manager import (
    SessionPluginSettings,
    SessionPluginManager,
)


def test_session_plugin_settings_typed_dict():
    """SessionPluginSettings is importable and is a TypedDict."""
    assert isinstance(SessionPluginSettings, type)


def test_session_plugin_manager_class():
    """SessionPluginManager is importable and is a class."""
    assert isinstance(SessionPluginManager, type)
