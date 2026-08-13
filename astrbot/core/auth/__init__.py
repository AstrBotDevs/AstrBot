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
from .service import AuthorizationService

__all__ = [
    "ACTIONS",
    "AuthContext",
    "AuthorizationService",
    "Decision",
    "Resource",
    "Role",
    "Subject",
    "canonical_session_resource",
]
