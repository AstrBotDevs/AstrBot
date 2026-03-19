from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from astrbot.core.context_compaction_scheduler import PeriodicContextCompactionScheduler


class DummyConfigManager:
    def __init__(self, default_conf: dict):
        self.default_conf = default_conf


def _build_scheduler(cfg: dict) -> PeriodicContextCompactionScheduler:
    manager = DummyConfigManager({"provider_settings": cfg})
    return PeriodicContextCompactionScheduler(
        config_manager=manager,
        conversation_manager=SimpleNamespace(),
        provider_manager=SimpleNamespace(),
    )


def test_load_config_normalizes_values() -> None:
    scheduler = _build_scheduler(
        {
            "periodic_context_compaction": {
                "enabled": "true",
                "interval_minutes": "0",
                "target_tokens": 1024,
                "trigger_tokens": 1000,
                "max_rounds": "2",
            }
        }
    )

    cfg = scheduler._load_config()

    assert cfg["enabled"] is True
    assert cfg["interval_minutes"] == 1
    assert cfg["target_tokens"] == 1024
    assert cfg["trigger_tokens"] == 1025
    assert cfg["max_rounds"] == 2


def test_sanitize_message_dict_keeps_supported_parts() -> None:
    scheduler = _build_scheduler({})

    raw = {
        "role": "assistant",
        "content": [
            {"type": "think", "think": "internal reasoning"},
            {"type": "text", "text": "visible answer"},
            {"type": "image_url", "image_url": {"url": "https://x.test/a.png"}},
            {"type": "unknown", "foo": "bar"},
        ],
    }

    sanitized = scheduler._sanitize_message_dict(raw)

    assert sanitized is not None
    assert sanitized["role"] == "assistant"
    assert isinstance(sanitized["content"], list)
    content = sanitized["content"]
    assert content[0]["type"] == "text"
    assert "internal reasoning" in content[0]["text"]
    assert any(part.get("type") == "image_url" for part in content)


def test_is_idle_enough_respects_threshold() -> None:
    now = datetime.now(timezone.utc)
    old = now - timedelta(minutes=30)
    recent = now - timedelta(minutes=2)

    assert PeriodicContextCompactionScheduler._is_idle_enough(old, 10) is True
    assert PeriodicContextCompactionScheduler._is_idle_enough(recent, 10) is False
    assert PeriodicContextCompactionScheduler._is_idle_enough(None, 10) is True
