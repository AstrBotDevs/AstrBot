//! Message types for AstrBot Core

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Message {
    pub id: String,
    pub content: String,
    pub sender: String,
    pub timestamp: f64,
    pub message_type: MessageType,
    pub metadata: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Default)]
#[serde(rename_all = "snake_case")]
pub enum MessageType {
    #[default]
    Text,
    Image,
    Audio,
    Video,
    File,
    System,
    Unknown,
}

impl Message {
    #[must_use]
    pub fn new(id: String, content: String, sender: String) -> Self {
        Self {
            id,
            content,
            sender,
            timestamp: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_secs_f64())
                .unwrap_or_default(),
            message_type: MessageType::Text,
            metadata: None,
        }
    }
}
