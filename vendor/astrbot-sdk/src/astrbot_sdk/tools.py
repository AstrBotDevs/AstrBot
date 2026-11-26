from __future__ import annotations

import inspect
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Annotated, Any, ClassVar, get_args, get_origin, get_type_hints

from .errors import InvalidPluginDefinition
from .events import UMO, MessageEvent
from .protocol_registry import register_protocol_dataclass


@register_protocol_dataclass
@dataclass(frozen=True, slots=True)
class ToolCallContext:
    """Context of one LLM tool invocation.

    Carries call-scoped data (id, umo, event) plus the plugin context. The
    plugin context is a live object attached by the Runner and never crosses
    the protocol; ``event`` is None for calls not originating from a message.
    """

    id: str
    umo: UMO | None = None
    event: MessageEvent | None = None
    ctx: Any = None


@register_protocol_dataclass
@dataclass(frozen=True, slots=True)
class ToolParam:
    """One JSON-schema-style tool parameter declaration."""

    name: str
    type: str
    description: str = ""
    required: bool = True


@register_protocol_dataclass
@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Public definition of one LLM tool."""

    name: str
    description: str
    params: tuple[ToolParam, ...] = ()
    resumable: bool = False
    streaming_input: bool = False


@register_protocol_dataclass
@dataclass(frozen=True, slots=True)
class ToolRef:
    """Handle of one dynamically registered tool."""

    name: str
    handler_id: str


ToolHandler = Callable[..., Awaitable[Any]]


class Tool:
    """Base class for self-contained dynamic tools.

    Subclasses declare ``name``/``description`` (and optionally ``params``)
    as class attributes and implement ``call``. The instance stays inside the
    plugin process; only the definition crosses to the Host. ``params`` is
    derived from the call() type annotations when omitted. The legacy ``run``
    method name is intentionally not supported here; the legacy compatibility
    layer handles it.
    """

    name: ClassVar[str]
    description: ClassVar[str] = ""
    params: ClassVar[tuple[ToolParam, ...] | None] = None

    async def call(self, *args: Any, **kwargs: Any) -> Any:
        """Implement the tool. May declare a leading ToolCallContext."""
        raise NotImplementedError


_JSON_SCHEMA_TYPES = {
    str: "string",
    int: "number",
    float: "number",
    bool: "boolean",
}


def _annotation_name(annotation: Any) -> str:
    """Return the bare class name of one annotation, string form included."""
    if isinstance(annotation, str):
        return annotation.rsplit(".", 1)[-1]
    return getattr(annotation, "__name__", "")


def is_tool_context_param(param: inspect.Parameter) -> bool:
    """Check whether one parameter is the ToolCallContext injection slot."""
    annotation = param.annotation
    if annotation is ToolCallContext:
        return True
    if _annotation_name(annotation) == "ToolCallContext":
        return True
    return param.name in {"call", "context"} and (
        param.annotation is inspect.Parameter.empty
    )


def tool_params_schema(
    handler: Callable[..., Any],
    *,
    handler_label: str = "tool",
) -> list[ToolParam]:
    """Derive JSON-schema-style parameters from a tool handler signature.

    Descriptions come from Annotated metadata (a plain string or an object
    with a ``description`` attribute, such as pydantic's Field).

    Args:
        handler: Tool handler (bound method or plain callable).
        handler_label: Label used in error messages.

    Returns:
        Ordered parameter declarations.

    Raises:
        InvalidPluginDefinition: A parameter uses an unsupported type.
    """
    try:
        hints = get_type_hints(handler, include_extras=True)
    except Exception:  # noqa: BLE001 - unresolved forward refs fall back to raw
        hints = {}

    parameters = list(inspect.signature(handler).parameters.values())
    if parameters and parameters[0].name == "self":
        parameters = parameters[1:]
    if parameters and is_tool_context_param(parameters[0]):
        parameters = parameters[1:]

    params: list[ToolParam] = []
    for param in parameters:
        if param.kind in (
            inspect.Parameter.VAR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        ):
            continue
        if is_tool_context_param(param):
            raise InvalidPluginDefinition(
                "the ToolCallContext injection must be the first tool parameter"
            )
        annotation = hints.get(param.name, param.annotation)
        description = None
        if get_origin(annotation) is Annotated:
            candidates = get_args(annotation)
            annotation = candidates[0]
            for item in candidates[1:]:
                if isinstance(item, str):
                    description = item
                elif hasattr(item, "description"):
                    description = getattr(item, "description", None)
        json_type = _JSON_SCHEMA_TYPES.get(annotation)
        if json_type is None:
            raise InvalidPluginDefinition(
                f"tool parameter {param.name!r} of {handler_label} "
                "must use str, int, float or bool"
            )
        params.append(
            ToolParam(
                name=param.name,
                type=json_type,
                description=description or "",
                required=param.default is inspect.Parameter.empty,
            ),
        )
    return params


def _description_of(handler: Callable[..., Any]) -> str | None:
    """Return the first paragraph of a handler's docstring."""
    doc = inspect.getdoc(handler)
    if not doc:
        return None
    return " ".join(doc.split("\n\n", 1)[0].splitlines())


class ToolService:
    """Register and remove dynamic LLM tools at runtime."""

    def __init__(self, ctx: Any) -> None:
        """Initialize the service.

        Args:
            ctx: Owning plugin context used for Host invocation.
        """
        self._ctx = ctx

    async def register(
        self,
        tool: ToolDefinition | ToolHandler,
        handler: ToolHandler | None = None,
    ) -> ToolRef:
        """Register one dynamic tool with the Host agent.

        The common case takes only the handler: the tool name defaults to its
        ``__name__``, the description to the first paragraph of its docstring,
        and the parameter schema is derived from its type annotations. Pass an
        explicit ToolDefinition to override any of these.

        Args:
            tool: Tool definition, or the handler itself.
            handler: Async callable implementing the tool, required when the
                first argument is a ToolDefinition. It may declare a leading
                ToolCallContext injection parameter.

        Returns:
            Reference used for unregister.

        Raises:
            InvalidPluginDefinition: The handler is invalid.
            CapabilityDenied: llm.tool.register was not granted.
        """
        declared_params: tuple[ToolParam, ...] | None = None
        if isinstance(tool, Tool):
            instance = tool
            if not isinstance(instance.name, str) or not instance.name:
                raise InvalidPluginDefinition("tool class must declare a name")
            handler = instance.call
            declared_params = instance.params
            tool = ToolDefinition(
                name=instance.name,
                description=(
                    instance.description
                    or _description_of(instance.call)
                    or instance.name
                ),
                params=instance.params if instance.params is not None else (),
            )
        elif handler is None:
            if not callable(tool) or isinstance(tool, ToolDefinition):
                raise InvalidPluginDefinition(
                    "register requires a handler, a Tool, or a ToolDefinition"
                )
            handler = tool
            tool = ToolDefinition(
                name=handler.__name__,
                description=_description_of(handler) or handler.__name__,
            )
        if not inspect.iscoroutinefunction(handler):
            raise InvalidPluginDefinition("dynamic tool handler must be async")
        params = (
            tool.params
            if declared_params is not None
            else tuple(tool_params_schema(handler, handler_label=f"tool {tool.name!r}"))
        )
        definition = ToolDefinition(
            name=tool.name,
            description=tool.description,
            params=params,
        )
        handler_id = f"dynamic:{uuid.uuid4().hex[:16]}"
        self._ctx._register_dynamic_tool(handler_id, handler)
        try:
            await self._ctx._invoke_capability(
                "llm.tool.register",
                "register",
                {"definition": definition, "handler_id": handler_id},
            )
        except Exception:
            self._ctx._unregister_dynamic_tool(handler_id)
            raise
        return ToolRef(name=tool.name, handler_id=handler_id)

    async def unregister(self, tool: ToolRef) -> None:
        """Remove one dynamically registered tool.

        Args:
            tool: Reference returned by register.
        """
        await self._ctx._invoke_capability(
            "llm.tool.register",
            "unregister",
            {"name": tool.name, "handler_id": tool.handler_id},
        )
        self._ctx._unregister_dynamic_tool(tool.handler_id)

    async def update_runtime_tools(
        self,
        tools: Sequence[tuple[ToolDefinition, ToolHandler] | Tool],
    ) -> list[ToolRef]:
        """Replace the plugin's dynamic runtime tool catalog atomically.

        Args:
            tools: Sequence of `(ToolDefinition, handler)` pairs or `Tool` objects.

        Returns:
            List of registered `ToolRef` handles.
        """
        entries: list[tuple[ToolDefinition, ToolHandler, str]] = []
        for item in tools:
            if isinstance(item, Tool):
                if not isinstance(item.name, str) or not item.name:
                    raise InvalidPluginDefinition("tool class must declare a name")
                handler = item.call
                params = (
                    item.params
                    if item.params is not None
                    else tuple(
                        tool_params_schema(
                            handler,
                            handler_label=f"tool {item.name!r}",
                        )
                    )
                )
                defn = ToolDefinition(
                    name=item.name,
                    description=(
                        item.description or _description_of(handler) or item.name
                    ),
                    params=params,
                )
            else:
                defn, handler = item
                if not inspect.iscoroutinefunction(handler):
                    raise InvalidPluginDefinition("runtime tool handler must be async")
                if not defn.params:
                    defn = ToolDefinition(
                        name=defn.name,
                        description=defn.description,
                        params=tuple(
                            tool_params_schema(
                                handler,
                                handler_label=f"tool {defn.name!r}",
                            )
                        ),
                        resumable=defn.resumable,
                        streaming_input=defn.streaming_input,
                    )
            handler_id = f"runtime:{defn.name}"
            entries.append((defn, handler, handler_id))

        for _, handler, handler_id in entries:
            self._ctx._register_dynamic_tool(handler_id, handler)

        await self._ctx._invoke_capability(
            "llm.tool.register",
            "replace_runtime",
            {
                "tools": [
                    {"definition": defn, "handler_id": handler_id}
                    for defn, _, handler_id in entries
                ]
            },
        )
        return [
            ToolRef(name=defn.name, handler_id=handler_id)
            for defn, _, handler_id in entries
        ]
