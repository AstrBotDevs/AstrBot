from __future__ import annotations

import re
import shlex
from collections.abc import Sequence
from typing import Any

from ..protocol.descriptors import ParamSpec


def normalize_command_invocation(text: str) -> str:
    normalized = re.sub(r"\s+", " ", str(text).strip())
    if not normalized:
        return ""
    normalized = re.sub(r"^/\s*", "", normalized)
    return normalized.strip()


def command_root_name(text: str) -> str:
    normalized = normalize_command_invocation(text)
    if not normalized:
        return ""
    return normalized.split(" ", 1)[0]


def match_command_name(text: str, command_name: str) -> str | None:
    normalized_command = normalize_command_invocation(command_name)
    if not normalized_command:
        return None
    command_tokens = [re.escape(token) for token in normalized_command.split()]
    command_pattern = r"\s+".join(command_tokens)
    pattern = rf"^\s*/?\s*{command_pattern}(?:\s+(?P<remainder>.*))?\s*$"
    match = re.match(pattern, text)
    if match is None:
        return None
    remainder = match.group("remainder")
    if remainder is None:
        return ""
    return remainder.strip()


def build_command_args(
    param_specs: Sequence[ParamSpec], remainder: str
) -> dict[str, Any]:
    if not param_specs or not remainder:
        return {}
    if len(param_specs) == 1:
        return {param_specs[0].name: remainder}
    parts = split_command_remainder(remainder)
    values: dict[str, Any] = {}
    for index, spec in enumerate(param_specs):
        if index >= len(parts):
            break
        if spec.type == "greedy_str":
            values[spec.name] = " ".join(parts[index:])
            break
        values[spec.name] = parts[index]
    return values


def build_regex_args(
    param_specs: Sequence[ParamSpec], match: re.Match[str]
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


def split_command_remainder(remainder: str) -> list[str]:
    if not remainder:
        return []
    try:
        return shlex.split(remainder)
    except ValueError:
        return remainder.split()
