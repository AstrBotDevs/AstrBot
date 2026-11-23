from __future__ import annotations

from typing import Any

from astrbot.core import logger
from astrbot.core.skills.skill_manager import SkillManager
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.filter.permission import PermissionTypeFilter
from astrbot.core.star.filter.regex import RegexFilter
from astrbot.core.star.star import StarMetadata
from astrbot.core.star.star_handler import EventType, star_handlers_registry


class PluginComponentMixin:
    """Build plugin metadata shared by modern and compatibility entry points."""

    translated_event_type: dict[EventType, str]

    def _build_command_filter_component(
        self,
        command_filter: CommandFilter,
        fallback_desc: str = "",
    ) -> dict:
        raise NotImplementedError

    def _build_command_group_child(
        self,
        command_filter: CommandFilter | CommandGroupFilter,
    ) -> dict:
        raise NotImplementedError

    async def get_plugin_handler_components(
        self,
        handler_full_names: list[str],
    ) -> list[dict]:
        components = []

        for handler_full_name in handler_full_names:
            info = {}
            handler = star_handlers_registry.star_handlers_map.get(
                handler_full_name,
                None,
            )
            if handler is None:
                continue
            info["event_type"] = handler.event_type.name
            info["event_type_h"] = self.translated_event_type.get(
                handler.event_type,
                handler.event_type.name,
            )
            info["handler_full_name"] = handler.handler_full_name
            info["description"] = handler.desc or "无描述"
            info["handler_name"] = handler.handler_name

            component_type = "hook"
            component: dict[str, Any] | None = None
            if handler.event_type == EventType.AdapterMessageEvent:
                has_admin = False
                for event_filter in handler.event_filters:
                    if isinstance(event_filter, CommandFilter):
                        component_type = "command"
                        info["display_type"] = "指令"
                        info["cmd"] = self._get_command_filter_display_name(
                            event_filter
                        )
                        component = self._build_command_filter_component(
                            event_filter,
                            handler.desc,
                        )
                    elif isinstance(event_filter, CommandGroupFilter):
                        component_type = "command"
                        info["display_type"] = "指令组"
                        info["cmd"] = event_filter.get_complete_command_names()[
                            0
                        ].strip()
                        component = self._build_command_group_component(
                            event_filter,
                            handler.desc,
                        )
                    elif isinstance(event_filter, RegexFilter):
                        component_type = "command"
                        info["display_type"] = "正则匹配"
                        info["cmd"] = event_filter.regex_str
                        component = {
                            "type": "command",
                            "name": event_filter.regex_str,
                            "description": handler.desc or "无描述",
                            "match": "regex",
                        }
                    elif isinstance(event_filter, PermissionTypeFilter):
                        has_admin = True
                info["has_admin"] = has_admin
                if "cmd" not in info:
                    info["cmd"] = "未知"
                if "display_type" not in info:
                    info["display_type"] = "事件监听器"
                    component_type = "listener"
            else:
                info["cmd"] = "自动触发"
                info["display_type"] = "无"
                if handler.event_type == EventType.OnCallingFuncToolEvent:
                    component_type = "llm_tool"

            if component is None:
                component = {
                    "type": component_type,
                    "name": handler.handler_name or handler.event_type.name,
                    "description": handler.desc or "无描述",
                }
            else:
                component["type"] = component_type

            if component_type == "command":
                component["event_type"] = info["event_type"]
                component["event_type_h"] = info["event_type_h"]
                component["handler_name"] = info["handler_name"]
                component["has_admin"] = info.get("has_admin", False)
                if "display_type" in info:
                    component["display_type"] = info["display_type"]
                if "cmd" in info:
                    component["command"] = info["cmd"]
            else:
                component.update(info)
            components.append(component)

        return self._merge_command_components(components)

    def get_plugin_skill_components(self, plugin: StarMetadata) -> list[dict]:
        plugin_names = {
            str(name)
            for name in (plugin.root_dir_name, plugin.name)
            if str(name or "").strip()
        }
        if not plugin_names:
            return []

        try:
            skills = SkillManager().list_skills(
                active_only=False,
                runtime="local",
                show_sandbox_path=False,
            )
        except Exception as exc:
            logger.warning(f"Failed to get skills for plugin {plugin.name}: {exc!s}")
            return []

        components = []
        for skill in skills:
            if skill.source_type != "plugin" or skill.plugin_name not in plugin_names:
                continue
            components.append(
                {
                    "type": "skill",
                    "name": skill.name,
                    "description": skill.description or "无描述",
                    "path": skill.path,
                }
            )
        return components

    @staticmethod
    def _get_command_filter_display_name(command_filter: CommandFilter) -> str:
        return command_filter.get_complete_command_names()[0].strip()

    @staticmethod
    def _get_command_description(
        command_filter: CommandFilter | CommandGroupFilter,
        fallback: str = "",
    ) -> str:
        handler_md = getattr(command_filter, "handler_md", None)
        desc = getattr(handler_md, "desc", "") if handler_md else ""
        return desc or fallback or "无描述"

    def _build_command_group_component(
        self,
        command_group_filter: CommandGroupFilter,
        fallback_desc: str = "",
    ) -> dict:
        parts = command_group_filter.get_complete_command_names()[0].strip().split()
        if not parts:
            parts = [command_group_filter.group_name]
        subcommands = [
            self._build_command_group_child(sub_filter)
            for sub_filter in command_group_filter.sub_command_filters
        ]
        component: dict[str, Any] = {
            "type": "command",
            "name": parts[-1],
            "description": self._get_command_description(
                command_group_filter,
                fallback_desc,
            ),
        }
        if subcommands:
            component["subcommands"] = subcommands
        return self._wrap_command_component(parts[:-1], component)

    @staticmethod
    def _wrap_command_component(parent_names: list[str], component: dict) -> dict:
        for parent_name in reversed(parent_names):
            component = {
                "type": "command",
                "name": parent_name,
                "description": "无描述",
                "subcommands": [component],
            }
        return component

    def _merge_command_components(self, components: list[dict]) -> list[dict]:
        merged: list[dict] = []
        for component in components:
            if component.get("type") != "command":
                merged.append(component)
                continue
            existing = next(
                (
                    item
                    for item in merged
                    if item.get("type") == "command"
                    and item.get("name") == component.get("name")
                    and item.get("match") == component.get("match")
                ),
                None,
            )
            if existing is None:
                merged.append(component)
                continue
            self._merge_command_component(existing, component)
        return merged

    def _merge_command_component(self, target: dict, source: dict) -> None:
        if target.get("description") == "无描述" and source.get("description"):
            target["description"] = source["description"]
        for key, value in source.items():
            if key in {"subcommands", "description"}:
                continue
            target.setdefault(key, value)

        source_subcommands = source.get("subcommands")
        if not isinstance(source_subcommands, list):
            return
        target_subcommands = target.setdefault("subcommands", [])
        for source_subcommand in source_subcommands:
            if not isinstance(source_subcommand, dict):
                continue
            existing = next(
                (
                    item
                    for item in target_subcommands
                    if isinstance(item, dict)
                    and item.get("name") == source_subcommand.get("name")
                ),
                None,
            )
            if existing is None:
                target_subcommands.append(source_subcommand)
                continue
            self._merge_command_component(existing, source_subcommand)
