from __future__ import annotations

import inspect
import shlex
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from ._typing_utils import unwrap_optional
from .errors import AstrBotError

COMMAND_MODEL_DOCS_URL = "https://docs.astrbot.org/sdk/parameter-injection"


@dataclass(slots=True)
class ResolvedCommandModelParam:
    name: str
    model_cls: type[BaseModel]


@dataclass(slots=True)
class CommandModelParseResult:
    model: BaseModel | None = None
    help_text: str | None = None


def resolve_command_model_param(handler: Any) -> ResolvedCommandModelParam | None:
    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError):
        return None
    try:
        type_hints = inspect.get_annotations(handler, eval_str=True)
    except Exception:
        type_hints = {}

    candidates: list[ResolvedCommandModelParam] = []
    other_names: list[str] = []
    for parameter in signature.parameters.values():
        if parameter.kind not in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            continue
        annotation = type_hints.get(parameter.name)
        if _is_injected_parameter(parameter.name, annotation):
            continue
        normalized, _is_optional = unwrap_optional(annotation)
        if isinstance(normalized, type) and issubclass(normalized, BaseModel):
            candidates.append(
                ResolvedCommandModelParam(
                    name=parameter.name,
                    model_cls=normalized,
                )
            )
            continue
        other_names.append(parameter.name)

    if not candidates:
        return None
    if len(candidates) > 1 or other_names:
        names = [item.name for item in candidates]
        raise ValueError(
            "Command BaseModel injection requires exactly one non-injected BaseModel "
            f"parameter, got models={names!r} others={other_names!r}"
        )
    _validate_supported_model(candidates[0].model_cls)
    return candidates[0]


def parse_command_model_remainder(
    *,
    remainder: str,
    model_param: ResolvedCommandModelParam,
    command_name: str,
) -> CommandModelParseResult:
    tokens = _split_command_remainder(remainder)
    if any(token in {"-h", "--help"} for token in tokens):
        return CommandModelParseResult(
            help_text=format_command_model_help(command_name, model_param.model_cls)
        )

    fields = model_param.model_cls.model_fields
    explicit_values: dict[str, Any] = {}
    positional_values: dict[str, Any] = {}
    positional_field_names = [
        name
        for name, field in fields.items()
        if _supported_scalar_type(field.annotation)[0] is not bool
    ]
    positional_index = 0
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not token.startswith("--"):
            assigned = False
            while positional_index < len(positional_field_names):
                field_name = positional_field_names[positional_index]
                positional_index += 1
                if field_name in explicit_values or field_name in positional_values:
                    continue
                positional_values[field_name] = token
                assigned = True
                break
            if not assigned:
                raise _command_parse_error("Too many positional arguments")
            index += 1
            continue

        raw_name = token[2:]
        if not raw_name:
            raise _command_parse_error("Invalid option '--'")
        explicit_value: str | None = None
        if "=" in raw_name:
            raw_name, explicit_value = raw_name.split("=", 1)
        negated = raw_name.startswith("no-")
        field_name = raw_name[3:] if negated else raw_name
        field = fields.get(field_name)
        if field is None:
            raise _command_parse_error(f"Unknown field: {field_name}")
        if field_name in explicit_values:
            raise _command_parse_error(f"Duplicate field: {field_name}")
        field_type, _is_optional = _supported_scalar_type(field.annotation)
        if field_type is bool:
            if explicit_value is not None:
                raise _command_parse_error(
                    f"Boolean field '{field_name}' only supports --{field_name} or --no-{field_name}"
                )
            explicit_values[field_name] = not negated
            index += 1
            continue
        if negated:
            raise _command_parse_error(
                f"Non-boolean field '{field_name}' does not support --no-{field_name}"
            )
        if explicit_value is None:
            index += 1
            if index >= len(tokens):
                raise _command_parse_error(f"Missing value for field: {field_name}")
            explicit_value = tokens[index]
        explicit_values[field_name] = explicit_value
        index += 1

    values = {**positional_values, **explicit_values}

    try:
        model = model_param.model_cls.model_validate(values)
    except Exception as exc:
        raise AstrBotError.invalid_input(
            "命令参数解析失败",
            hint=str(exc),
            docs_url=COMMAND_MODEL_DOCS_URL,
            details={
                "command": command_name,
                "parameter": model_param.name,
                "values": values,
            },
        ) from exc
    return CommandModelParseResult(model=model)


def format_command_model_help(command_name: str, model_cls: type[BaseModel]) -> str:
    _validate_supported_model(model_cls)
    lines = [f"用法: /{command_name} [options]"]
    if model_cls.model_fields:
        lines.append("参数:")
    for name, field in model_cls.model_fields.items():
        field_type, is_optional = _supported_scalar_type(field.annotation)
        type_name = getattr(field_type, "__name__", str(field_type))
        required = field.is_required()
        default_text = ""
        if not required:
            default_text = f"，默认 {field.default!r}"
        elif is_optional:
            default_text = "，默认 None"
        description = str(field.description or "").strip()
        detail = f"{name}: {type_name}"
        if description:
            detail += f" - {description}"
        detail += "，必填" if required else "，可选"
        detail += default_text
        if field_type is bool:
            detail += f"，使用 --{name} / --no-{name}"
        lines.append(detail)
    return "\n".join(lines)


def _validate_supported_model(model_cls: type[BaseModel]) -> None:
    for name, field in model_cls.model_fields.items():
        try:
            _supported_scalar_type(field.annotation)
        except TypeError as exc:
            raise ValueError(
                f"Unsupported command model field '{name}': {exc}"
            ) from exc


def _supported_scalar_type(annotation: Any) -> tuple[type[Any], bool]:
    normalized, is_optional = unwrap_optional(annotation)
    if normalized in {str, int, float, bool}:
        return normalized, is_optional
    raise TypeError("only str/int/float/bool and Optional variants are supported")


def _command_parse_error(message: str) -> AstrBotError:
    return AstrBotError.invalid_input(
        message,
        docs_url=COMMAND_MODEL_DOCS_URL,
    )


def _split_command_remainder(remainder: str) -> list[str]:
    if not remainder:
        return []
    try:
        return shlex.split(remainder)
    except ValueError:
        return remainder.split()


def _is_injected_parameter(name: str, annotation: Any) -> bool:
    if name in {"event", "ctx", "context", "sched", "schedule", "conversation", "conv"}:
        return True
    normalized, _is_optional = unwrap_optional(annotation)
    if normalized is None:
        return False
    try:
        from .context import Context
        from .conversation import ConversationSession
        from .events import MessageEvent
        from .schedule import ScheduleContext
    except Exception:
        return False
    if normalized in {Context, MessageEvent, ScheduleContext, ConversationSession}:
        return True
    if isinstance(normalized, type):
        return issubclass(
            normalized,
            (Context, MessageEvent, ScheduleContext, ConversationSession),
        )
    return False


__all__ = [
    "COMMAND_MODEL_DOCS_URL",
    "CommandModelParseResult",
    "ResolvedCommandModelParam",
    "format_command_model_help",
    "parse_command_model_remainder",
    "resolve_command_model_param",
]
