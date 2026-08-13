from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, TypeVar, overload

from astrbot.core.agent.tool import FunctionTool

TFunctionTool = TypeVar("TFunctionTool", bound=type[FunctionTool])

_MISSING = object()
BUILTIN_TOOL_DECLARATION_ATTR = "__astrbot_builtin_tool_declaration__"

BUILTIN_TOOL_MODULES = (
    "astrbot.core.memory.tools.memory_tools",
    "astrbot.core.tools.computer_tools",
    "astrbot.core.tools.cron_tools",
    "astrbot.core.tools.knowledge_base_tools",
    "astrbot.core.tools.message_tools",
    "astrbot.core.tools.web_search_tools",
)


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


@dataclass(frozen=True, slots=True)
class BuiltinToolDeclaration:
    """Immutable declaration attached to one builtin tool class.

    Runtime discovery belongs to :class:`FunctionToolManager`.  The decorator
    deliberately records only class-local metadata so importing a builtin tool
    module cannot mutate process-wide runtime registrations.
    """

    name: str
    config_rule: BuiltinToolConfigRule | None = None
    required_actions: tuple[str, ...] = ("session.manage",)


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


DEFAULT_BUILTIN_TOOL_CONFIG_RULES: Mapping[str, BuiltinToolConfigRule] = (
    MappingProxyType(
        {
            "send_message_to_user": BuiltinToolConfigRule(
                evaluator=_evaluate_send_message_tool,
            ),
        }
    )
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


@overload
def builtin_tool(
    tool_cls: None = None,
    *,
    config: dict[str, Any] | None = None,
    required_actions: tuple[str, ...] = ("session.manage",),
) -> Callable[[TFunctionTool], TFunctionTool]: ...


@overload
def builtin_tool[TFunctionTool: type[FunctionTool]](
    tool_cls: TFunctionTool,
    *,
    config: dict[str, Any] | None = None,
    required_actions: tuple[str, ...] = ("session.manage",),
) -> TFunctionTool: ...


def builtin_tool[TFunctionTool: type[FunctionTool]](
    tool_cls: TFunctionTool | None = None,
    *,
    config: dict[str, Any] | None = None,
    required_actions: tuple[str, ...] = ("session.manage",),
) -> TFunctionTool | Callable[[TFunctionTool], TFunctionTool]:
    def _declare(cls: TFunctionTool) -> TFunctionTool:
        tool_name = _resolve_builtin_tool_name(cls)
        if not required_actions or not all(
            isinstance(action, str) and action for action in required_actions
        ):
            raise ValueError("Builtin tool actions must be non-empty strings.")
        declaration = BuiltinToolDeclaration(
            name=tool_name,
            config_rule=(
                _build_rule_from_config_map(config) if config is not None else None
            ),
            required_actions=required_actions,
        )
        existing = cls.__dict__.get(BUILTIN_TOOL_DECLARATION_ATTR)
        if existing is not None and existing != declaration:
            raise ValueError(
                f"Builtin tool {cls.__module__}.{cls.__name__} has conflicting declarations.",
            )
        setattr(cls, BUILTIN_TOOL_DECLARATION_ATTR, declaration)
        return cls

    if tool_cls is None:
        return _declare
    return _declare(tool_cls)


__all__ = [
    "BUILTIN_TOOL_DECLARATION_ATTR",
    "BUILTIN_TOOL_MODULES",
    "DEFAULT_BUILTIN_TOOL_CONFIG_RULES",
    "BuiltinToolConfigRule",
    "BuiltinToolDeclaration",
    "builtin_tool",
]
