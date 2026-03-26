# ruff: noqa: E402
from __future__ import annotations

import pytest

from astrbot_sdk.errors import AstrBotError

from tests.test_sdk.unit._context_api_roundtrip import build_roundtrip_runtime


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_db_client_round_trips_through_core_bridge(tmp_path, monkeypatch):
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    plugin_a_ctx = runtime.make_context("plugin-a")
    plugin_b_ctx = runtime.make_context("plugin-b")

    await plugin_a_ctx.db.set("user_settings", {"theme": "dark", "lang": "zh"})
    await plugin_a_ctx.db.set_many(
        {
            "user:1": {"name": "Alice"},
            "user:2": {"name": "Bob"},
        }
    )
    await plugin_b_ctx.db.set("user_settings", {"theme": "light"})

    assert await plugin_a_ctx.db.get("user_settings") == {
        "theme": "dark",
        "lang": "zh",
    }
    assert await plugin_b_ctx.db.get("user_settings") == {"theme": "light"}
    assert await plugin_a_ctx.db.get_many(["user:1", "user:2", "missing"]) == {
        "user:1": {"name": "Alice"},
        "user:2": {"name": "Bob"},
        "missing": None,
    }
    assert await plugin_a_ctx.db.list("user") == [
        "user:1",
        "user:2",
        "user_settings",
    ]

    await plugin_a_ctx.db.delete("user:2")

    assert await plugin_a_ctx.db.get("user:2") is None
    assert runtime.runtime_sp.store == {
        ("plugin", "plugin-a", "user_settings"): {"theme": "dark", "lang": "zh"},
        ("plugin", "plugin-a", "user:1"): {"name": "Alice"},
        ("plugin", "plugin-b", "user_settings"): {"theme": "light"},
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_db_watch_exposes_current_core_bridge_limit(
    tmp_path,
    monkeypatch,
) -> None:
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    watcher = ctx.db.watch("user:")

    with pytest.raises(AstrBotError, match="unsupported in AstrBot SDK MVP"):
        await anext(watcher)
