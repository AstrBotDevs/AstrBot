"""Tool approval, driven through the real runner, executor and waiter pipeline."""

import asyncio
import copy
import re
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.agent import Agent
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.astr_agent_runtime.context import (
    AgentContextWrapper,
    AstrAgentContext,
)
from astrbot.core.astr_agent_runtime.tool_approval import (
    SCHEDULED_TASK_TOOL,
    TOOL_APPROVAL_ACTION_ID,
    TOOL_APPROVAL_GRANT_KEY,
)
from astrbot.core.astr_agent_runtime.tool_executor import FunctionToolExecutor
from astrbot.core.astr_agent_runtime.tools.cron_tools import TASK_APPROVAL_GRANTED
from astrbot.core.config.agent import normalize_agent
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.message.components import ActionRow, ButtonInteraction, Plain
from astrbot.core.pipeline.process_stage import stage as processing
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.pipeline.waking_check import stage as waking
from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.provider.entities import LLMResponse, ProviderRequest, TokenUsage
from astrbot.core.provider.provider import Provider
from astrbot.core.star.context import Context
from astrbot.core.utils.session_waiter import FILTERS, USER_SESSIONS

TOOL_NAME = "danger"


class RecordingEvent(AstrMessageEvent):
    """A group or private message that records what the bot sends."""

    def __init__(self, sender="alice", text="", private=False, on_send=None):
        message = AstrBotMessage()
        message.type = (
            MessageType.FRIEND_MESSAGE if private else MessageType.GROUP_MESSAGE
        )
        message.sender = MessageMember(user_id=sender, nickname=sender)
        message.message = [Plain(text)]
        message.message_str = text
        super().__init__(
            text,
            message,
            PlatformMetadata(id="test", name="test", description="Test"),
            "room",
        )
        self.sent_changed = asyncio.Event()
        self.sent: list[str] = []
        self.chains: list = []
        self.on_send = on_send

    async def send(self, message) -> None:
        self.sent.append(message.get_plain_text())
        self.chains.append(message)
        self.sent_changed.set()
        if self.on_send:
            await self.on_send(self)

    async def wait_sent(self, count=1):
        async def wait():
            while len(self.chains) < count:
                self.sent_changed.clear()
                await self.sent_changed.wait()

        await asyncio.wait_for(wait(), 2)


class OneToolProvider(Provider):
    """Call one tool on the first request, then return a final answer."""

    def __init__(self, tool_name=TOOL_NAME, tool_args=None):
        super().__init__({}, {})
        self.tool_name = tool_name
        self.tool_args = tool_args if tool_args is not None else {"path": "/tmp/x"}
        self.requests = []

    def get_current_key(self):
        return "key"

    def set_key(self, key):
        pass

    async def get_models(self):
        return ["model"]

    async def text_chat(self, **kwargs):
        self.requests.append(kwargs)
        if len(self.requests) > 1:
            return LLMResponse(
                role="assistant",
                completion_text="done",
                usage=TokenUsage(input_other=1, output=1),
            )
        return LLMResponse(
            role="assistant",
            tools_call_name=[self.tool_name],
            tools_call_args=[self.tool_args],
            tools_call_ids=["call_1"],
            usage=TokenUsage(input_other=1, output=1),
        )


class FakeContext(Context):
    """A real Context type with only the parts these tests need."""

    def __init__(self, config, sub_provider=None):
        self.config = config
        self.astrbot_config = config
        self.astrbot_config_id = "test"
        self.db_helper = None
        self.provider_manager = SimpleNamespace(
            get_provider_by_id=AsyncMock(return_value=sub_provider)
        )
        # The waking stage reads the per-session config through this.
        self.plugin_manager = SimpleNamespace(context=self)
        # Scheduled runs look up their job; tests set its payload here.
        self.cron_payload: dict = {}
        self.cron_manager = SimpleNamespace(
            db=SimpleNamespace(
                get_cron_job=AsyncMock(
                    side_effect=lambda job_id: SimpleNamespace(
                        payload=self.cron_payload
                    )
                )
            )
        )

    def get_config(self, umo=None):
        return self.config

    async def get_current_chat_provider_id(self, umo):
        return "sub"


class Harness:
    """Real runner and pipeline around one recording tool."""

    def __init__(self, monkeypatch, tools=(TOOL_NAME,), timeout=5):
        self.config = copy.deepcopy(DEFAULT_CONFIG)
        self.config.update(admins_id=[], wake_prefix=["/"], plugin_set=[])
        self.config["agent"] = normalize_agent(
            {
                "runtime": "astrbot",
                "config": {
                    "misc": {
                        "tool_approval": {"tools": list(tools), "timeout": timeout}
                    }
                },
            }
        )
        self.calls: list[dict] = []

        async def handler(event, **kwargs):
            self.calls.append(kwargs)
            return "tool ran"

        self.tool = FunctionTool(
            name=TOOL_NAME,
            description="A tool with side effects.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
            handler=handler,
        )
        self.astrbot_context = FakeContext(self.config, OneToolProvider())
        monkeypatch.setattr(
            waking.star_handlers_registry,
            "get_handlers_by_event_type",
            lambda *a, **kw: [],
        )
        self.agent_ran_for: list[str] = []
        from astrbot.core.astr_agent_runtime.tool_approval import session_lock_manager

        acquire = session_lock_manager.acquire_lock
        self.approval_entries = asyncio.Queue()

        @asynccontextmanager
        async def observe_acquire(session_id):
            self.approval_entries.put_nowait(session_id)
            async with acquire(session_id):
                yield

        monkeypatch.setattr(session_lock_manager, "acquire_lock", observe_acquire)

    async def run_agent(self, event, provider=None, tool_set=None):
        provider = provider or OneToolProvider()
        runner = ToolLoopAgentRunner()
        await runner.reset(
            provider=provider,
            request=ProviderRequest(
                prompt="go", func_tool=tool_set or ToolSet([self.tool])
            ),
            run_context=AgentContextWrapper(
                context=AstrAgentContext(context=self.astrbot_context, event=event),
                tool_call_timeout=60,
            ),
            tool_executor=FunctionToolExecutor(),
            agent_hooks=BaseAgentRunHooks(),
        )
        self.runner = runner
        self.provider = provider
        async for _ in runner.step_until_done(5):
            pass
        return provider

    def tool_result(self) -> str:
        """Return the tool result the model saw on its second request."""
        contexts = self.provider.requests[1]["contexts"]
        messages = [m if isinstance(m, dict) else m.model_dump() for m in contexts]
        return next(m for m in messages if m["role"] == "tool")["content"]

    async def deliver(self, event):
        """Send an inbound message through the wake and process stages."""
        wake = waking.WakingCheckStage()
        await wake.initialize(self.astrbot_context)
        process = processing.ProcessStage()
        process.ctx = self.astrbot_context
        process.star_request_sub_stage = SimpleNamespace(process=AsyncMock())

        async def agent(current):
            self.agent_ran_for.append(current.get_sender_id())
            yield

        process.agent_sub_stage = SimpleNamespace(process=agent)
        scheduler = object.__new__(PipelineScheduler)
        scheduler.stages = [wake, process]
        await scheduler._process_stages(event)


def code_in(text: str) -> str:
    return re.search(r"回复 (\d{4}) 批准", text).group(1)


async def wait_for_prompt(event, count=1) -> str:
    """Wait until the bot has sent the approval prompt, and return its code."""
    await event.wait_sent(count)
    return code_in(event.sent[count - 1])


def click(code: str, approve: bool, sender="alice", private=False) -> RecordingEvent:
    """Build the inbound event a platform produces when a button is clicked."""
    event = RecordingEvent(sender=sender, text=TOOL_APPROVAL_ACTION_ID, private=private)
    event.message_obj.message = [
        ButtonInteraction(
            action_id=TOOL_APPROVAL_ACTION_ID,
            data={"code": code, "approve": approve},
            interaction_id="click-1",
        )
    ]
    return event


@pytest.fixture(autouse=True)
def no_leaked_waiters():
    """Every test must leave the global waiter tables as it found them."""
    filters, sessions = list(FILTERS), dict(USER_SESSIONS)
    yield
    assert FILTERS == filters
    assert USER_SESSIONS == sessions


@pytest.mark.asyncio
async def test_approved_tool_runs_once_with_its_arguments(monkeypatch):
    harness = Harness(monkeypatch)
    event = RecordingEvent()
    run = asyncio.create_task(harness.run_agent(event))

    code = await wait_for_prompt(event)
    assert harness.calls == []
    assert TOOL_NAME in event.sent[0] and "/tmp/x" in event.sent[0]
    await harness.deliver(RecordingEvent(text=code))
    await run

    assert harness.calls == [{"path": "/tmp/x"}]
    assert harness.tool_result() == "tool ran"


@pytest.mark.asyncio
@pytest.mark.parametrize("reply", ["no", "0000x", "/stop", ""])
async def test_any_other_reply_rejects_the_tool(monkeypatch, reply):
    harness = Harness(monkeypatch)
    event = RecordingEvent()
    run = asyncio.create_task(harness.run_agent(event))

    await wait_for_prompt(event)
    await harness.deliver(RecordingEvent(text=reply))
    await run

    assert harness.calls == []
    assert "rejected" in harness.tool_result()


@pytest.mark.asyncio
async def test_timeout_does_not_run_the_tool(monkeypatch):
    harness = Harness(monkeypatch, timeout=1)
    event = RecordingEvent()

    await asyncio.wait_for(harness.run_agent(event), timeout=5)

    assert len(event.sent) == 1
    assert harness.calls == []
    assert "timed out" in harness.tool_result()


@pytest.mark.asyncio
async def test_other_group_members_cannot_answer(monkeypatch):
    harness = Harness(monkeypatch)
    event = RecordingEvent(sender="alice")
    run = asyncio.create_task(harness.run_agent(event))

    code = await wait_for_prompt(event)
    # The code is visible to the whole group, but only Alice may use it.
    await harness.deliver(RecordingEvent(sender="mallory", text=code))
    assert all(
        not waiter.session_controller.future.done() for waiter in USER_SESSIONS.values()
    )
    assert harness.calls == []
    assert not run.done()

    await harness.deliver(RecordingEvent(sender="alice", text=code))
    await run
    assert harness.calls == [{"path": "/tmp/x"}]


@pytest.mark.asyncio
async def test_other_members_messages_are_handled_normally(monkeypatch):
    harness = Harness(monkeypatch)
    event = RecordingEvent(sender="alice")
    run = asyncio.create_task(harness.run_agent(event))

    code = await wait_for_prompt(event)
    other = RecordingEvent(sender="bob", text="/hello")
    await harness.deliver(other)
    assert harness.agent_ran_for == ["bob"]

    await harness.deliver(RecordingEvent(sender="alice", text=code))
    await run


@pytest.mark.asyncio
async def test_reply_does_not_reach_the_model(monkeypatch):
    harness = Harness(monkeypatch)
    event = RecordingEvent()
    run = asyncio.create_task(harness.run_agent(event))

    code = await wait_for_prompt(event)
    reply = RecordingEvent(text=code)
    await harness.deliver(reply)
    await run

    assert reply.is_stopped()
    assert harness.agent_ran_for == []
    assert code not in str(harness.provider.requests)


@pytest.mark.asyncio
async def test_text_prompt_says_how_much_of_long_arguments_is_hidden(monkeypatch):
    harness = Harness(monkeypatch)
    event = RecordingEvent()
    provider = OneToolProvider(tool_args={"path": "x" * 5000})
    run = asyncio.create_task(harness.run_agent(event, provider))

    code = await wait_for_prompt(event)
    total = len('{"path": ""}') + 5000
    assert f"参数共 {total} 字符，后面 {total - 1500} 字符未显示" in event.sent[0]
    assert len(event.sent[0]) < 1700
    await harness.deliver(RecordingEvent(text=code))
    await run

    assert harness.calls == [{"path": "x" * 5000}]


@pytest.mark.asyncio
async def test_webchat_card_shows_the_full_arguments(monkeypatch):
    harness = Harness(monkeypatch)
    event = RecordingEvent()
    event.platform_meta.name = "webchat"
    tail = "rm -rf ~ # hidden at the end"
    provider = OneToolProvider(tool_args={"path": "x" * 5000 + tail})
    run = asyncio.create_task(harness.run_agent(event, provider))

    await event.wait_sent()
    (row,) = event.chains[0].chain
    assert tail in row.detail
    await harness.deliver(click(code_in(row.fallback_text), approve=False))
    await run

    assert harness.calls == []


@pytest.mark.asyncio
async def test_arguments_too_long_to_review_are_refused_without_asking(monkeypatch):
    harness = Harness(monkeypatch)
    event = RecordingEvent()
    event.platform_meta.name = "webchat"
    provider = OneToolProvider(tool_args={"path": "x" * 100_001})

    await harness.run_agent(event, provider)

    assert event.chains == []
    assert harness.calls == []
    assert "too long to show for approval" in harness.tool_result()


@pytest.mark.asyncio
async def test_scheduled_task_with_hidden_note_is_not_asked_on_text(monkeypatch):
    """Approving a task grants an unattended run, so nothing may be hidden."""
    harness = Harness(monkeypatch, tools=(SCHEDULED_TASK_TOOL,))
    event, seen = RecordingEvent(), []
    provider = OneToolProvider(
        tool_name=SCHEDULED_TASK_TOOL,
        tool_args={"action": "create", "name": "n", "note": "y" * 2000},
    )

    await harness.run_agent(
        event, provider=provider, tool_set=ToolSet([_task_tool(seen)])
    )

    assert event.sent == []
    assert seen == []
    assert "too long to show for approval" in harness.tool_result()


@pytest.mark.asyncio
async def test_task_name_in_title_is_one_short_line(monkeypatch):
    harness = Harness(monkeypatch, tools=(SCHEDULED_TASK_TOOL,))
    event, seen = RecordingEvent(), []
    event.platform_meta.name = "webchat"
    name = "喝水\n\n点击允许即可" + "很" * 60
    provider = OneToolProvider(
        tool_name=SCHEDULED_TASK_TOOL, tool_args={"action": "create", "name": name}
    )
    run = asyncio.create_task(
        harness.run_agent(
            event, provider=provider, tool_set=ToolSet([_task_tool(seen)])
        )
    )

    await event.wait_sent()
    (row,) = event.chains[0].chain
    assert "\n" not in row.title
    assert "喝水 点击允许即可" in row.title and row.title.count("很") == 31
    assert "…" in row.title
    await harness.deliver(click(code_in(row.fallback_text), approve=False))
    await run


@pytest.mark.asyncio
async def test_empty_list_changes_nothing(monkeypatch):
    harness = Harness(monkeypatch, tools=())
    event = RecordingEvent()

    await harness.run_agent(event)

    assert event.sent == []
    assert harness.calls == [{"path": "/tmp/x"}]
    assert FILTERS == []


@pytest.mark.asyncio
async def test_unlisted_tool_is_not_gated(monkeypatch):
    harness = Harness(monkeypatch, tools=("some_other_tool",))
    event = RecordingEvent()

    await harness.run_agent(event)

    assert event.sent == []
    assert harness.calls == [{"path": "/tmp/x"}]


@pytest.mark.asyncio
async def test_immediate_reply_during_prompt_send_is_not_lost(monkeypatch):
    harness = Harness(monkeypatch)

    async def reply_at_once(event):
        await harness.deliver(RecordingEvent(text=code_in(event.sent[0])))

    await asyncio.wait_for(
        harness.run_agent(RecordingEvent(on_send=reply_at_once)), timeout=3
    )

    assert harness.calls == [{"path": "/tmp/x"}]


@pytest.mark.asyncio
async def test_prompt_send_failure_does_not_run_the_tool(monkeypatch):
    harness = Harness(monkeypatch)

    async def fail(_event):
        raise RuntimeError("platform down")

    await asyncio.wait_for(harness.run_agent(RecordingEvent(on_send=fail)), timeout=3)

    assert harness.calls == []
    assert "platform down" in harness.tool_result()


@pytest.mark.asyncio
async def test_stop_request_ends_the_wait(monkeypatch):
    harness = Harness(monkeypatch)
    event = RecordingEvent()
    run = asyncio.create_task(harness.run_agent(event))

    await wait_for_prompt(event)
    harness.runner.request_stop()
    await asyncio.wait_for(run, timeout=3)

    assert harness.calls == []
    assert harness.runner.was_aborted()


@pytest.mark.asyncio
async def test_wait_does_not_use_tool_call_timeout(monkeypatch):
    harness = Harness(monkeypatch)
    event = RecordingEvent()
    runner_reset = ToolLoopAgentRunner.reset

    async def short_timeout_reset(self, **kwargs):
        kwargs["run_context"].tool_call_timeout = 0.01
        await runner_reset(self, **kwargs)

    monkeypatch.setattr(ToolLoopAgentRunner, "reset", short_timeout_reset)
    run = asyncio.create_task(harness.run_agent(event))

    code = await wait_for_prompt(event)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(asyncio.shield(run), 0.05)
    await harness.deliver(RecordingEvent(text=code))
    await run

    assert harness.calls == [{"path": "/tmp/x"}]


@pytest.mark.asyncio
async def test_subagent_tool_call_needs_approval(monkeypatch):
    """The real Context.tool_loop_agent path must not bypass the gate."""
    harness = Harness(monkeypatch)
    event = RecordingEvent()
    monkeypatch.setattr(
        FunctionToolExecutor,
        "_build_handoff_toolset",
        classmethod(lambda cls, run_context, tools: ToolSet([harness.tool])),
    )
    handoff = HandoffTool(Agent(name="sub", instructions="Help.", tools=[TOOL_NAME]))
    main_provider = OneToolProvider(handoff.name, {"input": "do it"})
    run = asyncio.create_task(
        harness.run_agent(event, main_provider, ToolSet([handoff]))
    )

    code = await wait_for_prompt(event)
    assert harness.calls == []
    await harness.deliver(RecordingEvent(text=code))
    await run

    assert harness.calls == [{"path": "/tmp/x"}]


@pytest.mark.asyncio
async def test_handoff_itself_can_be_listed(monkeypatch):
    harness = Harness(monkeypatch)
    handoff = HandoffTool(Agent(name="sub", instructions="Help.", tools=[]))
    harness.config["agent"]["config"]["misc"]["tool_approval"]["tools"] = [handoff.name]
    event = RecordingEvent()
    run = asyncio.create_task(
        harness.run_agent(
            event, OneToolProvider(handoff.name, {"input": "x"}), ToolSet([handoff])
        )
    )

    await wait_for_prompt(event)
    await harness.deliver(RecordingEvent(text="no"))
    await run

    assert "rejected" in harness.tool_result()


def _cron_event(harness, session="test:GroupMessage:room", creator="alice"):
    harness.astrbot_context.cron_payload.update(
        {"sender_id": creator} if creator else {}
    )
    prompt_sent = asyncio.Event()

    async def sent(*args, **kwargs):
        prompt_sent.set()
        return True

    event = AgentWakeupEvent(
        context=SimpleNamespace(send_message=AsyncMock(side_effect=sent)),
        session=MessageSession.from_str(session),
        platform_meta=PlatformMetadata(id="test", name="test", description="Test"),
        prompt="wake",
        source="cron",
        source_id="job_1",
    )
    event.prompt_sent = prompt_sent
    return event


@pytest.mark.asyncio
async def test_cron_run_is_approved_by_the_job_creator(monkeypatch):
    harness = Harness(monkeypatch)
    event = _cron_event(harness)
    run = asyncio.create_task(harness.run_agent(event))

    await asyncio.wait_for(event.prompt_sent.wait(), 2)
    prompt = event.context_obj.send_message.await_args.args[1].get_plain_text()
    code = code_in(prompt)

    await harness.deliver(RecordingEvent(sender="mallory", text=code))
    assert all(
        not waiter.session_controller.future.done() for waiter in USER_SESSIONS.values()
    )
    assert harness.calls == []

    await harness.deliver(RecordingEvent(sender="alice", text=code))
    await run
    assert harness.calls == [{"path": "/tmp/x"}]


@pytest.mark.asyncio
async def test_group_cron_without_creator_fails_closed(monkeypatch):
    """A scheduled run with no known creator has nobody to ask: deny at once."""
    harness = Harness(monkeypatch, timeout=1)
    event = _cron_event(harness, creator=None)

    await asyncio.wait_for(harness.run_agent(event), timeout=5)

    assert event.context_obj.send_message.await_count == 0
    assert harness.calls == []
    assert "no user to ask" in harness.tool_result()


@pytest.mark.asyncio
async def test_background_wakeup_fails_closed(monkeypatch):
    """Non-cron wakeups (background tasks, plugins) never wait for a click."""
    harness = Harness(monkeypatch, timeout=1)
    event = AgentWakeupEvent(
        context=SimpleNamespace(send_message=AsyncMock(return_value=True)),
        session=MessageSession.from_str("test:GroupMessage:room"),
        platform_meta=PlatformMetadata(id="test", name="test", description="Test"),
        prompt="wake",
        source="background_task",
        source_id="task_1",
    )

    await asyncio.wait_for(harness.run_agent(event), timeout=5)

    assert harness.calls == []
    assert "no user to ask" in harness.tool_result()


@pytest.mark.asyncio
async def test_concurrent_requests_ask_one_at_a_time(monkeypatch):
    harness = Harness(monkeypatch)
    event = RecordingEvent()
    runs = [
        asyncio.create_task(harness.run_agent(event)),
        asyncio.create_task(harness.run_agent(event)),
    ]

    first = await wait_for_prompt(event, 1)
    await asyncio.wait_for(harness.approval_entries.get(), 2)
    await asyncio.wait_for(harness.approval_entries.get(), 2)
    assert len(event.sent) == 1
    await harness.deliver(RecordingEvent(text=first))

    second = await wait_for_prompt(event, 2)
    await harness.deliver(RecordingEvent(text=second))
    await asyncio.gather(*runs)

    assert len(harness.calls) == 2


def test_default_config_keeps_the_section_and_stays_off():
    normalized = normalize_agent({"runtime": "astrbot", "config": {}})
    assert normalized["config"]["misc"]["tool_approval"] == {
        "tools": [],
        "timeout": 120,
    }


@pytest.mark.asyncio
async def test_prompt_carries_approve_and_reject_buttons(monkeypatch):
    harness = Harness(monkeypatch, timeout=7)
    event = RecordingEvent()
    run = asyncio.create_task(harness.run_agent(event))

    code = await wait_for_prompt(event)
    rows = [c for c in event.chains[0].chain if isinstance(c, ActionRow)]
    assert len(rows) == 1 and rows[0].action_timeout == 7
    assert rows[0].toDict()["data"]["single_use"] is True
    assert [b.id for b in rows[0].buttons] == [TOOL_APPROVAL_ACTION_ID] * 2
    assert [b.action.data for b in rows[0].buttons] == [
        {"code": code, "approve": True},
        {"code": code, "approve": False},
    ]
    await harness.deliver(click(code, approve=False))
    await run


@pytest.mark.asyncio
async def test_approve_button_runs_the_tool(monkeypatch):
    harness = Harness(monkeypatch)
    event = RecordingEvent()
    run = asyncio.create_task(harness.run_agent(event))

    code = await wait_for_prompt(event)
    await harness.deliver(click(code, approve=True))
    await run

    assert harness.calls == [{"path": "/tmp/x"}]
    assert harness.agent_ran_for == []


@pytest.mark.asyncio
async def test_reject_button_does_not_run_the_tool(monkeypatch):
    harness = Harness(monkeypatch)
    event = RecordingEvent()
    run = asyncio.create_task(harness.run_agent(event))

    code = await wait_for_prompt(event)
    await harness.deliver(click(code, approve=False))
    await run

    assert harness.calls == []
    assert "rejected" in harness.tool_result()


@pytest.mark.asyncio
async def test_button_from_an_earlier_request_cannot_approve(monkeypatch):
    harness = Harness(monkeypatch)
    event = RecordingEvent()
    run = asyncio.create_task(harness.run_agent(event))

    code = await wait_for_prompt(event)
    stale = f"{(int(code) + 1) % 10000:04d}"
    await harness.deliver(click(stale, approve=True))
    await run

    assert harness.calls == []
    assert "rejected" in harness.tool_result()


@pytest.mark.asyncio
async def test_other_members_cannot_click_the_button(monkeypatch):
    harness = Harness(monkeypatch, timeout=1)
    event = RecordingEvent()
    run = asyncio.create_task(harness.run_agent(event))

    code = await wait_for_prompt(event)
    bob = click(code, approve=True, sender="bob")
    await harness.deliver(bob)
    await run

    assert harness.calls == []
    assert "timed out" in harness.tool_result()
    assert bob.is_stopped() and harness.agent_ran_for == []


@pytest.mark.asyncio
async def test_click_after_the_request_ended_does_not_reach_the_model(monkeypatch):
    harness = Harness(monkeypatch)
    # Button clicks only wake the bot for a handler or a waiting request.
    late = click("1234", approve=True, private=True)

    await harness.deliver(late)

    assert late.is_stopped()
    assert harness.agent_ran_for == []
    assert late.sent == []


def _task_tool(seen: list):
    """A stand-in for the scheduled task tool that records the grant it saw."""

    async def handler(event, **kwargs):
        seen.append(TASK_APPROVAL_GRANTED.get())
        return "scheduled"

    return FunctionTool(
        name=SCHEDULED_TASK_TOOL,
        description="Schedule a task.",
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "name": {"type": "string"},
                "note": {"type": "string"},
            },
        },
        handler=handler,
    )


async def _run_task_tool(harness, event, seen, action="create"):
    provider = OneToolProvider(
        tool_name=SCHEDULED_TASK_TOOL, tool_args={"action": action, "name": "喝水"}
    )
    return await harness.run_agent(
        event, provider=provider, tool_set=ToolSet([_task_tool(seen)])
    )


@pytest.mark.asyncio
async def test_webchat_prompt_is_one_card_with_folded_arguments(monkeypatch):
    harness = Harness(monkeypatch)
    event = RecordingEvent()
    event.platform_meta.name = "webchat"
    run = asyncio.create_task(harness.run_agent(event))

    await event.wait_sent()
    (row,) = event.chains[0].chain
    assert isinstance(row, ActionRow)
    assert TOOL_NAME in row.title and "/tmp/x" not in row.title
    assert "/tmp/x" in row.detail
    # The card names the call it asks about, so ChatUI can mark it waiting.
    assert row.tool_call_id == "call_1"
    assert row.toDict()["data"]["tool_call_id"] == "call_1"
    await harness.deliver(click(code_in(row.fallback_text), approve=True))
    await run

    assert harness.calls == [{"path": "/tmp/x"}]


@pytest.mark.asyncio
async def test_approving_a_scheduled_task_grants_its_later_run(monkeypatch):
    harness = Harness(monkeypatch, tools=(SCHEDULED_TASK_TOOL,))
    event, seen = RecordingEvent(), []
    run = asyncio.create_task(_run_task_tool(harness, event, seen))

    code = await wait_for_prompt(event)
    assert "不再逐项询问" in event.sent[0]
    await harness.deliver(RecordingEvent(text=code))
    await run

    assert seen == [True]
    # The grant belongs to that one call: nothing is left on the shared event
    # or in this context for another call to pick up.
    assert event.get_extra(TOOL_APPROVAL_GRANT_KEY) is None
    assert TASK_APPROVAL_GRANTED.get() is False


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["approved", "unlisted", "rejected"])
async def test_task_edit_replaces_prior_approval_through_real_gate(
    monkeypatch, decision
):
    from astrbot.core.astr_agent_runtime.tools.cron_tools import FutureTaskTool

    harness = Harness(
        monkeypatch, tools=() if decision == "unlisted" else (SCHEDULED_TASK_TOOL,)
    )
    event = RecordingEvent()
    job = SimpleNamespace(
        job_id="job-1",
        name="reminder",
        run_once=False,
        cron_expression="0 8 * * *",
        next_run_time=None,
        payload={
            "session": event.unified_msg_origin,
            "sender_id": "alice",
            "tool_approval_granted": True,
            "note": "old",
        },
    )
    cron = harness.astrbot_context.cron_manager
    cron.db.get_cron_job = AsyncMock(return_value=job)
    cron.update_job = AsyncMock(return_value=job)
    run = asyncio.create_task(
        harness.run_agent(
            event,
            OneToolProvider(
                SCHEDULED_TASK_TOOL,
                {"action": "edit", "job_id": "job-1", "note": "changed"},
            ),
            ToolSet([FutureTaskTool()]),
        )
    )
    try:
        if decision != "unlisted":
            code = await wait_for_prompt(event)
            await harness.deliver(click(code, approve=decision == "approved"))
        await asyncio.wait_for(run, 3)
        if decision == "rejected":
            cron.update_job.assert_not_awaited()
        else:
            cron.update_job.assert_awaited_once()
            payload = cron.update_job.await_args.kwargs["payload"]
            assert payload["note"] == "changed"
            assert payload.get("tool_approval_granted", False) is (
                decision == "approved"
            )
    finally:
        if not run.done():
            run.cancel()
        await asyncio.gather(run, return_exceptions=True)


@pytest.mark.asyncio
async def test_rejected_scheduled_task_is_not_created(monkeypatch):
    harness = Harness(monkeypatch, tools=(SCHEDULED_TASK_TOOL,))
    event, seen = RecordingEvent(), []
    run = asyncio.create_task(_run_task_tool(harness, event, seen))

    await wait_for_prompt(event)
    await harness.deliver(RecordingEvent(text="no"))
    await run

    assert seen == []


@pytest.mark.asyncio
async def test_unlisted_scheduled_task_tool_gets_no_grant(monkeypatch):
    harness = Harness(monkeypatch, tools=(TOOL_NAME,))
    event, seen = RecordingEvent(), []

    await _run_task_tool(harness, event, seen)

    assert event.sent == []
    assert seen == [False]


@pytest.mark.asyncio
async def test_approving_a_task_deletion_grants_nothing(monkeypatch):
    harness = Harness(monkeypatch, tools=(SCHEDULED_TASK_TOOL,))
    event, seen = RecordingEvent(), []
    run = asyncio.create_task(_run_task_tool(harness, event, seen, action="delete"))

    code = await wait_for_prompt(event)
    assert "不再逐项询问" not in event.sent[0]
    await harness.deliver(RecordingEvent(text=code))
    await run

    assert seen == [False]


def _granted_cron_event(harness):
    event = _cron_event(harness)
    harness.astrbot_context.cron_payload[TOOL_APPROVAL_GRANT_KEY] = True
    return event


@pytest.mark.asyncio
async def test_granted_task_runs_listed_tools_without_asking(monkeypatch):
    harness = Harness(monkeypatch)
    event = _granted_cron_event(harness)

    await harness.run_agent(event)

    assert event.context_obj.send_message.await_count == 0
    assert harness.calls == [{"path": "/tmp/x"}]


@pytest.mark.asyncio
async def test_granted_task_must_still_ask_to_schedule_another(monkeypatch):
    harness = Harness(monkeypatch, tools=(SCHEDULED_TASK_TOOL,), timeout=1)
    event, seen = _granted_cron_event(harness), []

    await _run_task_tool(harness, event, seen)

    assert event.context_obj.send_message.await_count == 1
    assert seen == []
    assert "timed out" in harness.tool_result()


# ChatUI per-conversation permission modes.


def _confined_harness(
    monkeypatch, timeout=5, tool="astrbot_execute_shell", runtime="local"
):
    """A harness whose listed tool is one the workspace mode may confine.

    The Local runtime gives members host access here, so "workspace" mode is
    what narrows it.
    """
    from astrbot.core.astr_agent_runtime.tools.computer_tools import util

    monkeypatch.setattr(
        util, "get_process_sandbox_status", lambda: {"status": "detected"}
    )
    harness = Harness(monkeypatch, tools=(tool,), timeout=timeout)
    harness.tool.name = tool
    settings = harness.config["provider_settings"]
    settings["computer_use_runtime"] = runtime
    settings["computer_use_local_permissions"] = {
        role: {
            "allow_execution": True,
            "allow_network": True,
            "filesystem_scope": "host",
        }
        for role in ("admin", "member")
    }
    return harness


async def _asks(harness, event, tool) -> bool:
    """Run one call of the listed tool and report whether it asked first."""
    run = asyncio.create_task(harness.run_agent(event, OneToolProvider(tool)))
    prompt = asyncio.create_task(event.wait_sent())
    try:
        await asyncio.wait({run, prompt}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        prompt.cancel()
        await asyncio.gather(prompt, return_exceptions=True)
    asked = bool(event.chains)
    if asked:
        row = next(c for c in event.chains[-1].chain if isinstance(c, ActionRow))
        code = code_in(row.fallback_text or event.sent[-1])
        await harness.deliver(click(code, approve=False))
    await asyncio.wait_for(run, timeout=5)
    return asked


@pytest.mark.asyncio
async def test_full_mode_runs_listed_tools_without_asking(monkeypatch):
    harness = Harness(monkeypatch)
    event = RecordingEvent()
    event.set_extra("permission_mode", "full")

    await harness.run_agent(event)

    assert event.sent == []
    assert harness.calls == [{"path": "/tmp/x"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["create", "edit"])
async def test_full_mode_still_asks_before_granting_scheduled_execution(
    monkeypatch, action
):
    harness = Harness(monkeypatch, tools=(SCHEDULED_TASK_TOOL,))
    event, seen = RecordingEvent(), []
    event.set_extra("permission_mode", "full")
    run = asyncio.create_task(_run_task_tool(harness, event, seen, action))
    try:
        code = await wait_for_prompt(event)
        assert seen == []
        assert "不再逐项询问" in event.sent[0]
        await harness.deliver(RecordingEvent(text=code))
        await run
        assert seen == [True]
    finally:
        if not run.done():
            run.cancel()
        await asyncio.gather(run, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("delivered", [False, True])
async def test_closed_webchat_stream_uses_proactive_approval(monkeypatch, delivered):
    from astrbot.core.platform.sources.webchat.webchat_event import WebChatMessageEvent

    harness = Harness(monkeypatch)
    source = RecordingEvent()
    source.platform_meta.name = "webchat"
    source.message_obj.message_id = "closed-approval-request"
    event = WebChatMessageEvent(
        "", source.message_obj, source.platform_meta, source.session_id
    )
    sent = asyncio.Event()
    chains = []

    async def proactive(session, chain):
        chains.append(chain)
        sent.set()
        return delivered

    harness.astrbot_context.send_message = proactive
    run = asyncio.create_task(harness.run_agent(event))
    try:
        await asyncio.wait_for(sent.wait(), 2)
        if delivered:
            row = next(c for c in chains[0].chain if isinstance(c, ActionRow))
            await harness.deliver(click(code_in(row.fallback_text), approve=True))
        await asyncio.wait_for(run, 2)
        assert bool(harness.calls) is delivered
        if not delivered:
            assert "cannot ask" in harness.tool_result()
    finally:
        if not run.done():
            run.cancel()
        await asyncio.gather(run, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("passive_subscriber", [False, True])
async def test_proactive_delivery_surfaces_storage_failure(
    monkeypatch, tmp_path, passive_subscriber
):
    """A proactive approval that cannot be saved fails at once instead of
    looking delivered and waiting for an answer nobody can give."""
    from astrbot.core.message.message_event_result import MessageChain
    from astrbot.core.platform import Platform
    from astrbot.core.platform.sources.webchat import webchat_adapter
    from astrbot.core.platform.sources.webchat.webchat_queue_mgr import (
        WebChatQueueMgr,
    )

    adapter = object.__new__(webchat_adapter.WebChatAdapter)
    adapter._webchat_queue_mgr = WebChatQueueMgr()
    adapter.attachments_dir = tmp_path
    if passive_subscriber:
        # Only a WebSocket subscription is open: the message is still saved.
        adapter._webchat_queue_mgr.get_or_create_back_queue("ws_sub_1", "session")
        monkeypatch.setattr(
            webchat_adapter.WebChatMessageEvent, "_send", AsyncMock(return_value=1)
        )
    monkeypatch.setattr(
        webchat_adapter.db_helper,
        "insert_platform_message_history",
        AsyncMock(side_effect=RuntimeError("storage unavailable")),
    )
    monkeypatch.setattr(Platform, "send_by_session", AsyncMock())

    with pytest.raises(RuntimeError, match="storage unavailable"):
        await adapter.send_by_session(
            SimpleNamespace(session_id="webchat!alice!session"),
            MessageChain([Plain("approval")]),
        )


@pytest.mark.asyncio
async def test_workspace_mode_skips_only_workspace_confined_tools(monkeypatch):
    harness = _confined_harness(monkeypatch)
    event = RecordingEvent()
    event.set_extra("permission_mode", "workspace")
    await harness.run_agent(event, OneToolProvider("astrbot_execute_shell"))
    assert event.sent == []
    assert harness.calls == [{"path": "/tmp/x"}]

    other = Harness(monkeypatch, timeout=1)
    other_event = RecordingEvent()
    other_event.set_extra("permission_mode", "workspace")
    run = asyncio.create_task(other.run_agent(other_event))
    await wait_for_prompt(other_event)
    await asyncio.wait_for(run, timeout=5)
    assert other.calls == []


@pytest.mark.asyncio
async def test_workspace_mode_asks_when_nothing_is_narrowed(monkeypatch):
    """Skipping approval is only safe where the narrowed Local policy applies."""
    sandbox = _confined_harness(monkeypatch, runtime="sandbox")
    event = RecordingEvent()
    event.set_extra("permission_mode", "workspace")
    assert await _asks(sandbox, event, "astrbot_execute_shell")

    # The sandbox-runtime Python tool never consults the Local policy.
    ipython = _confined_harness(monkeypatch, tool="astrbot_execute_ipython")
    event = RecordingEvent()
    event.set_extra("permission_mode", "workspace")
    assert await _asks(ipython, event, "astrbot_execute_ipython")
    assert sandbox.calls == ipython.calls == []


def _wakeup_event(harness, platform="webchat"):
    harness.astrbot_context.cron_payload.update({"sender_id": "alice"})
    prompt_sent = asyncio.Event()

    async def sent(*args, **kwargs):
        prompt_sent.set()
        return True

    event = AgentWakeupEvent(
        context=SimpleNamespace(send_message=AsyncMock(side_effect=sent)),
        session=MessageSession.from_str(f"{platform}:FriendMessage:room"),
        platform_meta=PlatformMetadata(id=platform, name=platform, description=""),
        prompt="wake",
        source="cron",
        source_id="job_1",
    )
    event.prompt_sent = prompt_sent
    return event


@pytest.mark.asyncio
async def test_unattended_run_is_never_full_and_has_no_conversation_button(
    monkeypatch,
):
    harness = Harness(monkeypatch, timeout=1)
    event = _wakeup_event(harness)
    event.set_extra("permission_mode", "full")
    run = asyncio.create_task(harness.run_agent(event))
    await asyncio.wait_for(event.prompt_sent.wait(), 2)
    chain = event.context_obj.send_message.await_args.args[1].chain
    (row,) = [c for c in chain if isinstance(c, ActionRow)]
    assert [b.id for b in row.buttons] == [TOOL_APPROVAL_ACTION_ID] * 2
    await asyncio.wait_for(run, timeout=5)
    assert harness.calls == []


@pytest.mark.asyncio
async def test_ask_mode_and_unknown_modes_still_ask(monkeypatch):
    harness = Harness(monkeypatch, timeout=1)
    event = RecordingEvent()
    event.set_extra("permission_mode", "ask")
    run = asyncio.create_task(harness.run_agent(event))
    await wait_for_prompt(event)
    await asyncio.wait_for(run, timeout=5)
    assert harness.calls == []


class WebchatEvent(RecordingEvent):
    """Same session as RecordingEvent, but on a client with a mode selector."""

    def get_platform_name(self):
        return "webchat"


@pytest.mark.asyncio
async def test_allow_for_conversation_switches_the_turn_to_full(
    monkeypatch, live_modes
):
    from astrbot.core.astr_agent_runtime.tool_approval import (
        TOOL_APPROVAL_CONVERSATION_ACTION_ID,
    )

    harness = Harness(monkeypatch)
    event = WebchatEvent()
    run = asyncio.create_task(harness.run_agent(event))
    await event.wait_sent()
    row = next(c for c in event.chains[0].chain if isinstance(c, ActionRow))
    assert [b.id for b in row.buttons] == [
        TOOL_APPROVAL_ACTION_ID,
        TOOL_APPROVAL_CONVERSATION_ACTION_ID,
        TOOL_APPROVAL_ACTION_ID,
    ]
    code = row.buttons[1].action.data["code"]

    reply = RecordingEvent(text=TOOL_APPROVAL_CONVERSATION_ACTION_ID)
    reply.message_obj.message = [
        ButtonInteraction(
            action_id=TOOL_APPROVAL_CONVERSATION_ACTION_ID,
            data={"code": code, "approve": True},
            interaction_id="click-1",
        )
    ]
    await harness.deliver(reply)
    await run

    assert harness.calls == [{"path": "/tmp/x"}]
    assert event.get_extra("permission_mode") == "full"
    # Later listed tools in the same turn no longer ask.
    await harness.run_agent(event)
    assert len([c for c in event.chains if c.type != "approval_result"]) == 1
    assert len(harness.calls) == 2


@pytest.mark.asyncio
async def test_non_webchat_prompt_has_no_conversation_button(monkeypatch):
    harness = Harness(monkeypatch)
    event = RecordingEvent()
    run = asyncio.create_task(harness.run_agent(event))
    code = await wait_for_prompt(event)
    row = next(c for c in event.chains[0].chain if isinstance(c, ActionRow))
    assert [b.id for b in row.buttons] == [TOOL_APPROVAL_ACTION_ID] * 2
    await harness.deliver(RecordingEvent(text=code))
    await run


# The conversation's current mode reaches work already running (sub-agents
# share the event of the turn that spawned them).


@pytest.mark.asyncio
async def test_dont_ask_again_from_workspace_stays_in_workspace(
    monkeypatch, live_modes
):
    """ "Don't ask again" never widens access: workspace stays confined."""
    from astrbot.core.astr_agent_runtime.permission_mode import get_permission_mode

    harness = Harness(monkeypatch)  # an unconfined tool: workspace still asks
    event = WebchatEvent()
    event.set_extra("permission_mode", "workspace")
    run = asyncio.create_task(harness.run_agent(event))
    await event.wait_sent()
    row = next(c for c in event.chains[0].chain if isinstance(c, ActionRow))
    await harness.deliver(
        _conversation_click(event, row.buttons[1].action.data["code"])
    )
    await run

    assert harness.calls == [{"path": "/tmp/x"}]
    assert event.get_extra("permission_mode") == "workspace_no_ask"
    assert get_permission_mode(event) == "workspace_no_ask"
    # Later calls in the conversation do not ask.
    await harness.run_agent(event)
    assert len([c for c in event.chains if c.type != "approval_result"]) == 1
    assert len(harness.calls) == 2

    # Choosing workspace again in the menu asks again.
    live_modes(event.session_id, "workspace")
    event.set_extra("permission_mode", "workspace")
    sent = len(event.chains)
    run = asyncio.create_task(harness.run_agent(event))
    try:
        await event.wait_sent(sent + 1)
        prompts = [c for c in event.chains if c.type != "approval_result"]
        assert len(prompts) == 2
        assert len(harness.calls) == 2
    finally:
        run.cancel()
        await asyncio.gather(run, return_exceptions=True)


@pytest.mark.asyncio
async def test_workspace_no_ask_still_asks_before_scheduling(monkeypatch, live_modes):
    harness = Harness(monkeypatch, tools=(SCHEDULED_TASK_TOOL,))
    event, seen = RecordingEvent(), []
    event.set_extra("permission_mode", "workspace_no_ask")
    run = asyncio.create_task(_run_task_tool(harness, event, seen, "create"))
    try:
        code = await wait_for_prompt(event)
        assert seen == []
        await harness.deliver(RecordingEvent(text=code))
        await run
        assert seen == [True]
    finally:
        if not run.done():
            run.cancel()
        await asyncio.gather(run, return_exceptions=True)


@pytest.mark.asyncio
async def test_scheduled_run_gets_no_waiver_from_workspace_no_ask(
    monkeypatch, live_modes
):
    from astrbot.core.astr_agent_runtime.permission_mode import get_permission_mode

    harness = Harness(monkeypatch, timeout=1)
    event = _wakeup_event(harness)
    live_modes(event.session_id, "workspace_no_ask")
    # Only the narrowing carries over, never the waiver.
    assert get_permission_mode(event) == "workspace"
    run = asyncio.create_task(harness.run_agent(event))
    await asyncio.wait_for(event.prompt_sent.wait(), 2)
    await asyncio.wait_for(run, timeout=5)
    assert harness.calls == []


@pytest.fixture
def live_modes():
    from astrbot.core.astr_agent_runtime import permission_mode

    yield permission_mode.set_conversation_permission_mode
    permission_mode._conversation_modes.clear()


def _conversation_click(event, code):
    from astrbot.core.astr_agent_runtime.tool_approval import (
        TOOL_APPROVAL_CONVERSATION_ACTION_ID,
    )

    reply = RecordingEvent(text=TOOL_APPROVAL_CONVERSATION_ACTION_ID)
    reply.message_obj.message = [
        ButtonInteraction(
            action_id=TOOL_APPROVAL_CONVERSATION_ACTION_ID,
            data={"code": code, "approve": True},
            interaction_id="click-c",
        )
    ]
    return reply


@pytest.mark.asyncio
async def test_running_work_follows_a_later_switch_to_full(monkeypatch, live_modes):
    """A sub-agent spawned under "ask" stops asking once the user picks full."""
    harness = Harness(monkeypatch)
    event = WebchatEvent()
    event.set_extra("permission_mode", "ask")
    live_modes(event.session_id, "full")

    await harness.run_agent(event)

    assert event.chains == []
    assert harness.calls == [{"path": "/tmp/x"}]


@pytest.mark.asyncio
async def test_allow_for_conversation_covers_calls_already_waiting(
    monkeypatch, live_modes
):
    """Two sub-agents ask at once: one click on the first card covers both."""
    harness = Harness(monkeypatch)
    event = WebchatEvent()
    first = asyncio.create_task(harness.run_agent(event))
    await event.wait_sent()
    second = asyncio.create_task(harness.run_agent(event))
    await asyncio.wait_for(harness.approval_entries.get(), 2)
    await asyncio.wait_for(harness.approval_entries.get(), 2)
    row = next(c for c in event.chains[0].chain if isinstance(c, ActionRow))

    await harness.deliver(
        _conversation_click(event, row.buttons[0].action.data["code"])
    )
    await asyncio.wait_for(asyncio.gather(first, second), timeout=5)

    assert len([c for c in event.chains if c.type != "approval_result"]) == 1
    assert len(harness.calls) == 2


@pytest.mark.asyncio
async def test_scheduled_run_ignores_the_live_full_mode(monkeypatch, live_modes):
    harness = Harness(monkeypatch, timeout=1)
    event = _wakeup_event(harness)
    live_modes(event.session_id, "full")
    run = asyncio.create_task(harness.run_agent(event))
    await asyncio.wait_for(event.prompt_sent.wait(), 2)
    await asyncio.wait_for(run, timeout=5)

    assert event.context_obj.send_message.await_count == 2
    outcome = event.context_obj.send_message.await_args.args[1]
    assert outcome.type == "approval_result"
    assert outcome.chain[0].data == {"tool_call_id": "call_1", "outcome": "expired"}
    assert harness.calls == []


@pytest.mark.asyncio
async def test_a_live_mode_only_applies_to_chatui(monkeypatch, live_modes):
    """Other platforms have no mode selector: a stored live mode is ignored."""
    harness = Harness(monkeypatch, timeout=1)
    event = RecordingEvent()  # not ChatUI, same session ID as WebchatEvent
    live_modes(event.session_id, "full")
    run = asyncio.create_task(harness.run_agent(event))
    await wait_for_prompt(event)
    await asyncio.wait_for(run, timeout=5)
    assert harness.calls == []


# What actually happened to an approval, as ChatUI is told.


def _approval_results(event) -> list[dict]:
    import json as _json

    return [
        _json.loads(_json.dumps(chain.chain[0].data))
        for chain in event.chains
        if chain.type == "approval_result"
    ]


@pytest.mark.asyncio
async def test_a_wakeup_in_the_same_session_does_not_answer_the_approval(
    monkeypatch,
):
    """A scheduled task firing while a card waits was taken as a rejection."""
    harness = Harness(monkeypatch)
    event = WebchatEvent()
    run = asyncio.create_task(harness.run_agent(event))
    await event.wait_sent()
    row = next(c for c in event.chains[0].chain if isinstance(c, ActionRow))

    wakeup = AgentWakeupEvent(
        context=SimpleNamespace(send_message=AsyncMock(return_value=True)),
        session=MessageSession.from_str(event.unified_msg_origin),
        platform_meta=event.platform_meta,
        prompt="<system_reminder>cron</system_reminder>",
        source="cron",
        source_id="job_1",
    )
    wakeup.get_sender_id = lambda: event.get_sender_id()
    await harness.deliver(wakeup)
    assert all(
        not waiter.session_controller.future.done() for waiter in USER_SESSIONS.values()
    )
    assert not run.done()

    await harness.deliver(click(code_in(row.fallback_text), approve=True))
    await run
    assert harness.calls == [{"path": "/tmp/x"}]
    assert _approval_results(event) == [
        {"tool_call_id": "call_1", "outcome": "approved"}
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(("answer", "outcome"), [("no", "rejected"), (None, "expired")])
async def test_chatui_is_told_when_an_approval_did_not_go_through(
    monkeypatch, answer, outcome
):
    harness = Harness(monkeypatch, timeout=1)
    event = WebchatEvent()
    run = asyncio.create_task(harness.run_agent(event))
    await event.wait_sent()
    if answer:
        await harness.deliver(RecordingEvent(text=answer))
    await asyncio.wait_for(run, timeout=5)

    assert harness.calls == []
    assert _approval_results(event) == [{"tool_call_id": "call_1", "outcome": outcome}]


def test_saved_card_records_the_reported_outcome():
    import json as _json

    from astrbot.dashboard.services.chat_service import BotMessageAccumulator

    accumulator = BotMessageAccumulator()
    accumulator.add_part({"type": "actionrow", "tool_call_id": "c1", "buttons": []})
    accumulator.add_part({"type": "actionrow", "tool_call_id": "c2", "buttons": []})
    accumulator.add_plain(
        _json.dumps({"tool_call_id": "c1", "outcome": "expired"}),
        chain_type="approval_result",
        streaming=False,
    )

    parts = accumulator.build_message_parts()
    assert [part.get("outcome") for part in parts] == ["expired", None]


@pytest.mark.asyncio
async def test_approval_prompt_follows_the_system_language(monkeypatch):
    """The prompt uses the configured reply language (Context.locale)."""
    harness = Harness(monkeypatch)
    harness.config.setdefault("platform_settings", {})["locale"] = "en-US"
    event = WebchatEvent()
    run = asyncio.create_task(harness.run_agent(event))
    await event.wait_sent()
    row = next(item for item in event.chains[0].chain if isinstance(item, ActionRow))
    assert row.title == "Tool danger wants to run"
    assert any("allow" in button.label.lower() for button in row.buttons)
    await harness.deliver(click(row.buttons[0].action.data["code"], approve=False))
    await run
    assert not harness.calls


@pytest.mark.asyncio
async def test_stop_while_queued_behind_session_approval_lock(monkeypatch):
    from astrbot.core.astr_agent_runtime.tool_approval import session_lock_manager

    acquire = session_lock_manager.acquire_lock
    harness = Harness(monkeypatch)
    event = RecordingEvent()
    async with acquire(
        f"tool_approval:{event.unified_msg_origin}:{event.get_sender_id()}"
    ):
        run = asyncio.create_task(harness.run_agent(event))
        try:
            await asyncio.wait_for(harness.approval_entries.get(), 2)
            harness.runner.request_stop()
            await asyncio.wait_for(run, 3)
            assert harness.calls == []
            assert event.sent == []
            assert harness.runner.was_aborted()
        finally:
            run.cancel()
            await asyncio.gather(run, return_exceptions=True)
