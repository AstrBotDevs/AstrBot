from __future__ import annotations

from pathlib import Path

import pytest

from astrbot_sdk._internal.invocation_context import caller_plugin_scope
from astrbot_sdk.errors import AstrBotError
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


@pytest.mark.asyncio
async def test_http_unregister_empty_methods_removes_all_for_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    router = CapabilityRouter()

    await _call(
        router,
        "http.register_api",
        {
            "route": "/demo",
            "methods": ["GET", "POST"],
            "handler_capability": "demo.handler",
            "description": "demo",
        },
    )
    await _call(
        router,
        "http.unregister_api",
        {"route": "/demo", "methods": []},
    )

    listed = await _call(router, "http.list_apis", {})

    assert listed == {"apis": []}


@pytest.mark.asyncio
async def test_http_unregister_subset_preserves_other_methods(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    router = CapabilityRouter()

    await _call(
        router,
        "http.register_api",
        {
            "route": "/demo",
            "methods": ["GET", "POST"],
            "handler_capability": "demo.handler",
            "description": "demo",
        },
    )
    await _call(
        router,
        "http.unregister_api",
        {"route": "/demo", "methods": ["POST"]},
    )

    listed = await _call(router, "http.list_apis", {})

    assert listed == {
        "apis": [
            {
                "route": "/demo",
                "methods": ["GET"],
                "handler_capability": "demo.handler",
                "description": "demo",
                "plugin_id": "test-plugin",
            }
        ]
    }


@pytest.mark.asyncio
async def test_http_register_rejects_routes_with_empty_segments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    router = CapabilityRouter()

    with pytest.raises(AstrBotError) as exc_info:
        await _call(
            router,
            "http.register_api",
            {
                "route": "/foo//bar",
                "methods": ["GET"],
                "handler_capability": "demo.handler",
                "description": "demo",
            },
        )

    assert exc_info.value.code == "invalid_input"
