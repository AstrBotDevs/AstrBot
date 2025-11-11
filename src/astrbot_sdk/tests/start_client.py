import asyncio
from astrbot_sdk.runtime.galaxy import Galaxy
from astrbot_sdk.api.event import AstrMessageEvent
from astrbot_sdk.api.event.astrbot_message import AstrBotMessage, MessageMember
from astrbot_sdk.api.platform.platform_metadata import PlatformMetadata
from astrbot_sdk.api.event.message_type import MessageType


async def amain():
    galaxy = Galaxy()
    star = await galaxy.connect_to_websocket_star(
        "hello",
        {
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
    await star.call_handler(star._handlers[0], event)

    await star.stop()


if __name__ == "__main__":
    asyncio.run(amain())
