"""Shared fixtures for unit tests."""

from __future__ import annotations

from typing import Any

import pytest


class FakeGlobalSP:
    """In-memory stand-in for SharedPreferences global_get/global_put."""

    def __init__(self) -> None:
        self.data: dict[str, Any] = {}

    async def global_get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    async def global_put(self, key: str, value: Any) -> None:
        self.data[key] = value


@pytest.fixture(autouse=True)
def fake_bridge_sp(monkeypatch: pytest.MonkeyPatch) -> FakeGlobalSP:
    """Keep SDK bridge activation-state reads away from the real database."""
    fake = FakeGlobalSP()
    monkeypatch.setattr("astrbot.core.star.sdk_bridge.bridge.sp", fake)
    return fake
