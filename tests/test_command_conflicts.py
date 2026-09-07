"""指令冲突检测单元测试(主名 + 别名)。"""

from __future__ import annotations

from types import SimpleNamespace

from astrbot.core.star.command_management import (
    CommandDescriptor,
    _group_conflicts,
)


def _desc(
    handler_full_name: str,
    effective: str,
    aliases: list[str] | None = None,
    parent_signature: str = "",
    enabled: bool = True,
) -> CommandDescriptor:
    """构造一个用于冲突检测的最小 descriptor(不依赖插件注册表)。"""
    return CommandDescriptor(
        handler=SimpleNamespace(),
        handler_full_name=handler_full_name,
        effective_command=effective,
        aliases=list(aliases or []),
        parent_signature=parent_signature,
        module_path="test.module.not_registered",
        enabled=enabled,
    )


def test_no_conflict_for_distinct_commands():
    conflicts = _group_conflicts(
        [
            _desc("m_a", "weather", ["天气"]),
            _desc("m_b", "forecast", ["预报"]),
        ]
    )
    assert conflicts == {}


def test_alias_conflicts_with_other_alias():
    # 两个插件注册了同一个中文别名(如多语言别名撞车)
    conflicts = _group_conflicts(
        [
            _desc("m_a", "weather", ["帮助"]),
            _desc("m_b", "forecast", ["帮助"]),
        ]
    )
    assert set(conflicts) == {"帮助"}
    names = {d.handler_full_name for d in conflicts["帮助"]}
    assert names == {"m_a", "m_b"}


def test_alias_conflicts_with_other_main_name():
    # 某指令的别名与另一指令的主名相同
    conflicts = _group_conflicts(
        [
            _desc("m_a", "weather", ["预报"]),
            _desc("m_b", "预报", []),
        ]
    )
    assert set(conflicts) == {"预报"}
    assert {d.handler_full_name for d in conflicts["预报"]} == {"m_a", "m_b"}


def test_main_name_conflict_still_detected():
    conflicts = _group_conflicts(
        [
            _desc("m_a", "weather", []),
            _desc("m_b", "weather", []),
        ]
    )
    assert set(conflicts) == {"weather"}


def test_self_duplicate_alias_is_not_conflict():
    # 同一指令的主名与别名重复,不应算冲突
    conflicts = _group_conflicts(
        [
            _desc("m_a", "weather", ["weather"]),
            _desc("m_b", "forecast", []),
        ]
    )
    assert conflicts == {}


def test_disabled_command_ignored():
    conflicts = _group_conflicts(
        [
            _desc("m_a", "weather", ["天气"]),
            _desc("m_b", "forecast", ["天气"], enabled=False),
        ]
    )
    assert conflicts == {}


def test_sub_command_alias_includes_parent_signature():
    # 子指令别名需要带父级前缀:admin 组下的 info 别名 = "admin info"
    conflicts = _group_conflicts(
        [
            _desc("m_a", "admin help", ["info"], parent_signature="admin"),
            _desc("m_b", "admin info", []),
        ]
    )
    assert set(conflicts) == {"admin info"}
    assert {d.handler_full_name for d in conflicts["admin info"]} == {"m_a", "m_b"}
