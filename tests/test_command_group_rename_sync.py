"""指令组重命名后子指令前缀同步的测试（#9366）。

模拟 WebUI 中对指令组的重命名 / 别名修改流程，验证子指令（含嵌套指令组）
能够正确匹配新前缀，且不再匹配旧前缀。
"""

from __future__ import annotations

from astrbot.core.star.command_management import (
    _set_filter_aliases,
    _set_filter_fragment,
)
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter


def _make_group_with_sub() -> tuple[CommandGroupFilter, CommandFilter]:
    """模拟 register_command 的注册流程：子指令持有父级完整指令名的快照。"""
    group = CommandGroupFilter("example_cmd_group")
    sub = CommandFilter(
        "sub_cmd",
        parent_command_names=group.get_complete_command_names(),
    )
    group.add_sub_command_filter(sub)
    return group, sub


def test_rename_group_updates_sub_command_prefix():
    group, sub = _make_group_with_sub()

    # 预热缓存，模拟重命名前指令已被触发过
    assert sub.equals("example_cmd_group sub_cmd")

    _set_filter_fragment(group, "renamed_group")

    assert set(group.get_complete_command_names()) == {"renamed_group"}
    assert set(sub.get_complete_command_names()) == {"renamed_group sub_cmd"}
    assert sub.equals("renamed_group sub_cmd")
    assert not sub.equals("example_cmd_group sub_cmd")


def test_rename_group_updates_nested_group_and_leaf():
    root = CommandGroupFilter("g1")
    nested = CommandGroupFilter("g2", parent_group=root)
    root.add_sub_command_filter(nested)
    leaf = CommandFilter(
        "leaf",
        parent_command_names=nested.get_complete_command_names(),
    )
    nested.add_sub_command_filter(leaf)

    # 预热缓存
    assert leaf.equals("g1 g2 leaf")
    assert nested.equals("g1 g2")

    _set_filter_fragment(root, "root")

    assert set(nested.get_complete_command_names()) == {"root g2"}
    assert set(leaf.get_complete_command_names()) == {"root g2 leaf"}
    assert leaf.equals("root g2 leaf")
    assert not leaf.equals("g1 g2 leaf")


def test_rename_nested_group_only_affects_its_subtree():
    root = CommandGroupFilter("g1")
    nested = CommandGroupFilter("g2", parent_group=root)
    root.add_sub_command_filter(nested)
    direct_sub = CommandFilter(
        "direct",
        parent_command_names=root.get_complete_command_names(),
    )
    root.add_sub_command_filter(direct_sub)
    leaf = CommandFilter(
        "leaf",
        parent_command_names=nested.get_complete_command_names(),
    )
    nested.add_sub_command_filter(leaf)

    _set_filter_fragment(nested, "sub2")

    assert set(leaf.get_complete_command_names()) == {"g1 sub2 leaf"}
    # 兄弟指令不受影响
    assert set(direct_sub.get_complete_command_names()) == {"g1 direct"}


def test_group_alias_change_updates_sub_command_prefix():
    group, sub = _make_group_with_sub()
    assert sub.equals("example_cmd_group sub_cmd")

    _set_filter_aliases(group, ["ecg"])

    assert set(sub.get_complete_command_names()) == {
        "example_cmd_group sub_cmd",
        "ecg sub_cmd",
    }
    assert sub.equals("ecg sub_cmd")


def test_rename_group_with_sub_command_alias():
    group = CommandGroupFilter("example_cmd_group")
    sub = CommandFilter(
        "sub_cmd",
        alias={"sc"},
        parent_command_names=group.get_complete_command_names(),
    )
    group.add_sub_command_filter(sub)
    assert sub.equals("example_cmd_group sc")

    _set_filter_fragment(group, "renamed_group")

    assert set(sub.get_complete_command_names()) == {
        "renamed_group sub_cmd",
        "renamed_group sc",
    }
    assert sub.equals("renamed_group sc")
    assert not sub.equals("example_cmd_group sc")
