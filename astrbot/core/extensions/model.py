from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ExtensionKind(str, Enum):
    PLUGIN = "plugin"
    SKILL = "skill"
    MCP = "mcp"


class PolicyAction(str, Enum):
    ALLOW_DIRECT = "ALLOW_DIRECT"
    REQUIRE_CONFIRMATION = "REQUIRE_CONFIRMATION"
    DENY = "DENY"


class InstallResultStatus(str, Enum):
    SUCCESS = "success"
    PENDING = "pending"
    FAILED = "failed"
    DENIED = "denied"


@dataclass(slots=True)
class SearchRequest:
    kind: ExtensionKind
    query: str
    provider: str = ""


@dataclass(slots=True)
class InstallRequest:
    kind: ExtensionKind
    target: str
    provider: str = ""
    conversation_id: str = ""
    requester_id: str = ""
    requester_role: str = "member"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class InstallCandidate:
    kind: ExtensionKind
    provider: str
    identifier: str
    name: str
    description: str = ""
    version: str = ""
    source: str = ""
    install_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PolicyDecision:
    action: PolicyAction
    reason: str = ""


@dataclass(slots=True)
class InstallResult:
    status: InstallResultStatus
    message: str
    operation_id: str | None = None
    token: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
