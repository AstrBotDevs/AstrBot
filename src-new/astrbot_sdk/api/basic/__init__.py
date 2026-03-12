"""旧版 ``astrbot_sdk.api.basic`` 的兼容入口。"""

from .astrbot_config import AstrBotConfig
from .conversation_mgr import BaseConversationManager
from .entities import Conversation

__all__ = ["AstrBotConfig", "BaseConversationManager", "Conversation"]
