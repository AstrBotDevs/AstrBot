from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.astr_main_agent_resources import SendMessageToUserTool
from astrbot.core.message.components import At, File, Image, Plain, Record
from astrbot.core.message.message_event_result import MessageChain


def _build_run_context(
    unified_msg_origin: str = "test:FriendMessage:session-1",
) -> tuple[ContextWrapper, AsyncMock]:
    send_message = AsyncMock()
    inner_ctx = SimpleNamespace(send_message=send_message)
    event = SimpleNamespace(unified_msg_origin=unified_msg_origin)
    wrapped = ContextWrapper(context=SimpleNamespace(context=inner_ctx, event=event))
    return wrapped, send_message


@pytest.mark.asyncio
async def test_send_message_text_only_success():
    tool = SendMessageToUserTool()
    run_context, send_message = _build_run_context()

    result = await tool.call(run_context, text="hello")

    assert result.startswith("Message sent to session")
    send_message.assert_awaited_once()
    target_session, chain = send_message.await_args.args
    assert str(target_session) == "test:FriendMessage:session-1"
    assert isinstance(chain, MessageChain)
    assert len(chain.chain) == 1
    assert isinstance(chain.chain[0], Plain)
    assert chain.chain[0].text == "hello"


@pytest.mark.asyncio
async def test_send_message_rejects_multiple_primary_payloads():
    tool = SendMessageToUserTool()
    run_context, send_message = _build_run_context()

    result = await tool.call(run_context, text="hello", url="https://example.com/a.png")

    assert "only one primary payload is allowed" in result
    send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_message_supports_mention_with_text():
    tool = SendMessageToUserTool()
    run_context, send_message = _build_run_context()

    result = await tool.call(run_context, mention_user_id="12345", text="ping")

    assert result.startswith("Message sent to session")
    send_message.assert_awaited_once()
    _, chain = send_message.await_args.args
    assert isinstance(chain, MessageChain)
    assert len(chain.chain) == 2
    assert isinstance(chain.chain[0], At)
    assert isinstance(chain.chain[1], Plain)
    assert chain.chain[1].text == "ping"


@pytest.mark.asyncio
async def test_send_message_supports_mention_only():
    tool = SendMessageToUserTool()
    run_context, send_message = _build_run_context()

    result = await tool.call(run_context, mention_user_id="12345")

    assert result.startswith("Message sent to session")
    send_message.assert_awaited_once()
    _, chain = send_message.await_args.args
    assert isinstance(chain, MessageChain)
    assert len(chain.chain) == 1
    assert isinstance(chain.chain[0], At)


@pytest.mark.asyncio
async def test_send_message_url_infers_image_component():
    tool = SendMessageToUserTool()
    run_context, send_message = _build_run_context()

    result = await tool.call(run_context, url="https://example.com/photo.png")

    assert result.startswith("Message sent to session")
    send_message.assert_awaited_once()
    _, chain = send_message.await_args.args
    assert isinstance(chain, MessageChain)
    assert len(chain.chain) == 1
    assert isinstance(chain.chain[0], Image)


@pytest.mark.asyncio
async def test_send_message_path_infers_record_component(monkeypatch: pytest.MonkeyPatch):
    tool = SendMessageToUserTool()
    run_context, send_message = _build_run_context()
    monkeypatch.setattr(
        tool,
        "_resolve_path_from_sandbox",
        AsyncMock(return_value=("/tmp/voice.mp3", False)),
    )

    result = await tool.call(run_context, path="/sandbox/voice.mp3")

    assert result.startswith("Message sent to session")
    send_message.assert_awaited_once()
    _, chain = send_message.await_args.args
    assert isinstance(chain, MessageChain)
    assert len(chain.chain) == 1
    assert isinstance(chain.chain[0], Record)


@pytest.mark.asyncio
async def test_send_message_url_unknown_extension_falls_back_to_file():
    tool = SendMessageToUserTool()
    run_context, send_message = _build_run_context()

    result = await tool.call(
        run_context,
        url="https://example.com/report.unknown",
        name="report.txt",
    )

    assert result.startswith("Message sent to session")
    send_message.assert_awaited_once()
    _, chain = send_message.await_args.args
    assert isinstance(chain, MessageChain)
    assert len(chain.chain) == 1
    assert isinstance(chain.chain[0], File)
    assert chain.chain[0].name == "report.txt"

