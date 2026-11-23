"""Resolve dashboard values shared by serving and authentication."""

import os
import re
from collections.abc import Mapping


def expand_env_placeholders(value: str, field_name: str) -> str:
    missing_vars: list[str] = []
    pattern = re.compile(
        r"\$(?:\{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)(?::-(?P<default>[^}]*))?\}|(?P<plain>[A-Za-z_][A-Za-z0-9_]*))"
    )

    def replace(match: re.Match[str]) -> str:
        var_name = match.group("braced") or match.group("plain")
        default = match.group("default")
        env_value = os.environ.get(var_name)
        if env_value is not None:
            return env_value
        if default is not None:
            return default
        missing_vars.append(var_name)
        return match.group(0)

    expanded = pattern.sub(replace, value)
    if missing_vars:
        missing = ", ".join(sorted(set(missing_vars)))
        raise ValueError(
            f"Unresolved environment variable(s) in dashboard {field_name}: {missing}"
        )
    return expanded


def resolve_dashboard_host(dashboard_config: Mapping[str, object]) -> str:
    """Return the effective bind host using the dashboard environment aliases."""
    host = (
        os.environ.get("DASHBOARD_HOST")
        or os.environ.get("ASTRBOT_DASHBOARD_HOST")
        or os.environ.get("ASTRBOT_HOST")
        or dashboard_config.get("host", "0.0.0.0")
    )
    if not isinstance(host, str):
        raise ValueError("Dashboard host must be a non-empty string")
    host = expand_env_placeholders(host, "host").strip()
    if not host:
        raise ValueError("Dashboard host must be a non-empty string")
    return host
