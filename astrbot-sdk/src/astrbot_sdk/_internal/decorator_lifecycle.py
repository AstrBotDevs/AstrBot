from __future__ import annotations

import asyncio
import inspect
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from ..context import Context as RuntimeContext
from ..decorators import (
    BackgroundTaskMeta,
    HttpApiMeta,
    ValidateConfigMeta,
    get_background_task_meta,
    get_http_api_meta,
    get_provider_change_meta,
    get_skill_meta,
    get_validate_config_meta,
)
from ..star import Star
from .sdk_logger import logger
from .star_runtime import bind_star_runtime

_RUNTIME_STATE_ATTR = "__astrbot_decorator_runtime_state__"
_VALIDATED_CONFIGS_ATTR = "__astrbot_validated_configs__"


@dataclass(slots=True)
class DecoratorRuntimeState:
    http_apis: list[tuple[str, list[str]]] = field(default_factory=list)
    provider_hooks: list[asyncio.Task[None]] = field(default_factory=list)
    background_tasks: list[asyncio.Task[Any]] = field(default_factory=list)
    registered_skills: list[str] = field(default_factory=list)


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


def _decorator_target_name(instance: Any, method_name: str | None = None) -> str:
    class_name = instance.__class__.__name__
    if method_name is None:
        return class_name
    return f"{class_name}.{method_name}"


def _decorator_error(
    *,
    instance: Any,
    decorator_name: str,
    exc: Exception,
    method_name: str | None = None,
    details: str | None = None,
) -> RuntimeError:
    message = f"{_decorator_target_name(instance, method_name)} {decorator_name} failed"
    if details:
        message += f" ({details})"
    message += f": {exc}"
    return RuntimeError(message)


def _http_api_details(meta: HttpApiMeta) -> str:
    details = [f"route={meta.route!r}", f"methods={list(meta.methods)!r}"]
    if meta.capability_name:
        details.append(f"capability_name={meta.capability_name!r}")
    return ", ".join(details)


def _provider_change_details(meta: Any) -> str:
    return f"provider_types={list(meta.provider_types)!r}"


def _background_task_details(meta: BackgroundTaskMeta, method_name: str) -> str:
    description = meta.description or f"background_task:{method_name}"
    return (
        f"description={description!r}, auto_start={meta.auto_start!r}, "
        f"on_error={meta.on_error!r}"
    )


def _skill_details(name: str, path: str) -> str:
    return f"name={name!r}, path={path!r}"


def _normalize_provider_type(value: Any) -> str:
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        return enum_value.strip().lower()
    return str(value).strip().lower()


def _is_valid_schema_expected_type(value: Any) -> bool:
    if isinstance(value, type):
        return True
    return (
        isinstance(value, tuple)
        and len(value) > 0
        and all(isinstance(item, type) for item in value)
    )


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
            raise ValueError(str(exc)) from exc
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
        if expected_type is not None and not _is_valid_schema_expected_type(
            expected_type
        ):
            errors.append(
                f"{field_name}: invalid schema 'type' entry {expected_type!r}; "
                "expected a type or tuple of types"
            )
            continue
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
        try:
            await _run_model_validation(
                instance=instance,
                method_name=method_name,
                meta=meta,
                config=config,
            )
        except Exception as exc:
            raise _decorator_error(
                instance=instance,
                method_name=method_name,
                decorator_name="@validate_config",
                exc=exc,
            ) from exc


async def _register_http_apis(instance: Any, context: RuntimeContext) -> None:
    state = _runtime_state(instance)
    for method_name, bound, raw in _iter_bound_methods(instance):
        meta = get_http_api_meta(raw)
        if meta is None:
            continue
        try:
            await _register_http_api(bound=bound, meta=meta, context=context)
        except Exception as exc:
            raise _decorator_error(
                instance=instance,
                method_name=method_name,
                decorator_name="@http_api",
                details=_http_api_details(meta),
                exc=exc,
            ) from exc
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
    for method_name, bound, raw in _iter_bound_methods(instance):
        meta = get_provider_change_meta(raw)
        if meta is None:
            continue
        target_name = _decorator_target_name(instance, method_name)

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
            try:
                with bind_star_runtime(owner, context):
                    result = _bound(provider_id, provider_type, umo)
                    await _await_if_needed(result)
            except Exception as exc:
                raise RuntimeError(
                    f"{target_name} @on_provider_change callback failed "
                    f"(provider_id={provider_id!r}, provider_type={provider_type!r}, "
                    f"umo={umo!r}): {exc}"
                ) from exc

        try:
            task = await context.provider_manager.register_provider_change_hook(
                callback
            )
        except Exception as exc:
            raise _decorator_error(
                instance=instance,
                method_name=method_name,
                decorator_name="@on_provider_change",
                details=_provider_change_details(meta),
                exc=exc,
            ) from exc
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
        try:
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
        except Exception as exc:
            raise _decorator_error(
                instance=instance,
                method_name=method_name,
                decorator_name="@background_task",
                details=_background_task_details(meta, method_name),
                exc=exc,
            ) from exc
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
        except Exception as exc:
            if meta.on_error != "restart":
                raise _decorator_error(
                    instance=instance,
                    method_name=method_name,
                    decorator_name="@background_task",
                    details=_background_task_details(meta, method_name),
                    exc=exc,
                ) from exc
            context.logger.exception(
                "SDK decorator background_task restarting after failure: plugin_id={} task={} details={}",
                context.plugin_id,
                f"{instance.__class__.__name__}.{method_name}",
                _background_task_details(meta, method_name),
            )


def _iter_class_and_method_meta_entries(
    instance: Any,
    getter,
) -> list[tuple[str, Any]]:
    values = [
        (_decorator_target_name(instance), meta) for meta in getter(instance.__class__)
    ]
    for method_name, _bound, raw in _iter_bound_methods(instance):
        values.extend(
            (_decorator_target_name(instance, method_name), meta)
            for meta in getter(raw)
        )
    return values


async def _register_skills(instance: Any, context: RuntimeContext) -> None:
    state = _runtime_state(instance)
    for target_name, meta in _iter_class_and_method_meta_entries(
        instance, get_skill_meta
    ):
        try:
            await context.register_skill(
                name=meta.name,
                path=meta.path,
                description=meta.description,
            )
        except Exception as exc:
            raise RuntimeError(
                f"{target_name} @register_skill failed "
                f"({_skill_details(meta.name, meta.path)}): {exc}"
            ) from exc
        state.registered_skills.append(meta.name)


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
    # Wrap decorator-managed startup failures with decorator-specific context so
    # plugin authors do not only see a generic worker initialize timeout.
    # Keep the lifecycle wrapper centralized so decorator-managed resources still
    # work when plugins override on_start/on_stop without calling super().
    if method_name == "on_start":
        await _run_validate_config(instance, context)
        await _invoke_hook(instance=instance, hook=hook, context=context)
        await _register_http_apis(instance, context)
        await _register_provider_change_hooks(instance, context)
        await _register_skills(instance, context)
        await _start_background_tasks(instance, context)
        return

    try:
        await _invoke_hook(instance=instance, hook=hook, context=context)
    finally:
        if method_name == "on_stop":
            await _teardown_decorator_resources(instance, context)


__all__ = ["run_lifecycle_with_decorators"]
