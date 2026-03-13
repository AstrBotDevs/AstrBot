"""旧版 ``astrbot.core.utils.astrbot_path`` 兼容入口。"""

from __future__ import annotations

import os
from pathlib import Path


def get_astrbot_path() -> str:
    """返回当前兼容 SDK 的项目根路径。"""

    return str(Path(__file__).resolve().parents[4])


def get_astrbot_root() -> str:
    """返回 AstrBot 运行根目录。

    旧版优先读取 ``ASTRBOT_ROOT``，否则默认当前工作目录。compat 层保持
    这个约定，方便旧插件继续把数据写到 ``<root>/data`` 下。
    """

    root = os.environ.get("ASTRBOT_ROOT")
    if root:
        return str(Path(root).resolve())
    return str(Path.cwd().resolve())


def _data_child(*parts: str) -> str:
    return str(Path(get_astrbot_data_path(), *parts).resolve())


def get_astrbot_data_path() -> str:
    return str(Path(get_astrbot_root(), "data").resolve())


def get_astrbot_config_path() -> str:
    return _data_child("config")


def get_astrbot_plugin_path() -> str:
    return _data_child("plugins")


def get_astrbot_plugin_data_path() -> str:
    return _data_child("plugin_data")


def get_astrbot_t2i_templates_path() -> str:
    return _data_child("t2i_templates")


def get_astrbot_webchat_path() -> str:
    return _data_child("webchat")


def get_astrbot_temp_path() -> str:
    return _data_child("temp")


def get_astrbot_skills_path() -> str:
    return _data_child("skills")


def get_astrbot_site_packages_path() -> str:
    return _data_child("site-packages")


def get_astrbot_knowledge_base_path() -> str:
    return _data_child("knowledge_base")


def get_astrbot_backups_path() -> str:
    return _data_child("backups")
