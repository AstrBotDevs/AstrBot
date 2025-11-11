from ...api.star.context import Context as BaseContext
from .conversation_mgr import ConversationManager


class Context(BaseContext):
    def __init__(self, conversation_manager: ConversationManager):
        super().__init__()
        self.conversation_manager = conversation_manager
        # Auto-register the conversation manager
        self.register_component(self.conversation_manager)

    @classmethod
    def default_context(cls, runner=None):
        """Create a default context instance.

        Args:
            runner: Optional StarRunner instance to inject into conversation manager.
                   If provided, enables RPC functionality.
        """
        conversation_manager = ConversationManager(runner=runner)
        return cls(conversation_manager=conversation_manager)
