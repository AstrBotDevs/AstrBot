from ...api.basic.conversation_mgr import BaseConversationManager
from .util import rpc_method


class ConversationManager(BaseConversationManager):
    def __init__(self, runner=None):
        """Initialize ConversationManager.
        
        Args:
            runner: Optional StarRunner instance for RPC functionality.
        """
        self.runner = runner

    @rpc_method
    async def new_conversation(
        self,
        unified_msg_origin: str,
        platform_id: str | None = None,
        content: list[dict] | None = None,
        title: str | None = None,
        persona_id: str | None = None,
    ) -> str: ...
