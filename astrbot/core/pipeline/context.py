from dataclasses import dataclass
from typing import TYPE_CHECKING

from astrbot.core.config import AstrBotConfig

from .context_utils import call_event_hook, call_handler

if TYPE_CHECKING:
    from astrbot.core.auth.service import AuthorizationService
    from astrbot.core.execution_context import CoreExecutionContext
    from astrbot.core.file_token_service import FileTokenService
    from astrbot.core.star.plugin_catalog import PluginCatalog
    from astrbot.core.star.star import PluginRegistry
    from astrbot.core.star.star_handler import HandlerRegistry
    from astrbot.core.utils.shared_preferences import SharedPreferences
    from astrbot.core.utils.t2i.renderer import HtmlRenderer


@dataclass
class PipelineContext:
    """上下文对象，包含管道执行所需的上下文信息"""

    astrbot_config: AstrBotConfig  # AstrBot 配置对象
    plugin_catalog: PluginCatalog
    execution_context: CoreExecutionContext
    handlers: HandlerRegistry
    plugins: PluginRegistry
    astrbot_config_id: str
    html_renderer: HtmlRenderer
    file_token_service: FileTokenService
    preferences: SharedPreferences | None = None
    authorization: AuthorizationService | None = None
    call_handler = call_handler
    call_event_hook = call_event_hook
