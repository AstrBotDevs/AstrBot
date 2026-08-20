import importlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import astrbot.core.pipeline.process_stage as process_stage_pkg
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.runtime_catalogs import RuntimeCatalogs
from astrbot.core.star.star import StarMetadata

_original_process_stage_module = sys.modules.get(
    "astrbot.core.pipeline.process_stage.stage"
)
_had_stage_attr = hasattr(process_stage_pkg, "stage")
_original_stage_attr = getattr(process_stage_pkg, "stage", None)
_stub_process_stage_module = types.ModuleType(
    "astrbot.core.pipeline.process_stage.stage"
)


class Stage: ...


setattr(_stub_process_stage_module, "Stage", Stage)
sys.modules["astrbot.core.pipeline.process_stage.stage"] = _stub_process_stage_module
star_request = importlib.import_module(
    "astrbot.core.pipeline.process_stage.method.star_request"
)

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
    def __init__(self, extras: dict, *, at_or_wake: bool = False):
        self._extras = extras
        self._stopped = False
        self.is_at_or_wake_command = at_or_wake
        self.result_history: list[MessageEventResult] = []
        self.clear_result_calls = 0

    def get_extra(self, key: str):
        return self._extras.get(key)

    def is_stopped(self) -> bool:
        return self._stopped

    def clear_result(self) -> None:
        self.clear_result_calls += 1

    def set_result(self, result: MessageEventResult) -> None:
        self.result_history.append(result)

    def stop_event(self) -> None:
        self._stopped = True


def _handler_meta(name: str, module_path: str = "plugin.module"):
    return SimpleNamespace(
        handler_full_name=f"{module_path}.{name}",
        handler_module_path=module_path,
        handler_name=name,
        handler=object(),
    )


def _stage_with_runtime():
    stage = star_request.StarRequestSubStage.__new__(star_request.StarRequestSubStage)
    catalogs = RuntimeCatalogs()
    stage.ctx = SimpleNamespace(
        handlers=catalogs.handlers,
        plugins=catalogs.plugins,
    )
    return stage, catalogs


def _publish_plugin(catalogs: RuntimeCatalogs, module_path: str) -> None:
    catalogs.plugins.publish(StarMetadata(name="demo-plugin", module_path=module_path))


@pytest.mark.asyncio
async def test_star_request_process_dispatches_handlers_and_clears_previous_results(
    monkeypatch,
):
    stage, catalogs = _stage_with_runtime()
    handler_a = _handler_meta("first")
    handler_b = _handler_meta("second")
    event = FakeEvent(
        {
            "activated_handlers": [handler_a, handler_b],
            "handlers_parsed_params": {
                handler_a.handler_full_name: {"value": 1},
                handler_b.handler_full_name: {"value": 2},
            },
        }
    )

    _publish_plugin(catalogs, "plugin.module")

    call_args = []

    async def fake_call_handler(event_arg, handler, **params):
        call_args.append(params)
        yield f"resp-{params['value']}"

    monkeypatch.setattr(star_request, "call_handler", fake_call_handler)

    yielded = [item async for item in stage.process(event)]

    assert yielded == ["resp-1", "resp-2"]
    assert call_args == [{"value": 1}, {"value": 2}]
    assert event.clear_result_calls == 2


@pytest.mark.asyncio
async def test_star_request_process_skips_missing_plugin_metadata(monkeypatch):
    stage, _ = _stage_with_runtime()
    handler = _handler_meta("missing", module_path="missing.module")
    event = FakeEvent({"activated_handlers": [handler], "handlers_parsed_params": {}})

    monkeypatch.setattr(star_request, "call_handler", AsyncMock())

    yielded = [item async for item in stage.process(event)]

    assert yielded == []
    star_request.call_handler.assert_not_called()
    assert event.clear_result_calls == 0


@pytest.mark.asyncio
async def test_star_request_process_reports_handler_errors_and_stops(monkeypatch):
    stage, catalogs = _stage_with_runtime()
    handler = _handler_meta("boom")
    event = FakeEvent(
        {"activated_handlers": [handler], "handlers_parsed_params": {}},
        at_or_wake=True,
    )

    _publish_plugin(catalogs, "plugin.module")

    async def fake_call_handler(event_arg, handler_obj, **params):
        if False:
            yield None
        raise RuntimeError("broken handler")

    on_plugin_error = AsyncMock(return_value=False)
    monkeypatch.setattr(star_request, "call_handler", fake_call_handler)
    monkeypatch.setattr(star_request, "call_event_hook", on_plugin_error)

    yielded = [item async for item in stage.process(event)]

    assert yielded == [None]
    on_plugin_error.assert_awaited_once()
    assert (
        event.result_history[-1]
        .get_plain_text()
        .startswith(
            ":(\n\n在调用插件 demo-plugin 的处理函数 boom 时出现异常：broken handler"
        )
    )
    assert event.clear_result_calls == 1
    assert event.is_stopped() is True


@pytest.mark.asyncio
async def test_star_request_process_stops_before_running_later_handlers(monkeypatch):
    stage, catalogs = _stage_with_runtime()
    handler_a = _handler_meta("first")
    handler_b = _handler_meta("second")
    event = FakeEvent({"activated_handlers": [handler_a, handler_b]})

    _publish_plugin(catalogs, "plugin.module")

    async def fake_call_handler(event_arg, handler_obj, **params):
        yield f"resp-{handler_obj is handler_a.handler}"
        event_arg.stop_event()

    monkeypatch.setattr(star_request, "call_handler", fake_call_handler)

    yielded = [item async for item in stage.process(event)]

    assert yielded == ["resp-True"]
    assert event.clear_result_calls == 0
    assert event.is_stopped() is True


@pytest.mark.asyncio
async def test_star_request_process_non_wake_error_stops_without_user_facing_result(
    monkeypatch,
):
    stage, catalogs = _stage_with_runtime()
    handler = _handler_meta("boom")
    event = FakeEvent(
        {"activated_handlers": [handler], "handlers_parsed_params": {}},
        at_or_wake=False,
    )

    _publish_plugin(catalogs, "plugin.module")

    async def fake_call_handler(event_arg, handler_obj, **params):
        if False:
            yield None
        raise RuntimeError("broken handler")

    on_plugin_error = AsyncMock(return_value=False)
    monkeypatch.setattr(star_request, "call_handler", fake_call_handler)
    monkeypatch.setattr(star_request, "call_event_hook", on_plugin_error)

    yielded = [item async for item in stage.process(event)]

    assert yielded == []
    on_plugin_error.assert_awaited_once()
    assert event.result_history == []
    assert event.clear_result_calls == 0
    assert event.is_stopped() is True
