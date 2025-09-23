import pytest
import os
from unittest.mock import MagicMock
from astrbot.core.star.star_manager import PluginManager
from astrbot.core.star.star_handler import star_handlers_registry
from astrbot.core.star.star import star_registry
from astrbot.core.star.context import Context
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.db.sqlite import SQLiteDatabase
from asyncio import Queue


@pytest.fixture
def plugin_manager_pm(tmp_path):
    """
    Provides a fully isolated PluginManager instance for testing.
    - Uses a temporary directory for plugins.
    - Uses a temporary database.
    - Creates a fresh context for each test.
    """
    # Create temporary resources
    temp_plugins_path = tmp_path / "plugins"
    temp_plugins_path.mkdir()
    temp_db_path = tmp_path / "test_db.db"

    # Create fresh, isolated instances for the context
    event_queue = Queue()
    config = AstrBotConfig()
    db = SQLiteDatabase(str(temp_db_path))

    # Set the plugin store path in the config to the temporary directory
    config.plugin_store_path = str(temp_plugins_path)

    # Mock dependencies for the context
    provider_manager = MagicMock()
    platform_manager = MagicMock()
    conversation_manager = MagicMock()
    message_history_manager = MagicMock()
    persona_manager = MagicMock()
    astrbot_config_mgr = MagicMock()

    star_context = Context(
        event_queue,
        config,
        db,
        provider_manager,
        platform_manager,
        conversation_manager,
        message_history_manager,
        persona_manager,
        astrbot_config_mgr,
    )

    # Create the PluginManager instance
    manager = PluginManager(star_context, config)
    yield manager


def test_plugin_manager_initialization(plugin_manager_pm: PluginManager):
    assert plugin_manager_pm is not None
    assert plugin_manager_pm.context is not None
    assert plugin_manager_pm.config is not None


@pytest.mark.asyncio
async def test_plugin_manager_reload(plugin_manager_pm: PluginManager):
    success, err_message = await plugin_manager_pm.reload()
    assert success is True
    assert err_message is None


@pytest.mark.asyncio
async def test_install_plugin(plugin_manager_pm: PluginManager):
    """Tests successful plugin installation in an isolated environment."""
    test_repo = "https://github.com/Soulter/astrbot_plugin_essential"
    plugin_info = await plugin_manager_pm.install_plugin(test_repo)
    plugin_path = os.path.join(
        plugin_manager_pm.plugin_store_path, "astrbot_plugin_essential"
    )

    assert plugin_info is not None
    assert os.path.exists(plugin_path)
    assert any(md.name == "astrbot_plugin_essential" for md in star_registry), (
        "Plugin 'astrbot_plugin_essential' was not loaded into star_registry."
    )


@pytest.mark.asyncio
async def test_install_nonexistent_plugin(plugin_manager_pm: PluginManager):
    """Tests that installing a non-existent plugin raises an exception."""
    with pytest.raises(Exception):
        await plugin_manager_pm.install_plugin(
            "https://github.com/Soulter/non_existent_repo"
        )


@pytest.mark.asyncio
async def test_update_plugin(plugin_manager_pm: PluginManager):
    """Tests updating an existing plugin in an isolated environment."""
    # First, install the plugin
    test_repo = "https://github.com/Soulter/astrbot_plugin_essential"
    await plugin_manager_pm.install_plugin(test_repo)

    # Then, update it
    await plugin_manager_pm.update_plugin("astrbot_plugin_essential")


@pytest.mark.asyncio
async def test_update_nonexistent_plugin(plugin_manager_pm: PluginManager):
    """Tests that updating a non-existent plugin raises an exception."""
    with pytest.raises(Exception):
        await plugin_manager_pm.update_plugin("non_existent_plugin")


@pytest.mark.asyncio
async def test_uninstall_plugin(plugin_manager_pm: PluginManager):
    """Tests successful plugin uninstallation in an isolated environment."""
    # First, install the plugin
    test_repo = "https://github.com/Soulter/astrbot_plugin_essential"
    await plugin_manager_pm.install_plugin(test_repo)
    plugin_path = os.path.join(
        plugin_manager_pm.plugin_store_path, "astrbot_plugin_essential"
    )
    assert os.path.exists(plugin_path)  # Pre-condition

    # Then, uninstall it
    await plugin_manager_pm.uninstall_plugin("astrbot_plugin_essential")

    assert not os.path.exists(plugin_path)
    assert not any(md.name == "astrbot_plugin_essential" for md in star_registry), (
        "Plugin 'astrbot_plugin_essential' was not unloaded from star_registry."
    )
    assert not any(
        "astrbot_plugin_essential" in md.handler_module_path
        for md in star_handlers_registry
    ), (
        "Plugin 'astrbot_plugin_essential' handler was not unloaded from star_handlers_registry."
    )


@pytest.mark.asyncio
async def test_uninstall_nonexistent_plugin(plugin_manager_pm: PluginManager):
    """Tests that uninstalling a non-existent plugin raises an exception."""
    with pytest.raises(Exception):
        await plugin_manager_pm.uninstall_plugin("non_existent_plugin")
