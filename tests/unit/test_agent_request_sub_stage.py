import importlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import astrbot.core.pipeline.process_stage as process_stage_pkg
import astrbot.core.pipeline.process_stage.method.agent_sub_stages as agent_sub_stages_pkg

_original_process_stage_module = sys.modules.get(
    "astrbot.core.pipeline.process_stage.stage"
)
_original_internal_module = sys.modules.get(
    "astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal"
)
_original_third_party_module = sys.modules.get(
    "astrbot.core.pipeline.process_stage.method.agent_sub_stages.third_party"
)
_had_stage_attr = hasattr(process_stage_pkg, "stage")
_had_internal_attr = hasattr(agent_sub_stages_pkg, "internal")
_had_third_party_attr = hasattr(agent_sub_stages_pkg, "third_party")
_original_stage_attr = getattr(process_stage_pkg, "stage", None)
_original_internal_attr = getattr(agent_sub_stages_pkg, "internal", None)
_original_third_party_attr = getattr(agent_sub_stages_pkg, "third_party", None)

_stub_process_stage_module = types.ModuleType(
    "astrbot.core.pipeline.process_stage.stage"
)
_stub_internal_module = types.ModuleType(
    "astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal"
)
_stub_third_party_module = types.ModuleType(
    "astrbot.core.pipeline.process_stage.method.agent_sub_stages.third_party"
)


class Stage: ...


class FakeInternalAgentSubStage:
    def __init__(self) -> None:
        self.initialize = AsyncMock()
        self.process_calls = []
        self.responses = []

    async def process(self, event):
        self.process_calls.append(event)
        for item in self.responses:
            yield item


class FakeThirdPartyAgentSubStage:
    def __init__(self) -> None:
        self.initialize = AsyncMock()
        self.process_calls = []
        self.responses = []

    async def process(self, event):
        self.process_calls.append(event)
        for item in self.responses:
            yield item


setattr(_stub_process_stage_module, "Stage", Stage)
setattr(_stub_internal_module, "InternalAgentSubStage", FakeInternalAgentSubStage)
setattr(
    _stub_third_party_module, "ThirdPartyAgentSubStage", FakeThirdPartyAgentSubStage
)
sys.modules["astrbot.core.pipeline.process_stage.stage"] = _stub_process_stage_module
sys.modules["astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal"] = (
    _stub_internal_module
)
sys.modules[
    "astrbot.core.pipeline.process_stage.method.agent_sub_stages.third_party"
] = _stub_third_party_module
agent_request = importlib.import_module(
    "astrbot.core.pipeline.process_stage.method.agent_request"
)
agent_request = importlib.reload(agent_request)

if _original_process_stage_module is not None:
    sys.modules["astrbot.core.pipeline.process_stage.stage"] = (
        _original_process_stage_module
    )
else:
    sys.modules.pop("astrbot.core.pipeline.process_stage.stage", None)
if _had_stage_attr:
    process_stage_pkg.stage = _original_stage_attr
else:
    process_stage_pkg.__dict__.pop("stage", None)

if _original_internal_module is not None:
    sys.modules[
        "astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal"
    ] = _original_internal_module
else:
    sys.modules.pop(
        "astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal",
        None,
    )
if _had_internal_attr:
    agent_sub_stages_pkg.internal = _original_internal_attr
else:
    agent_sub_stages_pkg.__dict__.pop("internal", None)

if _original_third_party_module is not None:
    sys.modules[
        "astrbot.core.pipeline.process_stage.method.agent_sub_stages.third_party"
    ] = _original_third_party_module
else:
    sys.modules.pop(
        "astrbot.core.pipeline.process_stage.method.agent_sub_stages.third_party",
        None,
    )
if _had_third_party_attr:
    agent_sub_stages_pkg.third_party = _original_third_party_attr
else:
    agent_sub_stages_pkg.__dict__.pop("third_party", None)


class FakeEvent:
    def __init__(
        self,
        unified_msg_origin: str = "umo-1",
        platform_name: str = "test",
    ) -> None:
        self.unified_msg_origin = unified_msg_origin
        self.platform_name = platform_name

    def get_platform_name(self) -> str:
        return self.platform_name


async def _yield_items(*items):
    for item in items:
        yield item


def _ctx(
    *,
    agent_runner_type: str = "local",
    provider_enable: bool = True,
):
    return SimpleNamespace(
        preferences=SimpleNamespace(
            get_async=AsyncMock(return_value={}),
            put_async=AsyncMock(),
        ),
        astrbot_config={
            "command_prefixes": ["/"],
            "llm_access": {
                "prefixes": ["/"],
                "private": "open",
                "group": "prefix",
                "reply_to_bot": False,
            },
            "provider_settings": {
                "enable": provider_enable,
                "streaming_response": False,
                "unsupported_streaming_strategy": "turn_off",
            },
            "agent_runner": {
                "runner_type": agent_runner_type,
                "config": {},
            },
        },
    )


@pytest.mark.asyncio
async def test_initialize_uses_internal_stage_for_local_runner():
    stage = agent_request.AgentRequestSubStage()
    ctx = _ctx(agent_runner_type="local")

    await stage.initialize(ctx)

    assert type(stage.agent_sub_stage).__name__ == "FakeInternalAgentSubStage"
    stage.agent_sub_stage.initialize.assert_awaited_once_with(ctx)


@pytest.mark.asyncio
async def test_initialize_uses_third_party_stage_for_non_local_runner():
    stage = agent_request.AgentRequestSubStage()
    ctx = _ctx(agent_runner_type="dify")

    await stage.initialize(ctx)

    assert type(stage.agent_sub_stage).__name__ == "FakeThirdPartyAgentSubStage"
    stage.agent_sub_stage.initialize.assert_awaited_once_with(ctx)


@pytest.mark.asyncio
async def test_initialize_falls_back_to_local_for_unknown_runner_type():
    stage = agent_request.AgentRequestSubStage()
    ctx = _ctx(agent_runner_type="unknown-runner")

    await stage.initialize(ctx)

    assert ctx.astrbot_config["agent_runner"]["runner_type"] == "local"
    assert type(stage.agent_sub_stage).__name__ == "FakeInternalAgentSubStage"


@pytest.mark.asyncio
async def test_process_returns_early_when_provider_is_disabled(monkeypatch):
    stage = agent_request.AgentRequestSubStage()
    ctx = _ctx(provider_enable=False)
    await stage.initialize(ctx)

    should_process = AsyncMock(return_value=True)
    monkeypatch.setattr(
        agent_request.SessionServiceManager,
        "should_process_llm_request",
        should_process,
    )

    outputs = [item async for item in stage.process(FakeEvent())]

    assert outputs == []
    should_process.assert_not_awaited()
    assert stage.agent_sub_stage.process_calls == []


@pytest.mark.asyncio
async def test_process_returns_early_when_session_llm_is_disabled(monkeypatch):
    stage = agent_request.AgentRequestSubStage()
    ctx = _ctx()
    await stage.initialize(ctx)

    should_process = AsyncMock(return_value=False)
    monkeypatch.setattr(
        agent_request.SessionServiceManager,
        "should_process_llm_request",
        should_process,
    )

    outputs = [item async for item in stage.process(FakeEvent("umo-disabled"))]

    assert outputs == []
    should_process.assert_awaited_once()
    assert stage.agent_sub_stage.process_calls == []


@pytest.mark.asyncio
async def test_process_forwards_event_to_selected_substage(
    monkeypatch,
):
    stage = agent_request.AgentRequestSubStage()
    ctx = _ctx()
    await stage.initialize(ctx)
    stage.agent_sub_stage.responses = ["umo-ok:ask", "done"]

    should_process = AsyncMock(return_value=True)
    monkeypatch.setattr(
        agent_request.SessionServiceManager,
        "should_process_llm_request",
        should_process,
    )
    event = FakeEvent("umo-ok")

    outputs = [item async for item in stage.process(event)]

    assert outputs == ["umo-ok:ask", "done"]
    should_process.assert_awaited_once_with(event)
    assert stage.agent_sub_stage.process_calls == [event]
