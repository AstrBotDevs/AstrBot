"""SDK-native command group helpers.

本模块提供命令分组工具，用于组织具有层级关系的命令。

CommandGroup 允许以嵌套方式定义命令树，例如：
  admin
    ├── user
    │     ├── add
    │     └── remove
    └── config
          ├── get
          └── set

特性：
- 支持命令别名，自动展开父级路径的所有别名组合
- 自动生成命令树的可视化输出 (print_cmd_tree)
- 与 @on_command 装饰器无缝集成
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product

from .decorators import on_command, set_command_route_meta
from .protocol.descriptors import CommandRouteSpec


@dataclass(slots=True)
class _CommandNode:
    name: str
    aliases: list[str] = field(default_factory=list)
    description: str | None = None
    subgroups: list[CommandGroup] = field(default_factory=list)
    commands: list[tuple[str, str | None]] = field(default_factory=list)


class CommandGroup:
    def __init__(
        self,
        name: str,
        *,
        aliases: list[str] | None = None,
        description: str | None = None,
        parent: CommandGroup | None = None,
    ) -> None:
        self.name = name
        self.aliases = list(aliases or [])
        self.description = description
        self.parent = parent
        self._tree = _CommandNode(
            name=name, aliases=self.aliases, description=description
        )

    def group(
        self,
        name: str,
        *,
        aliases: list[str] | None = None,
        description: str | None = None,
    ) -> CommandGroup:
        child = CommandGroup(
            name,
            aliases=aliases,
            description=description,
            parent=self,
        )
        self._tree.subgroups.append(child)
        return child

    def command(
        self,
        name: str,
        *,
        aliases: list[str] | None = None,
        description: str | None = None,
    ):
        full_command = " ".join([*self.path, name])
        full_aliases = self._expand_aliases(name=name, aliases=aliases or [])
        display_command = full_command
        route = CommandRouteSpec(
            group_path=self.path,
            display_command=display_command,
            group_help=self.description,
        )

        def decorator(func):
            decorated = on_command(
                full_command,
                aliases=full_aliases,
                description=description,
            )(func)
            self._tree.commands.append((name, description))
            set_command_route_meta(decorated, route)
            return decorated

        return decorator

    @property
    def path(self) -> list[str]:
        if self.parent is None:
            return [self.name]
        return [*self.parent.path, self.name]

    def print_cmd_tree(self) -> str:
        lines: list[str] = []
        self._append_tree_lines(lines, indent=0)
        return "\n".join(lines)

    def _append_tree_lines(self, lines: list[str], *, indent: int) -> None:
        prefix = "  " * indent
        label = self.name
        if self.aliases:
            label += f" ({', '.join(self.aliases)})"
        lines.append(f"{prefix}{label}")
        for command_name, description in self._tree.commands:
            command_label = f"{prefix}  - {command_name}"
            if description:
                command_label += f": {description}"
            lines.append(command_label)
        for subgroup in self._tree.subgroups:
            subgroup._append_tree_lines(lines, indent=indent + 1)

    def _expand_aliases(self, *, name: str, aliases: list[str]) -> list[str]:
        group_segments: list[list[str]] = []
        cursor: CommandGroup | None = self
        ancestry: list[CommandGroup] = []
        while cursor is not None:
            ancestry.append(cursor)
            cursor = cursor.parent
        for group in reversed(ancestry):
            group_segments.append([group.name, *group.aliases])
        leaf_segments = [name, *aliases]
        expanded: set[str] = set()
        for parts in product(*group_segments, leaf_segments):
            route = " ".join(parts)
            if route != " ".join([*self.path, name]):
                expanded.add(route)
        return sorted(expanded)


def command_group(
    name: str,
    *,
    aliases: list[str] | None = None,
    description: str | None = None,
) -> CommandGroup:
    return CommandGroup(
        name,
        aliases=aliases,
        description=description,
    )


def print_cmd_tree(group: CommandGroup) -> str:
    return group.print_cmd_tree()


__all__ = ["CommandGroup", "command_group", "print_cmd_tree"]
