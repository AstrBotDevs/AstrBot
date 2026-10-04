"""Tests for Lark pre-ack emoji auto-remove behavior."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.pipeline.preprocess_stage.stage import PreProcessStage
from astrbot.core.platform.astr_message_event import (
    LAST_REACTION_CREATED,
    PRE_ACK_REACTION,
    AstrMessageEvent,
)
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent


def _lark_event(
    bot,
    self_id: str = "bot",
    app_id: str | None = None,
) -> LarkMessageEvent:
    """Build a Lark message event with the provided client double.

    Args:
        bot: Lark client or a compatible test double.
        self_id: Bot open id recorded on the message object.
        app_id: Optional application ID passed to the event for reaction ownership matching.

    Returns:
        Lark private message event for tests.
    """
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.self_id = self_id
    message.session_id = "sender"
    message.message_id = "message-1"
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
        app_id=app_id,
    )


def _lark_bot(reaction_api, app_id: str | None = None):
    """Wrap a message reaction API double into a Lark client double.

    Args:
        reaction_api: Double exposing acreate/adelete/alist awaitables.
        app_id: Optional application id exposed via the client config.

    Returns:
        Object compatible with ``LarkMessageEvent.bot``.
    """
    config = SimpleNamespace(app_id=app_id) if app_id is not None else None
    return SimpleNamespace(
        im=SimpleNamespace(v1=SimpleNamespace(message_reaction=reaction_api)),
        config=config,
    )


def _response(success: bool, data=None):
    """Build a Lark API response double.

    Args:
        success: Whether the API call succeeded.
        data: Optional response payload.

    Returns:
        Response object exposing success()/code/msg/data.
    """
    return SimpleNamespace(
        success=lambda: success, code=0 if success else 99991, msg="ok", data=data
    )


class _FakeEvent:
    """Minimal event double for PreProcessStage reaction tracking."""

    def __init__(
        self,
        reaction_id: str | None = "reaction-1",
        platform: str = "lark",
        reaction_created: bool | None = None,
    ):
        self._reaction_id = reaction_id
        self._platform = platform
        self._reaction_created = (
            reaction_created
            if reaction_created is not None
            else reaction_id is not None
        )
        self._extras: dict = {}
        self.is_at_or_wake_command = True
        self.message_obj = SimpleNamespace(message=[], message_str="")
        self.message_str = ""
        self.react_calls: list[str] = []

    def get_platform_name(self) -> str:
        return self._platform

    def get_messages(self):
        return self.message_obj.message

    def set_extra(self, key, value) -> None:
        self._extras[key] = value

    def get_extra(self, key: str | None = None, default=None):
        if key is None:
            return self._extras
        return self._extras.get(key, default)

    async def react(self, emoji: str):
        self.react_calls.append(emoji)
        self.set_extra(LAST_REACTION_CREATED, self._reaction_created)
        return self._reaction_id


async def _run_preprocess(event: _FakeEvent, cfg: dict, platform: str = "lark") -> None:
    """Run PreProcessStage with the given pre-ack config.

    Args:
        event: Fake event instance under test.
        cfg: platform_specific.<platform>.pre_ack_emoji config fragment.
        platform: Platform name used to look up platform_specific config.
    """
    stage = PreProcessStage()
    stage.config = {"platform_specific": {platform: {"pre_ack_emoji": cfg}}}
    stage.platform_settings = {}
    stage.stt_settings = {"enable": False}
    await stage.process(event)


async def _execute_scheduler(remove_reaction: AsyncMock, fail_processing: bool) -> None:
    """Run PipelineScheduler.execute with a stub event.

    Args:
        remove_reaction: Double standing in for the event remove_reaction method.
        fail_processing: Whether _process_stages should raise an error.
    """
    from astrbot.core.pipeline.scheduler import PipelineScheduler

    event = SimpleNamespace(
        get_extra=lambda key=None, default=None: (
            ("reaction-1", "Typing") if key == PRE_ACK_REACTION else default
        ),
        remove_reaction=remove_reaction,
        cleanup_temporary_local_files=lambda: None,
    )
    registry = SimpleNamespace(register=lambda e: None, unregister=lambda e: None)
    scheduler = PipelineScheduler.__new__(PipelineScheduler)
    process_stages = AsyncMock(
        side_effect=RuntimeError("boom") if fail_processing else None
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("astrbot.core.pipeline.scheduler.active_event_registry", registry)
        mp.setattr(PipelineScheduler, "_process_stages", process_stages)
        if fail_processing:
            with pytest.raises(RuntimeError, match="boom"):
                await PipelineScheduler.execute(scheduler, event)
        else:
            await PipelineScheduler.execute(scheduler, event)


def test_default_config_pre_ack_enables_auto_remove():
    pre_ack = DEFAULT_CONFIG["platform_specific"]["lark"]["pre_ack_emoji"]
    assert pre_ack == {"enable": False, "emojis": ["Typing"], "auto_remove": True}


@pytest.mark.asyncio
async def test_lark_react_returns_reaction_id():
    reaction_api = SimpleNamespace(
        acreate=AsyncMock(
            return_value=_response(True, SimpleNamespace(reaction_id="reaction-123"))
        )
    )
    event = _lark_event(_lark_bot(reaction_api))

    reaction_id = await event.react("Typing")

    assert reaction_id == "reaction-123"
    reaction_api.acreate.assert_awaited_once()


@pytest.mark.asyncio
async def test_lark_react_returns_none_on_failure():
    reaction_api = SimpleNamespace(acreate=AsyncMock(return_value=_response(False)))
    event = _lark_event(_lark_bot(reaction_api))

    reaction_id = await event.react("Typing")

    assert reaction_id is None
    assert event.get_extra(LAST_REACTION_CREATED) is False


@pytest.mark.asyncio
async def test_lark_react_marks_success_without_reaction_id():
    reaction_api = SimpleNamespace(acreate=AsyncMock(return_value=_response(True)))
    event = _lark_event(_lark_bot(reaction_api))

    reaction_id = await event.react("Typing")

    assert reaction_id is None
    assert event.get_extra(LAST_REACTION_CREATED) is True


@pytest.mark.asyncio
async def test_lark_remove_reaction_deletes_by_id():
    reaction_api = SimpleNamespace(adelete=AsyncMock(return_value=_response(True)))
    event = _lark_event(_lark_bot(reaction_api))

    await event.remove_reaction("reaction-123")

    reaction_api.adelete.assert_awaited_once()
    request = reaction_api.adelete.await_args.args[0]
    assert request.message_id == "message-1"
    assert request.reaction_id == "reaction-123"


@pytest.mark.asyncio
async def test_lark_remove_reaction_api_failure_without_emoji_does_not_raise():
    reaction_api = SimpleNamespace(adelete=AsyncMock(return_value=_response(False)))
    event = _lark_event(_lark_bot(reaction_api))

    await event.remove_reaction("reaction-123")

    reaction_api.adelete.assert_awaited_once()


@pytest.mark.asyncio
async def test_lark_remove_reaction_retries_same_id_after_delete_failure():
    reaction_api = SimpleNamespace(
        adelete=AsyncMock(side_effect=[_response(False), _response(True)]),
        alist=AsyncMock(
            return_value=_response(
                True,
                SimpleNamespace(
                    items=[
                        SimpleNamespace(
                            reaction_id="reaction-123",
                            operator=SimpleNamespace(operator_id="old-bot"),
                        ),
                        SimpleNamespace(
                            reaction_id="old-reaction",
                            operator=SimpleNamespace(operator_id="bot"),
                        ),
                    ],
                    has_more=False,
                    page_token=None,
                ),
            )
        ),
    )
    event = _lark_event(_lark_bot(reaction_api))

    await event.remove_reaction("reaction-123", "Typing")

    reaction_api.alist.assert_awaited_once()
    assert reaction_api.adelete.await_count == 2
    assert reaction_api.adelete.await_args_list[1].args[0].reaction_id == "reaction-123"


@pytest.mark.asyncio
async def test_lark_remove_reaction_does_not_delete_another_reaction_when_target_is_missing():
    reaction_api = SimpleNamespace(
        adelete=AsyncMock(return_value=_response(False)),
        alist=AsyncMock(
            return_value=_response(
                True,
                SimpleNamespace(
                    items=[
                        SimpleNamespace(
                            reaction_id="old-reaction",
                            operator=SimpleNamespace(operator_id="bot"),
                        )
                    ],
                    has_more=False,
                    page_token=None,
                ),
            )
        ),
    )
    event = _lark_event(_lark_bot(reaction_api))

    await event.remove_reaction("reaction-123", "Typing")

    reaction_api.alist.assert_awaited_once()
    reaction_api.adelete.assert_awaited_once()


@pytest.mark.asyncio
async def test_lark_remove_reaction_resolves_missing_id_by_emoji():
    reaction_api = SimpleNamespace(
        alist=AsyncMock(
            return_value=_response(
                True,
                SimpleNamespace(
                    items=[
                        SimpleNamespace(
                            reaction_id="reaction-123",
                            operator=SimpleNamespace(operator_id="bot"),
                        )
                    ],
                    has_more=False,
                    page_token=None,
                ),
            )
        ),
        adelete=AsyncMock(return_value=_response(True)),
    )
    event = _lark_event(_lark_bot(reaction_api))

    await event.remove_reaction(emoji="Typing")

    reaction_api.alist.assert_awaited_once()
    reaction_api.adelete.assert_awaited_once()
    assert reaction_api.adelete.await_args.args[0].reaction_id == "reaction-123"


@pytest.mark.asyncio
async def test_lark_remove_reaction_matches_operator_app_id():
    reaction_api = SimpleNamespace(
        alist=AsyncMock(
            return_value=_response(
                True,
                SimpleNamespace(
                    items=[
                        SimpleNamespace(
                            reaction_id="reaction-123",
                            operator=SimpleNamespace(operator_id="cli_app"),
                        )
                    ],
                    has_more=False,
                    page_token=None,
                ),
            )
        ),
        adelete=AsyncMock(return_value=_response(True)),
    )
    event = _lark_event(
        _lark_bot(reaction_api),
        self_id="ou_bot",
        app_id="cli_app",
    )

    await event.remove_reaction(emoji="Typing")

    reaction_api.adelete.assert_awaited_once()
    assert reaction_api.adelete.await_args.args[0].reaction_id == "reaction-123"


@pytest.mark.asyncio
async def test_lark_remove_reaction_paginates_until_found():
    reaction_api = SimpleNamespace(
        alist=AsyncMock(
            side_effect=[
                _response(
                    True,
                    SimpleNamespace(items=[], has_more=True, page_token="page-2"),
                ),
                _response(
                    True,
                    SimpleNamespace(
                        items=[
                            SimpleNamespace(
                                reaction_id="reaction-123",
                                operator=SimpleNamespace(operator_id="bot"),
                            )
                        ],
                        has_more=False,
                        page_token=None,
                    ),
                ),
            ]
        ),
        adelete=AsyncMock(return_value=_response(True)),
    )
    event = _lark_event(_lark_bot(reaction_api))

    await event.remove_reaction(emoji="Typing")

    assert reaction_api.alist.await_count == 2
    assert reaction_api.alist.await_args_list[1].args[0].page_token == "page-2"
    reaction_api.adelete.assert_awaited_once()
    assert reaction_api.adelete.await_args.args[0].reaction_id == "reaction-123"


@pytest.mark.asyncio
async def test_lark_remove_reaction_swallows_list_exception():
    reaction_api = SimpleNamespace(
        adelete=AsyncMock(return_value=_response(False)),
        alist=AsyncMock(side_effect=RuntimeError("list failed")),
    )
    event = _lark_event(_lark_bot(reaction_api))

    await event.remove_reaction("reaction-123", "Typing")

    reaction_api.alist.assert_awaited_once()
    reaction_api.adelete.assert_awaited_once()


@pytest.mark.asyncio
async def test_lark_remove_reaction_swallows_retry_delete_exception():
    reaction_api = SimpleNamespace(
        adelete=AsyncMock(
            side_effect=[_response(False), RuntimeError("delete failed")]
        ),
        alist=AsyncMock(
            return_value=_response(
                True,
                SimpleNamespace(
                    items=[
                        SimpleNamespace(
                            reaction_id="reaction-123",
                            operator=SimpleNamespace(operator_id="bot"),
                        )
                    ],
                    has_more=False,
                    page_token=None,
                ),
            )
        ),
    )
    event = _lark_event(_lark_bot(reaction_api))

    await event.remove_reaction("reaction-123", "Typing")

    assert reaction_api.adelete.await_count == 2


@pytest.mark.asyncio
async def test_base_remove_reaction_is_noop():
    class _Event(AstrMessageEvent):
        async def send(self, message):
            return None

    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.self_id = "bot"
    message.session_id = "session"
    message.message_id = "msg"
    message.sender = MessageMember(user_id="user", nickname="User")
    message.message = []
    message.message_str = "hello"
    event = _Event(
        message_str="hello",
        message_obj=message,
        platform_meta=PlatformMetadata(name="test", description="t", id="test"),
        session_id="session",
    )
    await event.remove_reaction("any")


@pytest.mark.asyncio
async def test_preprocess_stores_reaction_when_enabled():
    event = _FakeEvent(reaction_id="reaction-1")
    await _run_preprocess(
        event,
        {"enable": True, "emojis": ["Typing"], "auto_remove": True},
    )

    assert event.react_calls == ["Typing"]
    assert event.get_extra(PRE_ACK_REACTION) == ("reaction-1", "Typing")


@pytest.mark.asyncio
async def test_preprocess_skips_storage_when_auto_remove_disabled():
    event = _FakeEvent(reaction_id="reaction-1")
    await _run_preprocess(
        event,
        {"enable": True, "emojis": ["Typing"], "auto_remove": False},
    )

    assert event.react_calls == ["Typing"]
    assert event.get_extra(PRE_ACK_REACTION, None) is None


@pytest.mark.asyncio
async def test_preprocess_does_not_track_reaction_when_creation_returns_no_id():
    event = _FakeEvent(reaction_id=None)
    await _run_preprocess(event, {"enable": True, "emojis": ["Typing"]})

    assert event.get_extra(PRE_ACK_REACTION, None) is None


@pytest.mark.asyncio
async def test_preprocess_tracks_successful_reaction_without_id_for_removal():
    event = _FakeEvent(reaction_id=None, reaction_created=True)
    await _run_preprocess(
        event,
        {"enable": True, "emojis": ["Typing"], "auto_remove": True},
    )

    assert event.get_extra(PRE_ACK_REACTION) == (None, "Typing")


@pytest.mark.asyncio
async def test_preprocess_skips_reaction_when_disabled():
    for cfg in ({"enable": False, "emojis": ["Typing"]}, {"emojis": ["Typing"]}):
        event = _FakeEvent()
        await _run_preprocess(event, cfg)

        assert event.react_calls == []
        assert event.get_extra(PRE_ACK_REACTION, None) is None


@pytest.mark.asyncio
async def test_preprocess_skips_storage_on_non_lark_platform():
    event = _FakeEvent(reaction_id="reaction-1", platform="telegram")
    await _run_preprocess(
        event,
        {"enable": True, "emojis": ["Typing"]},
        platform="telegram",
    )

    assert event.react_calls == ["Typing"]
    assert event.get_extra(PRE_ACK_REACTION, None) is None


@pytest.mark.asyncio
async def test_scheduler_removes_pre_ack_reaction_on_completion():
    remove_reaction = AsyncMock()
    await _execute_scheduler(remove_reaction, fail_processing=False)

    remove_reaction.assert_awaited_once_with("reaction-1", "Typing")


@pytest.mark.asyncio
async def test_scheduler_finally_removes_pre_ack_reaction_on_error():
    remove_reaction = AsyncMock()
    await _execute_scheduler(remove_reaction, fail_processing=True)

    remove_reaction.assert_awaited_once_with("reaction-1", "Typing")


@pytest.mark.asyncio
async def test_scheduler_finally_swallows_remove_reaction_errors():
    remove_reaction = AsyncMock(side_effect=RuntimeError("delete failed"))
    await _execute_scheduler(remove_reaction, fail_processing=True)

    remove_reaction.assert_awaited_once()


@pytest.mark.asyncio
async def test_scheduler_cleans_up_when_reaction_removal_is_cancelled():
    from astrbot.core.pipeline.scheduler import PipelineScheduler

    cleanup = Mock()
    unregister = Mock()
    remove_reaction = AsyncMock(side_effect=asyncio.CancelledError())
    event = SimpleNamespace(
        get_extra=lambda key=None, default=None: (
            ("reaction-1", "Typing") if key == PRE_ACK_REACTION else default
        ),
        remove_reaction=remove_reaction,
        cleanup_temporary_local_files=cleanup,
    )
    registry = SimpleNamespace(register=Mock(), unregister=unregister)
    scheduler = PipelineScheduler.__new__(PipelineScheduler)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("astrbot.core.pipeline.scheduler.active_event_registry", registry)
        mp.setattr(PipelineScheduler, "_process_stages", AsyncMock())
        with pytest.raises(asyncio.CancelledError):
            await PipelineScheduler.execute(scheduler, event)

    cleanup.assert_called_once_with()
    unregister.assert_called_once_with(event)
