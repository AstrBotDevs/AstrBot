"""过渡期 ``astrbot_sdk.api.basic`` compat facade。"""

from .astrbot_config import AstrBotConfig
from .conversation_mgr import BaseConversationManager
from .entities import Conversation

__all__ = ["AstrBotConfig", "BaseConversationManager", "Conversation"]
