from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .model import InstallCandidate, InstallRequest, PolicyAction, PolicyDecision


@dataclass(slots=True)
class ExtensionPolicyConfig:
    mode: str = "secure"
    allowlist: list[dict[str, str]] | None = None
    blocklist: list[dict[str, str]] | None = None
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
            allowed_roles=list(cfg.get("allowed_roles", ["admin", "owner"]) or []),
        )

    @staticmethod
    def _match_rule(
        rule: dict[str, str], request: InstallRequest, candidate: InstallCandidate
    ) -> bool:
        expected_kind = str(rule.get("kind", "")).strip()
        if expected_kind and expected_kind != request.kind.value:
            return False

        expected_provider = str(rule.get("provider", "")).strip()
        if expected_provider and expected_provider != candidate.provider:
            return False

        expected_identifier = str(rule.get("identifier", "")).strip()
        if expected_identifier and expected_identifier != candidate.identifier:
            return False

        expected_author = str(rule.get("author", "")).strip()
        if not any([expected_provider, expected_identifier, expected_author]):
            return False
        if expected_author:
            candidate_author = str(candidate.install_payload.get("author", "")).strip()
            if candidate_author != expected_author:
                return False

        return True

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
            if self.config.mode == "secure" and self._match_rule(
                rule, request, candidate
            ):
                return PolicyDecision(
                    action=PolicyAction.ALLOW_DIRECT,
                    reason="target matched allowlist",
                )

        if self.config.mode == "secure":
            return PolicyDecision(
                action=PolicyAction.REQUIRE_CONFIRMATION,
                reason="non-allowlisted target requires confirmation",
            )

        return PolicyDecision(
            action=PolicyAction.ALLOW_DIRECT,
            reason="direct install allowed by policy",
        )
