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

event_queue = Queue()

config = AstrBotConfig()

db = SQLiteDatabase("data/data_v3.db")

# Create mock objects to satisfy the Context constructor
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


@pytest.fixture
def plugin_manager_pm():
    return PluginManager(star_context, config)


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
    """Tests successful plugin installation."""
    os.makedirs("data/plugins", exist_ok=True)
    test_repo = "https://github.com/Soulter/astrbot_plugin_essential"
    plugin_info = await plugin_manager_pm.install_plugin(test_repo)
    plugin_path = os.path.join(
        plugin_manager_pm.plugin_store_path, "astrbot_plugin_essential"
    )

    assert plugin_info is not None
    assert os.path.exists(plugin_path)
    assert any(
        md.name == "astrbot_plugin_essential" for md in star_registry
    ), "插件 astrbot_plugin_essential 未成功载入"

    # Cleanup after test
    await plugin_manager_pm.uninstall_plugin("astrbot_plugin_essential")


@pytest.mark.asyncio
async def test_install_nonexistent_plugin(plugin_manager_pm: PluginManager):
    """Tests that installing a non-existent plugin raises an exception."""
    with pytest.raises(Exception):
        await plugin_manager_pm.install_plugin(
            "https://github.com/Soulter/non_existent_repo"
        )


@pytest.mark.asyncio
async def test_update_plugin(plugin_manager_pm: PluginManager):
    """Tests updating an existing plugin."""
    # First, install the plugin
    test_repo = "https://github.com/Soulter/astrbot_plugin_essential"
    await plugin_manager_pm.install_plugin(test_repo)

    # Then, update it
    await plugin_manager_pm.update_plugin("astrbot_plugin_essential")

    # Cleanup after test
    await plugin_manager_pm.uninstall_plugin("astrbot_plugin_essential")


@pytest.mark.asyncio
async def test_update_nonexistent_plugin(plugin_manager_pm: PluginManager):
    """Tests that updating a non-existent plugin raises an exception."""
    with pytest.raises(Exception):
        await plugin_manager_pm.update_plugin("non_existent_plugin")


@pytest.mark.asyncio
async def test_uninstall_plugin(plugin_manager_pm: PluginManager):
    """Tests successful plugin uninstallation."""
    # First, install the plugin
    test_repo = "https://github.com/Soulter/astrbot_plugin_essential"
    await plugin_manager_pm.install_plugin(test_repo)
    plugin_path = os.path.join(
        plugin_manager_pm.plugin_store_path, "astrbot_plugin_essential"
    )

    # Then, uninstall it
    await plugin_manager_pm.uninstall_plugin("astrbot_plugin_essential")

    assert not os.path.exists(plugin_path)
    assert not any(
        md.name == "astrbot_plugin_essential" for md in star_registry
    ), "插件 astrbot_plugin_essential 未成功卸载"
    assert not any(
        "astrbot_plugin_essential" in md.handler_module_path
        for md in star_handlers_registry
    ), "插件 astrbot_plugin_essential handler 未成功卸载"


@pytest.mark.asyncio
async def test_uninstall_nonexistent_plugin(plugin_manager_pm: PluginManager):
    """Tests that uninstalling a non-existent plugin raises an exception."""
    with pytest.raises(Exception):
        await plugin_manager_pm.uninstall_plugin("non_existent_plugin")
