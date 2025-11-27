import asyncio
from astrbot_sdk.runtime.galaxy import Galaxy
from astrbot_sdk.api.event import AstrMessageEvent
from astrbot_sdk.api.event.astrbot_message import AstrBotMessage, MessageMember
from astrbot_sdk.api.platform.platform_metadata import PlatformMetadata
from astrbot_sdk.api.event.message_type import MessageType

from astrbot_sdk.api.star.context import Context
from astrbot_sdk.api.basic.conversation_mgr import BaseConversationManager


class ConversationManager(BaseConversationManager):
    async def new_conversation(
        self,
        unified_msg_origin: str,
        platform_id: str | None = None,
        content: list[dict] | None = None,
        title: str | None = None,
        persona_id: str | None = None,
    ) -> str:
        import uuid

        return str(uuid.uuid4())


class TestContext(Context):
    def __init__(self, conversation_manager: ConversationManager):
        super().__init__()
        self.conversation_manager = conversation_manager
        self._register_component(self.conversation_manager)


async def amain():
    galaxy = Galaxy()
    conversation_manager = ConversationManager()
    context = TestContext(conversation_manager)
    star = await galaxy.connect_to_websocket_star(
        context=context,
        star_name="hello",
        config={
            "url": "ws://127.0.0.1:8765",
        },
    )
    print("Connected to websocket star 'hello'")
    md = await star.handshake()
    print(f"Handshake metadata: {md}")

    abm = AstrBotMessage()
    abm.type = MessageType.FRIEND_MESSAGE
    abm.self_id = "astrbot_123"
    abm.session_id = "test_session"
    abm.message_id = "msg_001"
    abm.message_str = "hello"
    abm.sender = MessageMember(
        user_id="user_123", nickname="User123"
    )  # Simplified for this example
    abm.group = None
    abm.message = []
    abm.raw_message = {}
    event = AstrMessageEvent(
        message_str=abm.message_str,
        message_obj=abm,
        platform_meta=PlatformMetadata(
            name="fake", description="Fake Platform", id="fake_1"
        ),
        session_id="test_session",
    )

    async for result in star.call_handler(star._handlers[0], event):
        print(f"Handler result: {result}")

    await star.stop()


if __name__ == "__main__":
    asyncio.run(amain())
