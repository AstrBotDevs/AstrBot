import json

import pytest

from astrbot.core.conversation_mgr import ConversationManager, load_sanitized_history
from astrbot.core.utils.shared_preferences import SharedPreferences


@pytest.mark.asyncio
async def test_conversation_manager_creates_loads_and_isolates_sessions(
    temp_db, tmp_path
):
    await temp_db.initialize()
    preferences = SharedPreferences(temp_db, tmp_path / "preferences.json")
    await preferences.initialize()
    manager = ConversationManager(temp_db, preferences)
    try:
        umo_a = "webchat:FriendMessage:alice"
        umo_b = "webchat:FriendMessage:bob"
        cid_a = await manager.new_conversation(umo_a, title="Alice chat")
        cid_b = await manager.new_conversation(umo_b, title="Bob chat")
        dirty_history = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "hello"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,aGVsbG8="},
                    },
                ],
            }
        ]
        await manager.update_conversation(umo_a, cid_a, history=dirty_history)

        conv_a = await manager.get_conversation(umo_a, cid_a)
        conv_b = await manager.get_conversation(umo_b, cid_b)
        assert conv_a is not None
        assert conv_b is not None
        assert conv_a.title == "Alice chat"
        assert conv_b.title == "Bob chat"
        assert await manager.get_curr_conversation_id(umo_a) == cid_a
        assert await manager.get_curr_conversation_id(umo_b) == cid_b
        sanitized = load_sanitized_history(conv_a.history)
        assert sanitized[0]["content"][0]["text"] == "hello"
        assert "base64" not in json.dumps(sanitized)

        deleted: list[str] = []

        async def on_deleted(umo: str) -> None:
            deleted.append(umo)

        manager.register_on_session_deleted(on_deleted)
        await manager.delete_conversations_by_user_id(umo_a)

        assert deleted == [umo_a]
        assert await manager.get_conversation(umo_a, cid_a) is None
        remaining = await manager.get_conversation(umo_b, cid_b)
        assert remaining is not None
        assert remaining.title == "Bob chat"
    finally:
        await preferences.terminate()
