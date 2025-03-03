import pytest
import os
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

star_context = Context(event_queue, config, db)


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
async def test_plugin_crud(plugin_manager_pm: PluginManager):
    """测试插件安装和重载"""
    os.makedirs("data/plugins", exist_ok=True)
    test_repo = "https://github.com/Soulter/astrbot_plugin_essential"
    plugin_path = await plugin_manager_pm.install_plugin(test_repo)
    exists = False
    for md in star_registry:
        if md.name == "astrbot_plugin_essential":
            exists = True
            break
    assert plugin_path is not None
    assert os.path.exists(plugin_path)
    assert exists is True, "插件 astrbot_plugin_essential 未成功载入"
    # shutil.rmtree(plugin_path)

    # install plugin which is not exists
    with pytest.raises(Exception):
        plugin_path = await plugin_manager_pm.install_plugin(test_repo + "haha")

    # update
    await plugin_manager_pm.update_plugin("astrbot_plugin_essential")

    with pytest.raises(Exception):
        await plugin_manager_pm.update_plugin("astrbot_plugin_essentialhaha")

    # uninstall
    await plugin_manager_pm.uninstall_plugin("astrbot_plugin_essential")
    assert not os.path.exists(plugin_path)
    exists = False
    for md in star_registry:
        if md.name == "astrbot_plugin_essential":
            exists = True
            break
    assert exists is False, "插件 astrbot_plugin_essential 未成功卸载"
    exists = False
    for md in star_handlers_registry:
        if "astrbot_plugin_essential" in md.handler_module_path:
            exists = True
            break
    assert exists is False, "插件 astrbot_plugin_essential 未成功卸载"

    with pytest.raises(Exception):
        await plugin_manager_pm.uninstall_plugin("astrbot_plugin_essentialhaha")

    # TODO: file installation
