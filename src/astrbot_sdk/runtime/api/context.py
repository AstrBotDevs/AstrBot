from ...api.star.context import Context as BaseContext
from .conversation_mgr import ConversationManager


class Context(BaseContext):
    def __init__(self, conversation_manager: ConversationManager):
        self.conversation_manager = conversation_manager

    def _inject_rpc_handlers(self, runner):
        setattr(self.conversation_manager, "runner", runner)
