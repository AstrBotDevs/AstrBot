from functools import partial
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.provider.usage_attribution import iter_with_usage, plugin_for_handler
from astrbot.core.provider.usage_recorder import usage_scope
from astrbot.core.star.star import star_map


def test_plugin_identity_comes_from_registered_metadata(monkeypatch):
    def handler():
        pass

    monkeypatch.setitem(star_map, handler.__module__, SimpleNamespace(name="example"))
    assert plugin_for_handler(handler) == "example"
    assert plugin_for_handler(partial(handler)) == "example"
    assert plugin_for_handler(object()) is None


@pytest.mark.asyncio
async def test_attributed_generator_resets_scope_before_yield_and_closes(monkeypatch):
    from astrbot.core.provider import usage_attribution

    active = []
    seen = []
    from contextlib import contextmanager

    @contextmanager
    def scope(event, **kwargs):
        active.append(kwargs["plugin_id"])
        try:
            yield
        finally:
            active.pop()

    monkeypatch.setattr(usage_attribution, "event_usage_scope", scope)

    async def source():
        try:
            seen.append(list(active))
            yield "first"
            yield "second"
        finally:
            seen.append(list(active))

    iterator = iter_with_usage(source(), event=object(), plugin_id="example")
    with usage_scope(plugin_id="outer"):
        assert await anext(iterator) == "first"
        assert active == []
        await iterator.aclose()
        assert active == []
    assert seen == [["example"], ["example"]]


@pytest.mark.asyncio
async def test_plugin_direct_call_and_returned_request_keep_attribution(monkeypatch):
    from astrbot.core.pipeline.context_utils import call_handler
    from astrbot.core.provider.entities import LLMResponse, ProviderRequest, TokenUsage
    from astrbot.core.provider.usage_recorder import instrument_provider

    class Provider:
        provider_config = {"id": "model-a", "provider_source_id": "source-a"}

        def get_model(self):
            return "model"

        async def text_chat(self):
            return LLMResponse(role="assistant", usage=TokenUsage(output=3))

    writer = AsyncMock()
    provider = instrument_provider(
        Provider(), SimpleNamespace(insert_provider_stat=writer)
    )
    event = SimpleNamespace(
        unified_msg_origin="qq:GroupMessage:example",
        trace=SimpleNamespace(span_id="trace-a"),
    )

    async def handler(event):
        await provider.text_chat()
        yield ProviderRequest(prompt="test")

    monkeypatch.setitem(star_map, handler.__module__, SimpleNamespace(name="plugin-a"))
    result = [value async for value in call_handler(event, partial(handler))]
    assert result[0].usage_plugin_id == "plugin-a"
    await provider.text_chat()
    first, second = [item.kwargs for item in writer.await_args_list]
    assert first["stats"]["session_umo"] == event.unified_msg_origin
    assert first["stats"]["trace_id"] == "trace-a"
    assert first["stats"]["plugin_id"] == "plugin-a"
    assert second["stats"]["session_umo"] is None
    assert second["stats"]["plugin_id"] is None


@pytest.mark.asyncio
async def test_closing_plugin_dispatch_closes_handler_immediately():
    from astrbot.core.pipeline.context_utils import call_handler

    closed = []

    async def handler(event):
        try:
            yield "value"
        finally:
            closed.append(True)

    event = SimpleNamespace(unified_msg_origin="qq:GroupMessage:example")
    iterator = call_handler(event, handler, _usage_plugin_id="example")
    assert await anext(iterator) == "value"
    await iterator.aclose()
    assert closed == [True]
