"""Load unmodified legacy plugins through the compat layer."""

from __future__ import annotations

import inspect
import logging
import os
import re
import sys
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml

from ...errors import (
    InvalidHandlerResult,
    InvalidPluginDefinition,
    PluginImportError,
)
from ...events import MessageType, SenderRole
from ...registration import HandlerKind, HandlerRegistration, HandlerSpec
from ...results import EventResult, MessageResult
from ...services import prepare_outbound_chain
from . import api as compat_api
from .components import MessageEventResult
from .event import (
    _FILTERS_ATTR,
    AstrMessageEvent,
    ButtonActionFilter,
    CommandFilter,
    CustomFilter,
    EventMessageTypeFilter,
    HookMarker,
    LLMToolMarker,
    PermissionTypeFilter,
    PlatformAdapterTypeFilter,
    RegexFilter,
    UIActionFilter,
    _CommandGroup,
    translate_compat_result,
)
from .hooks import HOOK_STAGE_KINDS, invoke_compat_hook
from .platform_events import build_legacy_event
from .star import Context as CompatContext
from .star import Star


@dataclass(frozen=True, slots=True)
class LegacyMetadata:
    """Minimal metadata for one legacy plugin."""

    plugin_id: str
    name: str
    version: str
    author: str
    desc: str
    schema_version: int = 1
    views: tuple = ()


class CompatLoadedPlugin:
    """LoadedPlugin-shaped wrapper around one legacy Star instance."""

    def __init__(
        self,
        metadata: LegacyMetadata,
        instance: Star,
        registrations: tuple[HandlerRegistration, ...],
        plugin_root: Path,
    ) -> None:
        self.metadata = metadata
        self.instance = instance
        self.registrations = registrations
        self.plugin_root = plugin_root
        self.sdk_ctx = instance.context._inner
        self._by_id = {r.id: r for r in registrations}
        self._started = False

    def get_handler(self, handler_id: str) -> HandlerRegistration:
        return self._by_id[handler_id]

    async def start(self) -> None:
        if self._started:
            return
        await self.instance.initialize()
        await self.instance.context._drain_pending()
        await self.instance.context._prime_stars()
        self._started = True
        for registration in self.registrations:
            if registration.spec.kind is HandlerKind.LIFECYCLE_STARTUP:
                await registration.handler()

    async def reconfigure(self, config: Any) -> None:
        self.instance.context._config = config or {}

    async def shutdown(self, *, deadline: Any = None) -> None:
        if not self._started:
            return
        try:
            await self.instance.terminate()
        finally:
            for task in self.instance.context._tasks:
                task.cancel()
            self.instance.context._tasks.clear()
            self._started = False

    async def _prepare_result(self, result: EventResult | None) -> EventResult | None:
        # Upload local media sources so outbound chains only carry asset
        # references or public URLs across the protocol.
        if isinstance(result, MessageResult):
            prepared = await prepare_outbound_chain(
                result.message,
                self.sdk_ctx.assets,
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
        **kwargs: Any,
    ) -> AsyncIterator[EventResult | None]:
        dyn = self.instance.context._dynamic_commands.get(handler_id)
        target = dyn if dyn is not None else self.get_handler(handler_id).handler
        outcome = target(*args, **kwargs)
        if inspect.isasyncgen(outcome):
            try:
                async for item in outcome:
                    yield await self._prepare_result(item)
            finally:
                await outcome.aclose()
            return
        result = await outcome
        yield await self._prepare_result(result)

    async def invoke_hook(
        self,
        handler_id: str,
        event: Any,
        stage_payload: Any,
    ) -> dict[str, Any]:
        """Invoke one legacy hook handler through the stage facade."""
        registration = self.get_handler(handler_id)
        stage = registration.spec.kind.value.removeprefix("hook.")
        return await invoke_compat_hook(
            self.instance,
            registration.handler,
            stage,
            event,
            dict(stage_payload or {}),
        )

    async def invoke_tool(
        self,
        handler_id: str,
        call: Any,
        args: Any,
    ) -> Any:
        """Invoke one legacy llm_tool handler and return its result."""
        dynamic = self.sdk_ctx.dynamic_tools.get(handler_id)
        if dynamic is not None:
            return await dynamic(call, **dict(args))
        registration = self.get_handler(handler_id)
        if registration.spec.kind is not HandlerKind.TOOL:
            raise InvalidPluginDefinition(
                f"handler {handler_id!r} is not a tool handler"
            )
        return await registration.handler(call, **dict(args))

    async def invoke_cron(self, handler_id: str, payload: Any) -> Any:
        """Invoke one legacy cron job handler and return its result."""
        import inspect

        handler = self.sdk_ctx.cron_handlers.get(handler_id)
        if handler is None:
            from ...errors import InvalidRequest

            raise InvalidRequest(f"unknown cron handler: {handler_id}")
        args = list(payload.get("args") or ())
        kwargs = dict(payload.get("kwargs") or {})
        result = handler(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    async def invoke_web(self, request: Any) -> AsyncIterator[dict]:
        """Invoke one legacy register_web_api handler."""
        from ...errors import InvalidRequest, NotFound
        from .web import invoke_web_route

        entry = next(
            (
                item
                for item in self.instance.context._web_routes
                if item.route == request.route
            ),
            None,
        )
        if entry is None:
            raise NotFound(f"web route not found: {request.route}")
        if request.method.upper() not in entry.methods:
            raise InvalidRequest(
                f"method {request.method} not allowed for {request.route}"
            )
        async for item in invoke_web_route(self.instance, entry, request):
            yield item

    async def invoke_views(
        self,
        operation: str,
        page: str | None = None,
        path: str | None = None,
    ) -> AsyncIterator[dict]:
        """Serve the views manifest or stream one view file's content."""
        from ...errors import InvalidRequest, NotFound
        from ...views import load_i18n, read_view_file, scan_views

        if operation == "manifest":
            manifest = [
                {
                    "name": page_entry.name,
                    "files": [
                        {"path": file.path, "size": file.size}
                        for file in page_entry.files
                    ],
                }
                for page_entry in scan_views(self.plugin_root)
            ]
            yield {
                "info": {
                    "pages": manifest,
                    "i18n": load_i18n(self.plugin_root),
                    "content_type": "application/json",
                },
            }
            return
        if operation == "read":
            if not page or not path:
                raise InvalidRequest("views.read requires page and path")
            info, chunks = await read_view_file(self.plugin_root, page, path)
            yield {"info": info}
            async for chunk in chunks:
                yield {"chunk": chunk}
            return
        raise NotFound(f"unknown views operation: {operation}")


def _load_legacy_metadata(plugin_root: Path) -> LegacyMetadata:
    # Old plugins may ship without metadata.yaml; the register decorator or
    # class attributes then carry the plugin info, like the in-process
    # loader (name falls back to the directory name).
    metadata_path = plugin_root / "metadata.yaml"
    data = (
        yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        if metadata_path.is_file()
        else {}
    ) or {}
    name = str(data.get("name") or plugin_root.name)
    author = str(data.get("author") or "unknown")
    raw_views = data.get("views") if isinstance(data.get("views"), list) else None
    if raw_views is None and isinstance(data.get("pages"), list):
        raw_views = data.get("pages")
    return LegacyMetadata(
        plugin_id=f"{author.lower()}/{name.lower()}",
        name=name,
        version=str(data.get("version") or "0.0.0"),
        author=author,
        desc=str(data.get("desc") or ""),
        views=tuple(raw_views or ()),
    )


def _find_star_class(module: Any, namespace: str) -> type[Star]:
    candidates = []
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if (
            issubclass(obj, Star)
            and obj is not Star
            and obj.__module__.startswith(namespace)
        ):
            candidates.append(obj)
    if not candidates:
        raise InvalidPluginDefinition(
            f"no Star subclass found in module {module.__name__}"
        )
    # Mirror the in-process loader: the first class named *plugin or "main".
    for obj in candidates:
        lowered = obj.__name__.lower()
        if lowered.endswith("plugin") or lowered == "main":
            return obj
    # Prefer the class defined in the plugin's main module over imported ones.
    exact = [obj for obj in candidates if obj.__module__ == module.__name__]
    if exact:
        return exact[0]
    return candidates[0]


def _compile_filters(
    filters: list,
) -> tuple[HandlerSpec, list]:
    """Compile accumulated legacy filter decorators into one HandlerSpec.

    Returns the spec plus any custom Python filters, which are evaluated
    Runner-side at invoke time.
    """
    resolved_priority = next(
        (int(p) for s in filters if (p := getattr(s, "priority", None)) is not None),
        0,
    )
    for spec in filters:
        if isinstance(spec, HookMarker):
            stage = spec.stage
            if stage.startswith("lifecycle."):
                return HandlerSpec(
                    kind=HandlerKind.LIFECYCLE_STARTUP,
                    priority=resolved_priority,
                ), []
            kind = HOOK_STAGE_KINDS.get(stage)
            if kind is None:
                raise InvalidPluginDefinition(f"unsupported legacy hook stage: {stage}")
            return HandlerSpec(kind=kind, priority=resolved_priority), []
        if isinstance(spec, LLMToolMarker):
            return HandlerSpec(kind=HandlerKind.TOOL, tool_name=spec.name), []

    path = None
    group = False
    aliases: tuple[str, ...] = ()
    regex = None
    regex_flags = 0
    message_types: list[MessageType] = []
    platforms: list[str] = []
    allow_all_platforms = False
    roles: list[SenderRole] = []
    custom_filters = []
    button_action = False
    button_action_id: str | None = None
    ui_action = False
    ui_action_id: str | None = None

    for spec in filters:
        if isinstance(spec, CommandFilter):
            path = spec.command_name
            group = spec.is_group
            aliases = tuple(sorted(spec.alias))
        elif isinstance(spec, ButtonActionFilter):
            button_action = True
            button_action_id = spec.action_id
        elif isinstance(spec, UIActionFilter):
            ui_action = True
            ui_action_id = spec.action_id
        elif isinstance(spec, RegexFilter):
            raw_regex = spec.regex
            if isinstance(raw_regex, re.Pattern):
                # Old plugins may pass a compiled pattern; only its source
                # and flags can cross the protocol boundary.
                regex = raw_regex.pattern
                regex_flags = raw_regex.flags
            else:
                regex = raw_regex
        elif isinstance(spec, EventMessageTypeFilter):
            raw = spec.event_message_type
            from .event import EventMessageType

            values = raw if isinstance(raw, (list | tuple | set)) else [raw]
            for value in values:
                if isinstance(value, str):
                    lowered = value.lower()
                    if lowered in {"all", ""}:
                        continue
                    value = {
                        "groupmessage": EventMessageType.GROUP_MESSAGE,
                        "group": EventMessageType.GROUP_MESSAGE,
                        "friendmessage": EventMessageType.PRIVATE_MESSAGE,
                        "private": EventMessageType.PRIVATE_MESSAGE,
                    }.get(lowered, EventMessageType.OTHER_MESSAGE)
                if value & EventMessageType.GROUP_MESSAGE:
                    message_types.append(MessageType.GROUP)
                if value & EventMessageType.PRIVATE_MESSAGE:
                    message_types.append(MessageType.PRIVATE)
                if value & EventMessageType.OTHER_MESSAGE:
                    message_types.append(MessageType.OTHER)
        elif isinstance(spec, PlatformAdapterTypeFilter):
            from .event import PLATFORM_ADAPTER_NAMES, PlatformAdapterType

            platform_type = spec.platform_type
            if isinstance(platform_type, str):
                platforms.append(platform_type)
            elif isinstance(platform_type, PlatformAdapterType):
                if platform_type & PlatformAdapterType.ALL:
                    allow_all_platforms = True
                else:
                    for member, name in PLATFORM_ADAPTER_NAMES.items():
                        if platform_type & member:
                            platforms.append(name)
            else:
                platforms.append(str(platform_type))
        elif isinstance(spec, PermissionTypeFilter):
            from .event import PermissionType

            if spec.permission_type & PermissionType.ADMIN:
                roles.append(SenderRole.ADMIN)
        elif isinstance(spec, CustomFilter):
            custom_filters.append(spec.custom_filter)

    effective_platforms: tuple[str, ...] = (
        () if allow_all_platforms else tuple(platforms)
    )
    if path is not None:
        sub_command = bool(
            filters
            and isinstance(filters[0], CommandFilter)
            and filters[0].is_sub_command
        )
        group_custom_filters = bool(group and custom_filters)
        return (
            HandlerSpec(
                kind=HandlerKind.COMMAND,
                priority=resolved_priority,
                path=path,
                group=group,
                group_custom_filters=group_custom_filters,
                sub_command=sub_command,
                aliases=aliases,
                message_types=tuple(message_types),
                platforms=effective_platforms,
                roles=tuple(roles),
            ),
            custom_filters,
        )
    return (
        HandlerSpec(
            kind=HandlerKind.MESSAGE,
            priority=resolved_priority,
            message_types=tuple(message_types),
            platforms=effective_platforms,
            roles=tuple(roles),
            regex=regex,
            regex_flags=regex_flags,
            button_action=button_action,
            button_action_id=button_action_id,
            ui_action=ui_action,
            ui_action_id=ui_action_id,
        ),
        custom_filters,
    )


# Legacy docstring tool-param types (llm_tool convention) mapped onto the
# JSON-schema types the handshake understands.
_LEGACY_TOOL_PARAM_TYPES = {
    "string": "string",
    "str": "string",
    "number": "number",
    "int": "number",
    "float": "number",
    "boolean": "boolean",
    "bool": "boolean",
    "object": "object",
    "dict": "object",
    "array": "array",
    "list": "array",
}

_SIGNATURE_TOOL_PARAM_TYPES = {
    str: "string",
    int: "number",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _legacy_tool_params(method: Any) -> list[dict[str, Any]]:
    """Derive tool params from the legacy docstring convention.

    Legacy llm_tool declares parameters in the docstring as
    ``name(type): description`` lines under ``Args:``; when the docstring
    declares no typed params, fall back to the signature annotations.
    """
    doc = inspect.getdoc(method) or ""
    params: list[dict[str, Any]] = []
    in_args = False
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped.rstrip(":") == "Args":
            in_args = True
            continue
        if in_args and (not line.startswith((" ", "\t")) or not stripped):
            if stripped:
                in_args = False
            continue
        if not in_args:
            continue
        match = re.match(r"^(\w+)\s*\(([^)]+)\)\s*:\s*(.*)$", stripped)
        if match:
            name, type_name, description = match.groups()
            json_type = _LEGACY_TOOL_PARAM_TYPES.get(type_name.strip().lower())
            if json_type is not None:
                params.append(
                    {
                        "name": name,
                        "type": json_type,
                        "description": description.strip(),
                        "required": True,
                    },
                )
    if params:
        return params

    signature = inspect.signature(method)
    parameters = list(signature.parameters.values())
    if parameters and parameters[0].name == "self":
        parameters = parameters[1:]
    if parameters:
        # First parameter after self is always the injected event, whatever
        # its name; legacy tools receive it positionally.
        parameters = parameters[1:]
    for param in parameters:
        if param.kind in (
            inspect.Parameter.VAR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        ):
            continue
        annotation = param.annotation
        json_type = _SIGNATURE_TOOL_PARAM_TYPES.get(annotation)
        if json_type is None:
            raise InvalidPluginDefinition(
                f"legacy tool parameter {param.name!r} of {method.__name__} "
                "needs a docstring type or a str/int/float/bool annotation"
            )
        params.append(
            {
                "name": param.name,
                "type": json_type,
                "description": "",
                "required": param.default is inspect.Parameter.empty,
            },
        )
    return params


def _legacy_command_params(method: Any) -> list[dict[str, Any]]:
    """Derive command parameter metadata from a legacy command signature."""
    parameters = list(inspect.signature(method).parameters.values())
    if parameters and parameters[0].name == "self":
        parameters = parameters[1:]
    if parameters:
        # First parameter after self is always the event facade.
        parameters = parameters[1:]
    schema: list[dict[str, Any]] = []
    for param in parameters:
        if param.kind in (
            inspect.Parameter.VAR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        ):
            continue
        ann = param.annotation
        ann_name = (
            ann.__name__ if isinstance(ann, type) else str(ann).rsplit(".", 1)[-1]
        )
        has_default = param.default is not inspect.Parameter.empty
        if ann is GreedyStr or ann_name == "GreedyStr":
            param_type_name = "GreedyStr"
        elif ann in (str, int, float, bool) and isinstance(ann, type):
            param_type_name = ann.__name__
        elif ann_name in {"str", "int", "float", "bool"}:
            param_type_name = ann_name
        elif has_default and type(param.default) in (str, int, float, bool):
            param_type_name = type(param.default).__name__
        else:
            param_type_name = "str"
        schema.append(
            {
                "name": param.name,
                "type": param_type_name,
                "required": not has_default,
                "default": param.default if has_default else None,
            }
        )
    return schema


def _wrap_tool(
    plugin: Star,
    method: Any,
) -> Any:
    """Wrap one legacy llm_tool method into the new tool invoke contract."""

    async def wrapper(call, **kwargs):
        facade = None
        if call.event is not None:
            facade = build_legacy_event(call.event, plugin.context)
        outcome = method(facade, **kwargs)
        if inspect.isasyncgen(outcome):
            # Legacy tools may yield MessageEventResult items; send them
            # proactively and treat the generator as the tool body.
            sdk_ctx = plugin.context._inner
            async for item in outcome:
                translated = translate_compat_result(item, facade)
                message = getattr(translated, "message", None)
                if message is not None and call.umo is not None:
                    await sdk_ctx.messages.send(call.umo, message)
            return None
        returned = await outcome
        from .chatui import ViewResult as CompatViewResult

        if isinstance(returned, CompatViewResult):
            return returned.to_sdk_result()
        return returned

    wrapper.__name__ = method.__name__
    return wrapper


class GreedyStr(str):
    """Legacy marker: captures all remaining text as one argument."""


def _parse_legacy_args(
    method: Any,
    spec: HandlerSpec,
    text: str,
) -> dict[str, Any]:
    """Parse positional command args from the raw message text.

    Mirrors the legacy CommandFilter semantics: whitespace-split tokens after
    the command name, type conversion from annotations, defaults for missing
    optional params, and GreedyStr joining the remainder.
    """
    tokens = text.split()
    # Strip the matched command prefix as a whole: command paths may span
    # multiple tokens (e.g. group sub-commands "group sub"), so match the
    # longest candidate (path or alias) token-by-token instead of just the
    # first token. Only the first token may carry the "/" wake prefix.
    best = 0
    for candidate in (spec.path or "", *spec.aliases):
        parts = candidate.split()
        if not parts or len(parts) > len(tokens) or len(parts) <= best:
            continue
        if [tokens[0].lstrip("/"), *tokens[1 : len(parts)]] == parts:
            best = len(parts)
    tokens = tokens[best:]

    parameters = list(inspect.signature(method).parameters.values())
    if parameters and parameters[0].name == "self":
        parameters = parameters[1:]
    if parameters:
        # The legacy CommandFilter unconditionally treats the first two
        # signature parameters as self and the event, whatever their names
        # (plugins may call the event message, ctx, ...).
        parameters = parameters[1:]

    result: dict[str, Any] = {}
    for index, param in enumerate(parameters):
        annotation = param.annotation
        has_default = param.default is not inspect.Parameter.empty
        is_greedy = (
            annotation is GreedyStr
            or annotation == "GreedyStr"
            or getattr(annotation, "__name__", None) == "GreedyStr"
        )
        if is_greedy:
            result[param.name] = GreedyStr(" ".join(tokens[index:]))
            break
        if index >= len(tokens):
            if has_default:
                result[param.name] = param.default
                continue
            raise InvalidHandlerResult(
                f"missing required argument {param.name!r} for command {spec.path!r}"
            )
        token = tokens[index]
        convert = (
            annotation
            if isinstance(annotation, type)
            else type(
                param.default,
            )
            if has_default
            else str
        )
        if convert is bool:
            lowered = token.lower()
            if lowered in {"true", "yes", "1"}:
                result[param.name] = True
            elif lowered in {"false", "no", "0"}:
                result[param.name] = False
            else:
                raise InvalidHandlerResult(f"argument {param.name!r} must be a boolean")
            continue
        if convert in (str, inspect.Parameter.empty):
            result[param.name] = token
            continue
        try:
            result[param.name] = convert(token)
        except (TypeError, ValueError) as exc:
            raise InvalidHandlerResult(
                f"argument {param.name!r} has the wrong type"
            ) from exc
    return result


async def _execute_llm_request(
    plugin: Any,
    facade: AstrMessageEvent,
    request: Any,
) -> Any:
    """Execute a yielded legacy ProviderRequest via the provider facade.

    Returns a plain MessageEventResult with the completion; the conversation,
    when provided, gets the exchange recorded.
    """
    from .provider import Provider

    compat_ctx = plugin.context if hasattr(plugin, "context") else plugin
    provider = Provider(compat_ctx._inner, umo=facade._event.umo)
    response = await provider.text_chat(
        prompt=request.prompt,
        image_urls=request.image_urls,
        audio_urls=request.audio_urls,
        contexts=request.contexts,
        system_prompt=request.system_prompt,
        func_tool=request.func_tool,
    )
    if request.conversation is not None:
        from ...conversations import Message

        await compat_ctx._inner.conversations.append(
            facade._event.umo,
            request.conversation.cid,
            (
                Message(role="user", content=request.prompt or ""),
                Message(role="assistant", content=response.completion_text),
            ),
        )
    return facade.plain_result(response.completion_text)


def _wrap_handler(
    plugin: Any,
    method: Any,
    spec: HandlerSpec | None = None,
    custom_filters: list | None = None,
) -> Any:
    """Wrap one legacy handler into the new invoke contract."""
    compat_ctx = plugin.context if hasattr(plugin, "context") else plugin

    async def wrapper(event, **kwargs):
        bare_group = bool(kwargs.pop("bare_group", False))
        facade = build_legacy_event(event, compat_ctx)
        try:
            for custom_filter in custom_filters or []:
                # The global config does not cross the isolation boundary; custom
                # filters receive None for the legacy cfg argument.
                try:
                    accepted = custom_filter.filter(facade, None)
                except TypeError:
                    accepted = custom_filter.filter(facade)
                if inspect.isawaitable(accepted):
                    accepted = await accepted
                if not accepted:
                    return
            if bare_group and spec is not None and spec.group:
                from ...results import GroupUsage, Propagation

                yield GroupUsage(propagation=Propagation.STOP)
                return
            if spec is not None and spec.kind is HandlerKind.COMMAND:
                kwargs = {
                    **_parse_legacy_args(method, spec, facade.message_str),
                    **kwargs,
                }
            outcome = method(facade, **kwargs)
            if inspect.isasyncgen(outcome):
                async for item in outcome:
                    from .provider import ProviderRequest as _CompatProviderRequest

                    if isinstance(item, _CompatProviderRequest):
                        item = await _execute_llm_request(plugin, facade, item)
                        if item is None:
                            continue
                    yield translate_compat_result(item, facade)
                return
            returned = await outcome
            if isinstance(returned, MessageEventResult):
                # Legacy handlers may return event.plain_result(...) directly.
                yield returned.to_sdk_result()
            elif returned is not None:
                yield translate_compat_result(returned, facade)
            else:
                result = facade.get_result()
                if result is not None:
                    yield result.to_sdk_result()
                elif facade.is_stopped():
                    from ...results import EventResult, Propagation

                    yield EventResult(propagation=Propagation.STOP)
        finally:
            # Mirror the Host pipeline's event-scoped temp file cleanup.
            facade.cleanup_temporary_local_files()

    wrapper.__name__ = method.__name__
    return wrapper


def _resolve_astrbot_root(plugin_root: Path) -> Path | None:
    """Locate the AstrBot project root that contains the data directory.

    Prefers ASTRBOT_DATA_PATH (set by the Host for runner subprocesses) and
    falls back to the ``<root>/data/plugins/<plugin>`` directory convention.

    Args:
        plugin_root: Resolved plugin directory.

    Returns:
        The AstrBot project root, or None when the layout is unrecognized
        (the caller then anchors a virtual plugin root instead).
    """
    data_path = os.environ.get("ASTRBOT_DATA_PATH")
    if data_path:
        resolved_data = Path(data_path).resolve()
        if (resolved_data / "plugins" / plugin_root.name) == plugin_root:
            return resolved_data.parent
    if (
        plugin_root.parent.name == "plugins"
        and plugin_root.parent.parent.name == "data"
    ):
        return plugin_root.parents[2]
    return None


def load_legacy_plugin(
    plugin_root: str | Path,
    *,
    ctx: Any,
    config: Any = None,
    logger: logging.Logger | None = None,
    host_info: Any = None,
) -> CompatLoadedPlugin:
    """Import one legacy plugin and build new-style registrations.

    Args:
        plugin_root: Plugin directory containing metadata.yaml and main.py.
        ctx: New SDK plugin context used by the compat facade.
        config: Plugin configuration dict.
        logger: Optional logger.
        host_info: Optional Host metadata forwarded during initialization;
            the ``version`` entry feeds astrbot.core.config.default.VERSION.

    Returns:
        The compat loaded plugin.

    Raises:
        PluginImportError: The plugin cannot be imported.
        InvalidPluginDefinition: The plugin definition is unsupported.
    """
    root = Path(plugin_root).resolve()
    metadata = _load_legacy_metadata(root)

    host_version = None
    if isinstance(host_info, Mapping):
        version = host_info.get("version")
        host_version = str(version) if version else None
    compat_api.install(host_version=host_version)
    # Multiprocessing spawn children are fresh interpreters; this env flag lets
    # astrbot_sdk.runtime.__main__ reinstall the shims during spawn fixup.
    os.environ.setdefault("ASTRBOT_SDK_LEGACY_RUNNER", "1")
    if host_version:
        os.environ.setdefault("ASTRBOT_HOST_VERSION", host_version)
    import importlib

    # Mirror the in-process loader: import as data.plugins.<dir>.main so module
    # identity (__name__, ModuleSpec, __package__) is byte-for-byte identical.
    # Framework introspection (Flask/Quart instance paths, importlib.resources)
    # and spawned multiprocessing children depend on the real dotted path.
    package = f"data.plugins.{root.name}"
    astrbot_root = _resolve_astrbot_root(root)
    if astrbot_root is not None:
        if str(astrbot_root) not in sys.path:
            sys.path.insert(0, str(astrbot_root))
    else:
        # Remote runner: no AstrBot root on disk. Anchor the same dotted
        # path through an in-memory namespace package instead.
        from ...runtime.loader import install_virtual_plugin_root

        install_virtual_plugin_root(root)
    if (root / "main.py").is_file():
        module_name = f"{package}.main"
    elif (root / f"{root.name}.py").is_file():
        module_name = f"{package}.{root.name}"
    elif (root / "__init__.py").is_file():
        module_name = package
    else:
        module_name = f"{package}.main"

    # Bind the legacy facades before any plugin code runs: plugins may touch
    # StarTools/sp/html_renderer at module import time (top-level statements
    # and class-body defaults execute during import_module).
    from .star import CompatConfig

    if config is not None and not isinstance(config, CompatConfig):
        config = CompatConfig(config, ctx=ctx)
    snapshot = host_info.get("snapshot") if isinstance(host_info, Mapping) else None
    context = CompatContext(ctx, config=config, snapshot=snapshot)
    from .star import StarTools

    StarTools.initialize(context)
    from .html import HtmlRendererFacade

    HtmlRendererFacade.initialize(ctx)
    from .api import _SharedPreferences
    from .host_snapshot import FileTokenServiceFacade

    _SharedPreferences.initialize(ctx)
    FileTokenServiceFacade.initialize(ctx)

    raw_handlers = (
        (snapshot or {}).get("handlers") if isinstance(snapshot, Mapping) else None
    )
    if isinstance(raw_handlers, list):
        star_handler_mod = sys.modules.get("astrbot.core.star.star_handler")
        if star_handler_mod is not None:
            entries = [
                SimpleNamespace(
                    **{
                        **dict(entry),
                        "event_type": getattr(
                            star_handler_mod.EventType,
                            str(entry.get("event_type") or ""),
                            entry.get("event_type"),
                        ),
                    }
                )
                for entry in raw_handlers
                if isinstance(entry, Mapping)
            ]
            star_handler_mod.star_handlers_registry.clear()
            star_handler_mod.star_handlers_registry.extend(entries)

    # Legacy plugins may bare-import sibling modules (import helpers); the
    # in-process loader keeps plugin dirs on sys.path, so mirror that.
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    # Drop stale modules so a reload re-executes the package code,
    # mirroring the in-process loader.
    for name in [
        item
        for item in tuple(sys.modules)
        if item == package or item.startswith(f"{package}.")
    ]:
        del sys.modules[name]
    importlib.invalidate_caches()
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        raise PluginImportError(f"failed to import legacy plugin: {exc}") from exc

    star_class = _find_star_class(module, package)
    declared = getattr(star_class, "__astrbot_register__", None)
    if declared and not metadata.desc:
        # The in-process loader prioritizes metadata.yaml over the deprecated
        # register decorator, so decorator values only fill fields the yaml
        # file leaves empty. Some plugins pass empty strings to the decorator
        # (e.g. an empty version), which must not clobber the yaml metadata.
        metadata = LegacyMetadata(
            plugin_id=metadata.plugin_id,
            name=metadata.name,
            version=metadata.version,
            author=metadata.author,
            desc=str(declared.get("desc") or ""),
            views=metadata.views,
        )
    # Old loaders inject the plugin name as a class attribute before
    # instantiation; plugins rely on self.name during __init__.
    star_class.name = metadata.name
    try:
        if config is not None:
            instance = star_class(context, config)
        else:
            # Mirror the in-process loader: without a _conf_schema.json the
            # constructor receives only Context.
            instance = star_class(context)
    except TypeError:
        try:
            instance = star_class(context, config)
        except TypeError:
            try:
                instance = star_class(context)
            except TypeError as exc:
                raise InvalidPluginDefinition(
                    f"{star_class.__name__} must accept Context and optional config"
                ) from exc

    registrations: list[HandlerRegistration] = []
    for method_name in dir(instance):
        # Read the raw class attribute first: arbitrary properties on the
        # instance may raise or perform side effects, and they can never be
        # decorated handlers anyway.
        raw = inspect.getattr_static(instance, method_name)
        if isinstance(raw, _CommandGroup):
            # The command_group decorator replaces the class attribute with
            # this handle: the anchor's own filters live on raw.handler,
            # while decorators applied above command_group accumulate onto
            # the handle itself.
            anchor = raw.handler
            if anchor is None:
                continue
            filters = [
                *getattr(raw, _FILTERS_ATTR, ()),
                *getattr(anchor, _FILTERS_ATTR, ()),
            ]
            if not filters:
                continue
            method = anchor.__get__(instance, type(instance))
        else:
            filters = getattr(raw, _FILTERS_ATTR, None)
            if not filters:
                continue
            method = getattr(instance, method_name)
        spec, custom_filters = _compile_filters(filters)
        if spec.kind is HandlerKind.TOOL:
            handler = _wrap_tool(instance, method)
            handler.__tool_params__ = _legacy_tool_params(method)
        elif spec.kind in (HandlerKind.COMMAND, HandlerKind.MESSAGE):
            handler = _wrap_handler(instance, method, spec, custom_filters)
            if spec.kind is HandlerKind.COMMAND:
                handler.__command_params__ = _legacy_command_params(method)
        else:
            # Hook and lifecycle handlers keep their legacy signature; the
            # invoke paths adapt arguments per stage.
            handler = method
        spec = HandlerSpec(
            kind=spec.kind,
            id=method_name,
            description=inspect.getdoc(method),
            priority=spec.priority,
            path=spec.path,
            group=spec.group,
            group_custom_filters=spec.group_custom_filters,
            sub_command=spec.sub_command,
            aliases=spec.aliases,
            tool_name=spec.tool_name,
            message_types=spec.message_types,
            platforms=spec.platforms,
            roles=spec.roles,
            regex=spec.regex,
            regex_flags=spec.regex_flags,
            button_action=spec.button_action,
            button_action_id=spec.button_action_id,
            ui_action=spec.ui_action,
            ui_action_id=spec.ui_action_id,
        )
        registrations.append(
            HandlerRegistration(
                id=method_name,
                method_name=method_name,
                spec=spec,
                handler=handler,
            ),
        )

    star_handler_mod = sys.modules.get("astrbot.core.star.star_handler")
    if star_handler_mod is not None and isinstance(
        getattr(star_handler_mod, "star_handlers_registry", None), list
    ):
        existing_names = {
            getattr(item, "handler_full_name", "")
            for item in star_handler_mod.star_handlers_registry
        }
        event_type_cls = star_handler_mod.EventType
        for reg in registrations:
            full_name = f"{module_name}_{reg.method_name}"
            if full_name in existing_names:
                continue
            ev_type = (
                event_type_cls.AdapterMessageEvent
                if reg.spec.kind in (HandlerKind.COMMAND, HandlerKind.MESSAGE)
                else reg.spec.kind.value
            )
            star_handler_mod.star_handlers_registry.append(
                SimpleNamespace(
                    event_type=ev_type,
                    handler_full_name=full_name,
                    handler_name=reg.method_name,
                    handler_module_path=module_name,
                    desc=reg.spec.description or "",
                    enabled=True,
                    priority=reg.spec.priority,
                    plugin_name=metadata.name,
                    plugin_activated=True,
                    plugin_reserved=False,
                    filters=[],
                )
            )

    return CompatLoadedPlugin(
        metadata=metadata,
        instance=instance,
        registrations=tuple(registrations),
        plugin_root=root,
    )
