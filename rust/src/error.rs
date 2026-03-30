//! Error types for AstrBot Core

use thiserror::Error;

#[derive(Error, Debug)]
pub enum AstrBotError {
    #[error("Not connected: {0}")]
    NotConnected(String),

    #[error("Connection failed: {0}")]
    ConnectionFailed(String),

    #[error("Protocol error: {0}")]
    Protocol(String),

    #[error("Timeout: {0}")]
    Timeout(String),

    #[error("Invalid state: {0}")]
    InvalidState(String),

    #[error("Not found: {0}")]
    NotFound(String),

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),

    // ABP Protocol error codes (-32700 to -32211)
    #[error("Parse error: {0}")]
    ParseError(String),

    #[error("Invalid request: {0}")]
    InvalidRequest(String),

    #[error("Method not found: {0}")]
    MethodNotFound(String),

    #[error("Invalid params: {0}")]
    InvalidParams(String),

    #[error("Internal error: {0}")]
    InternalError(String),

    #[error("Plugin not found: {0}")]
    PluginNotFound(String),

    #[error("Plugin not ready: {0}")]
    PluginNotReady(String),

    #[error("Plugin crashed: {0}")]
    PluginCrashed(String),

    #[error("Tool not found: {0}")]
    ToolNotFound(String),

    #[error("Tool call failed: {0}")]
    ToolCallFailed(String),

    #[error("Handler not found: {0}")]
    HandlerNotFound(String),

    #[error("Handler error: {0}")]
    HandlerError(String),

    #[error("Event subscription failed: {0}")]
    EventSubscribeFailed(String),

    #[error("Permission denied: {0}")]
    PermissionDenied(String),

    #[error("Config error: {0}")]
    ConfigError(String),

    #[error("Dependency missing: {0}")]
    DependencyMissing(String),

    #[error("Version mismatch: {0}")]
    VersionMismatch(String),
}

/// ABP Protocol error codes
pub mod abp_error_codes {
    use super::AstrBotError;

    /// JSON-RPC parse error
    pub const PARSE_ERROR: i32 = -32700;
    /// Invalid request
    pub const INVALID_REQUEST: i32 = -32600;
    /// Method not found
    pub const METHOD_NOT_FOUND: i32 = -32601;
    /// Invalid params
    pub const INVALID_PARAMS: i32 = -32602;
    /// Internal error
    pub const INTERNAL_ERROR: i32 = -32603;
    /// Plugin not found
    pub const PLUGIN_NOT_FOUND: i32 = -32200;
    /// Plugin not ready
    pub const PLUGIN_NOT_READY: i32 = -32201;
    /// Plugin crashed
    pub const PLUGIN_CRASHED: i32 = -32202;
    /// Tool not found
    pub const TOOL_NOT_FOUND: i32 = -32203;
    /// Tool call failed
    pub const TOOL_CALL_FAILED: i32 = -32204;
    /// Handler not found
    pub const HANDLER_NOT_FOUND: i32 = -32205;
    /// Handler error
    pub const HANDLER_ERROR: i32 = -32206;
    /// Event subscribe failed
    pub const EVENT_SUBSCRIBE_FAILED: i32 = -32207;
    /// Permission denied
    pub const PERMISSION_DENIED: i32 = -32208;
    /// Config error
    pub const CONFIG_ERROR: i32 = -32209;
    /// Dependency missing
    pub const DEPENDENCY_MISSING: i32 = -32210;
    /// Version mismatch
    pub const VERSION_MISMATCH: i32 = -32211;

    /// Convert ABP error code to AstrBotError
    pub fn from_code(code: i32, message: String) -> AstrBotError {
        match code {
            PARSE_ERROR => AstrBotError::ParseError(message),
            INVALID_REQUEST => AstrBotError::InvalidRequest(message),
            METHOD_NOT_FOUND => AstrBotError::MethodNotFound(message),
            INVALID_PARAMS => AstrBotError::InvalidParams(message),
            INTERNAL_ERROR => AstrBotError::InternalError(message),
            PLUGIN_NOT_FOUND => AstrBotError::PluginNotFound(message),
            PLUGIN_NOT_READY => AstrBotError::PluginNotReady(message),
            PLUGIN_CRASHED => AstrBotError::PluginCrashed(message),
            TOOL_NOT_FOUND => AstrBotError::ToolNotFound(message),
            TOOL_CALL_FAILED => AstrBotError::ToolCallFailed(message),
            HANDLER_NOT_FOUND => AstrBotError::HandlerNotFound(message),
            HANDLER_ERROR => AstrBotError::HandlerError(message),
            EVENT_SUBSCRIBE_FAILED => AstrBotError::EventSubscribeFailed(message),
            PERMISSION_DENIED => AstrBotError::PermissionDenied(message),
            CONFIG_ERROR => AstrBotError::ConfigError(message),
            DEPENDENCY_MISSING => AstrBotError::DependencyMissing(message),
            VERSION_MISMATCH => AstrBotError::VersionMismatch(message),
            _ => AstrBotError::Protocol(format!("Unknown error code {}: {}", code, message)),
        }
    }
}
