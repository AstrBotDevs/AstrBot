import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.platform.astrbot_message import AstrBotMessage, Group, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.sources.lark import lark_group_info
from astrbot.core.platform.sources.lark.lark_adapter import LarkPlatformAdapter
from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent
from astrbot.core.platform.sources.lark.lark_group_info import get_lark_group


def _lark_event(bot) -> LarkMessageEvent:
    """Build a group event with the provided Lark client.

    Args:
        bot: Lark client or a compatible test double.

    Returns:
        Group message event for tests.
    """
    message = AstrBotMessage()
    message.type = MessageType.GROUP_MESSAGE
    message.self_id = "bot"
    message.session_id = "chat-1"
    message.message_id = "message-1"
    message.group = Group(group_id="chat-1")
    message.sender = MessageMember(user_id="sender", nickname="Sender")
    message.message = []
    message.message_str = "hello"
    message.raw_message = None
    return LarkMessageEvent(
        message_str=message.message_str,
        message_obj=message,
        platform_meta=PlatformMetadata(
            name="lark",
            description="Lark",
            id="lark-account",
        ),
        session_id=message.session_id,
        bot=bot,
    )


@pytest.fixture
def group_bot():
    """Build an isolated API client with group details and an empty member list.

    Returns:
        A Lark-compatible client with independently mocked API methods.
    """
    return SimpleNamespace(
        im=SimpleNamespace(
            v1=SimpleNamespace(
                chat=SimpleNamespace(
                    aget=AsyncMock(
                        return_value=SimpleNamespace(
                            success=lambda: True,
                            data=SimpleNamespace(
                                name="API Group",
                                avatar=None,
                                owner_id=None,
                                user_manager_id_list=None,
                                user_count="3",
                            ),
                        )
                    )
                ),
                chat_members=SimpleNamespace(
                    aget=AsyncMock(
                        return_value=SimpleNamespace(
                            success=lambda: True,
                            data=SimpleNamespace(
                                items=[],
                                member_total=3,
                                page_token=None,
                                has_more=False,
                            ),
                        )
                    )
                ),
            )
        )
    )


@pytest.mark.asyncio
async def test_lark_enriches_group_before_event_creation_without_loading_members(
    group_bot, monkeypatch
):
    """Coalesce incoming lookups and reuse details in explicit get_group calls."""
    adapter = LarkPlatformAdapter.__new__(LarkPlatformAdapter)
    adapter.config = {"id": "lark-test"}
    adapter.lark_api = group_bot
    events = []
    monkeypatch.setattr(adapter, "commit_event", events.append)
    create_event = adapter.create_event

    def create_enriched_event(message):
        assert message.group.group_name == "API Group"
        assert message.group.member_count == 3
        return create_event(message)

    monkeypatch.setattr(adapter, "create_event", create_enriched_event)
    response = group_bot.im.v1.chat.aget.return_value
    started, release = asyncio.Event(), asyncio.Event()

    async def fetch(_request):
        started.set()
        await release.wait()
        return response

    group_bot.im.v1.chat.aget.side_effect = fetch
    messages = [_lark_event(group_bot).message_obj for _ in range(3)]
    tasks = [
        asyncio.create_task(adapter.handle_msg(message, quoted_post_id="quoted"))
        for message in messages
    ]
    await started.wait()
    assert not events
    release.set()
    await asyncio.gather(*tasks)

    assert len(events) == 3
    assert all(event.get_extra("lark_quoted_post_id") == "quoted" for event in events)
    group_bot.im.v1.chat.aget.assert_awaited_once()
    group_bot.im.v1.chat_members.aget.assert_not_awaited()

    group = await events[0].get_group()
    assert group.group_name == "API Group"
    assert group.members == []
    group_bot.im.v1.chat.aget.assert_awaited_once()
    group_bot.im.v1.chat_members.aget.assert_awaited_once()


@pytest.mark.asyncio
async def test_lark_failed_lookups_preserve_messages_and_retry_after_cache_expiry(
    group_bot, monkeypatch
):
    """Cache missing permissions without preventing event creation or later retries."""
    clock = [100.0]
    monkeypatch.setattr(lark_group_info, "monotonic", lambda: clock[0])
    response = group_bot.im.v1.chat.aget.return_value
    group_bot.im.v1.chat.aget.return_value = SimpleNamespace(
        success=lambda: False, data=None, code=403, msg="permission denied"
    )
    adapter = LarkPlatformAdapter.__new__(LarkPlatformAdapter)
    adapter.config = {"id": "lark-test"}
    adapter.lark_api = group_bot
    events = []
    monkeypatch.setattr(adapter, "commit_event", events.append)
    for _ in range(2):
        message = _lark_event(group_bot).message_obj
        message.group.group_name = "Incoming Group"
        await adapter.handle_msg(message)
    assert len(events) == 2
    assert all(
        event.message_obj.group.group_name == "Incoming Group" for event in events
    )
    group_bot.im.v1.chat.aget.assert_awaited_once()
    group_bot.im.v1.chat_members.aget.assert_not_awaited()

    clock[0] += lark_group_info.GROUP_INFO_FAILURE_TTL
    group_bot.im.v1.chat.aget.return_value = response
    await adapter.handle_msg(_lark_event(group_bot).message_obj)
    assert events[-1].message_obj.group.group_name == "API Group"
    assert group_bot.im.v1.chat.aget.await_count == 2


@pytest.mark.asyncio
async def test_lark_success_cache_expiry_capacity_and_bot_isolation(
    group_bot, monkeypatch
):
    """Expire metadata, evict least-recently-used groups and isolate bot clients."""
    clock = [100.0]
    monkeypatch.setattr(lark_group_info, "monotonic", lambda: clock[0])
    monkeypatch.setattr(lark_group_info, "GROUP_INFO_CACHE_MAX_SIZE", 2)
    for group_id in ("1", "2", "1", "3"):
        await get_lark_group(group_bot, Group(group_id=group_id))
    assert list(group_bot._astrbot_group_info_cache) == ["1", "3"]
    assert group_bot.im.v1.chat.aget.await_count == 3
    clock[0] += lark_group_info.GROUP_INFO_CACHE_TTL - 1
    await get_lark_group(group_bot, Group(group_id="1"))
    assert group_bot.im.v1.chat.aget.await_count == 3
    clock[0] += 1
    await get_lark_group(group_bot, Group(group_id="1"))
    assert group_bot.im.v1.chat.aget.await_count == 4

    other_request = AsyncMock(return_value=group_bot.im.v1.chat.aget.return_value)
    other_bot = SimpleNamespace(
        im=SimpleNamespace(v1=SimpleNamespace(chat=SimpleNamespace(aget=other_request)))
    )
    await get_lark_group(other_bot, Group(group_id="1"))
    other_request.assert_awaited_once()


@pytest.mark.asyncio
async def test_lark_lookup_timeout_and_private_message_bypass(group_bot, monkeypatch):
    """Bound failed lookups and avoid chat metadata requests for private messages."""
    monkeypatch.setattr(lark_group_info, "GROUP_INFO_REQUEST_TIMEOUT", 0.01)

    async def never_responds(_request):
        await asyncio.Event().wait()

    group_bot.im.v1.chat.aget.side_effect = never_responds
    group = Group(group_id="timeout", group_name="Incoming Group")
    for _ in range(2):
        assert await get_lark_group(group_bot, group) is None
        assert group.group_name == "Incoming Group"
    group_bot.im.v1.chat.aget.assert_awaited_once()

    adapter = LarkPlatformAdapter.__new__(LarkPlatformAdapter)
    adapter.config = {"id": "lark-test"}
    adapter.lark_api = group_bot
    events = []
    monkeypatch.setattr(adapter, "commit_event", events.append)
    message = _lark_event(group_bot).message_obj
    message.type = MessageType.FRIEND_MESSAGE
    message.group = None
    await adapter.handle_msg(message)
    assert len(events) == 1
    group_bot.im.v1.chat.aget.assert_awaited_once()
    group_bot.im.v1.chat_members.aget.assert_not_awaited()


@pytest.mark.asyncio
async def test_lark_get_group_fetches_details_and_all_member_pages():
    chat_api = SimpleNamespace(
        aget=AsyncMock(
            return_value=SimpleNamespace(
                success=lambda: True,
                data=SimpleNamespace(
                    name="AstrBot Group",
                    avatar="https://example.com/avatar.png",
                    owner_id="owner",
                    user_manager_id_list=["admin"],
                    user_count="3",
                ),
            ),
        ),
    )
    members_api = SimpleNamespace(
        aget=AsyncMock(
            side_effect=[
                SimpleNamespace(
                    success=lambda: True,
                    data=SimpleNamespace(
                        items=[
                            SimpleNamespace(member_id="owner", name="Owner"),
                            SimpleNamespace(member_id="admin", name="Admin"),
                        ],
                        member_total=3,
                        page_token="next-page",
                        has_more=True,
                    ),
                ),
                SimpleNamespace(
                    success=lambda: True,
                    data=SimpleNamespace(
                        items=[SimpleNamespace(member_id="member", name="Member")],
                        member_total=3,
                        page_token=None,
                        has_more=False,
                    ),
                ),
            ],
        ),
    )
    bot = SimpleNamespace(
        im=SimpleNamespace(
            v1=SimpleNamespace(chat=chat_api, chat_members=members_api),
        ),
    )

    group = await _lark_event(bot).get_group()

    assert group is not None
    assert group.group_id == "chat-1"
    assert group.group_name == "AstrBot Group"
    assert group.group_avatar == "https://example.com/avatar.png"
    assert group.group_owner == "owner"
    assert group.group_admins == ["admin"]
    assert group.member_count == 3
    assert [(member.user_id, member.nickname) for member in group.members or []] == [
        ("owner", "Owner"),
        ("admin", "Admin"),
        ("member", "Member"),
    ]

    chat_request = chat_api.aget.await_args.args[0]
    assert chat_request.chat_id == "chat-1"
    assert chat_request.user_id_type == "open_id"
    member_requests = [call.args[0] for call in members_api.aget.await_args_list]
    assert member_requests[0].member_id_type == "open_id"
    assert member_requests[0].page_size == 100
    assert member_requests[0].page_token is None
    assert member_requests[1].page_token == "next-page"


@pytest.mark.asyncio
async def test_lark_get_group_falls_back_to_incoming_group_on_api_failure():
    chat_api = SimpleNamespace(
        aget=AsyncMock(
            return_value=SimpleNamespace(
                success=lambda: False,
                data=None,
                code=999,
                msg="permission denied",
            ),
        ),
    )
    bot = SimpleNamespace(
        im=SimpleNamespace(
            v1=SimpleNamespace(
                chat=chat_api,
                chat_members=SimpleNamespace(aget=AsyncMock()),
            ),
        ),
    )
    event = _lark_event(bot)

    group = await event.get_group()

    assert group is event.message_obj.group
    assert group.group_id == "chat-1"


@pytest.mark.asyncio
async def test_lark_get_group_does_not_publish_a_truncated_member_list():
    chat_api = SimpleNamespace(
        aget=AsyncMock(
            return_value=SimpleNamespace(
                success=lambda: True,
                data=SimpleNamespace(
                    name="AstrBot Group",
                    avatar=None,
                    owner_id=None,
                    user_manager_id_list=None,
                    user_count="10",
                ),
            ),
        ),
    )
    members_api = SimpleNamespace(
        aget=AsyncMock(
            return_value=SimpleNamespace(
                success=lambda: True,
                data=SimpleNamespace(
                    items=[SimpleNamespace(member_id="member", name="Member")],
                    member_total=10,
                    page_token=None,
                    has_more=False,
                    trigger_security_conf_limit=True,
                ),
            ),
        ),
    )
    bot = SimpleNamespace(
        im=SimpleNamespace(
            v1=SimpleNamespace(chat=chat_api, chat_members=members_api),
        ),
    )

    group = await _lark_event(bot).get_group()

    assert group is not None
    assert group.member_count == 10
    assert group.members is None
