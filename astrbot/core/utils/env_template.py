import os
import re
from collections.abc import Mapping

_ENV_PLACEHOLDER_RE = re.compile(
    r"\$(?:\{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)(?::-(?P<default>[^}]*))?\}|(?P<plain>[A-Za-z_][A-Za-z0-9_]*))",
)


def expand_env_placeholders(
    value: str,
    *,
    env: Mapping[str, str] | None = None,
    overrides: Mapping[str, str] | None = None,
    field_name: str = "value",
    strict: bool = False,
) -> str:
    env_map = env or os.environ
    override_map = overrides or {}
    missing_vars: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        var_name = match.group("braced") or match.group("plain")
        default = match.group("default")

        if var_name in override_map:
            override_value = override_map[var_name]
            if override_value != "" or default is None:
                return override_value

        env_value = env_map.get(var_name)
        if env_value is not None and (env_value != "" or default is None):
            return env_value

        if default is not None:
            return default

        if strict:
            missing_vars.append(var_name)
            return match.group(0)

        return ""

    expanded = _ENV_PLACEHOLDER_RE.sub(_replace, value)
    if missing_vars:
        missing = ", ".join(sorted(set(missing_vars)))
        raise ValueError(
            f"Unresolved environment variable(s) in {field_name}: {missing}",
        )
    return expanded
