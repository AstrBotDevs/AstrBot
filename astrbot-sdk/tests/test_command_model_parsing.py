"""
针对 command_model 解析逻辑的边界场景单元测试。
覆盖：--help 生成、位置参数超限、重复 flag、连字符映射。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pydantic import BaseModel

from astrbot_sdk._internal.command_model import (
    CommandModelParseResult,
    ResolvedCommandModelParam,
    format_command_model_help,
    parse_command_model_remainder,
    resolve_command_model_param,
)
from astrbot_sdk.errors import AstrBotError


# ── 测试用模型 ────────────────────────────────────────────────────


class SimpleModel(BaseModel):
    name: str
    count: int = 1
    verbose: bool = False


class HyphenModel(BaseModel):
    output_dir: str
    max_retries: int = 3


# ── 辅助：构建 ResolvedCommandModelParam ──────────────────────────


def _param(model_cls: type[BaseModel]) -> ResolvedCommandModelParam:
    return ResolvedCommandModelParam(name="args", model_cls=model_cls)


# ── --help 测试 ───────────────────────────────────────────────────


def test_help_flag_short() -> None:
    result = parse_command_model_remainder(
        remainder="-h", model_param=_param(SimpleModel), command_name="test"
    )
    assert result.model is None
    assert result.help_text is not None
    assert "test" in result.help_text


def test_help_flag_long() -> None:
    result = parse_command_model_remainder(
        remainder="--help", model_param=_param(SimpleModel), command_name="greet"
    )
    assert result.model is None
    assert result.help_text is not None
    assert "name" in result.help_text
    assert "count" in result.help_text
    assert "verbose" in result.help_text


def test_format_command_model_help_contains_bool_hint() -> None:
    text = format_command_model_help("myCmd", SimpleModel)
    assert "--verbose" in text
    assert "--no-verbose" in text


# ── 位置参数超限 ──────────────────────────────────────────────────


def test_too_many_positional_args_raises() -> None:
    with pytest.raises(AstrBotError) as exc_info:
        parse_command_model_remainder(
            remainder="alice 10 extra",
            model_param=_param(SimpleModel),
            command_name="cmd",
        )
    assert "Too many positional arguments" in str(exc_info.value)


def test_exactly_right_positional_args_succeeds() -> None:
    result = parse_command_model_remainder(
        remainder="alice 5",
        model_param=_param(SimpleModel),
        command_name="cmd",
    )
    assert result.model is not None
    assert result.model.name == "alice"  # type: ignore[attr-defined]
    assert result.model.count == 5  # type: ignore[attr-defined]


# ── 重复 flag ─────────────────────────────────────────────────────


def test_duplicate_named_flag_raises() -> None:
    with pytest.raises(AstrBotError) as exc_info:
        parse_command_model_remainder(
            remainder="--name alice --name bob",
            model_param=_param(SimpleModel),
            command_name="cmd",
        )
    assert "Duplicate option" in str(exc_info.value)


def test_duplicate_bool_flag_raises() -> None:
    with pytest.raises(AstrBotError) as exc_info:
        parse_command_model_remainder(
            remainder="--verbose --verbose",
            model_param=_param(SimpleModel),
            command_name="cmd",
        )
    assert "Duplicate option" in str(exc_info.value)


# ── 连字符映射下划线 ───────────────────────────────────────────────


def test_hyphen_flag_maps_to_underscore_field() -> None:
    result = parse_command_model_remainder(
        remainder="--output-dir /tmp --max-retries 5",
        model_param=_param(HyphenModel),
        command_name="build",
    )
    assert result.model is not None
    assert result.model.output_dir == "/tmp"  # type: ignore[attr-defined]
    assert result.model.max_retries == 5  # type: ignore[attr-defined]


def test_underscore_flag_still_works() -> None:
    """直接使用下划线形式也应正常解析（向后兼容）。"""
    result = parse_command_model_remainder(
        remainder="--output_dir /out",
        model_param=_param(HyphenModel),
        command_name="build",
    )
    assert result.model is not None
    assert result.model.output_dir == "/out"  # type: ignore[attr-defined]


# ── bool 标志 --no- 前缀 ──────────────────────────────────────────


def test_bool_negation_flag() -> None:
    result = parse_command_model_remainder(
        remainder="alice --no-verbose",
        model_param=_param(SimpleModel),
        command_name="cmd",
    )
    assert result.model is not None
    assert result.model.verbose is False  # type: ignore[attr-defined]


def test_bool_positive_flag() -> None:
    result = parse_command_model_remainder(
        remainder="alice --verbose",
        model_param=_param(SimpleModel),
        command_name="cmd",
    )
    assert result.model is not None
    assert result.model.verbose is True  # type: ignore[attr-defined]


# ── 未知字段 ──────────────────────────────────────────────────────


def test_unknown_flag_raises() -> None:
    with pytest.raises(AstrBotError) as exc_info:
        parse_command_model_remainder(
            remainder="--nonexistent foo",
            model_param=_param(SimpleModel),
            command_name="cmd",
        )
    assert "Unknown option" in str(exc_info.value)


# ── resolve_command_model_param ───────────────────────────────────


def test_resolve_finds_model_param() -> None:
    def handler(event: object, args: SimpleModel) -> None: ...

    resolved = resolve_command_model_param(handler)
    assert resolved is not None
    assert resolved.model_cls is SimpleModel


def test_resolve_returns_none_for_plain_handler() -> None:
    def handler(event: object, name: str) -> None: ...

    resolved = resolve_command_model_param(handler)
    assert resolved is None
