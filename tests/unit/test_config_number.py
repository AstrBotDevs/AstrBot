import math

import pytest

from astrbot.core.utils.config_number import (
    coerce_float_config,
    coerce_int_config,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (128_000, 128_000),
        (" 128000 ", 128_000),
        (1.9, 1),
    ],
)
def test_coerce_int_config_accepts_numeric_values(value: object, expected: int) -> None:
    assert coerce_int_config(value, default=0, warn=False) == expected


@pytest.mark.parametrize("value", [None, "", "invalid", True, False])
def test_coerce_int_config_rejects_invalid_values(value: object) -> None:
    assert coerce_int_config(value, default=42, warn=False) == 42


def test_coerce_int_config_clamps_to_minimum() -> None:
    assert coerce_int_config(-1, default=0, min_value=0, warn=False) == 0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.82, 0.82),
        (" 0.82 ", 0.82),
        (1, 1.0),
    ],
)
def test_coerce_float_config_accepts_numeric_values(
    value: object, expected: float
) -> None:
    assert coerce_float_config(value, default=0.5, warn=False) == pytest.approx(
        expected
    )


@pytest.mark.parametrize(
    "value",
    [None, "", "invalid", True, False, math.nan, math.inf, -math.inf],
)
def test_coerce_float_config_rejects_invalid_values(value: object) -> None:
    assert coerce_float_config(value, default=0.5, warn=False) == pytest.approx(0.5)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(-0.1, 0.01), (0.5, 0.5), (1.5, 1.0)],
)
def test_coerce_float_config_clamps_to_range(value: float, expected: float) -> None:
    assert coerce_float_config(
        value,
        default=0.82,
        min_value=0.01,
        max_value=1.0,
        warn=False,
    ) == pytest.approx(expected)
