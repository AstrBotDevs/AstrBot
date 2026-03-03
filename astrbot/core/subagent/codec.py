from __future__ import annotations

from typing import Any, Literal, cast

from .models import (
    SubagentAgentSpec,
    SubagentConfig,
    SubagentErrorClassifierConfig,
    ToolsScope,
)

_DEFAULT_CLASS_ALLOWED = {"fatal", "transient", "retryable"}
_DefaultClassLiteral = Literal["fatal", "transient", "retryable"]

_CONFIG_KEYS = {
    "main_enable",
    "enable",
    "remove_main_duplicate_tools",
    "router_system_prompt",
    "agents",
    "max_concurrent_subagent_runs",
    "max_nested_depth",
    "error_classifier",
    "diagnostics",
    "compat_warnings",
}
_AGENT_KEYS = {
    "name",
    "enabled",
    "enable",
    "persona_id",
    "provider_id",
    "public_description",
    "tools_scope",
    "tools",
    "instructions",
    "system_prompt",
    "max_steps",
}


def _validate_no_unknown_keys(data: dict[str, Any], allowed: set[str]) -> None:
    unknown = [k for k in data.keys() if k not in allowed and not k.startswith("x-")]
    if unknown:
        keys = ", ".join(sorted(unknown))
        raise ValueError(f"Unknown subagent config fields: {keys}")


def _infer_tools_scope(item: dict[str, Any]) -> ToolsScope:
    scope_raw = item.get("tools_scope")
    if scope_raw:
        return ToolsScope(str(scope_raw))

    tools = item.get("tools")
    persona_id = str(item.get("persona_id") or "").strip()
    if isinstance(tools, list):
        return ToolsScope.NONE if len(tools) == 0 else ToolsScope.LIST
    if tools is None and persona_id:
        return ToolsScope.PERSONA
    if tools is None:
        return ToolsScope.ALL
    raise ValueError("Invalid `tools` type, expected list or null.")


def decode_subagent_config(raw: dict[str, Any]) -> tuple[SubagentConfig, list[str]]:
    if not isinstance(raw, dict):
        raise ValueError("subagent config must be a JSON object")

    _validate_no_unknown_keys(raw, _CONFIG_KEYS)
    diagnostics: list[str] = []
    compat_warnings: list[str] = []

    main_enable = bool(raw.get("main_enable", raw.get("enable", False)))
    if "enable" in raw and "main_enable" not in raw:
        compat_warnings.append(
            "legacy field `enable` is accepted and mapped to `main_enable`."
        )

    agents_raw = raw.get("agents", [])
    if agents_raw is None:
        agents_raw = []
    if not isinstance(agents_raw, list):
        raise ValueError("`agents` must be a list")

    agents: list[SubagentAgentSpec] = []
    for idx, item in enumerate(agents_raw):
        if not isinstance(item, dict):
            raise ValueError(f"`agents[{idx}]` must be an object")
        _validate_no_unknown_keys(item, _AGENT_KEYS)

        scope = _infer_tools_scope(item)
        if "system_prompt" in item and "instructions" not in item:
            compat_warnings.append(
                f"legacy field `agents[{idx}].system_prompt` is accepted and mapped to `instructions`."
            )

        extensions = {k: v for k, v in item.items() if k.startswith("x-")}

        tools_raw = item.get("tools")
        tools: list[str] | None
        if scope == ToolsScope.LIST:
            if tools_raw is None:
                tools = []
            elif isinstance(tools_raw, list):
                tools = [str(t).strip() for t in tools_raw if str(t).strip()]
            else:
                raise ValueError(
                    f"`agents[{idx}].tools` must be a list when tools_scope=list"
                )
        else:
            tools = None

        try:
            spec = SubagentAgentSpec(
                name=str(item.get("name", "")).strip(),
                enabled=bool(item.get("enabled", item.get("enable", True))),
                persona_id=(
                    str(item.get("persona_id")).strip()
                    if item.get("persona_id") is not None
                    else None
                )
                or None,
                provider_id=(
                    str(item.get("provider_id")).strip()
                    if item.get("provider_id") is not None
                    else None
                )
                or None,
                public_description=str(item.get("public_description", "")).strip(),
                tools_scope=scope,
                tools=tools,
                instructions=str(
                    item.get("instructions", item.get("system_prompt", ""))
                ).strip(),
                max_steps=(
                    int(item["max_steps"])
                    if item.get("max_steps") is not None
                    else None
                ),
                extensions=extensions,
            )
        except Exception as exc:
            raise ValueError(f"invalid subagent at agents[{idx}]: {exc}") from exc
        agents.append(spec)

    error_classifier_raw = raw.get("error_classifier", {})
    if error_classifier_raw is None:
        error_classifier_raw = {}
    if not isinstance(error_classifier_raw, dict):
        raise ValueError("`error_classifier` must be an object")

    fatal_exceptions_raw = error_classifier_raw.get("fatal_exceptions")
    transient_exceptions_raw = error_classifier_raw.get("transient_exceptions")
    if fatal_exceptions_raw is None:
        fatal_exceptions_raw = ["ValueError", "PermissionError", "KeyError"]
    if transient_exceptions_raw is None:
        transient_exceptions_raw = [
            "asyncio.TimeoutError",
            "TimeoutError",
            "ConnectionError",
            "ConnectionResetError",
        ]
    if not isinstance(fatal_exceptions_raw, list):
        raise ValueError("`error_classifier.fatal_exceptions` must be a list")
    if not isinstance(transient_exceptions_raw, list):
        raise ValueError("`error_classifier.transient_exceptions` must be a list")

    error_classifier = SubagentErrorClassifierConfig(
        type=str(error_classifier_raw.get("type", "default")).strip() or "default",
        fatal_exceptions=[
            str(item).strip() for item in fatal_exceptions_raw if str(item).strip()
        ],
        transient_exceptions=[
            str(item).strip() for item in transient_exceptions_raw if str(item).strip()
        ],
        default_class=cast(
            _DefaultClassLiteral,
            (
                default_class
                if (
                    default_class := str(
                        error_classifier_raw.get("default_class", "transient")
                    ).strip()
                )
                in _DEFAULT_CLASS_ALLOWED
                else "transient"
            ),
        ),
    )

    extensions = {k: v for k, v in raw.items() if k.startswith("x-")}
    config = SubagentConfig(
        main_enable=main_enable,
        remove_main_duplicate_tools=bool(raw.get("remove_main_duplicate_tools", False)),
        router_system_prompt=str(raw.get("router_system_prompt", "")).strip(),
        agents=agents,
        max_concurrent_subagent_runs=int(raw.get("max_concurrent_subagent_runs", 8)),
        max_nested_depth=int(raw.get("max_nested_depth", 2)),
        error_classifier=error_classifier,
        extensions=extensions,
    )
    diagnostics.extend(compat_warnings)
    return config, diagnostics


def encode_subagent_config(
    config: SubagentConfig,
    *,
    diagnostics: list[str] | None = None,
    compat_warnings: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "main_enable": bool(config.main_enable),
        "remove_main_duplicate_tools": bool(config.remove_main_duplicate_tools),
        "router_system_prompt": config.router_system_prompt or "",
        "max_concurrent_subagent_runs": int(config.max_concurrent_subagent_runs),
        "max_nested_depth": int(config.max_nested_depth),
        "error_classifier": {
            "type": str(config.error_classifier.type or "default"),
            "fatal_exceptions": list(config.error_classifier.fatal_exceptions),
            "transient_exceptions": list(config.error_classifier.transient_exceptions),
            "default_class": str(config.error_classifier.default_class),
        },
        "agents": [],
    }
    if config.extensions:
        payload.update(config.extensions)

    for spec in config.agents:
        if spec.tools_scope == ToolsScope.LIST:
            tools = list(spec.tools or [])
        elif spec.tools_scope == ToolsScope.NONE:
            tools = []
        else:
            tools = None

        item: dict[str, Any] = {
            "name": spec.name,
            "enabled": bool(spec.enabled),
            "persona_id": spec.persona_id,
            "provider_id": spec.provider_id,
            "public_description": spec.public_description,
            "tools_scope": spec.tools_scope.value,
            "tools": tools,
            "instructions": spec.instructions,
            "system_prompt": spec.instructions,
            "max_steps": spec.max_steps,
        }
        if spec.extensions:
            item.update(spec.extensions)
        payload["agents"].append(item)

    if diagnostics:
        payload["diagnostics"] = diagnostics
    if compat_warnings:
        payload["compat_warnings"] = compat_warnings
    return payload
