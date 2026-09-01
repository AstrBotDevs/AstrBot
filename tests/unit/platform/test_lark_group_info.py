from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.platform.astrbot_message import AstrBotMessage, Group, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent

pytestmark = pytest.mark.platform


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

    assert group is not event.message_obj.group
    assert group == event.message_obj.group
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


@pytest.mark.asyncio
async def test_lark_get_group_caps_member_pages_and_omits_truncated_list():
    chat_api = SimpleNamespace(
        aget=AsyncMock(
            return_value=SimpleNamespace(
                success=lambda: True,
                data=SimpleNamespace(
                    name="AstrBot Group",
                    avatar=None,
                    owner_id=None,
                    user_manager_id_list=None,
                    user_count="2500",
                ),
            ),
        ),
    )
    calls = []

    async def endless_members(request):
        calls.append(request)
        return SimpleNamespace(
            success=lambda: True,
            data=SimpleNamespace(
                items=[
                    SimpleNamespace(member_id=f"member-{len(calls)}", name="Member")
                ],
                member_total=2500,
                page_token=f"page-{len(calls)}",
                has_more=True,
                trigger_security_conf_limit=False,
            ),
        )

    members_api = SimpleNamespace(aget=endless_members)
    bot = SimpleNamespace(
        im=SimpleNamespace(v1=SimpleNamespace(chat=chat_api, chat_members=members_api)),
    )

    group = await _lark_event(bot).get_group()

    assert group.member_count == 2500
    assert group.members is None
    assert len(calls) == 10
