from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .model import InstallCandidate, InstallRequest, PolicyAction, PolicyDecision


@dataclass(slots=True)
class ExtensionPolicyConfig:
    mode: str = "secure"
    allowlist: list[dict[str, str]] | None = None
    blocklist: list[dict[str, str]] | None = None
    confirmation_required_non_allowlist: bool = True
    allowed_roles: list[str] | None = None


class ExtensionPolicyEngine:
    """Policy engine for extension installation."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        provider_settings = (config or {}).get("provider_settings", {})
        cfg = provider_settings.get("extension_install", {})
        self.config = ExtensionPolicyConfig(
            mode=str(cfg.get("default_mode", "secure")),
            allowlist=list(cfg.get("allowlist", []) or []),
            blocklist=list(cfg.get("blocklist", []) or []),
            confirmation_required_non_allowlist=bool(
                cfg.get("confirmation_required_non_allowlist", True)
            ),
            allowed_roles=list(cfg.get("allowed_roles", ["admin", "owner"]) or []),
        )

    @staticmethod
    def _match_rule(
        rule: dict[str, str], request: InstallRequest, candidate: InstallCandidate
    ) -> bool:
        return (
            str(rule.get("kind", "")).strip() == request.kind.value
            and str(rule.get("provider", "")).strip() == candidate.provider
            and str(rule.get("identifier", "")).strip() == candidate.identifier
        )

    def evaluate(
        self, request: InstallRequest, candidate: InstallCandidate
    ) -> PolicyDecision:
        allowed_roles = set(self.config.allowed_roles or [])
        if request.requester_role not in allowed_roles:
            return PolicyDecision(
                action=PolicyAction.DENY,
                reason="requester role is not allowed",
            )

        for rule in self.config.blocklist or []:
            if self._match_rule(rule, request, candidate):
                return PolicyDecision(
                    action=PolicyAction.DENY,
                    reason="target matched blocklist",
                )

        for rule in self.config.allowlist or []:
            if self._match_rule(rule, request, candidate):
                return PolicyDecision(
                    action=PolicyAction.ALLOW_DIRECT,
                    reason="target matched allowlist",
                )

        if (
            self.config.mode == "secure"
            and self.config.confirmation_required_non_allowlist
        ):
            return PolicyDecision(
                action=PolicyAction.REQUIRE_CONFIRMATION,
                reason="non-allowlisted target requires confirmation",
            )

        if self.config.confirmation_required_non_allowlist:
            return PolicyDecision(
                action=PolicyAction.REQUIRE_CONFIRMATION,
                reason="confirmation enabled for non-allowlisted target",
            )

        return PolicyDecision(
            action=PolicyAction.ALLOW_DIRECT,
            reason="direct install allowed by policy",
        )
