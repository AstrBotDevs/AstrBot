from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .tool import ToolOutcome


@dataclass(slots=True)
class CompletionDecision:
    """Deterministic decision about whether a tool result satisfies a turn."""

    complete: bool
    status: str
    reason: str
    missing_evidence: list[str] = field(default_factory=list)
    fallback_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return a bounded JSON-compatible completion decision."""

        return {
            "complete": self.complete,
            "status": self.status,
            "reason": self.reason,
            "missing_evidence": list(self.missing_evidence),
            "fallback_allowed": self.fallback_allowed,
        }


class AgentSupervisor:
    """Validate tool outcomes before an Agent is allowed to claim completion."""

    _FAILURE_STATUSES = frozenset({"empty", "failed", "timeout", "cancelled"})

    @classmethod
    def check(
        cls,
        outcome: ToolOutcome,
        *,
        required_evidence: list[str] | tuple[str, ...] | None = None,
        completion_check: dict[str, Any] | None = None,
    ) -> CompletionDecision:
        """Evaluate a normalized outcome without using a model call.

        Args:
            outcome: Normalized result returned by the ToolGateway.
            required_evidence: Evidence identifiers or field names required by the
                selected capability.
            completion_check: Optional plan-level completion contract. The
                ``requires_evidence`` list is merged with ``required_evidence``.

        Returns:
            A deterministic decision describing whether the result is sufficient.
        """

        required = [
            str(item).strip() for item in (required_evidence or []) if str(item).strip()
        ]
        if isinstance(completion_check, dict):
            # ``requires_evidence`` is the public contract name; the router's
            # compact ToolPlan historically emitted ``evidence_classes``.
            # Accept both so a plan cannot silently bypass its evidence gate.
            for key in ("requires_evidence", "evidence_classes"):
                for item in completion_check.get(key, []) or []:
                    value = str(item).strip()
                    if value and value not in required:
                        required.append(value)

        if outcome.status in cls._FAILURE_STATUSES:
            return CompletionDecision(
                complete=False,
                status=outcome.status,
                reason=outcome.error_code
                or outcome.diagnostics
                or "tool did not produce usable evidence",
                missing_evidence=required,
                fallback_allowed=bool(
                    outcome.retryable and not outcome.side_effect_performed
                ),
            )

        if outcome.status == "direct_sent":
            if outcome.terminal and outcome.side_effect_performed:
                return CompletionDecision(True, "completed", "verified direct delivery")
            return CompletionDecision(
                False,
                "partial",
                "direct result was not verified as terminal delivery",
                missing_evidence=required,
                fallback_allowed=False,
            )

        if outcome.status != "success":
            return CompletionDecision(
                False,
                "failed",
                "unknown tool outcome status",
                missing_evidence=required,
                fallback_allowed=False,
            )

        evidence_ids = {
            str(item).strip() for item in outcome.evidence_ids if str(item).strip()
        }
        missing = [item for item in required if item not in evidence_ids]
        if missing:
            return CompletionDecision(
                False,
                "partial",
                "tool succeeded but required evidence is missing",
                missing_evidence=missing,
                fallback_allowed=bool(
                    outcome.retryable and not outcome.side_effect_performed
                ),
            )
        return CompletionDecision(
            True, "completed", "usable tool result and evidence verified"
        )


def completion_check_for_tool(
    outcome: ToolOutcome, tool: Any, plan: dict[str, Any] | None = None
) -> CompletionDecision:
    """Check a tool result using metadata exposed by a FunctionTool.

    Args:
        outcome: Normalized ToolGateway result.
        tool: Registered tool descriptor or FunctionTool instance.
        plan: Optional request-level ToolPlan.

    Returns:
        Deterministic completion decision.
    """

    required_evidence = list(getattr(tool, "evidence_requirements", None) or [])
    if isinstance(plan, dict):
        for item in plan.get("required_evidence", []) or []:
            value = str(item).strip()
            if value and value not in required_evidence:
                required_evidence.append(value)
    return AgentSupervisor.check(
        outcome,
        required_evidence=required_evidence,
        completion_check=(plan or {}).get("completion_check")
        if isinstance(plan, dict)
        else None,
    )
