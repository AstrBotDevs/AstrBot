"""Exercise event deduplication with a deterministic clock."""

from types import SimpleNamespace

import pytest

from astrbot.core.platform.sources.lark import lark_adapter as module


@pytest.mark.parametrize("age,duplicate", [(1799, True), (1800, True), (1801, False)])
def test_event_id_expires_only_after_retention_window(monkeypatch, age, duplicate):
    now = [10000.0]
    monkeypatch.setattr(module, "time", SimpleNamespace(time=lambda: now[0]))
    adapter = module.LarkPlatformAdapter.__new__(module.LarkPlatformAdapter)
    adapter.event_id_timestamps = {}

    assert adapter._is_duplicate_event("message-1") is False
    now[0] += age
    assert adapter._is_duplicate_event("message-1") is duplicate
    assert adapter.event_id_timestamps["message-1"] == (
        10000.0 if duplicate else now[0]
    )


def test_deduplication_preserves_other_live_events(monkeypatch):
    monkeypatch.setattr(module, "time", SimpleNamespace(time=lambda: 5000.0))
    adapter = module.LarkPlatformAdapter.__new__(module.LarkPlatformAdapter)
    adapter.event_id_timestamps = {"expired": 1000.0, "live": 4999.0}

    assert adapter._is_duplicate_event("new") is False
    assert adapter.event_id_timestamps == {"live": 4999.0, "new": 5000.0}
    assert adapter._is_duplicate_event("live") is True
    assert adapter.event_id_timestamps["live"] == 4999.0
