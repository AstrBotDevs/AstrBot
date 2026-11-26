from __future__ import annotations


class AstrBotSDKError(Exception):
    code = "SDK_ERROR"


class InvalidRequest(AstrBotSDKError):
    code = "INVALID_REQUEST"


class InvalidConfig(AstrBotSDKError):
    code = "INVALID_CONFIG"


class InvalidPluginDefinition(AstrBotSDKError):
    code = "INVALID_PLUGIN_DEFINITION"


class InvalidPluginMetadata(AstrBotSDKError):
    code = "INVALID_PLUGIN_METADATA"


class UnsupportedMetadataVersion(InvalidPluginMetadata):
    code = "UNSUPPORTED_METADATA_VERSION"


class LegacyPluginMetadata(InvalidPluginMetadata):
    code = "LEGACY_PLUGIN_METADATA"


class PluginImportError(AstrBotSDKError):
    code = "PLUGIN_IMPORT_ERROR"


class DuplicateHandlerID(InvalidPluginDefinition):
    code = "DUPLICATE_HANDLER_ID"


class DuplicateLifecycleHandler(InvalidPluginDefinition):
    code = "DUPLICATE_LIFECYCLE_HANDLER"


class InvalidHandlerSignature(InvalidPluginDefinition):
    code = "INVALID_HANDLER_SIGNATURE"


class InvalidHandlerResult(AstrBotSDKError):
    code = "INVALID_HANDLER_RESULT"


class CapabilityDenied(AstrBotSDKError):
    code = "CAPABILITY_DENIED"


class CallScopeRetired(AstrBotSDKError):
    code = "CALL_SCOPE_RETIRED"


class ServiceUnavailable(AstrBotSDKError):
    code = "SERVICE_UNAVAILABLE"


class DependencyBlocked(AstrBotSDKError):
    code = "DEPENDENCY_BLOCKED"


class NotFound(AstrBotSDKError):
    code = "NOT_FOUND"


class Conflict(AstrBotSDKError):
    code = "CONFLICT"


class RateLimited(AstrBotSDKError):
    code = "RATE_LIMITED"


class DeadlineExceeded(AstrBotSDKError):
    code = "DEADLINE_EXCEEDED"


class HostUnavailable(AstrBotSDKError):
    code = "HOST_UNAVAILABLE"


class RemoteError(AstrBotSDKError):
    """Represent an error returned by the remote protocol peer."""

    def __init__(self, code: str, message: str) -> None:
        """Initialize a remote error.

        Args:
            code: Stable error code returned by the remote peer.
            message: Human-readable error message.
        """
        super().__init__(message)
        self.code = code


class RemotePluginError(RemoteError):
    """Represent an error returned by a remote plugin Runner."""


class RemoteHostError(RemoteError):
    """Represent an error returned by the AstrBot Host."""


_REMOTE_ERROR_TYPES: dict[str, type[AstrBotSDKError]] = {
    "INVALID_REQUEST": InvalidRequest,
    "INVALID_CONFIG": InvalidConfig,
    "CAPABILITY_DENIED": CapabilityDenied,
    "CALL_SCOPE_RETIRED": CallScopeRetired,
    "SERVICE_UNAVAILABLE": ServiceUnavailable,
    "DEPENDENCY_BLOCKED": DependencyBlocked,
    "NOT_FOUND": NotFound,
    "CONFLICT": Conflict,
    "RATE_LIMITED": RateLimited,
    "DEADLINE_EXCEEDED": DeadlineExceeded,
    "HOST_UNAVAILABLE": HostUnavailable,
}


def map_remote_error(error: RemoteError) -> AstrBotSDKError:
    """Map a remote protocol error onto the matching typed SDK exception.

    Args:
        error: Error returned by the remote peer.

    Returns:
        Typed SDK exception, or the original error when the code has no
        registered mapping.
    """
    error_type = _REMOTE_ERROR_TYPES.get(error.code)
    if error_type is None:
        return error
    return error_type(str(error))
