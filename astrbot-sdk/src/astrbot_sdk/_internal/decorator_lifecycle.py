from __future__ import annotations

import asyncio
import inspect
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from pydantic import ValidationError

from ..context import Context as RuntimeContext
from ..decorators import (
    BackgroundTaskMeta,
    HttpApiMeta,
    MCPServerMeta,
    ValidateConfigMeta,
    get_background_task_meta,
    get_http_api_meta,
    get_mcp_server_meta,
    get_provider_change_meta,
    get_skill_meta,
    get_validate_config_meta,
)
from ..star import Star
from .star_runtime import bind_star_runtime

_RUNTIME_STATE_ATTR = "__astrbot_decorator_runtime_state__"
_VALIDATED_CONFIGS_ATTR = "__astrbot_validated_configs__"


@dataclass(slots=True)
class DecoratorRuntimeState:
    http_apis: list[tuple[str, list[str]]] = field(default_factory=list)
    provider_hooks: list[asyncio.Task[None]] = field(default_factory=list)
    background_tasks: list[asyncio.Task[Any]] = field(default_factory=list)
    registered_skills: list[str] = field(default_factory=list)
    local_mcp_servers: list[str] = field(default_factory=list)
    global_mcp_servers: list[str] = field(default_factory=list)


def _runtime_state(instance: Any) -> DecoratorRuntimeState:
    state = getattr(instance, _RUNTIME_STATE_ATTR, None)
    if isinstance(state, DecoratorRuntimeState):
        return state
    state = DecoratorRuntimeState()
    setattr(instance, _RUNTIME_STATE_ATTR, state)
    return state


def _iter_bound_methods(instance: Any):
    seen_names: set[str] = set()
    for name in dir(instance.__class__):
        if name.startswith("__") or name in seen_names:
            continue
        seen_names.add(name)
        try:
            raw_attr = inspect.getattr_static(instance, name)
        except AttributeError:
            continue
        if isinstance(raw_attr, property):
            continue
        bound = getattr(instance, name, None)
        if not callable(bound):
            continue
        raw = getattr(bound, "__func__", bound)
        yield name, bound, raw


def _validated_config_store(instance: Any) -> dict[str, Any]:
    values = getattr(instance, _VALIDATED_CONFIGS_ATTR, None)
    if isinstance(values, dict):
        return values
    values = {}
    setattr(instance, _VALIDATED_CONFIGS_ATTR, values)
    return values


def _positional_arg_count(func: Any) -> int:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return 0
    return sum(
        1
        for parameter in signature.parameters.values()
        if parameter.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    )


def _call_with_optional_context(bound: Any, context: RuntimeContext) -> Any:
    return bound(context) if _positional_arg_count(bound) >= 1 else bound()


async def _await_if_needed(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _normalize_provider_type(value: Any) -> str:
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        return enum_value.strip().lower()
    return str(value).strip().lower()


async def _run_model_validation(
    *,
    instance: Any,
    method_name: str,
    meta: ValidateConfigMeta,
    config: dict[str, Any],
) -> None:
    if meta.model is not None:
        try:
            validated = meta.model.model_validate(config)
        except ValidationError as exc:
            raise ValueError(
                f"{instance.__class__.__name__}.{method_name} validate_config failed: {exc}"
            ) from exc
        _validated_config_store(instance)[method_name] = validated
        return

    assert meta.schema is not None
    validated = _validate_schema_config(meta.schema, config)
    _validated_config_store(instance)[method_name] = validated


def _validate_schema_config(
    schema: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    validated: dict[str, Any] = {}
    errors: list[str] = []

    for field_name, field_schema in schema.items():
        if not isinstance(field_schema, dict):
            errors.append(f"{field_name}: schema entry must be an object")
            continue
        present = field_name in config
        value = config.get(field_name, field_schema.get("default"))
        required = bool(field_schema.get("required", False))
        if value is None:
            if required and "default" not in field_schema:
                errors.append(f"{field_name}: is required")
            validated[field_name] = value
            continue
        expected_type = field_schema.get("type")
        if expected_type is not None and not isinstance(value, expected_type):
            errors.append(
                f"{field_name}: expected {getattr(expected_type, '__name__', expected_type)}, "
                f"got {type(value).__name__}"
            )
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            minimum = field_schema.get("min")
            maximum = field_schema.get("max")
            range_value = field_schema.get("range")
            if minimum is not None and value < minimum:
                errors.append(f"{field_name}: must be >= {minimum}")
            if maximum is not None and value > maximum:
                errors.append(f"{field_name}: must be <= {maximum}")
            if (
                isinstance(range_value, tuple)
                and len(range_value) == 2
                and not (range_value[0] <= value <= range_value[1])
            ):
                errors.append(
                    f"{field_name}: must be within [{range_value[0]}, {range_value[1]}]"
                )
        if required and not present and "default" not in field_schema:
            errors.append(f"{field_name}: is required")
        validated[field_name] = value

    if errors:
        raise ValueError("validate_config schema failed: " + "; ".join(errors))
    return validated


async def _run_validate_config(instance: Any, context: RuntimeContext) -> None:
    config_payload = await context.metadata.get_plugin_config()
    config = dict(config_payload or {})
    for method_name, _bound, raw in _iter_bound_methods(instance):
        meta = get_validate_config_meta(raw)
        if meta is None:
            continue
        await _run_model_validation(
            instance=instance,
            method_name=method_name,
            meta=meta,
            config=config,
        )


async def _register_http_apis(instance: Any, context: RuntimeContext) -> None:
    state = _runtime_state(instance)
    for _method_name, bound, raw in _iter_bound_methods(instance):
        meta = get_http_api_meta(raw)
        if meta is None:
            continue
        await _register_http_api(bound=bound, meta=meta, context=context)
        state.http_apis.append((meta.route, list(meta.methods)))


async def _register_http_api(
    *,
    bound: Any,
    meta: HttpApiMeta,
    context: RuntimeContext,
) -> None:
    if meta.capability_name:
        await context.http.register_api(
            route=meta.route,
            handler_capability=meta.capability_name,
            methods=list(meta.methods),
            description=meta.description,
        )
        return
    await context.http.register_api(
        route=meta.route,
        handler=bound,
        methods=list(meta.methods),
        description=meta.description,
    )


async def _register_provider_change_hooks(
    instance: Any,
    context: RuntimeContext,
) -> None:
    state = _runtime_state(instance)
    for _method_name, bound, raw in _iter_bound_methods(instance):
        meta = get_provider_change_meta(raw)
        if meta is None:
            continue

        async def callback(
            provider_id: str,
            provider_type: Any,
            umo: str | None,
            *,
            _bound=bound,
            _meta=meta,
        ) -> None:
            if _meta.provider_types:
                current_type = _normalize_provider_type(provider_type)
                if current_type not in _meta.provider_types:
                    return
            owner = instance if isinstance(instance, Star) else None
            with bind_star_runtime(owner, context):
                result = _bound(provider_id, provider_type, umo)
                await _await_if_needed(result)

        task = await context.provider_manager.register_provider_change_hook(callback)
        # TODO: provider.manager.watch_changes is currently restricted to
        # reserved/system plugins. If this decorator should be public-facing,
        # the capability boundary needs to be widened or a dedicated event feed
        # should be introduced.
        state.provider_hooks.append(task)


async def _start_background_tasks(instance: Any, context: RuntimeContext) -> None:
    state = _runtime_state(instance)
    for method_name, bound, raw in _iter_bound_methods(instance):
        meta = get_background_task_meta(raw)
        if meta is None or not meta.auto_start:
            continue
        task = await context.register_task(
            _background_runner(
                instance=instance,
                bound=bound,
                context=context,
                meta=meta,
                method_name=method_name,
            ),
            meta.description
            or f"background_task:{instance.__class__.__name__}.{method_name}",
        )
        state.background_tasks.append(task)


async def _background_runner(
    *,
    instance: Any,
    bound: Any,
    context: RuntimeContext,
    meta: BackgroundTaskMeta,
    method_name: str,
) -> None:
    while True:
        try:
            owner = instance if isinstance(instance, Star) else None
            with bind_star_runtime(owner, context):
                result = _call_with_optional_context(bound, context)
                await _await_if_needed(result)
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            if meta.on_error != "restart":
                raise
            context.logger.exception(
                "SDK decorator background_task restarting after failure: plugin_id={} task={}",
                context.plugin_id,
                f"{instance.__class__.__name__}.{method_name}",
            )


def _iter_class_and_method_meta(
    instance: Any,
    getter,
) -> list[Any]:
    values = list(getter(instance.__class__))
    for _method_name, _bound, raw in _iter_bound_methods(instance):
        values.extend(getter(raw))
    return values


async def _register_skills(instance: Any, context: RuntimeContext) -> None:
    state = _runtime_state(instance)
    for meta in _iter_class_and_method_meta(instance, get_skill_meta):
        await context.register_skill(
            name=meta.name,
            path=meta.path,
            description=meta.description,
        )
        state.registered_skills.append(meta.name)


async def _register_mcp_servers(instance: Any, context: RuntimeContext) -> None:
    state = _runtime_state(instance)
    for meta in _iter_class_and_method_meta(instance, get_mcp_server_meta):
        await _register_mcp_server(meta=meta, context=context)
        if meta.scope == "global":
            state.global_mcp_servers.append(meta.name)
        else:
            state.local_mcp_servers.append(meta.name)


async def _register_mcp_server(
    *,
    meta: MCPServerMeta,
    context: RuntimeContext,
) -> None:
    if meta.scope == "global":
        if meta.config is None:
            raise ValueError(
                f"mcp_server(name={meta.name!r}, scope='global') requires config"
            )
        await context.mcp.register_global_server(
            meta.name,
            dict(meta.config),
            timeout=meta.timeout,
        )
        return

    if meta.config not in (None, {}):
        raise ValueError(
            f"mcp_server(name={meta.name!r}, scope='local') does not support config registration"
        )
    # TODO: local MCP only supports enable/disable of predeclared servers today.
    # If the decorator is expected to register brand-new local servers, the MCP
    # client/runtime needs a first-class local register/unregister API.
    await context.mcp.enable_server(meta.name)
    if meta.wait_until_ready:
        await context.mcp.wait_until_ready(meta.name, timeout=meta.timeout)


async def _teardown_decorator_resources(instance: Any, context: RuntimeContext) -> None:
    state = _runtime_state(instance)

    for task in reversed(state.provider_hooks):
        with suppress(asyncio.CancelledError):
            await context.provider_manager.unregister_provider_change_hook(task)
    state.provider_hooks.clear()

    for task in reversed(state.background_tasks):
        if not task.done():
            task.cancel()
    for task in reversed(state.background_tasks):
        with suppress(asyncio.CancelledError, Exception):
            await task
    state.background_tasks.clear()

    for route, methods in reversed(state.http_apis):
        try:
            await context.http.unregister_api(route, methods)
        except Exception:
            logger.exception(
                "decorator http_api cleanup failed: plugin_id={} route={}",
                context.plugin_id,
                route,
            )
    state.http_apis.clear()

    for name in reversed(state.registered_skills):
        with suppress(Exception):
            await context.unregister_skill(name)
    state.registered_skills.clear()

    for name in reversed(state.local_mcp_servers):
        with suppress(Exception):
            await context.mcp.disable_server(name)
    state.local_mcp_servers.clear()

    for name in reversed(state.global_mcp_servers):
        with suppress(Exception):
            await context.mcp.unregister_global_server(name)
    state.global_mcp_servers.clear()


async def _invoke_hook(
    *,
    instance: Any,
    hook: Any | None,
    context: RuntimeContext,
) -> None:
    if hook is None:
        return
    owner = instance if isinstance(instance, Star) else None
    with bind_star_runtime(owner, context):
        result = _call_with_optional_context(hook, context)
        await _await_if_needed(result)


async def run_lifecycle_with_decorators(
    *,
    instance: Any,
    hook: Any | None,
    method_name: str,
    context: RuntimeContext,
) -> None:
    # Keep the lifecycle wrapper centralized so decorator-managed resources still
    # work when plugins override on_start/on_stop without calling super().
    if method_name == "on_start":
        await _run_validate_config(instance, context)
        await _invoke_hook(instance=instance, hook=hook, context=context)
        await _register_http_apis(instance, context)
        await _register_provider_change_hooks(instance, context)
        await _register_skills(instance, context)
        await _register_mcp_servers(instance, context)
        await _start_background_tasks(instance, context)
        return

    try:
        await _invoke_hook(instance=instance, hook=hook, context=context)
    finally:
        if method_name == "on_stop":
            await _teardown_decorator_resources(instance, context)


__all__ = ["run_lifecycle_with_decorators"]
