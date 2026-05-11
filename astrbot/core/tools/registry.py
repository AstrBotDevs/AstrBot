from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from typing import Any, TypeVar

from astrbot.core.agent.tool import FunctionTool

TFunctionTool = TypeVar("TFunctionTool", bound=type[FunctionTool])

_BUILTIN_TOOL_MODULES = (
    "astrbot.core.tools.computer_tools",
    "astrbot.core.tools.cron_tools",
    "astrbot.core.tools.knowledge_base_tools",
    "astrbot.core.tools.message_tools",
    "astrbot.core.tools.web_search_tools",
)

_builtin_tool_classes_by_name: dict[str, type[FunctionTool]] = {}
_builtin_tool_names_by_class: dict[type[FunctionTool], str] = {}
_builtin_tools_loaded = False
_MISSING = object()


@dataclass(frozen=True)
class BuiltinToolConfigCondition:
    key: str
    operator: str
    expected: Any = None
    message: str | None = None

    def evaluate(self, config: dict[str, Any]) -> dict[str, Any]:
        actual = _get_config_value(config, self.key)

        if self.operator == "equals":
            matched = actual == self.expected
        elif self.operator == "in":
            expected_values = tuple(self.expected or ())
            matched = actual in expected_values
        elif self.operator == "truthy":
            matched = bool(actual)
        elif self.operator == "custom":
            matched = bool(self.expected)
        else:
            raise ValueError(
                f"Unsupported builtin tool config operator: {self.operator}"
            )

        return {
            "key": self.key,
            "operator": self.operator,
            "expected": _json_safe(self.expected),
            "actual": _json_safe(None if actual is _MISSING else actual),
            "matched": matched,
            "message": self.message,
        }


@dataclass(frozen=True)
class BuiltinToolConfigRule:
    conditions: tuple[BuiltinToolConfigCondition, ...] = ()
    evaluator: Callable[[dict[str, Any]], list[dict[str, Any]]] | None = None

    def evaluate(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        if self.evaluator is not None:
            return self.evaluator(config)
        return [condition.evaluate(config) for condition in self.conditions]


def _get_config_value(config: dict[str, Any], key_path: str) -> Any:
    current: Any = config
    for segment in key_path.split("."):
        if not isinstance(current, dict) or segment not in current:
            return _MISSING
        current = current[segment]
    return current


def _json_safe(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(val) for key, val in value.items()}
    return value


def _equals(key: str, expected: Any) -> BuiltinToolConfigCondition:
    return BuiltinToolConfigCondition(key=key, operator="equals", expected=expected)


def _in(key: str, expected: tuple[Any, ...]) -> BuiltinToolConfigCondition:
    return BuiltinToolConfigCondition(key=key, operator="in", expected=expected)


def _custom_condition(key: str, *, matched: bool, message: str) -> dict[str, Any]:
    return {
        "key": key,
        "operator": "custom",
        "expected": None,
        "actual": None,
        "matched": matched,
        "message": message,
    }


def _build_rule_from_config_map(
    config_map: dict[str, Any],
) -> BuiltinToolConfigRule:
    conditions: list[BuiltinToolConfigCondition] = []
    for key, expected in config_map.items():
        if isinstance(expected, tuple):
            conditions.append(_in(key, expected))
        else:
            conditions.append(_equals(key, expected))
    return BuiltinToolConfigRule(conditions=tuple(conditions))


def _evaluate_send_message_tool(config: dict[str, Any]) -> list[dict[str, Any]]:
    platform_configs = config.get("platform", [])
    if not isinstance(platform_configs, list):
        return [
            _custom_condition(
                "platform",
                matched=False,
                message="No enabled platform in this config supports proactive messaging.",
            )
        ]

    for platform_cfg in platform_configs:
        if not isinstance(platform_cfg, dict):
            continue
        if platform_cfg.get("enable", False) is False:
            continue

        platform_type = str(platform_cfg.get("type", "")).strip()
        platform_id = str(platform_cfg.get("id", "")).strip() or platform_type
        if not platform_type:
            continue

        if platform_type in {"wecom", "weixin_official_account"}:
            continue

        if platform_type == "wecom_ai_bot":
            webhook = str(platform_cfg.get("msg_push_webhook_url", "")).strip()
            if not webhook:
                continue
            return [
                _custom_condition(
                    "platform[].type",
                    matched=True,
                    message=(
                        f"Enabled platform `{platform_id}` uses `wecom_ai_bot`, which supports proactive messaging "
                        "when `platform[].msg_push_webhook_url` is configured."
                    ),
                ),
                BuiltinToolConfigCondition(
                    key="platform[].msg_push_webhook_url",
                    operator="truthy",
                ).evaluate({"platform[]": {"msg_push_webhook_url": webhook}}),
            ]

        return [
            _custom_condition(
                "platform[].type",
                matched=True,
                message=(
                    f"Enabled platform `{platform_id}` (`{platform_type}`) supports proactive messaging."
                ),
            )
        ]

    return [
        _custom_condition(
            "platform",
            matched=False,
            message="No enabled platform in this config supports proactive messaging.",
        )
    ]


_BUILTIN_TOOL_CONFIG_RULES: dict[str, BuiltinToolConfigRule] = {}


def _register_builtin_tool_config_rule(
    tool_names: tuple[str, ...],
    rule: BuiltinToolConfigRule,
) -> None:
    for tool_name in tool_names:
        _BUILTIN_TOOL_CONFIG_RULES[tool_name] = rule


_register_builtin_tool_config_rule(
    ("send_message_to_user",),
    BuiltinToolConfigRule(evaluator=_evaluate_send_message_tool),
)


def _resolve_builtin_tool_name(tool_cls: type[FunctionTool]) -> str:
    tool_name = getattr(tool_cls, "name", None)
    if isinstance(tool_name, str) and tool_name:
        return tool_name

    dataclass_fields = getattr(tool_cls, "__dataclass_fields__", {})
    name_field = dataclass_fields.get("name")
    if name_field is not None and isinstance(name_field.default, str):
        return name_field.default

    raise ValueError(
        f"Builtin tool class {tool_cls.__module__}.{tool_cls.__name__} does not define a valid name.",
    )


def builtin_tool(
    tool_cls: TFunctionTool | None = None,
    *,
    config: dict[str, Any] | None = None,
) -> TFunctionTool | Callable[[TFunctionTool], TFunctionTool]:
    def _register(cls: TFunctionTool) -> TFunctionTool:
        tool_name = _resolve_builtin_tool_name(cls)
        existing = _builtin_tool_classes_by_name.get(tool_name)
        if existing is not None and existing is not cls:
            raise ValueError(
                f"Builtin tool name conflict detected: {tool_name} is already registered by "
                f"{existing.__module__}.{existing.__name__}.",
            )

        _builtin_tool_classes_by_name[tool_name] = cls
        _builtin_tool_names_by_class[cls] = tool_name
        if config is not None:
            _BUILTIN_TOOL_CONFIG_RULES[tool_name] = _build_rule_from_config_map(config)
        return cls

    if tool_cls is None:
        return _register
    return _register(tool_cls)


def ensure_builtin_tools_loaded() -> None:
    global _builtin_tools_loaded
    if _builtin_tools_loaded:
        return

    for module_name in _BUILTIN_TOOL_MODULES:
        import_module(module_name)

    _builtin_tools_loaded = True


def get_builtin_tool_class(name: str) -> type[FunctionTool] | None:
    ensure_builtin_tools_loaded()
    return _builtin_tool_classes_by_name.get(name)


def get_builtin_tool_name(tool_cls: type[FunctionTool]) -> str | None:
    ensure_builtin_tools_loaded()
    return _builtin_tool_names_by_class.get(tool_cls)


def iter_builtin_tool_classes() -> tuple[type[FunctionTool], ...]:
    ensure_builtin_tools_loaded()
    return tuple(_builtin_tool_classes_by_name.values())


def get_builtin_tool_config_rule(name: str) -> BuiltinToolConfigRule | None:
    ensure_builtin_tools_loaded()
    return _BUILTIN_TOOL_CONFIG_RULES.get(name)


def get_builtin_tool_config_statuses(
    tool_name: str,
    config_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rule = get_builtin_tool_config_rule(tool_name)
    if rule is None:
        return []

    statuses: list[dict[str, Any]] = []
    for entry in config_entries:
        config = entry.get("config")
        if not isinstance(config, dict):
            continue

        conditions = rule.evaluate(config)
        enabled = bool(conditions) and all(
            bool(condition.get("matched")) for condition in conditions
        )
        statuses.append(
            {
                "conf_id": entry.get("conf_id"),
                "conf_name": entry.get("conf_name"),
                "enabled": enabled,
                "matched_conditions": [
                    condition for condition in conditions if condition.get("matched")
                ],
                "failed_conditions": [
                    condition
                    for condition in conditions
                    if not condition.get("matched")
                ],
            }
        )
    return statuses


def get_builtin_tool_config_tags(
    tool_name: str,
    config_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        status
        for status in get_builtin_tool_config_statuses(tool_name, config_entries)
        if status["enabled"]
    ]


__all__ = [
    "builtin_tool",
    "ensure_builtin_tools_loaded",
    "get_builtin_tool_config_rule",
    "get_builtin_tool_config_statuses",
    "get_builtin_tool_config_tags",
    "get_builtin_tool_class",
    "get_builtin_tool_name",
    "iter_builtin_tool_classes",
]
