import importlib
import sys
import types
from types import SimpleNamespace

import pytest

import astrbot.core.pipeline.process_stage as process_stage_pkg
import astrbot.core.pipeline.process_stage.method as process_stage_method_pkg
from astrbot.core.agent.llm_types import ProviderRequest

_original_agent_request_module = sys.modules.get(
    "astrbot.core.pipeline.process_stage.method.agent_request"
)
_original_star_request_module = sys.modules.get(
    "astrbot.core.pipeline.process_stage.method.star_request"
)
_original_process_stage_module = sys.modules.get(
    "astrbot.core.pipeline.process_stage.stage"
)
_had_agent_request_attr = hasattr(process_stage_method_pkg, "agent_request")
_had_star_request_attr = hasattr(process_stage_method_pkg, "star_request")
_had_stage_attr = hasattr(process_stage_pkg, "stage")
_original_agent_request_attr = getattr(
    process_stage_method_pkg,
    "agent_request",
    None,
)
_original_star_request_attr = getattr(
    process_stage_method_pkg,
    "star_request",
    None,
)
_original_stage_attr = getattr(process_stage_pkg, "stage", None)

_stub_agent_request_module = types.ModuleType(
    "astrbot.core.pipeline.process_stage.method.agent_request"
)
_stub_star_request_module = types.ModuleType(
    "astrbot.core.pipeline.process_stage.method.star_request"
)


class AgentRequestSubStage: ...


class StarRequestSubStage: ...


setattr(_stub_agent_request_module, "AgentRequestSubStage", AgentRequestSubStage)
setattr(_stub_star_request_module, "StarRequestSubStage", StarRequestSubStage)
sys.modules["astrbot.core.pipeline.process_stage.method.agent_request"] = (
    _stub_agent_request_module
)
sys.modules["astrbot.core.pipeline.process_stage.method.star_request"] = (
    _stub_star_request_module
)
sys.modules.pop("astrbot.core.pipeline.process_stage.stage", None)
process_stage_module = importlib.import_module(
    "astrbot.core.pipeline.process_stage.stage"
)

if _original_agent_request_module is not None:
    sys.modules["astrbot.core.pipeline.process_stage.method.agent_request"] = (
        _original_agent_request_module
    )
else:
    sys.modules.pop("astrbot.core.pipeline.process_stage.method.agent_request", None)
if _had_agent_request_attr:
    process_stage_method_pkg.agent_request = _original_agent_request_attr
else:
    process_stage_method_pkg.__dict__.pop("agent_request", None)

if _original_star_request_module is not None:
    sys.modules["astrbot.core.pipeline.process_stage.method.star_request"] = (
        _original_star_request_module
    )
else:
    sys.modules.pop("astrbot.core.pipeline.process_stage.method.star_request", None)
if _had_star_request_attr:
    process_stage_method_pkg.star_request = _original_star_request_attr
else:
    process_stage_method_pkg.__dict__.pop("star_request", None)

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


class FakeEvent:
    def __init__(
        self,
        extras: dict | None = None,
        *,
        has_send_oper: bool = False,
        at_or_wake: bool = False,
        call_llm: bool = False,
        result=None,
        stopped: bool = False,
    ) -> None:
        self._extras = extras or {}
        self._has_send_oper = has_send_oper
        self.is_at_or_wake_command = at_or_wake
        self.call_llm = call_llm
        self._result = result
        self._stopped = stopped

    def get_extra(self, key: str):
        return self._extras.get(key)

    def set_extra(self, key: str, value) -> None:
        self._extras[key] = value

    def get_result(self):
        return self._result

    def is_stopped(self) -> bool:
        return self._stopped


class FakeSubStage:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def process(self, *args):
        self.calls.append(args)
        for response in self.responses:
            yield response


def _stage(
    *,
    provider_enabled: bool = True,
    star_responses=None,
    agent_responses=None,
):
    stage = process_stage_module.ProcessStage.__new__(process_stage_module.ProcessStage)
    stage.ctx = SimpleNamespace(
        astrbot_config={"provider_settings": {"enable": provider_enabled}}
    )
    stage.star_request_sub_stage = FakeSubStage(star_responses or [])
    stage.agent_sub_stage = FakeSubStage(agent_responses or [])
    return stage


@pytest.mark.asyncio
async def test_process_stage_plugin_provider_request_routes_to_agent_and_sets_extra():
    stage = _stage(
        star_responses=[ProviderRequest(prompt="hello")],
        agent_responses=["agent-step-1", "agent-step-2"],
    )
    event = FakeEvent(extras={"activated_handlers": [SimpleNamespace(name="handler")]})

    yielded = [item async for item in stage.process(event)]

    assert yielded == [None, None]
    assert isinstance(event.get_extra("provider_request"), ProviderRequest)
    assert stage.star_request_sub_stage.calls == [(event,)]
    assert stage.agent_sub_stage.calls == [(event,)]


@pytest.mark.asyncio
async def test_process_stage_plugin_provider_request_yields_once_when_agent_emits_nothing():
    stage = _stage(
        star_responses=[ProviderRequest(prompt="hello")],
        agent_responses=[],
    )
    event = FakeEvent(extras={"activated_handlers": [SimpleNamespace(name="handler")]})

    yielded = [item async for item in stage.process(event)]

    assert yielded == [None]
    assert stage.agent_sub_stage.calls == [(event,)]


@pytest.mark.asyncio
async def test_process_stage_plugin_provider_request_does_not_fall_through_to_wake_agent():
    stage = _stage(
        star_responses=[ProviderRequest(prompt="hello")],
        agent_responses=["agent-step"],
    )
    event = FakeEvent(
        extras={"activated_handlers": [SimpleNamespace(name="handler")]},
        at_or_wake=True,
    )

    yielded = [item async for item in stage.process(event)]

    assert yielded == [None]
    assert stage.agent_sub_stage.calls == [(event,)]


@pytest.mark.asyncio
async def test_process_stage_plain_plugin_response_does_not_trigger_agent():
    stage = _stage(star_responses=["plugin-result"], agent_responses=["agent-step"])
    event = FakeEvent(extras={"activated_handlers": [SimpleNamespace(name="handler")]})

    yielded = [item async for item in stage.process(event)]

    assert yielded == [None]
    assert stage.star_request_sub_stage.calls == [(event,)]
    assert stage.agent_sub_stage.calls == []


@pytest.mark.asyncio
async def test_process_stage_wake_path_runs_agent_without_plugin_handlers():
    stage = _stage(agent_responses=["agent-step"])
    event = FakeEvent(
        extras={"activated_handlers": []},
        at_or_wake=True,
        result=None,
    )

    yielded = [item async for item in stage.process(event)]

    assert yielded == [None]
    assert stage.agent_sub_stage.calls == [(event,)]


@pytest.mark.asyncio
async def test_process_stage_skips_agent_when_event_stopped_with_existing_result():
    stage = _stage(agent_responses=["agent-step"])
    event = FakeEvent(
        extras={"activated_handlers": []},
        at_or_wake=True,
        result=object(),
        stopped=True,
    )

    yielded = [item async for item in stage.process(event)]

    assert yielded == []
    assert stage.agent_sub_stage.calls == []


@pytest.mark.asyncio
async def test_process_stage_provider_disabled_skips_wake_agent_request():
    stage = _stage(provider_enabled=False, agent_responses=["agent-step"])
    event = FakeEvent(
        extras={"activated_handlers": []},
        at_or_wake=True,
        result=None,
    )

    yielded = [item async for item in stage.process(event)]

    assert yielded == []
    assert stage.agent_sub_stage.calls == []


@pytest.mark.asyncio
async def test_process_stage_call_llm_flag_skips_wake_agent_request():
    stage = _stage(agent_responses=["agent-step"])
    event = FakeEvent(
        extras={"activated_handlers": []},
        at_or_wake=True,
        call_llm=True,
        result=None,
    )

    yielded = [item async for item in stage.process(event)]

    assert yielded == []
    assert stage.agent_sub_stage.calls == []


@pytest.mark.asyncio
async def test_process_stage_existing_result_without_stop_still_runs_wake_agent():
    stage = _stage(agent_responses=["agent-step"])
    event = FakeEvent(
        extras={"activated_handlers": []},
        at_or_wake=True,
        result=object(),
        stopped=False,
    )

    yielded = [item async for item in stage.process(event)]

    assert yielded == [None]
    assert stage.agent_sub_stage.calls == [(event,)]
