# ruff: noqa: E402
from __future__ import annotations

import sys
import types
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.command_compatibility import (
    CommandRegistration,
    CrossSystemCommandConflict,
)


def _install_optional_dependency_stubs() -> None:
    def install(name: str, attrs: dict[str, object]) -> None:
        if name in sys.modules:
            return
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module

    install(
        "faiss",
        {
            "read_index": lambda *args, **kwargs: None,
            "write_index": lambda *args, **kwargs: None,
            "IndexFlatL2": type("IndexFlatL2", (), {}),
            "IndexIDMap": type("IndexIDMap", (), {}),
            "normalize_L2": lambda *args, **kwargs: None,
        },
    )
    install("pypdf", {"PdfReader": type("PdfReader", (), {})})
    install(
        "jieba",
        {
            "cut": lambda text, *args, **kwargs: text.split(),
            "lcut": lambda text, *args, **kwargs: text.split(),
        },
    )
    install("rank_bm25", {"BM25Okapi": type("BM25Okapi", (), {})})


_install_optional_dependency_stubs()

from astrbot.core.pipeline.process_stage.stage import ProcessStage
from astrbot.core.sdk_bridge import plugin_bridge as plugin_bridge_module
from astrbot.core.sdk_bridge.plugin_bridge import (
    SKIP_LEGACY_REPLIED,
    SKIP_LEGACY_STOPPED,
    SdkPluginBridge,
)


class _FakeEvent:
    def __init__(self, *, stopped: bool = False, has_send_oper: bool = False) -> None:
        self._extras = {"activated_handlers": ["legacy-handler"]}
        self._stopped = stopped
        self._result = None
        self._has_send_oper = has_send_oper
        self.call_llm = False
        self.is_at_or_wake_command = True
        self.unified_msg_origin = "test-platform:friend:session"

    def get_extra(self, key: str, default=None):
        return self._extras.get(key, default)

    def set_extra(self, key: str, value) -> None:
        self._extras[key] = value

    def stop_event(self) -> None:
        self._stopped = True

    def is_stopped(self) -> bool:
        return self._stopped

    def set_result(self, result) -> None:
        self._result = result

    def get_result(self):
        return self._result

    def should_call_llm(self, call_llm: bool) -> None:
        self.call_llm = call_llm


class _FakeStarContext:
    def get_all_stars(self) -> list:
        return []


@dataclass
class _FakeHandler:
    handler_full_name: str


async def _drain(generator: AsyncGenerator[None, None] | None) -> int:
    if generator is None:
        return 0
    count = 0
    async for _ in generator:
        count += 1
    return count


def _make_process_stage(
    *,
    sdk_bridge,
    star_process,
    agent_process,
) -> ProcessStage:
    stage = ProcessStage()
    stage.ctx = SimpleNamespace(
        astrbot_config={"provider_settings": {"enable": True}},
    )
    stage.sdk_plugin_bridge = sdk_bridge
    stage.star_request_sub_stage = SimpleNamespace(process=star_process)
    stage.agent_sub_stage = SimpleNamespace(process=agent_process)
    return stage


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_stage_preserves_legacy_stop_and_skips_sdk_and_llm() -> None:
    sdk_bridge = SimpleNamespace(dispatch_message=AsyncMock())
    agent_process = AsyncMock()

    async def legacy_process(event):
        event.stop_event()
        yield None

    async def agent_process_gen(_event):
        if False:  # pragma: no cover
            yield None

    stage = _make_process_stage(
        sdk_bridge=sdk_bridge,
        star_process=legacy_process,
        agent_process=agent_process_gen,
    )
    event = _FakeEvent()

    yielded = await _drain(stage.process(event))

    assert yielded == 1
    assert event.is_stopped() is True
    sdk_bridge.dispatch_message.assert_not_awaited()
    assert event.call_llm is False
    assert agent_process.await_count == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_stage_keeps_default_llm_suppressed_after_legacy_reply() -> None:
    sdk_bridge = SimpleNamespace(
        dispatch_message=AsyncMock(
            return_value=SimpleNamespace(sent_message=False, stopped=False)
        )
    )
    agent_process = AsyncMock()

    async def legacy_process(event):
        event._has_send_oper = True
        yield None

    async def agent_process_gen(_event):
        agent_process()
        if False:  # pragma: no cover
            yield None

    stage = _make_process_stage(
        sdk_bridge=sdk_bridge,
        star_process=legacy_process,
        agent_process=agent_process_gen,
    )
    event = _FakeEvent()

    yielded = await _drain(stage.process(event))

    assert yielded == 1
    sdk_bridge.dispatch_message.assert_awaited_once_with(event)
    assert event._has_send_oper is True
    assert event.call_llm is False
    assert agent_process.await_count == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_stage_filters_conflicting_legacy_handler_and_runs_sdk() -> None:
    async def sdk_dispatch(event):
        event._has_send_oper = True
        return SimpleNamespace(sent_message=True, stopped=False)

    sdk_bridge = SimpleNamespace(
        COMMAND_OVERRIDE_WARNING_TYPE="legacy_sdk_command_override",
        detect_legacy_command_conflict=lambda _event, _handlers: (
            CrossSystemCommandConflict(
                command_name="hello",
                legacy=CommandRegistration(
                    runtime_kind="legacy",
                    plugin_name="legacy-demo",
                    plugin_display_name="Legacy Demo",
                    handler_full_name="legacy.demo.hello",
                    command_name="hello",
                ),
                sdk=CommandRegistration(
                    runtime_kind="sdk",
                    plugin_name="sdk-demo",
                    plugin_display_name="SDK Demo",
                    handler_full_name="sdk-demo:main.hello",
                    command_name="hello",
                ),
            )
        ),
        dispatch_message=AsyncMock(side_effect=sdk_dispatch),
    )
    legacy_called = False
    agent_process_calls = 0

    async def legacy_process(_event):
        nonlocal legacy_called
        legacy_called = True
        yield None

    async def agent_process_gen(_event):
        nonlocal agent_process_calls
        agent_process_calls += 1
        if False:  # pragma: no cover
            yield None

    stage = _make_process_stage(
        sdk_bridge=sdk_bridge,
        star_process=legacy_process,
        agent_process=agent_process_gen,
    )
    event = _FakeEvent()
    event.set_extra(
        "activated_handlers",
        [_FakeHandler("legacy.demo.hello")],
    )
    event.set_extra(
        "handlers_parsed_params",
        {"legacy.demo.hello": {"name": "old"}},
    )

    yielded = await _drain(stage.process(event))

    assert yielded == 1
    assert legacy_called is False
    sdk_bridge.dispatch_message.assert_awaited_once_with(event)
    assert event.is_stopped() is False
    assert event.get_extra("activated_handlers") == []
    assert event.get_extra("handlers_parsed_params") == {}
    assert agent_process_calls == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_stage_skips_conflict_detection_without_active_sdk_commands() -> (
    None
):
    detect_calls = 0
    sdk_bridge = SimpleNamespace(
        has_active_sdk_command_handlers=lambda: False,
        detect_legacy_command_conflict=lambda _event, _handlers: _increment_calls(),
        dispatch_message=AsyncMock(
            return_value=SimpleNamespace(sent_message=False, stopped=False)
        ),
    )

    def _increment_calls():
        nonlocal detect_calls
        detect_calls += 1
        return None

    legacy_called = False

    async def legacy_process(_event):
        nonlocal legacy_called
        legacy_called = True
        yield None

    async def agent_process_gen(_event):
        if False:  # pragma: no cover
            yield None

    stage = _make_process_stage(
        sdk_bridge=sdk_bridge,
        star_process=legacy_process,
        agent_process=agent_process_gen,
    )
    event = _FakeEvent()
    event.set_extra(
        "activated_handlers",
        [_FakeHandler("legacy.demo.hello")],
    )

    yielded = await _drain(stage.process(event))

    assert yielded == 1
    assert legacy_called is True
    assert detect_calls == 0
    sdk_bridge.dispatch_message.assert_awaited_once_with(event)


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event", "expected_reason"),
    [
        (_FakeEvent(stopped=True), SKIP_LEGACY_STOPPED),
        (_FakeEvent(has_send_oper=True), SKIP_LEGACY_REPLIED),
    ],
)
async def test_sdk_bridge_skips_sdk_execution_when_legacy_already_handled_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    event: _FakeEvent,
    expected_reason: str,
) -> None:
    monkeypatch.setattr(
        plugin_bridge_module,
        "get_astrbot_data_path",
        lambda: str(tmp_path),
    )

    bridge = SdkPluginBridge(_FakeStarContext())

    result = await bridge.dispatch_message(event)

    assert result.matched_handlers == []
    assert result.executed_handlers == []
    assert result.sent_message is False
    assert result.stopped is False
    assert result.skipped_reason == expected_reason
