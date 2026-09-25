"""Tests for global prefixes that suppress the normal LLM fallback."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.config.default import CONFIG_METADATA_3, DEFAULT_CONFIG
from astrbot.core.pipeline.process_stage.stage import AgentRequestSubStage
from astrbot.core.pipeline.process_stage.method.agent_request import (
    SessionServiceManager,
)
from astrbot.core.pipeline.waking_check.stage import WakingCheckStage
from astrbot.core.platform.message_type import MessageType
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.session_plugin_manager import SessionPluginManager


class StubEvent:
    def __init__(self, message: str, extras: dict | None = None):
        self.unified_msg_origin = "test:session"
        self.message_str = message
        self.message_obj = SimpleNamespace(type=MessageType.GROUP_MESSAGE)
        self.role = "member"
        self.extras = extras or {}

    def get_extra(self, key=None, default=None):
        return self.extras.get(key, default)

    def set_extra(self, key, value):
        self.extras[key] = value

    def get_messages(self):
        return [SimpleNamespace()]

    def get_self_id(self):
        return "bot"

    def get_sender_id(self):
        return "sender"

    def get_platform_name(self):
        return "test"

    def is_private_chat(self):
        return False

    def stop_event(self):
        self.is_stopped = True


async def make_waking_stage(prefixes: list[str]) -> WakingCheckStage:
    stage = WakingCheckStage()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config={
                "admins_id": [],
                "wake_prefix": ["/"],
                "plugin_set": ["*"],
                "provider_settings": {"llm_no_reply_prefixes": prefixes},
                "platform_settings": {},
            },
            astrbot_config_id="test-conf-id",
            db_helper=MagicMock(),
        )
    )
    return stage


async def make_agent_stage() -> tuple[object, list[object]]:
    config = {
        "wake_prefix": ["/"],
        "provider_settings": {
            "enable": True,
            "wake_prefix": "",
            "llm_no_reply_prefixes": ["/", "!"],
        },
        "agent_runner": {"runner_type": "dify", "config": {}},
    }
    stage = AgentRequestSubStage()
    stage.ctx = SimpleNamespace(astrbot_config=config)
    stage.prov_wake_prefix = ""
    requests = []

    async def backend(event, provider_wake_prefix):  # noqa: ARG001
        requests.append(event)
        yield None

    stage.agent_sub_stage = SimpleNamespace(process=backend)
    return stage, requests


async def consume(response):
    async for _ in response:
        pass


@pytest.mark.asyncio
async def test_default_config_has_no_no_reply_prefixes():
    metadata = CONFIG_METADATA_3["ai_group"]["metadata"]["others"]["items"]

    assert DEFAULT_CONFIG["provider_settings"]["llm_no_reply_prefixes"] == []
    assert metadata["provider_settings.llm_no_reply_prefixes"]["type"] == "list"


@pytest.mark.asyncio
async def test_waking_stage_detects_original_prefix_after_removing_wake_prefix(
    monkeypatch,
):
    stage = await make_waking_stage(["/", "!"])
    event = StubEvent("/style 1")
    monkeypatch.setattr(
        "astrbot.core.pipeline.waking_check.stage."
        "star_handlers_registry.get_handlers_by_event_type",
        lambda *_args, **_kwargs: [],
    )

    async def return_handlers(_event, handlers):
        return handlers

    monkeypatch.setattr(
        SessionPluginManager,
        "filter_handlers_by_session",
        return_handlers,
    )

    await stage.process(event)

    assert event.message_str == "style 1"
    assert event.get_extra("_llm_no_reply_prefix") is True


@pytest.mark.asyncio
async def test_blank_no_reply_prefixes_do_not_match_message(monkeypatch):
    stage = await make_waking_stage(["", "   "])
    event = StubEvent("hello")
    monkeypatch.setattr(
        "astrbot.core.pipeline.waking_check.stage."
        "star_handlers_registry.get_handlers_by_event_type",
        lambda *_args, **_kwargs: [],
    )

    await stage.process(event)

    assert event.get_extra("_llm_no_reply_prefix") is False


@pytest.mark.asyncio
async def test_agent_request_skips_normal_fallback_for_marked_event(monkeypatch):
    stage, requests = await make_agent_stage()
    monkeypatch.setattr(
        SessionServiceManager,
        "should_process_llm_request",
        AsyncMock(return_value=True),
    )
    event = StubEvent("style 1", {"_llm_no_reply_prefix": True})

    await consume(stage.process(event))

    assert requests == []


@pytest.mark.asyncio
async def test_agent_request_still_processes_plugin_request_for_marked_event(
    monkeypatch,
):
    stage, requests = await make_agent_stage()
    monkeypatch.setattr(
        SessionServiceManager,
        "should_process_llm_request",
        AsyncMock(return_value=True),
    )
    provider_request = ProviderRequest(prompt="plugin prompt")
    event = StubEvent(
        "style 1",
        {"_llm_no_reply_prefix": True, "provider_request": provider_request},
    )

    await consume(stage.process(event))

    assert requests == [event]


@pytest.mark.asyncio
async def test_agent_request_processes_unmarked_normal_message(monkeypatch):
    stage, requests = await make_agent_stage()
    monkeypatch.setattr(
        SessionServiceManager,
        "should_process_llm_request",
        AsyncMock(return_value=True),
    )
    event = StubEvent("hello")

    await consume(stage.process(event))

    assert requests == [event]
