from __future__ import annotations

import inspect
import re
import shlex
import typing
from dataclasses import dataclass
from typing import Any, get_type_hints

from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot_sdk.events import MessageEvent as SdkMessageEvent
from astrbot_sdk.protocol.descriptors import (
    CommandTrigger,
    CompositeFilterSpec,
    HandlerDescriptor,
    LocalFilterRefSpec,
    MessageTrigger,
    MessageTypeFilterSpec,
    ParamSpec,
    PlatformFilterSpec,
)


@dataclass(slots=True)
class TriggerMatch:
    plugin_id: str
    handler_id: str
    args: dict[str, Any]
    priority: int
    load_order: int
    declaration_order: int


class TriggerConverter:
    @staticmethod
    def _message_type_name(event: AstrMessageEvent) -> str:
        explicit = str(event.get_message_type().value).lower()
        if explicit in {"group", "private", "other"}:
            return explicit
        if event.get_group_id():
            return "group"
        if event.get_sender_id():
            return "private"
        return "other"

    @staticmethod
    def _match_command_name(text: str, command_name: str) -> str | None:
        normalized = text.strip()
        if normalized == command_name:
            return ""
        if normalized.startswith(f"{command_name} "):
            return normalized[len(command_name) :].strip()
        return None

    @staticmethod
    def _split_command_remainder(remainder: str) -> list[str]:
        try:
            return shlex.split(remainder)
        except ValueError:
            return remainder.split()

    @classmethod
    def _build_command_args(cls, handler, remainder: str) -> dict[str, Any]:
        param_specs = getattr(handler, "param_specs", None)
        if not isinstance(param_specs, list):
            names = cls._legacy_arg_parameter_names(handler)
            if not names or not remainder:
                return {}
            if len(names) == 1:
                return {names[0]: remainder}
            parts = cls._split_command_remainder(remainder)
            return {
                name: parts[index]
                for index, name in enumerate(names)
                if index < len(parts)
            }
        if not param_specs or not remainder:
            return {}
        if len(param_specs) == 1:
            return {param_specs[0].name: remainder}
        parts = cls._split_command_remainder(remainder)
        args: dict[str, Any] = {}
        for index, spec in enumerate(param_specs):
            if index >= len(parts):
                break
            if spec.type == "greedy_str":
                args[spec.name] = " ".join(parts[index:])
                break
            args[spec.name] = parts[index]
        return args

    @classmethod
    def _build_regex_args(cls, handler, match: re.Match[str]) -> dict[str, Any]:
        named = {
            key: value for key, value in match.groupdict().items() if value is not None
        }
        param_specs = getattr(handler, "param_specs", None)
        if isinstance(param_specs, list):
            names = [spec.name for spec in param_specs if spec.name not in named]
        else:
            names = [
                name
                for name in cls._legacy_arg_parameter_names(handler)
                if name not in named
            ]
        positional = [value for value in match.groups() if value is not None]
        for index, value in enumerate(positional):
            if index >= len(names):
                break
            named[names[index]] = value
        return named

    @classmethod
    def _build_descriptor_command_args(
        cls,
        param_specs: list[ParamSpec],
        remainder: str,
    ) -> dict[str, Any]:
        if not param_specs or not remainder:
            return {}
        if len(param_specs) == 1:
            return {param_specs[0].name: remainder}
        parts = cls._split_command_remainder(remainder)
        args: dict[str, Any] = {}
        for index, spec in enumerate(param_specs):
            if index >= len(parts):
                break
            if spec.type == "greedy_str":
                args[spec.name] = " ".join(parts[index:])
                break
            args[spec.name] = parts[index]
        return args

    @classmethod
    def _build_descriptor_regex_args(
        cls,
        param_specs: list[ParamSpec],
        match: re.Match[str],
    ) -> dict[str, Any]:
        named = {
            key: value for key, value in match.groupdict().items() if value is not None
        }
        names = [spec.name for spec in param_specs if spec.name not in named]
        positional = [value for value in match.groups() if value is not None]
        for index, value in enumerate(positional):
            if index >= len(names):
                break
            named[names[index]] = value
        return named

    @classmethod
    def _match_filters(
        cls,
        descriptor: HandlerDescriptor,
        event: AstrMessageEvent,
    ) -> bool:
        for filter_spec in descriptor.filters:
            if not cls._match_filter_spec(filter_spec, event):
                return False
        return True

    @classmethod
    def _match_filter_spec(cls, filter_spec, event: AstrMessageEvent) -> bool:
        if isinstance(filter_spec, PlatformFilterSpec):
            return event.get_platform_name() in filter_spec.platforms
        if isinstance(filter_spec, MessageTypeFilterSpec):
            return cls._message_type_name(event) in filter_spec.message_types
        if isinstance(filter_spec, LocalFilterRefSpec):
            return True
        if isinstance(filter_spec, CompositeFilterSpec):
            results = [
                cls._match_filter_spec(child, event) for child in filter_spec.children
            ]
            if filter_spec.kind == "and":
                return all(results)
            return any(results)
        return True

    @classmethod
    def _legacy_arg_parameter_names(cls, handler) -> list[str]:
        try:
            signature = inspect.signature(handler)
        except (TypeError, ValueError):
            return []
        try:
            type_hints = get_type_hints(handler)
        except Exception:
            type_hints = {}
        names: list[str] = []
        for parameter in signature.parameters.values():
            if parameter.kind not in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            ):
                continue
            if cls._is_injected_parameter(
                parameter.name, type_hints.get(parameter.name)
            ):
                continue
            names.append(parameter.name)
        return names

    @classmethod
    def _is_injected_parameter(cls, name: str, annotation: Any) -> bool:
        if name in {"event", "ctx", "context"}:
            return True
        normalized = cls._unwrap_optional(annotation)
        if normalized is None:
            return False
        if normalized in {AstrMessageEvent, SdkMessageEvent}:
            return True
        if isinstance(normalized, type) and issubclass(
            normalized,
            (AstrMessageEvent, SdkMessageEvent),
        ):
            return True
        return False

    @staticmethod
    def _unwrap_optional(annotation: Any) -> Any:
        if annotation is None:
            return None
        origin = typing.get_origin(annotation)
        if origin is typing.Union:
            options = [
                item for item in typing.get_args(annotation) if item is not type(None)
            ]
            if len(options) == 1:
                return options[0]
        return annotation

    @classmethod
    def match_handler(
        cls,
        *,
        plugin_id: str,
        handler=None,
        descriptor: HandlerDescriptor,
        event: AstrMessageEvent,
        load_order: int,
        declaration_order: int,
    ) -> TriggerMatch | None:
        trigger = descriptor.trigger

        if descriptor.permissions.require_admin and not event.is_admin():
            return None
        if not cls._match_filters(descriptor, event):
            return None

        if isinstance(trigger, CommandTrigger):
            text = event.get_message_str().strip()
            for command_name in [trigger.command, *trigger.aliases]:
                if not command_name:
                    continue
                remainder = cls._match_command_name(text, command_name)
                if remainder is None:
                    continue
                return TriggerMatch(
                    plugin_id=plugin_id,
                    handler_id=descriptor.id,
                    args=(
                        cls._build_command_args(handler, remainder)
                        if handler is not None
                        else cls._build_descriptor_command_args(
                            descriptor.param_specs,
                            remainder,
                        )
                    ),
                    priority=descriptor.priority,
                    load_order=load_order,
                    declaration_order=declaration_order,
                )
            return None

        if isinstance(trigger, MessageTrigger):
            text = event.get_message_str()
            if trigger.regex:
                match = re.search(trigger.regex, text)
                if match is None:
                    return None
                args = (
                    cls._build_regex_args(handler, match) if handler is not None else {}
                )
                if handler is None:
                    args = cls._build_descriptor_regex_args(
                        descriptor.param_specs, match
                    )
            else:
                if trigger.keywords and not any(
                    keyword in text for keyword in trigger.keywords
                ):
                    return None
                args = {}
            return TriggerMatch(
                plugin_id=plugin_id,
                handler_id=descriptor.id,
                args=args,
                priority=descriptor.priority,
                load_order=load_order,
                declaration_order=declaration_order,
            )

        return None

    @staticmethod
    def sort_key(match: TriggerMatch) -> tuple[int, int, int]:
        return (-match.priority, match.load_order, match.declaration_order)
