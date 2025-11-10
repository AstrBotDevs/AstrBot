from abc import ABC, abstractmethod
from ..basic.conversation_mgr import BaseConversationManager


class Context(ABC):
    conversation_manager: BaseConversationManager
