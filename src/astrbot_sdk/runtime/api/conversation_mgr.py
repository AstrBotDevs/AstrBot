from ...api.basic.conversation_mgr import BaseConversationManager
from ..star_runner import StarRunner


class ConversationManager(BaseConversationManager):
    def __init__(self, runner: StarRunner):
        """Initialize ConversationManager.

        Args:
            runner: Optional StarRunner instance for RPC functionality.
        """
        self.runner = runner

    async def new_conversation(
        self,
        unified_msg_origin: str,
        platform_id: str | None = None,
        content: list[dict] | None = None,
        title: str | None = None,
        persona_id: str | None = None,
    ) -> str:
        result = await self.runner._call_context_function(
            f"{self.__class__.__name__}.{self.new_conversation.__name__}",
            {
                "unified_msg_origin": unified_msg_origin,
                "platform_id": platform_id,
                "content": content,
                "title": title,
                "persona_id": persona_id,
            },
        )
        return result["data"]
