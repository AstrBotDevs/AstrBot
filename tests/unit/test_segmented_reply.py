import pytest

from astrbot.core.utils.segmented_reply import (
    calc_segment_interval,
    cleanup_segments,
    compile_split_words_pattern,
    split_text_by_regex,
    split_text_by_words,
)


def test_regex_split_normalizes_capture_group_matches_before_cleanup():
    segments = split_text_by_regex("alpha.beta.", r"(\w+)(\.)")

    assert segments == ["alpha.", "beta."]
    assert cleanup_segments(segments, r"\.") == ["alpha", "beta"]


def test_regex_split_falls_back_when_regex_is_not_a_string():
    assert split_text_by_regex("plain text", None) == ["plain text"]


def test_split_words_ignores_invalid_container_types():
    assert compile_split_words_pattern("|") is None


def test_split_words_converts_non_string_words_for_matching():
    split_words = [7, "", None]
    pattern = compile_split_words_pattern(split_words)

    assert split_text_by_words("alpha7beta", split_words, pattern) == ["alpha", "beta"]


def test_log_interval_uses_safe_non_negative_fallback_for_invalid_base():
    assert calc_segment_interval("alpha beta", "log", (0, 0), 1.0) >= 0


@pytest.mark.parametrize(
    "interval_range",
    [
        (-3.0, -1.0),
        (-2.0, 2.0),
    ],
)
def test_random_interval_is_never_negative(interval_range):
    assert calc_segment_interval("alpha", "random", interval_range, 2.6) >= 0
