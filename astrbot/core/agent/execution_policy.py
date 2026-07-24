"""Request-scoped execution policy for AstrBot's built-in agent runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from astrbot.core.platform.astr_message_event import AstrMessageEvent

AGENT_EXECUTION_POLICY_EXTRA_KEY = "agent_execution_policy"
AGENT_TOOL_AUTHORIZATION_EXTRA_KEY = "agent_tool_authorization"

AgentRoute = Literal["fast", "standard", "deep"]
KnowledgeMode = Literal["off", "retrieve", "agentic"]


@dataclass(slots=True, frozen=True)
class AgentExecutionPolicy:
    """Validated execution limits supplied by a trusted routing plugin.

    Args:
        route: Complexity route selected for this request.
        provider_id: Optional provider override.
        allowed_tools: Tool allowlist. ``None`` preserves the legacy tool set.
        knowledge_mode: Knowledge-base behavior for this request.
        max_steps: Maximum number of model/tool loop steps.
        tool_timeout_seconds: Timeout for each individual tool call.
        request_max_retries: Maximum provider retries within one runner step.
        tool_required: Whether the request must observe a successful allowed tool.
        selected_tool: Exact tool selected by the semantic planner, when known.
        semantic_intent: Normalized semantic intent for observability.
        semantic_confidence: Deterministic/planner confidence in the intent.
        required_evidence: Evidence classes required before answering.
        fallback_tools: Ordered read-only alternatives when the selected tool fails.
        completion_check: Structured conditions that must be satisfied before reply.
        principal_id: Stable platform-scoped identity used for auditing.
        permission_snapshot: Read-only authorization attributes for auditing.
    """

    route: AgentRoute
    provider_id: str | None = None
    allowed_tools: tuple[str, ...] | None = None
    knowledge_mode: KnowledgeMode = "off"
    max_steps: int = 3
    tool_timeout_seconds: int = 30
    request_max_retries: int = 0
    tool_required: bool = False
    selected_tool: str = ""
    semantic_intent: str = "chat"
    semantic_confidence: float = 0.0
    required_evidence: tuple[str, ...] = ()
    fallback_tools: tuple[str, ...] = ()
    completion_check: dict[str, Any] = field(default_factory=dict)
    principal_id: str = ""
    permission_snapshot: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_value(cls, value: object) -> AgentExecutionPolicy | None:
        """Parse and validate an event-extra policy value.

        Args:
            value: Existing policy instance or a JSON-like mapping.

        Returns:
            A validated policy, or ``None`` when the input is invalid.
        """

        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            return None

        route = value.get("route")
        knowledge_mode = value.get("knowledge_mode", "off")
        if route not in {"fast", "standard", "deep"}:
            return None
        if knowledge_mode not in {"off", "retrieve", "agentic"}:
            return None

        max_steps = value.get("max_steps", 3)
        tool_timeout = value.get("tool_timeout_seconds", 30)
        retries = value.get("request_max_retries", 0)
        tool_required = value.get("tool_required", False)
        selected_tool = value.get("selected_tool", "")
        semantic_intent = value.get("semantic_intent", "chat")
        semantic_confidence = value.get("semantic_confidence", 0.0)
        required_evidence = value.get("required_evidence", [])
        fallback_tools = value.get("fallback_tools", [])
        completion_check = value.get("completion_check", {})
        if (
            isinstance(max_steps, bool)
            or not isinstance(max_steps, int)
            or not 1 <= max_steps <= 10
        ):
            return None
        if (
            isinstance(tool_timeout, bool)
            or not isinstance(tool_timeout, int)
            or not 5 <= tool_timeout <= 120
        ):
            return None
        if (
            isinstance(retries, bool)
            or not isinstance(retries, int)
            or retries not in {0, 1}
        ):
            return None
        if not isinstance(tool_required, bool):
            return None
        if not isinstance(selected_tool, str) or not isinstance(semantic_intent, str):
            return None
        if (
            isinstance(semantic_confidence, bool)
            or not isinstance(semantic_confidence, (int, float))
            or not 0.0 <= float(semantic_confidence) <= 1.0
        ):
            return None
        if not isinstance(required_evidence, list) or not all(
            isinstance(item, str) and item.strip() for item in required_evidence
        ):
            return None
        if not isinstance(fallback_tools, list) or not all(
            isinstance(item, str) and item.strip() for item in fallback_tools
        ):
            return None
        if not isinstance(completion_check, dict):
            return None

        provider_id = value.get("provider_id")
        if provider_id is not None and (
            not isinstance(provider_id, str) or not provider_id.strip()
        ):
            return None

        raw_tools = value.get("allowed_tools")
        allowed_tools: tuple[str, ...] | None
        if raw_tools is None:
            allowed_tools = None
        elif isinstance(raw_tools, list) and all(
            isinstance(item, str) and item.strip() for item in raw_tools
        ):
            allowed_tools = tuple(dict.fromkeys(item.strip() for item in raw_tools))
        else:
            return None

        principal_id = value.get("principal_id", "")
        permission_snapshot = value.get("permission_snapshot", {})
        if not isinstance(principal_id, str) or not isinstance(
            permission_snapshot, dict
        ):
            return None

        return cls(
            route=route,
            provider_id=provider_id.strip() if provider_id else None,
            allowed_tools=allowed_tools,
            knowledge_mode=knowledge_mode,
            max_steps=max_steps,
            tool_timeout_seconds=tool_timeout,
            request_max_retries=retries,
            tool_required=tool_required,
            selected_tool=selected_tool.strip(),
            semantic_intent=semantic_intent.strip() or "chat",
            semantic_confidence=float(semantic_confidence),
            required_evidence=tuple(
                dict.fromkeys(item.strip() for item in required_evidence)
            ),
            fallback_tools=tuple(
                dict.fromkeys(item.strip() for item in fallback_tools)
            ),
            completion_check=completion_check.copy(),
            principal_id=principal_id,
            permission_snapshot=permission_snapshot.copy(),
        )


def get_agent_execution_policy(
    event: AstrMessageEvent,
) -> AgentExecutionPolicy | None:
    """Return the validated execution policy attached to an event.

    Args:
        event: Current message event.

    Returns:
        A validated policy, or ``None`` to preserve legacy behavior.
    """

    return AgentExecutionPolicy.from_value(
        event.get_extra(AGENT_EXECUTION_POLICY_EXTRA_KEY)
    )
