"""Import smoke tests for astrbot.core.star.star_manager."""
from astrbot.core.star.star_manager import (
    PluginManager,
    PluginVersionIncompatibleError,
    PluginDependencyInstallError,
)


def test_plugin_version_incompatible_error():
    """PluginVersionIncompatibleError is importable and instantiable."""
    exc = PluginVersionIncompatibleError("test")
    assert isinstance(exc, Exception)
    assert str(exc) == "test"


def test_plugin_dependency_install_error():
    """PluginDependencyInstallError is importable and instantiable."""
    try:
        raise ValueError("oh no")
    except ValueError as e:
        exc = PluginDependencyInstallError(
            plugin_label="my_plugin",
            requirements_path="/path/to/requirements.txt",
            error=e,
        )
    assert isinstance(exc, Exception)
    assert exc.plugin_label == "my_plugin"
    assert exc.requirements_path == "/path/to/requirements.txt"


def test_plugin_manager_class():
    """PluginManager is importable and is a class."""
    assert isinstance(PluginManager, type)
