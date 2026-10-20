import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from astrbot.core.astr_main_agent import _process_quote_message, collect_initial_request
from astrbot.core.message.components import Reply
from astrbot.core.pipeline.process_stage.method.agent_sub_stages import third_party
from astrbot.core.pipeline.waking_check import stage as waking
from astrbot.core.platform.sources.lark.lark_adapter import LarkPlatformAdapter
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.utils.quoted_message_parser import extract_quoted_message_text


@pytest.fixture
def lark_message():
    """Prepare incoming and quoted Lark payloads without network access.

    Returns:
        Adapter, incoming event, and parent message returned by the mocked API.
    """
    adapter = LarkPlatformAdapter.__new__(LarkPlatformAdapter)
    adapter.config = {"id": "lark-test"}
    adapter.bot_open_id, adapter.bot_name = "ou_bot", "AstrBot"
    adapter.commit_event = MagicMock()
    parent = SimpleNamespace(
        message_id="parent-1",
        sender=SimpleNamespace(id="ou_sender"),
        create_time="1700000000000",
        body=SimpleNamespace(content="{}"),
        msg_type="post",
        mentions=[
            SimpleNamespace(
                key="@_user_1", id=SimpleNamespace(open_id="ou_bot"), name="AstrBot"
            )
        ],
    )
    adapter.lark_api = MagicMock()
    adapter.lark_api.im.v1.message.aget = AsyncMock(
        return_value=SimpleNamespace(
            success=lambda: True, data=SimpleNamespace(items=[parent])
        )
    )
    event = MagicMock()
    event.event.sender.sender_id.open_id = "ou_sender"
    event.event.message = SimpleNamespace(
        create_time="1700000000000",
        chat_type="group",
        chat_id="oc_group",
        parent_id=None,
        mentions=[],
        content="{}",
        message_id="message-1",
        message_type="post",
    )
    return adapter, event, parent


@pytest_asyncio.fixture
async def waking_stage(monkeypatch):
    """Isolate storage and plugin discovery while retaining real wake handling.

    Args:
        monkeypatch: Fixture for replacing external dependencies.

    Returns:
        Initialized waking stage with the slash prefix.
    """
    stage = waking.WakingCheckStage()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config={
                "admins_id": [],
                "wake_prefix": ["/"],
                "platform_settings": {},
            },
            astrbot_config_id="test",
            db_helper=MagicMock(),
        )
    )
    stage._umo_auto_name_recorder = MagicMock()
    monkeypatch.setattr(
        waking.star_handlers_registry,
        "get_handlers_by_event_type",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        waking.SessionPluginManager,
        "filter_handlers_by_session",
        AsyncMock(return_value=[]),
    )
    return stage


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("quoted", "title", "wake_prefix", "provider_prefix", "platform", "message_type"),
    [
        (False, "Report", "", "", "lark", "post"),
        (False, "", "", "", "lark", "post"),
        (False, "", "/", "llm:", "lark", "post"),
        (True, "Report", "", "", "lark", "post"),
        (True, "", "", "", "lark", "post"),
        (False, "", "/", "", "lark", "text"),
        (False, "", "/", "", "telegram", "text"),
    ],
)
async def test_lark_post_preserves_formatting(
    quoted,
    title,
    wake_prefix,
    provider_prefix,
    platform,
    message_type,
    monkeypatch,
    main_agent_build_config,
    lark_message,
    waking_stage,
):
    content = {
        "title": title,
        "content": [
            [
                {"tag": "text", "text": "    ABC"},
                {"tag": "text", "text": "123", "style": ["bold"]},
                {"tag": "text", "text": ",42"},
            ],
            [],
            [{"tag": "text", "text": "    "}, {"tag": "text", "text": "1.item  "}],
            [{"tag": "text", "text": "\tsecond\n    third"}],
            [{"tag": "a", "text": " docs ", "href": "https://example.com"}],
            [],
        ],
    }
    expected = (
        (f"{title}\n" if title else "")
        + "    ABC123,42\n\n    1.item  \n\tsecond\n    third\n docs (https://example.com)\n"
    )
    adapter, event, parent = lark_message
    parent.body.content = json.dumps(content)
    event.event.message.parent_id = "parent-1" if quoted else None
    if not quoted and wake_prefix:
        content["content"][0].insert(
            0, {"tag": "text", "text": f"  {wake_prefix}  {provider_prefix}"}
        )
    event.event.message.content = json.dumps({"text": "Reply"} if quoted else content)
    event.event.message.message_type = "text" if quoted else "post"

    await adapter.convert_msg(event)

    parsed_event = adapter.commit_event.call_args.args[0]
    message = parsed_event.message_obj
    # Exercise the shared pipeline with the same text under each source type.
    parsed_event.platform_meta.name = platform
    if not quoted:
        parsed_event.message_obj.raw_message.message_type = message_type
    if quoted:
        reply = message.message[0]
        assert type(reply) is Reply
        request = ProviderRequest()
        await _process_quote_message(parsed_event, request, "", MagicMock())
        assert request.extra_user_content_parts[0].text == (
            f"<Quoted Message>\n({reply.sender_nickname}): {expected}\n</Quoted Message>"
        )
        # A marker for one reply must not affect another reply on the same event.
        other_reply = Reply(id="other", message_str="  other  ")
        assert await extract_quoted_message_text(parsed_event, other_reply) == "other"
        parsed_event.platform_meta.name = "telegram"
        assert await extract_quoted_message_text(parsed_event) == expected.strip()
    else:
        waking_stage.ctx.astrbot_config["wake_prefix"] = [wake_prefix]
        main_agent_build_config.provider_wake_prefix = provider_prefix
        monkeypatch.setattr(
            "astrbot.core.astr_main_agent._get_session_conv",
            AsyncMock(return_value=SimpleNamespace(history="[]")),
        )
        await waking_stage.process(parsed_event)
        request, _ = await collect_initial_request(
            parsed_event, MagicMock(), main_agent_build_config
        )
        expected_prompt = (
            expected
            if platform == "lark" and message_type == "post"
            else expected.strip()
        )
        assert request.prompt == expected_prompt
        third_party_stage = third_party.ThirdPartyAgentSubStage()
        third_party_stage._resolve_persona_custom_error_message = AsyncMock(
            return_value=None
        )
        hook = AsyncMock(return_value=True)
        monkeypatch.setattr(third_party, "call_event_hook", hook)
        async for _ in third_party_stage.process(parsed_event, provider_prefix):
            pass
        assert hook.await_args.args[2].prompt == expected_prompt


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ({"title": "Title only", "content": []}, "Title only"),
        ({"title": "", "content": []}, ""),
        ({"content": [[{"tag": "text", "text": "  No title  "}]]}, "  No title  "),
    ],
)
async def test_lark_post_title_boundaries(content, expected):
    adapter = LarkPlatformAdapter.__new__(LarkPlatformAdapter)
    components = await adapter._parse_message_components(
        message_id="message-1", message_type="post", content=content, at_map={}
    )
    assert (
        adapter._build_message_str_from_components(components, preserve_whitespace=True)
        == expected
    )


@pytest.mark.asyncio
async def test_lark_third_party_skips_whitespace_only_prompt(monkeypatch):
    event = MagicMock()
    event.get_platform_name.return_value = "lark"
    event.message_str = "    \n"
    event.message_obj.message = []
    hook = AsyncMock(return_value=True)
    monkeypatch.setattr(third_party, "call_event_hook", hook)
    stage = third_party.ThirdPartyAgentSubStage()
    stage._resolve_persona_custom_error_message = AsyncMock(return_value=None)

    async for _ in stage.process(event, ""):
        pass

    hook.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message_type", "title", "mention", "body", "is_wake", "matches"),
    [
        ("post", "", True, "/help run", True, True),
        ("text", "", True, "/help run", True, True),
        ("post", "", False, "/help run", True, True),
        ("post", "Report", True, "/help run", True, False),
        ("post", "Report", False, "/help run", False, False),
        ("post", "/help", False, "run", True, True),
    ],
)
async def test_lark_commands_match_complete_message(
    lark_message, waking_stage, message_type, title, mention, body, is_wake, matches
):
    adapter, event, parent = lark_message
    row = [{"tag": "text", "text": " \t"}]
    if mention:
        row.append({"tag": "at", "user_id": "@_user_1"})
        event.event.message.mentions = parent.mentions
    row.append({"tag": "text", "text": f" {body}"})
    if mention:
        row.append({"tag": "at", "user_id": "@_user_1"})
    event.event.message.message_type = message_type
    event.event.message.content = json.dumps(
        {"title": title, "content": [[], row]}
        if message_type == "post"
        else {"text": f" \t@_user_1 {body} @_user_1 "}
    )
    await adapter.convert_msg(event)
    parsed_event = adapter.commit_event.call_args.args[0]
    if mention and not title:
        assert parsed_event.message_str == (
            f"\n \t {body}@AstrBot" if message_type == "post" else f"{body} @AstrBot"
        )

    await waking_stage.process(parsed_event)

    command = CommandFilter("help")
    command.handler_params = {}
    assert parsed_event.is_wake is is_wake
    assert command.filter(parsed_event, waking_stage.ctx.astrbot_config) is matches
    assert (
        CommandGroupFilter("help").filter(parsed_event, waking_stage.ctx.astrbot_config)
        is matches
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message_type", "content", "expected"),
    [
        ("file", {"file_key": "file", "file_name": "report.pdf"}, "[File:report.pdf]"),
        ("image", {"image_key": "image"}, "[Image]"),
        ("text", {"text": "@_user_1 hello"}, "@AstrBothello"),
    ],
)
async def test_lark_non_post_quotes_keep_existing_text(
    lark_message, tmp_path, message_type, content, expected
):
    adapter, event, parent = lark_message
    parent.msg_type = message_type
    parent.body.content = json.dumps(content)
    adapter._download_message_resource = AsyncMock(return_value=b"image")
    adapter._download_file_resource_to_temp = AsyncMock(
        return_value=str(tmp_path / "report.pdf")
    )
    event.event.message.parent_id = parent.message_id
    event.event.message.content = json.dumps(
        {"content": [[{"tag": "text", "text": "Reply"}]]}
    )
    await adapter.convert_msg(event)
    parsed_event = adapter.commit_event.call_args.args[0]

    assert await extract_quoted_message_text(parsed_event) == expected
