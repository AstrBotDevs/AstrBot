from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.message import Message
from astrbot.core.config.default import PERIODIC_CONTEXT_COMPACTION_DEFAULTS
from astrbot.core.context_compaction_scheduler import (
    CompactionConfig,
    CompactionPolicy,
    PeriodicContextCompactionScheduler,
)


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

    assert cfg.enabled is True
    assert cfg.interval_minutes == 1
    assert cfg.target_tokens == 1024
    assert cfg.trigger_tokens == 1000
    assert cfg.trigger_min_context_ratio == pytest.approx(0.3)
    assert cfg.max_rounds == 2


@pytest.mark.parametrize(
    ("raw_enabled", "expected"),
    [
        ("true", True),
        ("false", False),
        ("1", True),
        ("0", False),
        ("yes", True),
        ("no", False),
        ("unknown", False),
    ],
)
def test_load_config_enabled_bool_parsing(raw_enabled: str, expected: bool) -> None:
    scheduler = _build_scheduler(
        {
            "periodic_context_compaction": {
                "enabled": raw_enabled,
            }
        }
    )

    cfg = scheduler._load_config()
    assert cfg.enabled is expected


@pytest.mark.parametrize(
    ("raw_cfg", "expected_interval", "expected_scan_page_size", "expected_min_messages"),
    [
        ({"interval_minutes": 0, "scan_page_size": 1, "min_messages": 0}, 1, 10, 2),
        (
            {"interval_minutes": -3, "scan_page_size": -5, "min_messages": -1},
            1,
            10,
            2,
        ),
        (
            {"interval_minutes": "0", "scan_page_size": "1", "min_messages": "0"},
            1,
            10,
            2,
        ),
    ],
)
def test_load_config_clamps_numeric_minimums(
    raw_cfg: dict,
    expected_interval: int,
    expected_scan_page_size: int,
    expected_min_messages: int,
) -> None:
    scheduler = _build_scheduler({"periodic_context_compaction": raw_cfg})
    cfg = scheduler._load_config()

    assert cfg.interval_minutes == expected_interval
    assert cfg.scan_page_size == expected_scan_page_size
    assert cfg.min_messages == expected_min_messages


@pytest.mark.parametrize(
    ("raw_cfg", "expected_target", "expected_trigger"),
    [
        ({"target_tokens": 1024}, 1024, 0),
        ({"target_tokens": 1024, "trigger_tokens": None}, 1024, 0),
        ({"target_tokens": 1024, "trigger_tokens": 512}, 1024, 512),
        ({"target_tokens": 1024, "trigger_tokens": "512"}, 1024, 512),
        ({"target_tokens": 1024, "trigger_tokens": 2048}, 1024, 2048),
        ({"target_tokens": 10}, 512, 0),
    ],
)
def test_load_config_token_threshold_normalization(
    raw_cfg: dict,
    expected_target: int,
    expected_trigger: int,
) -> None:
    scheduler = _build_scheduler({"periodic_context_compaction": raw_cfg})
    cfg = scheduler._load_config()

    assert cfg.target_tokens == expected_target
    assert cfg.trigger_tokens == expected_trigger


@pytest.mark.parametrize(
    ("raw_ratio", "expected"),
    [
        (0.3, 0.3),
        ("30", 0.3),
        ("0.25", 0.25),
        (-1, 0.0),
        (500, 1.0),
    ],
)
def test_load_config_trigger_ratio_normalization(raw_ratio, expected: float) -> None:
    scheduler = _build_scheduler(
        {"periodic_context_compaction": {"trigger_min_context_ratio": raw_ratio}}
    )
    cfg = scheduler._load_config()
    assert cfg.trigger_min_context_ratio == pytest.approx(expected)


@pytest.mark.parametrize("raw_value", [None, 1, "not-a-dict", []])
def test_load_config_falls_back_for_non_dict(raw_value) -> None:
    scheduler = _build_scheduler({"periodic_context_compaction": raw_value})
    cfg = scheduler._load_config()

    expected = CompactionConfig(**PERIODIC_CONTEXT_COMPACTION_DEFAULTS)
    assert cfg == expected


def test_get_status_returns_runtime_snapshot() -> None:
    scheduler = _build_scheduler(
        {"periodic_context_compaction": {"enabled": True, "interval_minutes": 3}}
    )
    status = scheduler.get_status()

    assert status["running"] is False
    assert status["config"]["enabled"] is True
    assert status["config"]["interval_minutes"] == 3
    assert status["last_report"] is None


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

    sanitized = scheduler._history_parser.sanitize_message_dict(raw)

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

    assert CompactionPolicy.is_idle_enough(old, 10) is True
    assert CompactionPolicy.is_idle_enough(recent, 10) is False
    assert CompactionPolicy.is_idle_enough(None, 10) is True


def test_resolve_run_limits_treats_max_scan_as_upper_bound() -> None:
    scheduler = _build_scheduler({})
    cfg = replace(
        scheduler._load_config(),
        max_conversations_per_run=8,
        max_scan_per_run=3,
        scan_page_size=5,
    )

    max_to_compact, max_to_scan, page_size = scheduler._resolve_run_limits(cfg, None)
    assert max_to_compact == 3
    assert max_to_scan == 3
    assert page_size == 10

    max_to_compact, max_to_scan, _ = scheduler._resolve_run_limits(cfg, 20)
    assert max_to_compact == 3
    assert max_to_scan == 3


def test_resolve_trigger_tokens_prefers_manual_value() -> None:
    scheduler = _build_scheduler({})
    cfg = replace(
        scheduler._load_config(),
        target_tokens=1024,
        trigger_tokens=1500,
        trigger_min_context_ratio=0.3,
    )
    policy = CompactionPolicy(cfg=cfg, token_counter=SimpleNamespace())
    provider = SimpleNamespace(
        provider_config={"max_context_tokens": 32768},
        get_model=lambda: "unknown-model",
    )

    resolved = policy.resolve_trigger_tokens(provider)
    assert resolved == 1500


def test_resolve_trigger_tokens_uses_ratio_when_auto_mode() -> None:
    scheduler = _build_scheduler({})
    cfg = replace(
        scheduler._load_config(),
        target_tokens=1024,
        trigger_tokens=0,
        trigger_min_context_ratio=0.3,
    )
    policy = CompactionPolicy(cfg=cfg, token_counter=SimpleNamespace())
    provider = SimpleNamespace(
        provider_config={"max_context_tokens": 32768},
        get_model=lambda: "unknown-model",
    )

    resolved = policy.resolve_trigger_tokens(provider)
    assert resolved == 9830


def test_resolve_trigger_tokens_falls_back_when_provider_context_unknown() -> None:
    scheduler = _build_scheduler({})
    cfg = replace(
        scheduler._load_config(),
        target_tokens=1024,
        trigger_tokens=0,
        trigger_min_context_ratio=0.3,
    )
    policy = CompactionPolicy(cfg=cfg, token_counter=SimpleNamespace())
    provider = SimpleNamespace(
        provider_config={"max_context_tokens": 0},
        get_model=lambda: "unknown-model",
    )

    resolved = policy.resolve_trigger_tokens(provider)
    assert resolved == 1536


def test_resolve_token_counter_uses_configured_mode_and_provider_model(monkeypatch) -> None:
    scheduler = _build_scheduler({"context_token_counter_mode": "auto"})
    provider = SimpleNamespace(get_model=lambda: "gpt-4o")
    called: dict[str, str | None] = {}

    fake_counter = SimpleNamespace(count_tokens=lambda *_args, **_kwargs: 0)

    def _fake_create(mode: str | None = None, *, model: str | None = None):
        called["mode"] = mode
        called["model"] = model
        return fake_counter

    monkeypatch.setattr(
        "astrbot.core.context_compaction_scheduler.create_token_counter",
        _fake_create,
    )

    resolved = scheduler._resolve_token_counter(provider)
    assert resolved is fake_counter
    assert called["mode"] == "auto"
    assert called["model"] == "gpt-4o"


def test_resolve_token_counter_prefers_provider_level_mode(monkeypatch) -> None:
    scheduler = _build_scheduler({"context_token_counter_mode": "estimate"})
    provider = SimpleNamespace(
        get_model=lambda: "gpt-4o",
        provider_settings={"context_token_counter_mode": "tokenizer"},
    )
    called: dict[str, str | None] = {}

    fake_counter = SimpleNamespace(count_tokens=lambda *_args, **_kwargs: 0)

    def _fake_create(mode: str | None = None, *, model: str | None = None):
        called["mode"] = mode
        called["model"] = model
        return fake_counter

    monkeypatch.setattr(
        "astrbot.core.context_compaction_scheduler.create_token_counter",
        _fake_create,
    )

    resolved = scheduler._resolve_token_counter(provider)
    assert resolved is fake_counter
    assert called["mode"] == "tokenizer"
    assert called["model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_iter_candidate_conversations_does_not_apply_idle_filter_in_db_query() -> None:
    scheduler = _build_scheduler(
        {"periodic_context_compaction": {"enabled": True, "min_idle_minutes": 30}}
    )

    class _FakeDB:
        def __init__(self) -> None:
            self.updated_before_calls: list[datetime | None] = []

        async def get_filtered_conversations(
            self,
            *,
            page: int,
            page_size: int,
            updated_before: datetime | None,
            min_messages: int,
        ):
            self.updated_before_calls.append(updated_before)
            return [], 0

    fake_db = _FakeDB()
    scheduler.conversation_manager = SimpleNamespace(db=fake_db)  # type: ignore[assignment]

    cfg = scheduler._load_config()
    result = [
        conv
        async for conv in scheduler._iter_candidate_conversations(
            scan_page_size=40,
            cfg=cfg,
        )
    ]

    assert result == []
    assert fake_db.updated_before_calls == [None]


@pytest.mark.asyncio
async def test_compact_one_conversation_dry_run_reports_skipped(monkeypatch) -> None:
    scheduler = _build_scheduler({"periodic_context_compaction": {"enabled": True}})
    cfg = replace(scheduler._load_config(), dry_run=True)

    conv = SimpleNamespace(
        conversation_id="conv-1",
        user_id="user-1",
        content=[],
        token_usage=0,
        updated_at=None,
    )
    scheduler._resolve_provider = AsyncMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(get_model=lambda: "gpt-4o")
    )
    scheduler._run_compaction_rounds = AsyncMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(
            messages=[Message(role="user", content="after")],
            changed=True,
            rounds=1,
        )
    )
    scheduler._resolve_token_counter = lambda _provider: SimpleNamespace(  # type: ignore[method-assign]
        count_tokens=lambda *_args, **_kwargs: 50
    )
    scheduler._persist_compacted_history = AsyncMock(  # type: ignore[method-assign]
        return_value=True
    )
    monkeypatch.setattr(
        CompactionPolicy,
        "check_eligibility",
        lambda self, _conv, _parser: ([Message(role="user", content="before")], 100),
    )
    monkeypatch.setattr(
        CompactionPolicy,
        "resolve_trigger_tokens",
        lambda self, _provider: 1,
    )

    outcome = await scheduler._compact_one_conversation(conv, cfg)

    assert outcome == "skipped"
    scheduler._persist_compacted_history.assert_not_awaited()
