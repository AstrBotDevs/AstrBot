"""Platform-independent authorization primitives owned by an AstrBot runtime."""

from .models import (
    ACTIONS,
    AuthContext,
    Decision,
    Resource,
    Role,
    Subject,
    canonical_session_resource,
)
from .registry import ACTION_POLICIES, Relation, policy_for
from .service import AuthorizationService

__all__ = [
    "ACTIONS",
    "ACTION_POLICIES",
    "AuthContext",
    "AuthorizationService",
    "Decision",
    "Relation",
    "Resource",
    "Role",
    "Subject",
    "canonical_session_resource",
    "policy_for",
]
