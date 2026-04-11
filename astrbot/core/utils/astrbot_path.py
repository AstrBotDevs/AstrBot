"""Centralized AstrBot path helpers.

Project path:
- Fixed to the source tree location.

Root path:
- Defaults to the current working directory.
- Can be overridden with the ``ASTRBOT_ROOT`` environment variable.

Data subdirectories:
- Most runtime data lives under ``<root>/data``.
- A few tool-runtime files intentionally live under the system temporary
  directory as ``.astrbot``.
"""

import os
import tempfile

from astrbot.core.utils.runtime_env import is_packaged_desktop_runtime


def get_astrbot_path() -> str:
    """Return the AstrBot project source path."""
    return os.path.realpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../"),
    )


def get_astrbot_root() -> str:
    """Return the AstrBot root directory."""
    if path := os.environ.get("ASTRBOT_ROOT"):
        return os.path.realpath(path)
    if is_packaged_desktop_runtime():
        return os.path.realpath(os.path.join(os.path.expanduser("~"), ".astrbot"))
    return os.path.realpath(os.getcwd())


def get_astrbot_data_path() -> str:
    """Return the AstrBot data directory path."""
    return os.path.realpath(os.path.join(get_astrbot_root(), "data"))


def get_astrbot_config_path() -> str:
    """Return the AstrBot config directory path."""
    return os.path.realpath(os.path.join(get_astrbot_data_path(), "config"))


def get_astrbot_plugin_path() -> str:
    """Return the AstrBot plugin directory path."""
    return os.path.realpath(os.path.join(get_astrbot_data_path(), "plugins"))


def get_astrbot_plugin_data_path() -> str:
    """Return the AstrBot plugin data directory path."""
    return os.path.realpath(os.path.join(get_astrbot_data_path(), "plugin_data"))


def get_astrbot_t2i_templates_path() -> str:
    """Return the AstrBot T2I templates directory path."""
    return os.path.realpath(os.path.join(get_astrbot_data_path(), "t2i_templates"))


def get_astrbot_webchat_path() -> str:
    """Return the AstrBot WebChat data directory path."""
    return os.path.realpath(os.path.join(get_astrbot_data_path(), "webchat"))


def get_astrbot_temp_path() -> str:
    """Return the AstrBot temporary data directory path."""
    return os.path.realpath(os.path.join(get_astrbot_data_path(), "temp"))


def get_astrbot_skills_path() -> str:
    """Return the AstrBot skills directory path."""
    return os.path.realpath(os.path.join(get_astrbot_data_path(), "skills"))


def get_astrbot_workspaces_path() -> str:
    """Return the AstrBot workspaces directory path."""
    return os.path.realpath(os.path.join(get_astrbot_data_path(), "workspaces"))


def get_astrbot_system_tmp_path() -> str:
    """Return the shared system temporary directory used by local tools."""
    return os.path.realpath(os.path.join(tempfile.gettempdir(), ".astrbot"))


def get_astrbot_site_packages_path() -> str:
    """Return the AstrBot third-party site-packages directory path."""
    return os.path.realpath(os.path.join(get_astrbot_data_path(), "site-packages"))


def get_astrbot_knowledge_base_path() -> str:
    """Return the AstrBot knowledge base root path."""
    return os.path.realpath(os.path.join(get_astrbot_data_path(), "knowledge_base"))


def get_astrbot_backups_path() -> str:
    """Return the AstrBot backups directory path."""
    return os.path.realpath(os.path.join(get_astrbot_data_path(), "backups"))
