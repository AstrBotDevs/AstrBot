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
}
