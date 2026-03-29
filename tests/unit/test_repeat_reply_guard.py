import inspect

from astrbot.core.astr_agent_run_util import (
    DEFAULT_REPEAT_REPLY_GUARD_THRESHOLD,
    normalize_config_repeat_reply_guard_threshold,
    normalize_repeat_reply_guard_threshold,
    run_agent,
    run_live_agent,
)
from astrbot.core.config.default import DEFAULT_CONFIG


def test_runtime_repeat_reply_guard_threshold_normalization():
    assert normalize_repeat_reply_guard_threshold("2") == 2
    assert normalize_repeat_reply_guard_threshold(-1) == 0
    assert normalize_repeat_reply_guard_threshold(None) == 0
    assert normalize_repeat_reply_guard_threshold(True) == 0


def test_config_repeat_reply_guard_threshold_normalization():
    assert normalize_config_repeat_reply_guard_threshold("4") == 4
    assert normalize_config_repeat_reply_guard_threshold(-1) == 0
    assert (
        normalize_config_repeat_reply_guard_threshold(None)
        == DEFAULT_REPEAT_REPLY_GUARD_THRESHOLD
    )
    assert (
        normalize_config_repeat_reply_guard_threshold(True)
        == DEFAULT_REPEAT_REPLY_GUARD_THRESHOLD
    )


def test_repeat_reply_guard_default_is_shared():
    assert (
        DEFAULT_CONFIG["provider_settings"]["repeat_reply_guard_threshold"]
        == DEFAULT_REPEAT_REPLY_GUARD_THRESHOLD
    )
    assert (
        inspect.signature(run_agent).parameters["repeat_reply_guard_threshold"].default
        == DEFAULT_REPEAT_REPLY_GUARD_THRESHOLD
    )
    assert (
        inspect.signature(run_live_agent)
        .parameters["repeat_reply_guard_threshold"]
        .default
        == DEFAULT_REPEAT_REPLY_GUARD_THRESHOLD
    )
