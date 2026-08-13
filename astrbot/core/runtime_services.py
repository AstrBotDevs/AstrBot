"""Explicitly constructed runtime-owned services.

Importing this module only defines the factory; it does not touch user data,
create directories, start schedulers, or configure logging.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from astrbot.core.agent.follow_up import FollowUpCoordinator
from astrbot.core.agent.tool_image_cache import ToolImageCache
from astrbot.core.auth.service import AuthorizationService
from astrbot.core.computer.computer_client import ComputerRuntime
from astrbot.core.config import AstrBotConfig
from astrbot.core.config.default import DB_PATH
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.file_token_service import FileTokenService
from astrbot.core.log import LogManager
from astrbot.core.runtime_catalogs import RuntimeCatalogs
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.llm_metadata import LLMMetadataCatalog
from astrbot.core.utils.metrics import MetricsRuntime
from astrbot.core.utils.pip_installer import PipInstaller
from astrbot.core.utils.shared_preferences import SharedPreferences
from astrbot.core.utils.t2i.renderer import HtmlRenderer
from astrbot.core.utils.totp import TotpRuntimeState
from astrbot.core.webchat.queue_manager import WebChatQueueManager
from astrbot.core.webchat.run_coordinator import WebChatRunCoordinator


@dataclass(slots=True)
class RuntimeServices:
    """Services owned by one AstrBot runtime instance."""

    config: AstrBotConfig
    catalogs: RuntimeCatalogs
    db: SQLiteDatabase
    preferences: SharedPreferences
    html_renderer: HtmlRenderer
    file_token_service: FileTokenService
    pip_installer: PipInstaller
    webchat_queue_manager: WebChatQueueManager
    webchat_run_coordinator: WebChatRunCoordinator
    follow_up_coordinator: FollowUpCoordinator
    llm_metadata_catalog: LLMMetadataCatalog
    metrics: MetricsRuntime
    computer_runtime: ComputerRuntime
    tool_image_cache: ToolImageCache
    totp_runtime_state: TotpRuntimeState
    demo_mode: bool
    authorization: AuthorizationService | None = None


def create_runtime_services() -> RuntimeServices:
    """Create runtime services after the process environment has been prepared."""
    config = AstrBotConfig()
    # configure_logger adjusts settings; GetLogger installs the output bridge.
    runtime_logger = LogManager.GetLogger("astrbot")
    LogManager.configure_logger(runtime_logger, config)
    LogManager.configure_trace_logger(config)
    db = SQLiteDatabase(DB_PATH)
    authorization = AuthorizationService(db)
    webchat_queue_manager = WebChatQueueManager()
    computer_runtime = ComputerRuntime()
    tool_image_cache = ToolImageCache(
        Path(get_astrbot_temp_path()) / ToolImageCache.CACHE_DIR_NAME
    )
    catalogs = RuntimeCatalogs()
    html_renderer = HtmlRenderer()
    file_token_service = FileTokenService()
    pip_installer = PipInstaller(
        config.get("pip_install_arg", ""),
        config.get("pypi_index_url", None),
    )
    webchat_run_coordinator = WebChatRunCoordinator(webchat_queue_manager)
    follow_up_coordinator = FollowUpCoordinator()
    llm_metadata_catalog = LLMMetadataCatalog()
    metrics = MetricsRuntime(config, db)
    totp_runtime_state = TotpRuntimeState()

    # SharedPreferences starts a scheduler in its constructor.  Construct it
    # only after the other factory steps that can fail, so a failed factory
    # call never leaves an otherwise-unowned scheduler thread behind.
    preferences = SharedPreferences(db_helper=db)
    return RuntimeServices(
        config=config,
        catalogs=catalogs,
        db=db,
        authorization=authorization,
        preferences=preferences,
        html_renderer=html_renderer,
        file_token_service=file_token_service,
        pip_installer=pip_installer,
        webchat_queue_manager=webchat_queue_manager,
        webchat_run_coordinator=webchat_run_coordinator,
        follow_up_coordinator=follow_up_coordinator,
        llm_metadata_catalog=llm_metadata_catalog,
        metrics=metrics,
        computer_runtime=computer_runtime,
        tool_image_cache=tool_image_cache,
        totp_runtime_state=totp_runtime_state,
        demo_mode=os.getenv("DEMO_MODE", "False").strip().lower() in ("true", "1", "t"),
    )
