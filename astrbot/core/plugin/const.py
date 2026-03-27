"""ABP Protocol Constants"""

# Protocol version
ABP_VERSION = "1.0.0"

# ABP Error codes (JSON-RPC 2.0 base + ABP extension)
# JSON-RPC standard errors
PARSE_ERROR: int = -32700
INVALID_REQUEST: int = -32600
METHOD_NOT_FOUND: int = -32601
INVALID_PARAMS: int = -32602
INTERNAL_ERROR: int = -32603

# ABP extension errors (-32200 to -32211)
PLUGIN_NOT_FOUND: int = -32200
PLUGIN_NOT_READY: int = -32201
PLUGIN_CRASHED: int = -32202
TOOL_NOT_FOUND: int = -32203
TOOL_CALL_FAILED: int = -32204
HANDLER_NOT_FOUND: int = -32205
HANDLER_ERROR: int = -32206
EVENT_SUBSCRIBE_FAILED: int = -32207
PERMISSION_DENIED: int = -32208
CONFIG_ERROR: int = -32209
DEPENDENCY_MISSING: int = -32210
VERSION_MISMATCH: int = -32211

# Plugin load modes
LOAD_MODE_IN_PROCESS: str = "in_process"
LOAD_MODE_OUT_OF_PROCESS: str = "out_of_process"

# Transport types
TRANSPORT_STDIO: str = "stdio"
TRANSPORT_UNIX_SOCKET: str = "unix_socket"
TRANSPORT_HTTP: str = "http"


def get_error_message(code: int) -> str:
    """Get error message for error code."""
    messages = {
        PARSE_ERROR: "Parse error - Invalid JSON",
        INVALID_REQUEST: "Invalid request",
        METHOD_NOT_FOUND: "Method not found",
        INVALID_PARAMS: "Invalid params",
        INTERNAL_ERROR: "Internal error",
        PLUGIN_NOT_FOUND: "Plugin not found",
        PLUGIN_NOT_READY: "Plugin not ready",
        PLUGIN_CRASHED: "Plugin crashed",
        TOOL_NOT_FOUND: "Tool not found",
        TOOL_CALL_FAILED: "Tool call failed",
        HANDLER_NOT_FOUND: "Handler not found",
        HANDLER_ERROR: "Handler error",
        EVENT_SUBSCRIBE_FAILED: "Event subscription failed",
        PERMISSION_DENIED: "Permission denied",
        CONFIG_ERROR: "Configuration error",
        DEPENDENCY_MISSING: "Dependency missing",
        VERSION_MISMATCH: "Version mismatch",
    }
    return messages.get(code, f"Unknown error code: {code}")
