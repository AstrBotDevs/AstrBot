from __future__ import annotations

import dataclasses
import hashlib
import importlib
import importlib.machinery
import inspect
import logging
import os
import sys
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from .._version import __version__
from ..capabilities import DEFAULT_CAPABILITY_IDS, CapabilityGrant, CapabilitySet
from ..config import validate_config_against_model
from ..context import (
    _ACTIVE_INVOCATION_CTX,
    HostCapabilityInvoker,
    HostCapabilityStreamInvoker,
    HostServiceInvoker,
    PluginContext,
    PluginInfo,
    RuntimeMode,
)
from ..errors import (
    CapabilityDenied,
    InvalidConfig,
    InvalidHandlerResult,
    InvalidPluginDefinition,
    InvalidRequest,
    NotFound,
    PluginImportError,
)
from ..events import MessageEvent
from ..lifecycle import ConfigChangedEvent, ShutdownEvent
from ..plugin import Plugin
from ..registration import (
    HandlerKind,
    HandlerRegistration,
    discover_handlers,
)
from ..results import EventResult, MessageResult, Propagation, message_result
from ..services import prepare_outbound_chain
from ..tools import ToolCallContext
from .metadata import PluginMetadata, load_metadata


def _load_metadata_for_legacy(plugin_root: Path) -> PluginMetadata:
    """Read legacy metadata.yaml into the metadata shape used by the loader."""
    import yaml

    from .metadata import (
        CapabilityDeclarations,
        PluginAPIFamily,
        PluginMetadata,
        RuntimeMetadata,
    )

    metadata_file = plugin_root / "metadata.yaml"
    # Old plugins may ship without metadata.yaml; the register decorator or
    # class attributes then carry the plugin info (name falls back to the
    # directory name), like the in-process loader.
    data = (
        yaml.safe_load(metadata_file.read_text(encoding="utf-8"))
        if metadata_file.is_file()
        else {}
    ) or {}
    name = str(data.get("name") or plugin_root.name)
    author = str(data.get("author") or "unknown")
    raw_views = data.get("views") if isinstance(data.get("views"), list) else None
    if raw_views is None and isinstance(data.get("pages"), list):
        raw_views = data.get("pages")
    support_platforms = data.get("support_platforms")
    if not isinstance(support_platforms, list):
        support_platforms = ()
    return PluginMetadata(
        schema_version=1,
        name=name,
        display_name=(
            str(data.get("display_name")) if data.get("display_name") else None
        ),
        short_desc=(str(data.get("short_desc")) if data.get("short_desc") else None),
        repo=str(data.get("repo")) if data.get("repo") else None,
        astrbot_version=(
            str(data.get("astrbot_version")) if data.get("astrbot_version") else None
        ),
        support_platforms=tuple(str(item) for item in support_platforms),
        author=author,
        version=str(data.get("version") or "0.0.0"),
        desc=str(data.get("desc") or ""),
        pages=tuple(raw_views or ()),
        runtime=RuntimeMetadata(
            api=PluginAPIFamily.LEGACY,
            entrypoint="main",
            module="main",
            plugin_class="",
            sdk_version="",
        ),
        capabilities=CapabilityDeclarations(),
    )


def _default_data_dir(metadata: PluginMetadata) -> Path:
    """Resolve the Runner-local persistent directory for one plugin.

    Args:
        metadata: Loaded plugin metadata.

    Returns:
        Directory below ASTRBOT_SDK_DATA_DIR or the current working directory.
    """
    base = os.environ.get("ASTRBOT_SDK_DATA_DIR")
    root = Path(base) if base else Path.cwd() / "data" / "sdk-plugins"
    return root / metadata.plugin_id.replace("/", "_")


def _is_event_parameter(param: inspect.Parameter) -> bool:
    """Check whether one parameter is the MessageEvent injection slot."""
    annotation = param.annotation
    if annotation is MessageEvent:
        return True
    import types
    import typing

    if typing.get_origin(annotation) in (typing.Union, types.UnionType):
        if MessageEvent in typing.get_args(annotation):
            return True
    if isinstance(annotation, str):
        name = annotation.rsplit(".", 1)[-1].removesuffix(" | None")
        if name == "MessageEvent":
            return True
    return param.name == "event" and annotation is inspect.Parameter.empty


def _is_tool_context_param(param: inspect.Parameter) -> bool:
    """Check whether one parameter is the ToolCallContext injection slot."""
    annotation = param.annotation
    if annotation is ToolCallContext:
        return True
    if isinstance(annotation, str):
        return annotation.rsplit(".", 1)[-1] == "ToolCallContext"
    return param.name == "call" and annotation is inspect.Parameter.empty


def _plugin_namespace(plugin_root: Path) -> str:
    digest = hashlib.sha256(str(plugin_root.resolve()).encode()).hexdigest()[:16]
    return f"_astrbot_plugin_{digest}"


def _install_namespace(plugin_root: Path) -> str:
    namespace = _plugin_namespace(plugin_root)
    if namespace in sys.modules:
        return namespace

    init_file = plugin_root / "__init__.py"
    module = ModuleType(namespace)
    module.__path__ = [str(plugin_root)]  # type: ignore[attr-defined]
    module.__package__ = namespace
    module.__spec__ = importlib.machinery.ModuleSpec(
        namespace,
        loader=None,
        # Mirror a real package spec: frameworks that introspect importlib
        # metadata (e.g. Flask/Quart instance-path discovery) break on a
        # spec without origin and search locations.
        origin=str(init_file) if init_file.is_file() else "namespace",
        is_package=True,
    )
    module.__spec__.submodule_search_locations = [str(plugin_root)]
    sys.modules[namespace] = module
    return namespace


VIRTUAL_PLUGIN_PARENTS_ENV = "ASTRBOT_SDK_VIRTUAL_PLUGIN_PARENTS"


def _anchor_virtual_parent(parent: str) -> None:
    """Anchor one plugin parent directory under ``data.plugins``.

    Prefers a real ``data``/``data.plugins`` package when one is importable
    and only creates in-memory namespace packages as a fallback, so mirrored
    (local) and virtual (remote) layouts can coexist in one interpreter.
    """
    data = sys.modules.get("data")
    if data is None:
        try:
            data = importlib.import_module("data")
        except ImportError:
            data = ModuleType("data")
            data.__path__ = []  # type: ignore[attr-defined]
            data.__spec__ = importlib.machinery.ModuleSpec(
                "data", loader=None, is_package=True
            )
            sys.modules["data"] = data
    plugins = sys.modules.get("data.plugins")
    if plugins is None:
        try:
            plugins = importlib.import_module("data.plugins")
        except ImportError:
            plugins = ModuleType("data.plugins")
            plugins.__package__ = "data.plugins"
            plugins.__path__ = []  # type: ignore[attr-defined]
            plugins.__spec__ = importlib.machinery.ModuleSpec(
                "data.plugins", loader=None, is_package=True
            )
            sys.modules["data.plugins"] = plugins
            data.plugins = plugins  # type: ignore[attr-defined]
    paths = list(getattr(plugins, "__path__", None) or [])
    if parent not in paths:
        # Reassign instead of append: real namespace packages expose a
        # read-only _NamespacePath.
        plugins.__path__ = [*paths, parent]  # type: ignore[attr-defined]


def install_virtual_plugin_root(plugin_root: Path) -> str:
    """Anchor ``data.plugins.<dir>`` resolution without an AstrBot root.

    Remote runners have no AstrBot checkout on disk, so the real dotted
    path cannot resolve through sys.path. Point a namespace package at the
    plugin's real parent directory instead, preserving the
    ``data.plugins.<dir>`` module identity that framework introspection
    (Flask/Quart instance paths, importlib.resources) and multiprocessing
    spawn children rely on. The parent directory is recorded in
    VIRTUAL_PLUGIN_PARENTS_ENV because spawn children are fresh
    interpreters: they inherit env vars but not sys.modules.

    Args:
        plugin_root: Resolved plugin directory.

    Returns:
        The dotted package name of the plugin (``data.plugins.<dir>``).
    """
    parent = str(plugin_root.parent)
    _anchor_virtual_parent(parent)
    recorded = os.environ.get(VIRTUAL_PLUGIN_PARENTS_ENV, "")
    if parent not in recorded.split(os.pathsep):
        os.environ[VIRTUAL_PLUGIN_PARENTS_ENV] = (
            f"{recorded}{os.pathsep}{parent}" if recorded else parent
        )
    return f"data.plugins.{plugin_root.name}"


def reinstall_virtual_plugin_roots_from_env() -> None:
    """Re-anchor virtual plugin roots in a fresh interpreter.

    multiprocessing spawn children inherit environment variables but not
    sys.modules; ``runtime.__main__`` calls this during spawn fixup.
    """
    recorded = os.environ.get(VIRTUAL_PLUGIN_PARENTS_ENV, "")
    for parent in recorded.split(os.pathsep):
        if parent:
            _anchor_virtual_parent(parent)


def _resolve_entrypoint(
    metadata: PluginMetadata,
    plugin_root: Path,
) -> type[Plugin[Any]]:
    namespace = _install_namespace(plugin_root)
    module_name = f"{namespace}.{metadata.runtime.module}"
    importlib.invalidate_caches()
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        raise PluginImportError(
            f"failed to import plugin module {metadata.runtime.module!r}: {exc}"
        ) from exc

    entrypoint: Any = module
    try:
        for attribute in metadata.runtime.plugin_class.split("."):
            entrypoint = getattr(entrypoint, attribute)
    except AttributeError as exc:
        raise PluginImportError(
            f"plugin entrypoint {metadata.runtime.entrypoint!r} was not found"
        ) from exc

    if not inspect.isclass(entrypoint) or not issubclass(entrypoint, Plugin):
        raise InvalidPluginDefinition(
            f"{metadata.runtime.entrypoint!r} must point to a Plugin subclass"
        )
    return entrypoint


def _filter_grants(
    metadata: PluginMetadata,
    grants: CapabilitySet,
) -> CapabilitySet:
    missing = metadata.capabilities.required_ids - set(grants)
    if missing:
        capability_id = sorted(missing)[0]
        raise CapabilityDenied(f"required capability was not granted: {capability_id}")
    declared = metadata.capabilities.all_ids
    return CapabilitySet(
        [grant for grant in grants.values() if grant.id in declared]
        + [
            CapabilityGrant(id=capability_id)
            for capability_id in sorted(DEFAULT_CAPABILITY_IDS - declared)
        ]
    )


def _normalize_result(value: Any) -> EventResult | None:
    if value is None or isinstance(value, EventResult):
        return value
    try:
        return message_result(value)
    except (TypeError, ValueError) as exc:
        raise InvalidHandlerResult(
            f"handler returned unsupported value {type(value)!r}"
        ) from exc


@dataclass(slots=True)
class LoadedPlugin:
    metadata: PluginMetadata
    instance: Plugin[Any]
    registrations: tuple[HandlerRegistration, ...]
    plugin_root: Path = Path(".")
    _registrations_by_id: Mapping[str, HandlerRegistration] = field(
        init=False,
        repr=False,
    )
    _started: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self._registrations_by_id = {
            registration.id: registration for registration in self.registrations
        }

    def get_handler(self, handler_id: str) -> HandlerRegistration:
        try:
            return self._registrations_by_id[handler_id]
        except KeyError as exc:
            raise NotFound(f"handler not found: {handler_id}") from exc

    async def invoke_web(
        self,
        request: Any,
        *,
        call_id: str | None = None,
    ) -> AsyncIterator[dict]:
        """Invoke one web route handler and stream the response.

        Yields the response info first, then body chunks, for the Host to
        replay as an HTTP response.
        """
        from ..web import WebRequest, normalize_web_result

        registration = next(
            (
                item
                for item in self.instance._ctx.web.routes
                if item.route == request.route
            ),
            None,
        )
        if registration is None:
            raise NotFound(f"web route not found: {request.route}")
        if request.method.upper() not in registration.methods:
            raise InvalidRequest(
                f"method {request.method} not allowed for {request.route}"
            )
        scoped_ctx = (
            self.instance._ctx.scoped_for_invocation(call_id)
            if call_id is not None
            else self.instance._ctx
        )
        ctx_token = _ACTIVE_INVOCATION_CTX.set(scoped_ctx)
        try:
            facade = WebRequest(request, scoped_ctx)
            outcome = registration.handler(facade, **request.path_params)
            result = await outcome if inspect.isawaitable(outcome) else outcome
            info, chunks = await normalize_web_result(result)
            yield {"info": info}
            async for chunk in chunks:
                yield {"chunk": chunk}
        finally:
            if call_id is not None:
                scoped_ctx._retire()
            _ACTIVE_INVOCATION_CTX.reset(ctx_token)

    async def invoke_views(
        self,
        operation: str,
        page: str | None = None,
        path: str | None = None,
    ) -> AsyncIterator[dict]:
        """Serve view manifest or stream one view file's content."""
        from ..views import load_i18n, read_view_file, scan_views

        plugin_root = self.plugin_root
        if operation == "manifest":
            manifest = [
                {
                    "name": page.name,
                    "files": [
                        {"path": file.path, "size": file.size} for file in page.files
                    ],
                }
                for page in scan_views(plugin_root)
            ]
            yield {
                "info": {
                    "pages": manifest,
                    "i18n": load_i18n(plugin_root),
                    "content_type": "application/json",
                },
            }
            return
        if operation == "read":
            if not page or not path:
                raise InvalidRequest("views.read requires page and path")
            info, chunks = await read_view_file(plugin_root, page, path)
            yield {"info": info}
            async for chunk in chunks:
                yield {"chunk": chunk}
            return
        raise NotFound(f"unknown views operation: {operation}")

    async def _invoke_lifecycle(
        self,
        kind: HandlerKind,
        event: object | None = None,
    ) -> None:
        registration = next(
            (item for item in self.registrations if item.spec.kind is kind),
            None,
        )
        if registration is None:
            return

        parameters = inspect.signature(registration.handler).parameters
        if event is None:
            outcome = registration.handler()
        elif len(parameters) == 0:
            outcome = registration.handler()
        else:
            outcome = registration.handler(event)
        if inspect.isasyncgen(outcome):
            await outcome.aclose()
            raise InvalidHandlerResult(f"{kind.value} lifecycle handler cannot yield")
        result = await outcome
        if result is not None:
            raise InvalidHandlerResult(
                f"{kind.value} lifecycle handler must return None"
            )

    async def start(self) -> None:
        if self._started:
            return
        await self._invoke_lifecycle(HandlerKind.LIFECYCLE_STARTUP)
        self._started = True

    async def validate_config(self, candidate: Any) -> Any:
        """Validate candidate config via config_model and validate_config hook."""
        config_model = getattr(type(self.instance), "config_model", None)
        validated = (
            validate_config_against_model(config_model, candidate)
            if config_model is not None
            else candidate
        )
        registration = next(
            (
                item
                for item in self.registrations
                if item.spec.kind is HandlerKind.LIFECYCLE_VALIDATE_CONFIG
            ),
            None,
        )
        if registration is not None:
            try:
                outcome = registration.handler(validated)
                if inspect.isawaitable(outcome):
                    await outcome
            except InvalidConfig:
                raise
            except Exception as exc:
                raise InvalidConfig(str(exc)) from exc
        return validated

    async def reconfigure(self, config: Any) -> None:
        previous = self.instance._ctx.config
        validated = await self.validate_config(config)
        self.instance._ctx._update_config(validated)
        try:
            await self._invoke_lifecycle(
                HandlerKind.LIFECYCLE_CONFIG_CHANGED,
                ConfigChangedEvent(previous=previous, current=validated),
            )
        except Exception:
            self.instance._ctx._update_config(previous)
            raise

    async def check_health(self) -> None:
        """Run background TaskGroup health check and optional @lifecycle.health."""
        self.instance._ctx.tasks.check_health()
        await self._invoke_lifecycle(HandlerKind.LIFECYCLE_HEALTH)

    async def invoke_service(
        self,
        service_name: str,
        payload: Mapping[str, Any],
        *,
        call_id: str | None = None,
    ) -> Any:
        """Invoke an exported host-scoped or direct cross-plugin service."""
        registration = next(
            (
                item
                for item in self.registrations
                if item.spec.kind in (HandlerKind.SERVICE, HandlerKind.DIRECT_SERVICE)
                and (
                    item.spec.service_name == service_name
                    or item.id == service_name
                    or item.id == f"service:{service_name}"
                )
            ),
            None,
        )
        if registration is None:
            raise NotFound(f"service not found: {service_name}")

        if registration.spec.kind is HandlerKind.DIRECT_SERVICE:
            params = list(inspect.signature(registration.handler).parameters.values())
            dctx = self.instance._ctx.direct_view()
            outcome = (
                registration.handler(dict(payload), dctx)
                if len(params) >= 2
                else registration.handler(dict(payload))
            )
            if not inspect.isawaitable(outcome):
                raise InvalidHandlerResult("direct service handler must be async")
            return await outcome

        scoped_ctx = (
            self.instance._ctx.scoped_for_invocation(call_id)
            if call_id is not None
            else self.instance._ctx
        )
        ctx_token = _ACTIVE_INVOCATION_CTX.set(scoped_ctx)
        try:
            outcome = registration.handler(dict(payload))
            if not inspect.isawaitable(outcome):
                raise InvalidHandlerResult("service handler must be async")
            return await outcome
        finally:
            if call_id is not None:
                scoped_ctx._retire()
            _ACTIVE_INVOCATION_CTX.reset(ctx_token)

    async def discover_tools(self) -> list[dict[str, Any]]:
        """Invoke @on.tool_discovery if registered and return serialized specs."""
        registration = next(
            (
                item
                for item in self.registrations
                if item.spec.kind is HandlerKind.LIFECYCLE_TOOL_DISCOVERY
            ),
            None,
        )
        if registration is None:
            return []
        outcome = registration.handler()
        if not inspect.isawaitable(outcome):
            raise InvalidHandlerResult("tool_discovery handler must be async")
        discovered = await outcome
        return list(discovered or [])

    async def invoke_cron(self, handler_id: str, payload: Any) -> Any:
        """Invoke one scheduled cron handler registered on PluginContext."""
        handler = self.instance._ctx.cron_handlers.get(handler_id)
        if handler is None:
            raise InvalidRequest(f"unknown cron handler: {handler_id}")
        args = list(payload.get("args") or ())
        kwargs = dict(payload.get("kwargs") or {})
        result = handler(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    async def shutdown(
        self,
        *,
        deadline: datetime | None = None,
        reason: str = "shutdown",
    ) -> None:
        if not self._started:
            return
        try:
            await self.instance._ctx.tasks.shutdown()
            await self._invoke_lifecycle(
                HandlerKind.LIFECYCLE_SHUTDOWN,
                ShutdownEvent(deadline=deadline, reason=reason),
            )
        finally:
            self.instance._ctx._retire()
            self._started = False

    async def invoke_tool(
        self,
        handler_id: str,
        call: ToolCallContext,
        args: Mapping[str, Any],
        *,
        call_id: str | None = None,
    ) -> Any:
        """Invoke one tool handler and return its JSON-safe result."""
        handler: Callable[..., Any] | None = self.instance._ctx.dynamic_tools.get(
            handler_id,
        )
        if handler is None:
            registration = self.get_handler(handler_id)
            if registration.spec.kind is not HandlerKind.TOOL:
                raise InvalidPluginDefinition(
                    f"handler {handler_id!r} is not a tool handler"
                )
            handler = registration.handler

        scoped_ctx = (
            self.instance._ctx.scoped_for_invocation(call_id)
            if call_id is not None
            else self.instance._ctx
        )
        umo = call.umo or (call.event.umo if call.event is not None else None)
        token = scoped_ctx._bind_ambient_umo(umo) if umo is not None else None
        event_token = (
            scoped_ctx._bind_ambient_event(call.event)
            if call.event is not None
            else None
        )
        ctx_token = _ACTIVE_INVOCATION_CTX.set(scoped_ctx)
        try:
            signature = inspect.signature(handler)
            parameters = list(signature.parameters.values())
            kwargs = dict(args)
            if parameters and _is_tool_context_param(parameters[0]):
                call = dataclasses.replace(call, ctx=scoped_ctx)
                outcome = handler(call, **kwargs)
            else:
                outcome = handler(**kwargs)

            if inspect.isasyncgen(outcome):
                await outcome.aclose()
                raise InvalidHandlerResult("tool handler cannot yield results")
            if not inspect.isawaitable(outcome):
                raise InvalidHandlerResult(
                    f"tool handler {handler_id!r} did not return an awaitable"
                )
            return await outcome
        finally:
            if call_id is not None:
                scoped_ctx._retire()
            _ACTIVE_INVOCATION_CTX.reset(ctx_token)
            if token is not None:
                scoped_ctx._reset_ambient_umo(token)
            if event_token is not None:
                scoped_ctx._reset_ambient_event(event_token)

    async def invoke_hook(
        self,
        handler_id: str,
        event: MessageEvent | None,
        stage_payload: Mapping[str, Any],
        *,
        call_id: str | None = None,
    ) -> dict[str, Any]:
        """Invoke one Pipeline hook handler."""
        from ..hooks import build_stage_dto
        from ..registration import _HOOK_KINDS

        registration = self.get_handler(handler_id)
        kind = registration.spec.kind
        if kind not in _HOOK_KINDS:
            raise InvalidPluginDefinition(
                f"handler {handler_id!r} is not a hook handler"
            )
        stage = kind.value.removeprefix("hook.")
        dto = build_stage_dto(stage, stage_payload)

        parameters = list(inspect.signature(registration.handler).parameters.values())
        args: list[Any] = []
        if parameters and _is_event_parameter(parameters[0]):
            args.append(event)
            parameters = parameters[1:]
        if parameters and dto is not None:
            args.append(dto)

        scoped_ctx = (
            self.instance._ctx.scoped_for_invocation(call_id)
            if call_id is not None
            else self.instance._ctx
        )
        ctx_token = _ACTIVE_INVOCATION_CTX.set(scoped_ctx)
        try:
            outcome = registration.handler(*args)
            if inspect.isasyncgen(outcome):
                await outcome.aclose()
                raise InvalidHandlerResult("hook handler cannot yield results")
            if not inspect.isawaitable(outcome):
                raise InvalidHandlerResult(
                    f"hook handler {handler_id!r} did not return an awaitable"
                )
            result = await outcome
            if result is not None:
                raise InvalidHandlerResult(
                    f"hook handler {handler_id!r} must return None"
                )
            from ..hooks import HookDTO

            return {
                "writes": (
                    await dto._prepare_write_ops(scoped_ctx.assets)
                    if isinstance(dto, HookDTO)
                    else []
                ),
            }
        finally:
            if call_id is not None:
                scoped_ctx._retire()
            _ACTIVE_INVOCATION_CTX.reset(ctx_token)

    async def _prepare_result(self, result: EventResult | None) -> EventResult | None:
        # Upload local media sources so outbound chains only carry asset
        # references or public URLs across the protocol.
        if isinstance(result, MessageResult):
            prepared = await prepare_outbound_chain(
                result.message,
                self.instance._ctx.assets,
            )
            if prepared is not result.message:
                return MessageResult(
                    propagation=result.propagation,
                    message=prepared,
                    quote=result.quote,
                )
        return result

    async def invoke(
        self,
        handler_id: str,
        *args: Any,
        call_id: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[EventResult | None]:
        registration = self.get_handler(handler_id)
        if registration.spec.kind.value.startswith("lifecycle."):
            raise InvalidPluginDefinition(
                "lifecycle handlers cannot be invoked as event handlers"
            )

        scoped_ctx = (
            self.instance._ctx.scoped_for_invocation(call_id)
            if call_id is not None
            else self.instance._ctx
        )
        event = next(
            (arg for arg in args if isinstance(arg, MessageEvent)),
            None,
        )
        umo = event.umo if event is not None else None
        token = scoped_ctx._bind_ambient_umo(umo) if umo is not None else None
        event_token = (
            scoped_ctx._bind_ambient_event(event) if event is not None else None
        )
        ctx_token = _ACTIVE_INVOCATION_CTX.set(scoped_ctx)
        try:
            outcome = registration.handler(*args, **kwargs)
            if inspect.isasyncgen(outcome):
                try:
                    async for value in outcome:
                        result = _normalize_result(value)
                        if (
                            result is not None
                            and result.propagation is Propagation.STOP
                        ):
                            await outcome.aclose()
                            yield await self._prepare_result(result)
                            return
                        yield await self._prepare_result(result)
                finally:
                    await outcome.aclose()
                return

            if not inspect.isawaitable(outcome):
                raise InvalidHandlerResult(
                    f"handler {handler_id!r} did not return an awaitable"
                )
            yield await self._prepare_result(_normalize_result(await outcome))
        finally:
            if call_id is not None:
                scoped_ctx._retire()
            _ACTIVE_INVOCATION_CTX.reset(ctx_token)
            if token is not None:
                scoped_ctx._reset_ambient_umo(token)
            if event_token is not None:
                scoped_ctx._reset_ambient_event(event_token)


def load_plugin(
    plugin_root: str | Path,
    *,
    config: Any = None,
    granted_capabilities: CapabilitySet | None = None,
    runtime_mode: RuntimeMode = RuntimeMode.ISOLATED,
    logger: logging.Logger | None = None,
    host_capability_invoker: HostCapabilityInvoker | None = None,
    host_capability_stream_invoker: HostCapabilityStreamInvoker | None = None,
    host_service_invoker: HostServiceInvoker | None = None,
    data_dir: str | Path | None = None,
) -> LoadedPlugin:
    root = Path(plugin_root).resolve()
    metadata = load_metadata(root)
    if not SpecifierSet(metadata.runtime.sdk_version).contains(
        Version(__version__),
        prereleases=True,
    ):
        raise InvalidPluginDefinition(
            f"astrbot-sdk {__version__} does not satisfy {metadata.runtime.sdk_version}"
        )

    grants = _filter_grants(
        metadata,
        granted_capabilities or CapabilitySet(),
    )
    plugin_data_dir = (
        Path(data_dir)
        if data_dir is not None
        else _default_data_dir(
            metadata,
        )
    )
    plugin_data_dir.mkdir(parents=True, exist_ok=True)
    plugin_class = _resolve_entrypoint(metadata, root)
    config_model = getattr(plugin_class, "config_model", None)
    initial_config = (
        validate_config_against_model(config_model, config)
        if config_model is not None
        else config
    )
    context = PluginContext(
        plugin=PluginInfo(
            id=metadata.plugin_id,
            name=metadata.name,
            version=metadata.version,
            runtime_mode=runtime_mode,
        ),
        config=initial_config,
        logger=logger or logging.getLogger(f"astrbot.plugin.{metadata.name}"),
        capabilities=grants,
        data_dir=plugin_data_dir,
        _host_capability_invoker=host_capability_invoker,
        _host_capability_stream_invoker=host_capability_stream_invoker,
        _host_service_invoker=host_service_invoker,
    )

    try:
        instance = plugin_class(context)
    except TypeError as exc:
        raise InvalidPluginDefinition(
            f"{metadata.runtime.entrypoint!r} must accept only PluginContext"
        ) from exc

    registrations = discover_handlers(instance)
    enabled: list[HandlerRegistration] = []
    for registration in registrations:
        capability_id = registration.spec.required_capability
        if capability_id is None:
            enabled.append(registration)
            continue
        if capability_id not in metadata.capabilities.all_ids:
            raise InvalidPluginDefinition(
                f"handler {registration.id!r} requires undeclared capability "
                f"{capability_id!r}"
            )
        if grants.has(capability_id):
            enabled.append(registration)

    return LoadedPlugin(
        metadata=metadata,
        instance=instance,
        registrations=tuple(enabled),
        plugin_root=root,
    )
