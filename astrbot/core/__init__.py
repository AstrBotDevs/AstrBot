import os

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

from .log import LogBroker, LogManager
from .utils.astrbot_path import (
    get_astrbot_config_path,
    get_astrbot_data_path,
    get_astrbot_knowledge_base_path,
    get_astrbot_plugin_path,
    get_astrbot_site_packages_path,
    get_astrbot_skills_path,
    get_astrbot_temp_path,
)

# Initialize required data directories eagerly so later agent/tool flows do not
# fail on missing paths when the runtime root resolves to a fresh location.
for required_dir in (
    get_astrbot_data_path(),
    get_astrbot_config_path(),
    get_astrbot_plugin_path(),
    get_astrbot_temp_path(),
    get_astrbot_knowledge_base_path(),
    get_astrbot_skills_path(),
    get_astrbot_site_packages_path(),
):
    os.makedirs(required_dir, exist_ok=True)

DEMO_MODE = os.getenv("DEMO_MODE", "False").strip().lower() in ("true", "1", "t")

astrbot_config = AstrBotConfig()
t2i_base_url = astrbot_config.get("t2i_endpoint", "https://t2i.soulter.top/text2img")
html_renderer = HtmlRenderer(t2i_base_url)
logger = LogManager.GetLogger(log_name="astrbot")
LogManager.configure_logger(
    logger, astrbot_config, override_level=os.getenv("ASTRBOT_LOG_LEVEL")
)
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
__all__ = [
    "AstrBotConfig",
    "DEMO_MODE",
    "astrbot_config",
    "t2i_base_url",
    "html_renderer",
    "logger",
    "LogBroker",
    "LogManager",
    "db_helper",
    "sp",
    "file_token_service",
    "pip_installer",
]
