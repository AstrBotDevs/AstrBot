import os
from typing import TYPE_CHECKING

from astrbot.core.config import AstrBotConfig
from astrbot.core.config.default import DB_PATH
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.file_token_service import FileTokenService
from astrbot.core.utils.pip_installer import (
    DependencyConflictError as DependencyConflictError,
)
from astrbot.core.utils.pip_installer import (
    PipInstaller,
)
from astrbot.core.utils.requirements_utils import (
    RequirementsPrecheckFailed as RequirementsPrecheckFailed,
)
from astrbot.core.utils.requirements_utils import (
    find_missing_requirements as find_missing_requirements,
)
from astrbot.core.utils.requirements_utils import (
    find_missing_requirements_or_raise as find_missing_requirements_or_raise,
)
from astrbot.core.utils.shared_preferences import SharedPreferences
from astrbot.core.utils.t2i.renderer import HtmlRenderer

from .log import LogBroker, LogManager  # noqa
from .utils.astrbot_path import get_astrbot_data_path

DEMO_MODE = os.getenv("DEMO_MODE", "False").strip().lower() in ("true", "1", "t")

_initialized = False

if TYPE_CHECKING:
    import logging

    astrbot_config: AstrBotConfig
    t2i_base_url: str
    html_renderer: HtmlRenderer
    logger: logging.Logger
    db_helper: SQLiteDatabase
    sp: SharedPreferences
    file_token_service: FileTokenService
    pip_installer: PipInstaller

# PEP 562 module-level __getattr__ and __dir__ for lazy loading of global instances
_lazy_attrs = {
    "astrbot_config",
    "t2i_base_url",
    "html_renderer",
    "logger",
    "db_helper",
    "sp",
    "file_token_service",
    "pip_installer",
}


def _bootstrap():
    """
    internal initialization function, triggered only on first access to global instances.
    Do not call this function directly from outside.
    """
    global _initialized

    if _initialized:
        return

    global \
        astrbot_config, \
        t2i_base_url, \
        html_renderer, \
        logger, \
        db_helper, \
        sp, \
        file_token_service, \
        pip_installer

    # 初始化数据存储文件夹
    os.makedirs(get_astrbot_data_path(), exist_ok=True)

    astrbot_config = AstrBotConfig()
    t2i_base_url = astrbot_config.get(
        "t2i_endpoint", "https://t2i.soulter.top/text2img"
    )
    html_renderer = HtmlRenderer(t2i_base_url)
    logger = LogManager.GetLogger(log_name="astrbot")
    LogManager.configure_logger(logger, astrbot_config)
    LogManager.configure_trace_logger(astrbot_config)
    db_helper = SQLiteDatabase(DB_PATH)
    # 简单的偏好设置存储, 这里后续应该存储到数据库中, 一些部分可以存储到配置中
    sp = SharedPreferences(db_helper=db_helper)
    # 文件令牌服务
    file_token_service = FileTokenService()
    pip_installer = PipInstaller(
        astrbot_config.get("pip_install_arg", ""),
        astrbot_config.get("pypi_index_url", None),
    )

    _initialized = True


def __getattr__(name: str):
    """lazy load global instances on first access"""
    if name in _lazy_attrs:
        _bootstrap()
        return globals()[name]
    raise AttributeError(f"module 'astrbot.core' has no attribute {name!r}")


def __dir__():
    """make sure dir() and IDE completion can discover lazy-loaded attributes"""
    # auto-collect all public symbols in the module __dict__ that do not start with an underscore
    public_api = {k for k in globals() if not k.startswith("_")}
    return sorted(public_api | _lazy_attrs)
