from __future__ import annotations

from pathlib import Path

import pytest

from astrbot_sdk._internal.invocation_context import caller_plugin_scope
from astrbot_sdk.runtime.capability_router import CapabilityRouter


async def _call(
    router: CapabilityRouter,
    capability: str,
    payload: dict[str, object],
    *,
    plugin_id: str = "test-plugin",
) -> dict[str, object]:
    with caller_plugin_scope(plugin_id):
        result = await router.execute(
            capability,
            payload,
            stream=False,
            cancel_token=object(),
            request_id=f"{plugin_id}:{capability}",
        )
    assert isinstance(result, dict)
    return result


async def _stream(
    router: CapabilityRouter,
    capability: str,
    payload: dict[str, object],
    *,
    plugin_id: str = "test-plugin",
):
    with caller_plugin_scope(plugin_id):
        result = await router.execute(
            capability,
            payload,
            stream=True,
            cancel_token=object(),
            request_id=f"{plugin_id}:{capability}:stream",
        )
    return result


@pytest.mark.asyncio
async def test_db_watch_returns_plugin_local_key_view(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    router = CapabilityRouter()

    stream = await _stream(router, "db.watch", {"prefix": None}, plugin_id="plugin-a")
    await _call(
        router,
        "db.set",
        {"key": "user:1", "value": {"name": "Alice"}},
        plugin_id="plugin-a",
    )

    event = await anext(stream.iterator)

    assert event == {
        "op": "set",
        "key": "user:1",
        "value": {"name": "Alice"},
    }


@pytest.mark.asyncio
async def test_db_watch_prefix_filters_within_plugin_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    router = CapabilityRouter()

    stream = await _stream(router, "db.watch", {"prefix": "user:"}, plugin_id="plugin-a")
    await _call(router, "db.set", {"key": "config:1", "value": 1}, plugin_id="plugin-a")
    await _call(router, "db.set", {"key": "user:2", "value": 2}, plugin_id="plugin-b")
    await _call(router, "db.set", {"key": "user:1", "value": 3}, plugin_id="plugin-a")

    event = await anext(stream.iterator)

    assert event == {"op": "set", "key": "user:1", "value": 3}
