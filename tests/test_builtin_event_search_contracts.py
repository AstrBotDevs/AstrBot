"""Built-in event and search handlers preserve shared behavioral contracts."""

import asyncio
import json
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.api.provider import LLMResponse
from astrbot.builtin_stars.astrbot import main as builtin
from astrbot.builtin_stars.session_controller import main as sessions
from astrbot.builtin_stars.web_searcher import main as search
from astrbot.builtin_stars.web_searcher.engines import SearchResult
from astrbot.core import sp
from astrbot.core.message.components import At, Plain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata


def _event(text: str, *, group: bool = True, platform: str = "test"):
    message = AstrBotMessage()
    message.type = MessageType.GROUP_MESSAGE if group else MessageType.FRIEND_MESSAGE
    message.self_id = "bot"
    message.sender = MessageMember(user_id="alice", nickname="Alice")
    message.session_id = "room"
    message.message = [Plain(text)] if text else [At(qq="bot")]
    message.message_str = text
    return AstrMessageEvent(
        text,
        message,
        PlatformMetadata(name=platform, description="Test", id="platform-id"),
        "room",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("module", [builtin, sessions])
async def test_mention_waiters_ignore_blank_content_and_enqueue_a_running_copy(
    module, monkeypatch
):
    queue = asyncio.Queue()
    main = module.Main.__new__(module.Main)
    main.context = SimpleNamespace(
        get_config=lambda **kwargs: {
            "platform_settings": {"empty_mention_waiting_need_reply": False}
        },
        locale=lambda umo: "en-US",
        get_event_queue=lambda: queue,
    )
    initial, blank, follow_up = _event(""), _event("  "), _event("Question 内容")
    controller = SimpleNamespace(stop=Mock())

    def immediate_waiter(timeout):
        assert timeout == 60

        def decorate(callback):
            async def wait(event):
                assert event is initial
                await callback(controller, blank)
                assert queue.empty()
                assert not blank.is_stopped()
                controller.stop.assert_not_called()
                await callback(controller, follow_up)

            return wait

        return decorate

    monkeypatch.setattr(module, "session_waiter", immediate_waiter)
    assert [item async for item in main.handle_empty_mention(initial)] == []
    queued = queue.get_nowait()
    assert queue.empty()
    assert queued is not follow_up
    assert not queued.is_stopped()
    assert queued.unified_msg_origin == follow_up.unified_msg_origin
    assert queued.message_str == "Question 内容"
    assert str(queued.get_messages()[0].qq) == "bot"
    assert queued.get_messages()[1].text == "Question 内容"
    assert initial.is_stopped() and follow_up.is_stopped()
    controller.stop.assert_called_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "configured, expected", [(0, 1), (-3, 1), ("2", 2), (None, 700), ("bad", 700)]
)
async def test_incoming_and_outgoing_group_history_use_the_same_bounded_limit(
    configured, expected
):
    main = builtin.Main.__new__(builtin.Main)
    insert = AsyncMock(return_value=SimpleNamespace(id=42))
    main.context = SimpleNamespace(
        get_config=lambda **kwargs: {
            "provider_ltm_settings": {
                "group_message_history_enable": True,
                "group_message_history_max_cnt": configured,
            }
        },
        message_history_manager=SimpleNamespace(insert_message_chain=insert),
    )
    event = _event("Question")
    await main.persist_group_message(event)
    await main.persist_llm_response(
        event, LLMResponse(role="assistant", completion_text="Reply")
    )
    calls = [call.kwargs for call in insert.await_args_list]
    assert [call["role"] for call in calls] == ["user", "bot"]
    assert [call["max_messages"] for call in calls] == [expected, expected]
    assert [call["message_chain"].chain[0].text for call in calls] == [
        "Question",
        "Reply",
    ]
    assert all(call["user_id"] == event.unified_msg_origin for call in calls)
    assert event.get_extra("_current_platform_message_history_id") == 42


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "group, platform, enabled",
    [(False, "test", True), (True, "webchat", True), (True, "test", False)],
)
async def test_history_configuration_excludes_ineligible_sessions(
    group, platform, enabled
):
    main = builtin.Main.__new__(builtin.Main)
    insert = AsyncMock()
    main.context = SimpleNamespace(
        get_config=lambda **kwargs: {
            "provider_ltm_settings": {"group_message_history_enable": enabled}
        },
        message_history_manager=SimpleNamespace(insert_message_chain=insert),
    )
    event = _event("Question", group=group, platform=platform)
    await main.persist_group_message(event)
    await main.persist_llm_response(
        event, LLMResponse(role="assistant", completion_text="Reply")
    )
    insert.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["tavily", "bocha"])
async def test_search_tools_emit_consistent_references_and_cache_favicons(
    provider, monkeypatch
):
    main = search.Main.__new__(search.Main)
    main.context = SimpleNamespace(
        get_config=lambda **kwargs: {
            "provider_settings": {f"websearch_{provider}_key": ["test-key"]}
        }
    )
    results = [
        SearchResult(
            "First 内容", "https://one.invalid", "摘要", "https://one.invalid/icon"
        ),
        SearchResult("Second", "https://two.invalid", "Other result"),
    ]
    monkeypatch.setattr(
        main, f"_web_search_{provider}", AsyncMock(return_value=results)
    )
    cache = {"https://old.invalid": "old-icon"}
    monkeypatch.setitem(sp.temporary_cache, "_ws_favicon", cache)
    output = await getattr(main, f"search_from_{provider}")(_event("query"), "query")
    formatted = json.loads(output)["results"]
    prefix = formatted[0]["index"].split(".")[0]
    assert re.fullmatch(r"[0-9a-f]{4}", prefix)
    assert formatted == [
        {
            "title": result.title,
            "url": result.url,
            "snippet": result.snippet,
            "index": f"{prefix}.{index}",
        }
        for index, result in enumerate(results, 1)
    ]
    assert "摘要" in output
    assert cache == {
        "https://old.invalid": "old-icon",
        "https://one.invalid": "https://one.invalid/icon",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "results", [[], [{"url": "https://page.invalid", "raw_content": "Extracted"}]]
)
async def test_tavily_extraction_preserves_empty_result_error_and_success_identity(
    results, monkeypatch
):
    main = search.Main.__new__(search.Main)
    monkeypatch.setattr(main, "_get_tavily_key", AsyncMock(return_value="test-key"))
    response = SimpleNamespace(
        status=200, json=AsyncMock(return_value={"results": results})
    )
    response_context = AsyncMock()
    response_context.__aenter__.return_value = response
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.post = Mock(return_value=response_context)
    monkeypatch.setattr(search.aiohttp, "ClientSession", Mock(return_value=session))
    if results:
        assert (
            await main._extract_tavily({}, {"urls": ["https://page.invalid"]})
            is results
        )
    else:
        with pytest.raises(
            ValueError, match="Error: Tavily web searcher does not return any results."
        ):
            await main._extract_tavily({}, {"urls": ["https://page.invalid"]})
