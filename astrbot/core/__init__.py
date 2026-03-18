from __future__ import annotations

import os
from importlib import import_module
from typing import TYPE_CHECKING, Any

from .utils.astrbot_path import get_astrbot_data_path

if TYPE_CHECKING:
    from .config import AstrBotConfig
    from .db.sqlite import SQLiteDatabase
    from .file_token_service import FileTokenService
    from .log import LogBroker, LogManager
    from .utils.pip_installer import DependencyConflictError, PipInstaller
    from .utils.requirements_utils import (
        RequirementsPrecheckFailed,
        find_missing_requirements,
        find_missing_requirements_or_raise,
    )
else:
    AstrBotConfig: Any
    SQLiteDatabase: Any
    FileTokenService: Any
    LogBroker: Any
    LogManager: Any
    DependencyConflictError: Any
    PipInstaller: Any
    RequirementsPrecheckFailed: Any
    find_missing_requirements: Any
    find_missing_requirements_or_raise: Any
    astrbot_config: Any
    db_helper: Any
    file_token_service: Any
    html_renderer: Any
    logger: Any
    pip_installer: Any
    sp: Any

os.makedirs(get_astrbot_data_path(), exist_ok=True)

DEMO_MODE = os.getenv("DEMO_MODE", "False").strip().lower() in ("true", "1", "t")

__all__ = [
    "AstrBotConfig",
    "DEMO_MODE",
    "DependencyConflictError",
    "FileTokenService",
    "LogBroker",
    "LogManager",
    "PipInstaller",
    "RequirementsPrecheckFailed",
    "SQLiteDatabase",
    "astrbot_config",
    "db_helper",
    "file_token_service",
    "find_missing_requirements",
    "find_missing_requirements_or_raise",
    "html_renderer",
    "logger",
    "pip_installer",
    "sp",
]

_SINGLETON_CACHE: dict[str, Any] = {}


def _get_astrbot_config():
    config_module = import_module(".config", __name__)
    cached = _SINGLETON_CACHE.get("astrbot_config")
    if cached is None:
        cached = config_module.AstrBotConfig()
        _SINGLETON_CACHE["astrbot_config"] = cached
    return cached


def _get_log_manager():
    return import_module(".log", __name__).LogManager


def _get_logger():
    cached = _SINGLETON_CACHE.get("logger")
    if cached is None:
        logger_obj = _get_log_manager().GetLogger(log_name="astrbot")
        config = _get_astrbot_config()
        log_manager = _get_log_manager()
        log_manager.configure_logger(logger_obj, config)
        log_manager.configure_trace_logger(config)
        _SINGLETON_CACHE["logger"] = logger_obj
        cached = logger_obj
    return cached


def _get_db_helper():
    cached = _SINGLETON_CACHE.get("db_helper")
    if cached is None:
        sqlite_module = import_module(".db.sqlite", __name__)
        default_module = import_module(".config.default", __name__)
        cached = sqlite_module.SQLiteDatabase(default_module.DB_PATH)
        _SINGLETON_CACHE["db_helper"] = cached
    return cached


def _get_shared_preferences():
    cached = _SINGLETON_CACHE.get("sp")
    if cached is None:
        shared_preferences_module = import_module(".utils.shared_preferences", __name__)
        cached = shared_preferences_module.SharedPreferences(db_helper=_get_db_helper())
        _SINGLETON_CACHE["sp"] = cached
    return cached


def _get_file_token_service():
    cached = _SINGLETON_CACHE.get("file_token_service")
    if cached is None:
        service_module = import_module(".file_token_service", __name__)
        cached = service_module.FileTokenService()
        _SINGLETON_CACHE["file_token_service"] = cached
    return cached


def _get_html_renderer():
    cached = _SINGLETON_CACHE.get("html_renderer")
    if cached is None:
        renderer_module = import_module(".utils.t2i.renderer", __name__)
        config = _get_astrbot_config()
        endpoint = config.get("t2i_endpoint", "https://t2i.soulter.top/text2img")
        cached = renderer_module.HtmlRenderer(endpoint)
        _SINGLETON_CACHE["html_renderer"] = cached
    return cached


def _get_pip_installer():
    cached = _SINGLETON_CACHE.get("pip_installer")
    if cached is None:
        installer_module = import_module(".utils.pip_installer", __name__)
        config = _get_astrbot_config()
        cached = installer_module.PipInstaller(
            config.get("pip_install_arg", ""),
            config.get("pypi_index_url", None),
        )
        _SINGLETON_CACHE["pip_installer"] = cached
    return cached


def __getattr__(name: str) -> Any:
    if name == "AstrBotConfig":
        return import_module(".config", __name__).AstrBotConfig
    if name in {"LogBroker", "LogManager"}:
        module = import_module(".log", __name__)
        return getattr(module, name)
    if name == "DependencyConflictError":
        return import_module(".utils.pip_installer", __name__).DependencyConflictError
    if name == "FileTokenService":
        return import_module(".file_token_service", __name__).FileTokenService
    if name == "PipInstaller":
        return import_module(".utils.pip_installer", __name__).PipInstaller
    if name == "RequirementsPrecheckFailed":
        return import_module(
            ".utils.requirements_utils", __name__
        ).RequirementsPrecheckFailed
    if name == "SQLiteDatabase":
        return import_module(".db.sqlite", __name__).SQLiteDatabase
    if name == "find_missing_requirements":
        return import_module(
            ".utils.requirements_utils", __name__
        ).find_missing_requirements
    if name == "find_missing_requirements_or_raise":
        return import_module(
            ".utils.requirements_utils", __name__
        ).find_missing_requirements_or_raise
    if name == "astrbot_config":
        return _get_astrbot_config()
    if name == "logger":
        return _get_logger()
    if name == "db_helper":
        return _get_db_helper()
    if name == "sp":
        return _get_shared_preferences()
    if name == "file_token_service":
        return _get_file_token_service()
    if name == "html_renderer":
        return _get_html_renderer()
    if name == "pip_installer":
        return _get_pip_installer()
    raise AttributeError(name)
