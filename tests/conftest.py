import sys
import os

# 将项目根目录添加到 sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from unittest import mock
from unittest.mock import AsyncMock

from astrbot.core.config.astrbot_config import AstrBotConfig
import inspect
from types import ModuleType
from astrbot.core.star import Star
from apscheduler.schedulers.asyncio import AsyncIOScheduler


# 全局变量，用于持有 mock 对象
_db_mock = None

@pytest.fixture(scope="function", autouse=True)
def patch_plugin_loading(monkeypatch):
    """
    通过猴子补丁修复插件加载和关闭逻辑中的问题，仅在测试期间生效。
    """
    # 补丁 _get_classes 方法以正确识别所有插件类
    def new_get_classes(self, arg: ModuleType):
        classes = []
        for name, obj in inspect.getmembers(arg, inspect.isclass):
            if issubclass(obj, Star) and obj is not Star:
                classes.append(name)
        return classes

    monkeypatch.setattr(
        "astrbot.core.star.star_manager.PluginManager._get_classes",
        new_get_classes
    )

    # 补丁 apscheduler的shutdown方法以避免事件循环关闭的错误
    async def mock_shutdown(*args, **kwargs):
        pass

    monkeypatch.setattr(
        AsyncIOScheduler,
        "shutdown",
        mock_shutdown
    )


@pytest.fixture(scope="function")
def config():
    """
    提供一个干净的、从文件加载的配置对象。
    每次测试函数都会重新加载，以保证测试隔离。
    """
    # 加载项目中的实际配置文件 data/cmd_config.json，
    return AstrBotConfig(config_path="data/cmd_config.json")

def pytest_configure(config):
    """
    在 pytest 启动时应用全局模拟，以防止导入时副作用。
    """
    global _db_mock
    # 模拟掉类本身，以防止它们的构造函数在导入时被调用并产生副作用
    db_mock_instance = mock.MagicMock()
    db_mock_instance.initialize = AsyncMock()
    db_mock_instance.get_personas = AsyncMock(return_value=[])
    _db_mock = mock.patch('astrbot.core.db.sqlite.SQLiteDatabase', return_value=db_mock_instance)

    # 启动模拟
    _db_mock.start()


def pytest_unconfigure(config):
    """
    在 pytest 会话结束时停止模拟。
    """
    global _db_mock
    if _db_mock:
        _db_mock.stop()