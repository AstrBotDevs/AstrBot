from astr_agent_sdk.message import AssistantMessageSegment, UserMessageSegment
from astrbot_sdk.api.basic.entities import Conversation
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
        result = await self.runner.call_context_function(
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

    async def switch_conversation(
        self, unified_msg_origin: str, conversation_id: str
    ) -> None:
        await self.runner.call_context_function(
            f"{self.__class__.__name__}.{self.switch_conversation.__name__}",
            {
                "unified_msg_origin": unified_msg_origin,
                "conversation_id": conversation_id,
            },
        )

    async def delete_conversation(
        self,
        unified_msg_origin: str,
        conversation_id: str | None = None,
    ) -> None:
        await self.runner.call_context_function(
            f"{self.__class__.__name__}.{self.delete_conversation.__name__}",
            {
                "unified_msg_origin": unified_msg_origin,
                "conversation_id": conversation_id,
            },
        )

    async def delete_conversations_by_user_id(self, unified_msg_origin: str) -> None:
        await self.runner.call_context_function(
            f"{self.__class__.__name__}.{self.delete_conversations_by_user_id.__name__}",
            {
                "unified_msg_origin": unified_msg_origin,
            },
        )

    async def get_curr_conversation_id(self, unified_msg_origin: str) -> str | None:
        result = await self.runner.call_context_function(
            f"{self.__class__.__name__}.{self.get_curr_conversation_id.__name__}",
            {
                "unified_msg_origin": unified_msg_origin,
            },
        )
        return result["data"]

    async def get_conversation(
        self,
        unified_msg_origin: str,
        conversation_id: str,
        create_if_not_exists: bool = False,
    ) -> Conversation | None:
        result = await self.runner.call_context_function(
            f"{self.__class__.__name__}.{self.get_conversation.__name__}",
            {
                "unified_msg_origin": unified_msg_origin,
                "conversation_id": conversation_id,
                "create_if_not_exists": create_if_not_exists,
            },
        )
        return Conversation(**result["data"]) if result["data"] else None

    async def get_conversations(
        self, unified_msg_origin: str | None = None, platform_id: str | None = None
    ) -> list[Conversation]:
        result = await self.runner.call_context_function(
            f"{self.__class__.__name__}.{self.get_conversations.__name__}",
            {
                "unified_msg_origin": unified_msg_origin,
                "platform_id": platform_id,
            },
        )
        return [Conversation(**conv) for conv in result["data"]]

    async def update_conversation(
        self,
        unified_msg_origin: str,
        conversation_id: str | None = None,
        history: list[dict] | None = None,
        title: str | None = None,
        persona_id: str | None = None,
    ) -> None:
        await self.runner.call_context_function(
            f"{self.__class__.__name__}.{self.update_conversation.__name__}",
            {
                "unified_msg_origin": unified_msg_origin,
                "conversation_id": conversation_id,
                "history": history,
                "title": title,
                "persona_id": persona_id,
            },
        )

    async def add_message_pair(
        self,
        cid: str,
        user_message: UserMessageSegment | dict,
        assistant_message: AssistantMessageSegment | dict,
    ) -> None:
        """Add a user-assistant message pair to the conversation history.

        Args:
            cid (str): Conversation ID
            user_message (UserMessageSegment | dict): OpenAI-format user message object or dict
            assistant_message (AssistantMessageSegment | dict): OpenAI-format assistant message object or dict

        Raises:
            Exception: If the conversation with the given ID is not found
        """
        ...
