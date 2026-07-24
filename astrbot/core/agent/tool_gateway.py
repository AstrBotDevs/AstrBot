from __future__ import annotations

import asyncio
import inspect
import time
import uuid
from collections import defaultdict, deque
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from typing import Any

import jsonschema
import mcp

from astrbot import logger

from .evidence_store import get_agent_evidence_store
from .run_context import ContextWrapper
from .supervisor import completion_check_for_tool
from .tool import FunctionTool, ToolOutcome


@dataclass(slots=True)
class ToolDescriptor:
    """Validated metadata exposed by the capability broker."""

    name: str
    description: str
    parameters: dict[str, Any]
    provider: str = "astrbot"
    plugin: str = ""
    risk: str = "R3"
    read_only: bool = False
    idempotent: bool = False
    resource_group: str = "plugin"
    fallback_group: str = ""
    evidence_requirements: list[str] = field(default_factory=list)
    output_schema: dict[str, Any] | None = None
    timeout_seconds: float = 120.0
    direct_send: bool = False
    active: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible capability descriptor."""

        return asdict(self)


class ToolContractError(ValueError):
    """Raised when a tool descriptor or argument contract is invalid."""


class ToolResourceScheduler:
    """Bounded async resource pools shared by every Agent tool invocation."""

    LIMITS = {
        "main_llm": 4,
        "fast": 1,
        "deep": 1,
        "realtime_search": 2,
        "browser": 2,
        "vision": 2,
        "vision_deep": 1,
        "office": 1,
        "plugin": 3,
    }

    def __init__(self) -> None:
        self._semaphores = {
            name: asyncio.Semaphore(limit) for name, limit in self.LIMITS.items()
        }
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._breakers: dict[str, float] = {}

    @asynccontextmanager
    async def lease(self, tool: FunctionTool, session_id: str, timeout: float):
        """Acquire a resource and session lease immediately before execution.

        Args:
            tool: Tool whose resource metadata determines the pool.
            session_id: Unified message origin used for per-session ordering.
            timeout: Maximum queue wait in seconds.

        Yields:
            Nothing; the context owns and releases both leases.

        Raises:
            TimeoutError: If the resource or session queue exceeds the deadline.
            RuntimeError: If the tool circuit is open.
        """

        name = tool.name
        breaker_until = self._breakers.get(name, 0.0)
        if breaker_until > time.time():
            raise RuntimeError("tool_circuit_open")
        group = str(getattr(tool, "resource_group", "plugin") or "plugin")
        semaphore = self._semaphores.setdefault(
            group, asyncio.Semaphore(self.LIMITS.get("plugin", 3))
        )
        lock = None
        lock_acquired = False
        if session_id:
            lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        bounded_timeout = max(0.1, min(float(timeout), 120.0))
        await asyncio.wait_for(semaphore.acquire(), timeout=bounded_timeout)
        try:
            if lock is not None:
                await asyncio.wait_for(lock.acquire(), timeout=bounded_timeout)
                lock_acquired = True
            yield
        finally:
            # Only the task that acquired a session lock may release it. A
            # timed-out waiter must never unlock the task currently executing.
            if lock is not None and lock_acquired:
                lock.release()
            semaphore.release()

    def observe(self, tool_name: str, status: str) -> None:
        """Update a five-minute per-tool circuit breaker from an outcome."""

        now = time.time()
        failures = self._failures[tool_name]
        while failures and now - failures[0] > 300:
            failures.popleft()
        if status in {"success", "direct_sent", "cancelled"}:
            failures.clear()
            self._breakers.pop(tool_name, None)
            return
        failures.append(now)
        if len(failures) >= 2:
            self._breakers[tool_name] = now + 300

    def snapshot(self) -> dict[str, Any]:
        """Return bounded scheduler and breaker metrics for diagnostics."""

        return {
            "resources": {
                name: {"limit": limit, "available": self._semaphores[name]._value}
                for name, limit in self.LIMITS.items()
            },
            "breakers": {
                name: max(0, int(until - time.time()))
                for name, until in self._breakers.items()
                if until > time.time()
            },
        }


class ToolGateway:
    """Single normalized invocation boundary for local and MCP tools."""

    scheduler = ToolResourceScheduler()

    @staticmethod
    def describe(tool: FunctionTool) -> ToolDescriptor:
        """Build a descriptor from a registered FunctionTool.

        Args:
            tool: Registered tool instance.

        Returns:
            Normalized descriptor used by discovery and planning.

        Raises:
            ToolContractError: If the name, description or JSON Schema is invalid.
        """

        name = str(getattr(tool, "name", "")).strip()
        description = str(getattr(tool, "description", "")).strip()
        parameters = getattr(tool, "parameters", None) or {
            "type": "object",
            "properties": {},
        }
        if not name:
            raise ToolContractError("tool name is empty")
        if not description:
            raise ToolContractError(f"tool {name!r} has an empty description")
        try:
            jsonschema.Draft202012Validator.check_schema(parameters)
        except jsonschema.SchemaError as exc:
            raise ToolContractError(f"tool {name!r} has invalid schema: {exc}") from exc
        output_schema = getattr(tool, "output_schema", None)
        if output_schema is not None:
            try:
                jsonschema.Draft202012Validator.check_schema(output_schema)
            except jsonschema.SchemaError as exc:
                raise ToolContractError(
                    f"tool {name!r} has invalid output schema: {exc}"
                ) from exc
        raw_evidence_requirements = getattr(tool, "evidence_requirements", None)
        if isinstance(raw_evidence_requirements, (list, tuple, set)):
            evidence_requirements = [
                str(item).strip()
                for item in raw_evidence_requirements
                if str(item).strip()
            ]
        else:
            # Older plugins may expose an unmaterialized Pydantic FieldInfo.
            evidence_requirements = []
        return ToolDescriptor(
            name=name,
            description=description[:4000],
            parameters=parameters,
            provider=str(getattr(tool, "provider", "astrbot") or "astrbot"),
            plugin=str(getattr(tool, "plugin", "") or ""),
            risk=str(getattr(tool, "risk", "R3") or "R3"),
            read_only=bool(getattr(tool, "read_only", False)),
            idempotent=bool(getattr(tool, "idempotent", False)),
            resource_group=str(getattr(tool, "resource_group", "plugin") or "plugin"),
            fallback_group=str(getattr(tool, "fallback_group", "") or ""),
            evidence_requirements=evidence_requirements,
            output_schema=output_schema,
            timeout_seconds=max(
                0.1, min(float(getattr(tool, "timeout_seconds", 120.0) or 120.0), 120.0)
            ),
            direct_send=bool(getattr(tool, "direct_send", False)),
            active=bool(getattr(tool, "active", True)),
        )

    @staticmethod
    def validate_arguments(
        tool: FunctionTool, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Validate and return a copy of tool arguments.

        Args:
            tool: Registered tool with a JSON Schema.
            arguments: Model-provided arguments.

        Returns:
            A validated argument dictionary.

        Raises:
            ToolContractError: If the arguments do not satisfy the Schema.
        """

        if not isinstance(arguments, dict):
            raise ToolContractError("tool arguments must be an object")
        schema = getattr(tool, "parameters", None) or {
            "type": "object",
            "properties": {},
        }
        validator = jsonschema.Draft202012Validator(schema)
        errors = sorted(
            validator.iter_errors(arguments), key=lambda item: list(item.path)
        )
        if errors:
            detail = "; ".join(error.message for error in errors[:3])
            raise ToolContractError(f"invalid arguments for {tool.name}: {detail}")
        properties = schema.get("properties", {})
        if isinstance(properties, dict) and schema.get("additionalProperties") is False:
            return {key: arguments[key] for key in properties if key in arguments}
        return dict(arguments)

    @staticmethod
    def _normalize(value: Any) -> ToolOutcome:
        if isinstance(value, ToolOutcome):
            return value
        if isinstance(value, mcp.types.CallToolResult):
            has_content = bool(value.content or value.structuredContent)
            return ToolOutcome(
                status=(
                    "failed" if value.isError else "success" if has_content else "empty"
                ),
                result=value,
                retryable=bool(value.isError or not has_content),
                error_code="mcp_error"
                if value.isError
                else ""
                if has_content
                else "empty_result",
            )
        if value is None:
            return ToolOutcome(
                status="empty",
                retryable=True,
                error_code="empty_result",
                diagnostics="Tool returned no value.",
                result=mcp.types.CallToolResult(
                    content=[
                        mcp.types.TextContent(
                            type="text",
                            text="error: tool returned no usable result",
                        )
                    ],
                    isError=True,
                ),
            )
        text = str(value).strip()
        return ToolOutcome(
            status="success" if text else "empty",
            retryable=not bool(text),
            error_code="" if text else "empty_result",
            result=mcp.types.CallToolResult(
                content=[
                    mcp.types.TextContent(
                        type="text", text=text or "error: empty result"
                    )
                ],
                isError=not bool(text),
            ),
        )

    @classmethod
    async def invoke(
        cls,
        executor: Callable[..., AsyncGenerator[Any, None]],
        tool: FunctionTool,
        run_context: ContextWrapper[Any],
        **arguments: Any,
    ) -> AsyncGenerator[ToolOutcome, None]:
        """Invoke one tool through validation, tracing and result normalization.

        Args:
            executor: Existing executor callback for compatibility with AstrBot.
            tool: Registered tool to execute.
            run_context: Authenticated Agent execution context.
            **arguments: Model-provided tool arguments.

        Yields:
            Normalized outcomes. Empty and failed outcomes remain visible to the Agent.
        """

        event = getattr(getattr(run_context, "context", None), "event", None)
        trace_id = ""
        if event is not None and hasattr(event, "get_extra"):
            trace_id = str(event.get_extra("agent_trace_id") or "")
        if not trace_id:
            trace_id = f"trace-{uuid.uuid4().hex}"
            if event is not None and hasattr(event, "set_extra"):
                event.set_extra("agent_trace_id", trace_id)
        store = get_agent_evidence_store()
        trace_started = bool(
            event is not None
            and hasattr(event, "get_extra")
            and event.get_extra("agent_trace_started", False)
        )
        if not trace_started:
            store.start_run(
                trace_id=trace_id,
                session_id=str(getattr(event, "unified_msg_origin", "unknown")),
                principal_id=str(getattr(event, "get_sender_id", lambda: "unknown")()),
                goal=str(getattr(event, "message_str", ""))[:4000],
                route="tool",
            )
            if event is not None and hasattr(event, "set_extra"):
                event.set_extra("agent_trace_started", True)
        attempt_id = store.start_attempt(
            trace_id=trace_id,
            tool_name=tool.name,
            tool_version=str(getattr(tool, "version", "unknown") or "unknown"),
            arguments=arguments,
        )
        store.update_phase(trace_id, "RUNNING_TOOL")
        final: ToolOutcome | None = None
        arguments_hash = store._hash(arguments)
        started_monotonic = time.monotonic()
        try:
            try:
                valid_arguments = cls.validate_arguments(tool, arguments)
            except ToolContractError as exc:
                final = ToolOutcome(
                    status="failed",
                    retryable=False,
                    error_code="invalid_arguments",
                    diagnostics=str(exc)[:1000],
                    result=mcp.types.CallToolResult(
                        content=[
                            mcp.types.TextContent(type="text", text=f"error: {exc}")
                        ],
                        isError=True,
                    ),
                )
                yield final
                return
            event = getattr(getattr(run_context, "context", None), "event", None)
            session_id = str(getattr(event, "unified_msg_origin", "") or "")
            timeout = float(getattr(run_context, "tool_call_timeout", 120) or 120)
            timeout = min(
                max(0.1, timeout),
                max(
                    0.1,
                    min(float(getattr(tool, "timeout_seconds", 120.0) or 120.0), 120.0),
                ),
            )

            # A model can accidentally repeat an identical call forever. Keep the
            # guard scoped to the current event/run so separate requests are not
            # affected by one another.
            arguments_hash = store._hash(valid_arguments)
            if event is not None and hasattr(event, "get_extra"):
                call_counts = event.get_extra("agent_tool_call_counts", {})
                if not isinstance(call_counts, dict):
                    call_counts = {}
                call_key = f"{tool.name}:{arguments_hash}"
                current_count = int(call_counts.get(call_key, 0) or 0)
                breaker_open = cls.scheduler._breakers.get(tool.name, 0.0) > time.time()
                if current_count >= 2 and not breaker_open:
                    final = ToolOutcome(
                        status="failed",
                        retryable=False,
                        error_code="repeated_tool_call",
                        diagnostics="The same tool and arguments were already attempted twice.",
                        result=mcp.types.CallToolResult(
                            content=[
                                mcp.types.TextContent(
                                    type="text",
                                    text="error: repeated identical tool call blocked",
                                )
                            ],
                            isError=True,
                        ),
                    )
                    yield final
                    return
                call_counts[call_key] = current_count + 1
                event.set_extra("agent_tool_call_counts", call_counts)
            try:
                async with cls.scheduler.lease(tool, session_id, timeout):
                    yielded = False
                    # Keep executor creation, any awaitable returned by the
                    # executor, and generator iteration inside one watchdog.
                    # Some legacy executors await an internal queue before
                    # returning their async generator; placing only iteration
                    # under the timeout leaves that queue unbounded.
                    async with asyncio.timeout(timeout):
                        stream = executor(tool, run_context, **valid_arguments)
                        if inspect.isawaitable(stream):
                            stream = await stream
                        async for raw in stream:
                            yielded = True
                            outcome = cls._normalize(raw)
                            if (
                                outcome.status == "success"
                                and outcome.result is not None
                                and getattr(tool, "output_schema", None)
                                and outcome.result.structuredContent is not None
                            ):
                                try:
                                    jsonschema.validate(
                                        outcome.result.structuredContent,
                                        tool.output_schema,
                                        cls=jsonschema.Draft202012Validator,
                                    )
                                except jsonschema.ValidationError as exc:
                                    outcome = ToolOutcome(
                                        status="failed",
                                        retryable=bool(
                                            getattr(tool, "read_only", False)
                                        ),
                                        error_code="invalid_output",
                                        diagnostics=str(exc)[:1000],
                                        result=mcp.types.CallToolResult(
                                            content=[
                                                mcp.types.TextContent(
                                                    type="text",
                                                    text="error: tool output did not match its schema",
                                                )
                                            ],
                                            isError=True,
                                        ),
                                    )
                            final = outcome
                            yield outcome
                    if not yielded:
                        final = cls._normalize(None)
                        yield final
            except RuntimeError as exc:
                if str(exc) != "tool_circuit_open":
                    raise
                final = ToolOutcome(
                    status="failed",
                    retryable=False,
                    error_code="tool_circuit_open",
                    diagnostics="Tool is temporarily paused after repeated failures.",
                    result=mcp.types.CallToolResult(
                        content=[
                            mcp.types.TextContent(
                                type="text",
                                text="error: tool temporarily paused after repeated failures",
                            )
                        ],
                        isError=True,
                    ),
                )
                yield final
            except asyncio.TimeoutError:
                final = ToolOutcome(
                    status="timeout",
                    retryable=bool(getattr(tool, "read_only", False)),
                    error_code="tool_timeout",
                    diagnostics="Tool exceeded its queue or execution deadline.",
                    result=mcp.types.CallToolResult(
                        content=[
                            mcp.types.TextContent(
                                type="text", text="error: tool queue/execution timeout"
                            )
                        ],
                        isError=True,
                    ),
                )
                yield final
        except asyncio.CancelledError:
            final = ToolOutcome(
                status="cancelled",
                retryable=False,
                error_code="cancelled",
                diagnostics="Tool invocation cancelled.",
            )
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unified tool gateway failed for %s", tool.name)
            final = ToolOutcome(
                status="failed",
                retryable=bool(getattr(tool, "read_only", False)),
                error_code="tool_gateway_error",
                diagnostics=str(exc)[:1000],
                result=mcp.types.CallToolResult(
                    content=[
                        mcp.types.TextContent(
                            type="text", text=f"error: tool gateway failed: {exc!s}"
                        )
                    ],
                    isError=True,
                ),
            )
            yield final
        finally:
            if final is not None:
                final.trace_id = trace_id
                final.attempt_id = attempt_id
                final.arguments_hash = arguments_hash
                final.elapsed_ms = max(
                    0, int((time.monotonic() - started_monotonic) * 1000)
                )
                if final.result is not None:
                    final.content = "\n".join(
                        str(getattr(item, "text", "") or "")
                        for item in final.result.content
                        if getattr(item, "text", None)
                    )[:65536]
                    final.structured_content = final.result.structuredContent
            output = final.result if final is not None else None
            store.finish_attempt(
                attempt_id=attempt_id,
                status=final.status if final is not None else "empty",
                error_code=final.error_code if final is not None else "empty_result",
                output=output,
            )
            if final is not None and final.error_code != "invalid_arguments":
                cls.scheduler.observe(tool.name, final.status)
            if final is not None and final.status in {"success", "direct_sent"}:
                source_url = ""
                if final.result and final.result.structuredContent:
                    source_url = str(
                        final.result.structuredContent.get("source_url", "")
                    )[:500]
                evidence_id = store.record_evidence(
                    trace_id=trace_id,
                    attempt_id=attempt_id,
                    source_name=tool.name,
                    content=output or "",
                    source_url=source_url,
                    freshness="live" if source_url else "unknown",
                    confidence=1.0,
                )
                final.evidence_ids.append(evidence_id)
            if final is not None:
                # Completion is deterministic and recorded after evidence is
                # attached; the model may observe this decision but cannot
                # override policy or claim success without the required proof.
                plan = (
                    event.get_extra(
                        "agent_tool_plan",
                        event.get_extra("agent_control_tool_plan", {})
                        if hasattr(event, "get_extra")
                        else {},
                    )
                    if event is not None and hasattr(event, "get_extra")
                    else {}
                )
                decision = completion_check_for_tool(final, tool, plan)
                if event is not None and hasattr(event, "set_extra"):
                    event.set_extra("agent_completion_decision", decision.to_dict())
                if not decision.complete and final.status == "success":
                    store.update_phase(
                        trace_id,
                        "OBSERVING",
                        reason=decision.reason,
                    )
            if final is not None and final.status not in {"success", "direct_sent"}:
                store.update_phase(
                    trace_id,
                    "OBSERVING",
                    reason=final.error_code or final.status,
                )
            if not trace_started:
                store.finish_run(
                    trace_id,
                    final.status if final is not None else "empty",
                )
                if event is not None and hasattr(event, "set_extra"):
                    event.set_extra("agent_trace_started", False)
