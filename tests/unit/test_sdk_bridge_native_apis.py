"""Exercise the native SDK interfaces through the Host and Runner."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from astrbot_sdk.conversations import ConversationPatch
from astrbot_sdk.errors import Conflict
from astrbot_sdk.events import UMO, MessageType

from astrbot.core import chatui
from astrbot.core.agent.events import (
    AgentSessionRef,
    RuntimeEvent,
    TextDelta,
    TurnFinished,
    TurnResult,
)
from astrbot.core.agent.output import PlainOutput
from astrbot.core.agent.runtime import InputReceipt, SessionState
from astrbot.core.agent_service import AgentSessionStatus
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.message import components
from astrbot.core.pipeline.context_utils import call_handler
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType as CoreMessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.provider.entities import DecisionBooleanAnswer
from astrbot.core.star.sdk_bridge import SDKPluginBridge
from astrbot.core.star.sdk_bridge.services.conversation import (
    ConversationReadService,
    ConversationWriteService,
)
from astrbot.core.star.star_handler import star_handlers_registry
from tests.unit.test_sdk_bridge import write_sdk_plugin

SOURCE = """
from astrbot_sdk import MessageEvent, Plugin, on
from astrbot_sdk.agents import PlainInput, TextDelta
from astrbot_sdk.decision import DecisionBooleanQuestion
from astrbot_sdk.message_components import ActionRow, Button, CallbackAction


class TestPlugin(Plugin):
    @on.command("decide")
    async def decide(self, event: MessageEvent):
        answers = await self.ctx.decision.ask(
            {"reply": DecisionBooleanQuestion("Should we reply?")},
            state={"messages": ["hi"]},
        )
        yield event.reply(str(answers["reply"].probability))

    @on.command("run")
    async def run(self, event: MessageEvent):
        turn = await self.ctx.agent.run_turn(
            input_message=[PlainInput("work")], send_to_user=False,
            metadata={"marker": True},
        )
        observed = []
        async for current in turn.events():
            if isinstance(current.payload, TextDelta):
                observed.append(current.payload.text)
        receipt = await turn.steer(input_message=[PlainInput("more")])
        assert receipt is not None and await receipt
        assert (await turn.session()).id == "session"
        following = await turn.follow_up(input_message=[PlainInput("next")])
        await following.cancel()
        yield event.reply(f"{''.join(observed)}:{(await turn.result()).text}")

    @on.command("button")
    async def button(self, event: MessageEvent):
        yield event.reply(ActionRow((Button("go", "Go", CallbackAction({"n": 3})),)))

    @on.button_action("go")
    async def clicked(self, event: MessageEvent):
        yield event.reply(str(event.get_button_interaction().data["n"]))

    @on.command("view")
    async def view(self, event: MessageEvent):
        yield event.view_result(name="counter", text="Count", data={"n": 1})

    @on.ui_action("increase")
    async def increase(self, event: MessageEvent):
        view = event.get_ui_interaction().view
        yield event.view_result(data={"n": view.data["n"] + 1})
"""


@pytest.fixture
def native_bridge(tmp_path, monkeypatch):
    """Build a native Runner with a persistent view and mocked model endpoints."""
    plugin_root = tmp_path / "native"
    write_sdk_plugin(
        plugin_root, SOURCE, capabilities=[{"id": "decision.ask"}, {"id": "agent.run"}]
    )
    metadata_path = plugin_root / "metadata.yaml"
    metadata = yaml.safe_load(metadata_path.read_text())
    metadata["views"] = [
        {"name": "counter", "target": "chat_message", "actions": ["increase"]}
    ]
    metadata_path.write_text(yaml.safe_dump(metadata))
    html = plugin_root / "views/counter/index.html"
    html.parent.mkdir(parents=True)
    html.write_text("<html></html>")
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.bridge._asset_root", lambda: tmp_path / "assets"
    )
    monkeypatch.setattr(chatui, "view_store", chatui.ViewStore(tmp_path / "views.db"))
    context = MagicMock()
    context.decision.ask = AsyncMock(return_value={"reply": DecisionBooleanAnswer(0.8)})
    context.registered_web_apis = []
    return SDKPluginBridge(plugin_root, context)


def core_event(text: str, *parts) -> AstrMessageEvent:
    """Build a real Core event without a live adapter."""
    message = AstrBotMessage()
    message.type = CoreMessageType.FRIEND_MESSAGE
    message.self_id = "bot"
    message.session_id = "source"
    message.message_id = "native-test-message"
    message.sender = MessageMember(user_id="user", nickname="Tester")
    message.message = list(parts) or [components.Plain(text)]
    message.raw_message = ("user", "source", {})
    event = AstrMessageEvent(
        text,
        message,
        PlatformMetadata("webchat", "", "webchat", support_ui_interaction=True),
        "source",
    )
    event.role = "admin"
    event.send = AsyncMock()
    return event


@pytest.mark.asyncio
async def test_models_over_native_bridge(native_bridge):
    """Decision and Agent models keep their types across the protocol."""
    bridge = native_bridge
    session = AgentSessionRef("astrbot", "session")
    result = TurnResult(content=(PlainOutput(text="done"),))
    pending = InputReceipt()
    pending.resolve(True)

    async def events():
        for index, payload in enumerate(
            (
                TextDelta(message_id="m", part_index=0, text="working"),
                TurnFinished(result=result),
            )
        ):
            yield RuntimeEvent(
                event_id=str(index),
                turn_id="turn",
                session=session,
                created_at=datetime.now(UTC),
                payload=payload,
            )

    following = SimpleNamespace(id="next", done=True, cancel=AsyncMock())
    run = SimpleNamespace(
        id="first",
        done=True,
        events=events,
        result=AsyncMock(return_value=result),
        session=AgentSessionStatus(session, SessionState.RUNNING, 0, "first"),
        steer=AsyncMock(return_value=pending),
        follow_up=AsyncMock(return_value=following),
    )
    bridge.context.agent.run_turn = AsyncMock(return_value=run)
    try:
        await bridge.start()
        for name, expected in (("decide", "0.8"), ("run", "working:done")):
            event = core_event(name)
            handler = star_handlers_registry.star_handlers_map[
                f"{bridge.module_path}_{name}"
            ]
            async for _ in handler.handler(event):
                assert event.get_result().chain[0].text == expected
            if name == "run":
                assert (
                    bridge.context.agent.run_turn.await_args.kwargs["source_event"]
                    is event
                )
        assert bridge.context.decision.ask.await_args.args[1] == {"messages": ["hi"]}
        params = bridge.context.agent.run_turn.await_args.kwargs
        assert params["send_to_user"] is False
        assert params["metadata"] == {"marker": True}
        assert params["input_message"][0].text == "work"
        following.cancel.assert_awaited_once()
    finally:
        await bridge.stop()


@pytest.mark.asyncio
async def test_native_buttons_and_views(native_bridge):
    """Core receives button segments and owns view creation and updates."""
    bridge = native_bridge
    try:
        await bridge.start()
        button = star_handlers_registry.star_handlers_map[
            f"{bridge.module_path}_button"
        ]
        clicked = star_handlers_registry.star_handlers_map[
            f"{bridge.module_path}_clicked"
        ]
        view = star_handlers_registry.star_handlers_map[f"{bridge.module_path}_view"]
        increase = star_handlers_registry.star_handlers_map[
            f"{bridge.module_path}_increase"
        ]

        event = core_event("button")
        async for _ in button.handler(event):
            assert event.get_result().chain[0].buttons[0].action.data == {"n": 3}

        event = core_event(
            "",
            components.ButtonInteraction(
                action_id="go", interaction_id="click", data={"n": 3}
            ),
        )
        assert clicked.event_filters[0].filter(event, {})
        async for _ in clicked.handler(event):
            assert event.get_result().chain[0].text == "3"

        event = core_event("view")
        _ = [value async for value in call_handler(event, view.handler)]
        emitted = event.send.await_args.args[0].chain[0].data
        assert chatui.view_store.get(emitted["id"])["data"] == {"n": 1}

        event = core_event(
            "",
            components.UIInteraction(
                action_id="increase",
                interaction_id="click",
                view=components.ViewContext(
                    id=emitted["id"],
                    name="counter",
                    version=1,
                    revision=0,
                    data={"n": 1},
                ),
            ),
        )
        assert increase.event_filters[0].filter(event, {})
        updates = [item async for item in call_handler(event, increase.handler)]
        assert isinstance(updates[0], chatui.ViewResult) and updates[0].name is None
        assert updates[0].data == {"n": 2}
    finally:
        await bridge.stop()


@pytest.mark.asyncio
async def test_conversation_event_storage_and_revision(database):
    """The bridge uses the real append log, revision checks and plugin namespace."""
    umo = UMO("webchat", MessageType.PRIVATE, "test-owner")
    record = await database.conversation_store.create(
        umo="webchat:FriendMessage:test-owner", platform_id="webchat"
    )
    context = SimpleNamespace(conversation_manager=ConversationManager(database))
    reader = ConversationReadService(context, "tester/demo")
    writer = ConversationWriteService(context, "tester/demo")
    payload = {"umo": umo, "conversation_id": record.conversation_id}
    original = (await reader.handle("get", payload))["conversation"]
    assert original.revision.head_seq == 1

    message_id = await writer.handle(
        "append_message", {**payload, "content": "hello", "message_id": "sdk-message"}
    )
    assert message_id == await writer.handle(
        "append_message", {**payload, "content": "hello", "message_id": "sdk-message"}
    )
    custom = {**payload, "event_type": "done", "data": {"success": True}}
    await writer.handle("append_plugin_event", custom)
    events = await reader.handle("list_plugin_events", custom)
    assert len(events) == 1 and events[0].data == {"success": True}
    other = ConversationReadService(context, "other/demo")
    assert await other.handle("list_plugin_events", custom) == []
    with pytest.raises(Conflict):
        await writer.handle(
            "update",
            {
                **payload,
                "patch": ConversationPatch(messages=()),
                "expected_revision": original.revision,
            },
        )
    fork_id = await writer.handle("fork", {"umo": umo, "source_event_id": message_id})
    fork = (await reader.handle("get", {**payload, "conversation_id": fork_id}))[
        "conversation"
    ]
    assert [part.content for part in fork.messages] == ["hello"]
