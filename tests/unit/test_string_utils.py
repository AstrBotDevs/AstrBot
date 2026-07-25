"""Tests for astrbot.core.utils.string_utils."""

import pytest

from astrbot.core.utils.string_utils import normalize_optional_text


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("\n\t ", None),
        ("hello", "hello"),
        ("  hello  ", "hello"),
        ("  多行\n文本  ", "多行\n文本"),
    ],
)
def test_normalize_optional_text(value: str | None, expected: str | None):
    assert normalize_optional_text(value) == expected
