"""指令组重命名/别名向子指令传播（#9366）。"""

from types import SimpleNamespace

from astrbot.core.star.command_management import (
    _apply_config_to_runtime,
    _refresh_sub_command_names,
    _set_filter_aliases,
)
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter


def _group_with_child() -> tuple[CommandGroupFilter, CommandFilter]:
    group = CommandGroupFilter("example_cmd_group")
    child = CommandFilter("sub_cmd", parent_command_names=["example_cmd_group"])
    group.add_sub_command_filter(child)
    return group, child


def test_refresh_updates_child_parent_names_and_cache():
    group, child = _group_with_child()
    assert child.get_complete_command_names() == ["example_cmd_group sub_cmd"]
    group.group_name = "/example_cmd_group"

    _refresh_sub_command_names(group)

    assert child.parent_command_names == ["/example_cmd_group"]
    assert child._cmpl_cmd_names is None
    assert child.get_complete_command_names() == ["/example_cmd_group sub_cmd"]


def test_refresh_recurses_into_nested_groups():
    root = CommandGroupFilter("root_group")
    sub_group = CommandGroupFilter("mid_group", parent_group=root)
    leaf = CommandFilter("leaf", parent_command_names=["root_group mid_group"])
    sub_group.add_sub_command_filter(leaf)
    root.add_sub_command_filter(sub_group)

    sub_group.get_complete_command_names()
    leaf.get_complete_command_names()
    root.group_name = "/root_group"

    _refresh_sub_command_names(root)

    # the nested group's cache is rebuilt fresh from the renamed root
    assert sub_group._cmpl_cmd_names == ["/root_group mid_group"]
    assert leaf.parent_command_names == ["/root_group mid_group"]
    assert leaf.get_complete_command_names() == ["/root_group mid_group leaf"]


def test_apply_config_to_runtime_propagates_group_rename():
    group, child = _group_with_child()
    descriptor = SimpleNamespace(
        handler=SimpleNamespace(enabled=True),
        filter_ref=group,
        current_fragment="/example_cmd_group",
    )
    config = SimpleNamespace(
        enabled=True, resolved_command="/example_cmd_group", extra_data={}
    )

    _apply_config_to_runtime(descriptor, config)

    assert group.group_name == "/example_cmd_group"
    assert child.parent_command_names == ["/example_cmd_group"]
    assert child.get_complete_command_names() == ["/example_cmd_group sub_cmd"]


def test_apply_config_to_runtime_propagates_group_aliases():
    group, child = _group_with_child()
    _set_filter_aliases(group, ["eg"])

    _refresh_sub_command_names(group)

    assert child.parent_command_names == ["example_cmd_group", "eg"]
    assert child.get_complete_command_names() == [
        "example_cmd_group sub_cmd",
        "eg sub_cmd",
    ]
