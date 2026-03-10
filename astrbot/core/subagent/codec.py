from __future__ import annotations

from typing import Any, Literal, cast

from .constants import (
    DEFAULT_AGENT_MAX_STEPS,
    DEFAULT_BASE_DELAY_MS,
    DEFAULT_BATCH_SIZE,
    DEFAULT_ERROR_RETRY_MAX_INTERVAL,
    DEFAULT_FATAL_EXCEPTION_NAMES,
    DEFAULT_JITTER_RATIO,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_MAX_CONCURRENT_TASKS,
    DEFAULT_MAX_DELAY_MS,
    DEFAULT_MAX_NESTED_HANDOFF_DEPTH,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_TRANSIENT_EXCEPTION_NAMES,
)
from .models import (
    SubagentAgentSpec,
    SubagentConfig,
    SubagentErrorClassifierConfig,
    SubagentExecutionConfig,
    SubagentRuntimeConfig,
    SubagentWorkerConfig,
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
    "runtime",
    "worker",
    "execution",
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


def _parse_bool(value: Any, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise ValueError(f"`{field_name}` must be a boolean value")


def _validate_no_unknown_keys(data: dict[str, Any], allowed: set[str]) -> None:
    unknown = [k for k in data.keys() if k not in allowed and not k.startswith("x-")]
    if unknown:
        keys = ", ".join(sorted(unknown))
        raise ValueError(f"Unknown subagent config fields: {keys}")


def _parse_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"`{field_name}` must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"`{field_name}` must be an integer") from exc


def _parse_float(value: Any, *, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"`{field_name}` must be a number")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"`{field_name}` must be a number") from exc


def _parse_optional_int(value: Any, *, field_name: str) -> int | None:
    if value is None or value == "":
        return None
    return _parse_int(value, field_name=field_name)


def _parse_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _parse_agent_max_steps(value: Any) -> int | None:
    if value is None or value == "":
        return None
    parsed = _parse_int(value, field_name="agents[].max_steps")
    return parsed if parsed > 0 else None


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

    if "main_enable" in raw:
        main_enable = _parse_bool(raw["main_enable"], field_name="main_enable")
    elif "enable" in raw:
        main_enable = _parse_bool(raw["enable"], field_name="enable")
        compat_warnings.append(
            "legacy field `enable` is accepted and mapped to `main_enable`."
        )
    else:
        main_enable = False

    agents_raw = raw.get("agents", [])
    if agents_raw is None:
        agents_raw = []
    if not isinstance(agents_raw, list):
        raise ValueError("`agents` must be a list")

    agents: list[SubagentAgentSpec] = []
    for idx, item in enumerate(agents_raw):
        if not isinstance(item, dict):
            raise ValueError(f"`agents[{idx}]` must be an object")

        try:
            _validate_no_unknown_keys(item, _AGENT_KEYS)
            scope = _infer_tools_scope(item)
            if "enabled" in item:
                enabled = _parse_bool(
                    item["enabled"], field_name=f"agents[{idx}].enabled"
                )
            elif "enable" in item:
                enabled = _parse_bool(
                    item["enable"], field_name=f"agents[{idx}].enable"
                )
            else:
                enabled = True
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

            spec = SubagentAgentSpec(
                name=str(item.get("name", "")).strip(),
                enabled=enabled,
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
                    _parse_agent_max_steps(item.get("max_steps"))
                    if "max_steps" in item
                    else DEFAULT_AGENT_MAX_STEPS
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
        fatal_exceptions_raw = DEFAULT_FATAL_EXCEPTION_NAMES
    if transient_exceptions_raw is None:
        transient_exceptions_raw = DEFAULT_TRANSIENT_EXCEPTION_NAMES
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

    runtime_raw = raw.get("runtime", {})
    if runtime_raw is None:
        runtime_raw = {}
    if not isinstance(runtime_raw, dict):
        raise ValueError("`runtime` must be an object")
    runtime = SubagentRuntimeConfig(
        max_attempts=_parse_int(
            runtime_raw.get("max_attempts", DEFAULT_MAX_ATTEMPTS),
            field_name="runtime.max_attempts",
        ),
        base_delay_ms=_parse_int(
            runtime_raw.get("base_delay_ms", DEFAULT_BASE_DELAY_MS),
            field_name="runtime.base_delay_ms",
        ),
        max_delay_ms=_parse_int(
            runtime_raw.get("max_delay_ms", DEFAULT_MAX_DELAY_MS),
            field_name="runtime.max_delay_ms",
        ),
        jitter_ratio=_parse_float(
            runtime_raw.get("jitter_ratio", DEFAULT_JITTER_RATIO),
            field_name="runtime.jitter_ratio",
        ),
    )

    worker_raw = raw.get("worker", {})
    if worker_raw is None:
        worker_raw = {}
    if not isinstance(worker_raw, dict):
        raise ValueError("`worker` must be an object")
    worker = SubagentWorkerConfig(
        poll_interval=_parse_float(
            worker_raw.get("poll_interval", DEFAULT_POLL_INTERVAL),
            field_name="worker.poll_interval",
        ),
        batch_size=_parse_int(
            worker_raw.get("batch_size", DEFAULT_BATCH_SIZE),
            field_name="worker.batch_size",
        ),
        error_retry_max_interval=_parse_float(
            worker_raw.get(
                "error_retry_max_interval",
                DEFAULT_ERROR_RETRY_MAX_INTERVAL,
            ),
            field_name="worker.error_retry_max_interval",
        ),
    )

    execution_raw = raw.get("execution", {})
    if execution_raw is None:
        execution_raw = {}
    if not isinstance(execution_raw, dict):
        raise ValueError("`execution` must be an object")
    streaming_response_raw = execution_raw.get("streaming_response")
    execution = SubagentExecutionConfig(
        computer_use_runtime=_parse_optional_str(
            execution_raw.get("computer_use_runtime")
        ),
        default_max_steps=_parse_optional_int(
            execution_raw.get("default_max_steps"),
            field_name="execution.default_max_steps",
        ),
        streaming_response=(
            _parse_bool(
                streaming_response_raw,
                field_name="execution.streaming_response",
            )
            if streaming_response_raw is not None
            else None
        ),
        tool_call_timeout=_parse_optional_int(
            execution_raw.get("tool_call_timeout"),
            field_name="execution.tool_call_timeout",
        ),
    )

    extensions = {k: v for k, v in raw.items() if k.startswith("x-")}
    config = SubagentConfig(
        main_enable=main_enable,
        remove_main_duplicate_tools=(
            _parse_bool(
                raw["remove_main_duplicate_tools"],
                field_name="remove_main_duplicate_tools",
            )
            if "remove_main_duplicate_tools" in raw
            else False
        ),
        router_system_prompt=str(raw.get("router_system_prompt", "")).strip(),
        agents=agents,
        max_concurrent_subagent_runs=_parse_int(
            raw.get("max_concurrent_subagent_runs", DEFAULT_MAX_CONCURRENT_TASKS),
            field_name="max_concurrent_subagent_runs",
        ),
        max_nested_depth=_parse_int(
            raw.get("max_nested_depth", DEFAULT_MAX_NESTED_HANDOFF_DEPTH),
            field_name="max_nested_depth",
        ),
        error_classifier=error_classifier,
        runtime=runtime,
        worker=worker,
        execution=execution,
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
        "runtime": {
            "max_attempts": int(config.runtime.max_attempts),
            "base_delay_ms": int(config.runtime.base_delay_ms),
            "max_delay_ms": int(config.runtime.max_delay_ms),
            "jitter_ratio": float(config.runtime.jitter_ratio),
        },
        "worker": {
            "poll_interval": float(config.worker.poll_interval),
            "batch_size": int(config.worker.batch_size),
            "error_retry_max_interval": float(config.worker.error_retry_max_interval),
        },
        "execution": {
            "computer_use_runtime": config.execution.computer_use_runtime,
            "default_max_steps": config.execution.default_max_steps,
            "streaming_response": config.execution.streaming_response,
            "tool_call_timeout": config.execution.tool_call_timeout,
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
            # TRANSITIONAL: `system_prompt` is a deprecated mirror of
            # `instructions`.  Both are emitted during the transition period
            # so older dashboard versions and plugins continue to work.
            # Remove `system_prompt` once all consumers migrate to
            # `instructions`.
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
