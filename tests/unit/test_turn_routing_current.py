"""Pin current inbound routing behavior before the turn-routing refactor."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.command import build_command_catalog
from astrbot.core.message.components import At, Plain
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.star import StarMetadata
from astrbot.core.star.star_handler import EventType, StarHandlerMetadata
from tests.unit.test_agent_request_sub_stage import FakeEvent as AgentFakeEvent
from tests.unit.test_agent_request_sub_stage import _ctx as agent_request_ctx
from tests.unit.test_agent_request_sub_stage import agent_request
from tests.unit.test_waking_check_stage import FakeEvent, install_handlers, make_stage


def _chat_group_handlers() -> tuple[StarHandlerMetadata, StarHandlerMetadata]:
    group = CommandGroupFilter("chat")

    def group_handler(self) -> None: ...

    group_md = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        "test.plugin_chat_group",
        "chat",
        "test.plugin",
        group_handler,
        [group],
    )

    async def status(self, event) -> None: ...

    child_md = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        "test.plugin_chat_status",
        "status",
        "test.plugin",
        status,
        [],
        extras_configs={"sub_command": True},
    )
    child = CommandFilter("status", parent_command_names=["chat"])
    child.init_handler_md(child_md)
    child_md.event_filters.append(child)
    group.add_sub_command_filter(child)
    return group_md, child_md


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("settings", "text", "expected_wake"),
    [
        ({}, "今天天气", True),
        ({"llm_access": {"private": "prefix"}}, "今天天气", False),
        ({"llm_access": {"private": "prefix"}}, "/今天天气", True),
    ],
)
async def test_private_llm_access_prefix_matrix(settings, text, expected_wake):
    stage = await make_stage(**settings)
    event = FakeEvent([Plain(text)], private=True, message_text=text)

    assert (await stage._detect_wake(event)).should_wake is expected_wake
    assert event.is_wake is expected_wake
    assert event.is_at_or_wake_command is expected_wake


@pytest.mark.asyncio
async def test_private_extra_token_chat_leaves_slash_and_bare_forms():
    stage = await make_stage()
    slash = FakeEvent(
        [Plain("/chat 今天天气")],
        private=True,
        message_text="/chat 今天天气",
    )
    bare = FakeEvent(
        [Plain("chat 今天天气")],
        private=True,
        message_text="chat 今天天气",
    )

    assert (await stage._detect_wake(slash)).should_wake is True
    assert slash.message_str == "chat 今天天气"
    assert (await stage._detect_wake(bare)).should_wake is True
    assert bare.message_str == "chat 今天天气"


@pytest.mark.asyncio
async def test_extra_token_chat_matches_slash_and_bare_after_first_gate(monkeypatch):
    stage = agent_request.AgentRequestSubStage()
    ctx = agent_request_ctx()
    await stage.initialize(ctx)
    stage.agent_sub_stage.responses = ["done"]
    monkeypatch.setattr(
        agent_request.SessionServiceManager,
        "should_process_llm_request",
        AsyncMock(return_value=True),
    )

    slash = AgentFakeEvent("umo-slash")
    slash.message_str = "chat 今天天气"
    bare = AgentFakeEvent("umo-bare")
    bare.message_str = "chat 今天天气"

    slash_out = [item async for item in stage.process(slash)]
    bare_out = [item async for item in stage.process(bare)]

    assert slash_out == ["done"]
    assert bare_out == ["done"]
    assert stage.agent_sub_stage.process_calls == [slash, bare]


@pytest.mark.asyncio
async def test_chat_status_is_command_and_unknown_subcommand_does_not_reach_llm(
    monkeypatch,
):
    stage = await make_stage()
    group_md, child_md = _chat_group_handlers()
    install_handlers(stage, monkeypatch, [group_md, child_md])

    status = FakeEvent([Plain("/chat status")], message_text="/chat status")
    await stage.process(status)
    assert status.stopped is False
    assert status.sent == []
    assert status.get_extra("activated_handlers") == [child_md]
    assert status.is_at_or_wake_command is True

    unknown = FakeEvent(
        [Plain("/chat 今天天气")],
        message_text="/chat 今天天气",
    )
    await stage.process(unknown)
    assert unknown.stopped is True
    assert unknown.sent
    assert "不存在子指令" in unknown.sent[0].get_plain_text()
    assert unknown.get_extra("activated_handlers", []) == []


@pytest.mark.asyncio
async def test_two_plugins_sharing_a_name_neither_dispatches(monkeypatch):
    stage = await make_stage()

    async def first(self, event) -> None: ...

    async def second(self, event) -> None: ...

    first_md = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        "plugin.alpha_hello",
        "hello",
        "plugin.alpha",
        first,
        [],
    )
    first_filter = CommandFilter("hello")
    first_filter.init_handler_md(first_md)
    first_md.event_filters.append(first_filter)

    second_md = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        "plugin.beta_hello",
        "hello",
        "plugin.beta",
        second,
        [],
    )
    second_filter = CommandFilter("hello")
    second_filter.init_handler_md(second_md)
    second_md.event_filters.append(second_filter)

    stage.ctx.handlers = SimpleNamespace(
        get_handlers_by_event_type=lambda *_args, **_kwargs: [first_md, second_md],
    )
    for handler, name in ((first_md, "alpha"), (second_md, "beta")):
        stage.ctx.plugins.publish(
            StarMetadata(
                name=name,
                module_path=handler.handler_module_path,
                activated=True,
            )
        )
    stage.command_catalog.replace(build_command_catalog([first_md, second_md]))

    event = FakeEvent([Plain("/hello")], message_text="/hello")
    await stage.process(event)

    assert event.get_extra("activated_handlers") == []


@pytest.mark.asyncio
async def test_napcat_input_status_is_not_queued():
    from astrbot.core.platform.sources.napcat.generated.ob11_events import OB11AllEvent
    from tests.unit.platform.napcat_adapter_support import _make_adapter

    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "notify",
            "sub_type": "input_status",
            "time": 1720000000,
            "self_id": 123456,
            "user_id": 3013138453,
            "group_id": 0,
            "event_type": 1,
            "status_text": "对方正在输入...",
        }
    )

    await adapter.handle_forward_ws_event(event)

    assert queue.empty()


@pytest.mark.asyncio
async def test_group_prefix_does_not_wake_when_first_component_ats_someone_else():
    stage = await make_stage()
    event = FakeEvent(
        [At(qq="other"), Plain("/hello")],
        message_text="/hello",
    )

    decision = await stage._detect_wake(event)

    assert decision.should_wake is False
    assert event.is_wake is False
    assert event.is_at_or_wake_command is False
    assert event.message_str == "/hello"


@pytest.mark.asyncio
async def test_non_command_filter_still_handles_notice_and_request(monkeypatch):
    stage = await make_stage()

    class NoticeFilter:
        def filter(self, event, _cfg) -> bool:
            return event.get_extra("onebot_post_type") in {"notice", "request"}

    handler = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        "test.plugin_notice",
        "on_notice",
        "test.plugin",
        lambda *_args: None,
        [NoticeFilter()],
    )
    install_handlers(stage, monkeypatch, [handler])

    notice = FakeEvent(
        [Plain("poke")],
        extras={"onebot_post_type": "notice"},
    )
    await stage.process(notice)
    assert notice.stopped is False
    assert notice.get_extra("activated_handlers") == [handler]
    assert notice.is_wake is True
    assert notice.is_at_or_wake_command is False

    request = FakeEvent(
        [Plain("friend add")],
        extras={"onebot_post_type": "request"},
    )
    await stage.process(request)
    assert request.stopped is False
    assert request.get_extra("activated_handlers") == [handler]
    assert request.is_wake is True
    assert request.is_at_or_wake_command is False
