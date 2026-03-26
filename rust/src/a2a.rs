//! A2A (Agent-to-Agent) Protocol Implementation
//!
//! A2A is an open protocol by Google Cloud for inter-agent communication.
//! This module implements the A2A client for AstrBot.
//!
//! Reference: https://google-a2a.github.io/

use crate::error::AstrBotError;
use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// ============================================================================
// A2A Data Models
// ============================================================================

/// Agent Card - describes agent capabilities for service discovery
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AgentCard {
    pub name: String,
    pub description: Option<String>,
    pub version: String,
    pub provider: Option<AgentProvider>,
    pub capabilities: AgentCapabilities,
    pub skills: Vec<AgentSkill>,
    #[serde(default)]
    pub security_schemes: HashMap<String, SecurityScheme>,
    pub url: String,
}

/// Provider information
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AgentProvider {
    pub organization: String,
    pub url: Option<String>,
}

/// Agent capabilities
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct AgentCapabilities {
    #[serde(default)]
    pub streaming: bool,
    #[serde(default)]
    pub push_notifications: bool,
    #[serde(default)]
    pub extensions: Vec<String>,
}

/// Agent skill
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AgentSkill {
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub tags: Vec<String>,
    #[serde(default)]
    pub examples: Vec<SkillExample>,
}

/// Skill example
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SkillExample {
    pub user: String,
    pub agent: String,
}

/// Security scheme
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SecurityScheme {
    #[serde(rename = "type")]
    pub scheme_type: String,
    #[serde(default)]
    pub flows: Vec<String>,
    #[serde(default)]
    pub authorization_url: Option<String>,
}

/// Task status
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TaskStatus {
    pub state: TaskState,
    pub timestamp: String,
}

/// Task states
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum TaskState {
    Submitted,
    Working,
    Completed,
    Failed,
    Canceled,
    Rejected,
    InputRequired,
    AuthRequired,
}

/// Task representation
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Task {
    pub id: String,
    #[serde(default)]
    pub context_id: Option<String>,
    pub status: TaskStatus,
    #[serde(default)]
    pub artifacts: Vec<Artifact>,
    #[serde(default)]
    pub history: Vec<Message>,
    #[serde(default)]
    pub metadata: HashMap<String, serde_json::Value>,
}

/// Artifact - immutable output from agent
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Artifact {
    #[serde(default)]
    pub artifact_id: Option<String>,
    pub name: Option<String>,
    pub parts: Vec<Part>,
}

/// Message part - atomic content unit
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
#[serde(tag = "type")]
pub enum Part {
    Text { text: String },
    File { file: FilePart },
    Data { data: serde_json::Value },
}

/// File part
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FilePart {
    pub name: String,
    pub uri: String,
}

/// Message between client and agent
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Message {
    #[serde(default)]
    pub message_id: Option<String>,
    pub role: MessageRole,
    pub parts: Vec<Part>,
    #[serde(default)]
    pub reference_task_ids: Vec<String>,
}

/// Message role
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum MessageRole {
    User,
    Agent,
}

/// A2A Response
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct A2AResponse {
    #[serde(default)]
    pub task: Option<Task>,
    #[serde(default)]
    pub message: Option<Message>,
}

// ============================================================================
// A2A Client
// ============================================================================

/// A2A Client for connecting to remote agents
#[derive(Debug)]
pub struct A2AClient {
    /// Base URL of the A2A server
    server_url: String,
    /// Authentication header value
    auth_header: Option<String>,
    /// HTTP client
    client: Option<reqwest::Client>,
    /// Task history
    tasks: HashMap<String, Task>,
}

impl A2AClient {
    /// Create a new A2A client
    pub fn new(server_url: &str) -> Self {
        Self {
            server_url: server_url.to_string(),
            auth_header: None,
            client: None,
            tasks: HashMap::new(),
        }
    }

    /// Set authentication
    pub fn with_auth(mut self, auth_header: &str) -> Self {
        self.auth_header = Some(auth_header.to_string());
        self
    }

    /// Initialize the client
    pub async fn connect(&mut self) -> Result<(), AstrBotError> {
        self.client = Some(reqwest::Client::new());

        tracing::info!("A2A client connected to {}", self.server_url);
        Ok(())
    }

    /// Fetch agent card for service discovery
    pub async fn get_agent_card(&self) -> Result<AgentCard, AstrBotError> {
        let client = self
            .client
            .as_ref()
            .ok_or_else(|| AstrBotError::NotConnected("A2A client not connected".into()))?;

        let url = format!("{}/.well-known/agent-card.json", self.server_url);
        let response = client.get(&url).send().await.map_err(|e| {
            AstrBotError::ConnectionFailed(format!("Failed to fetch agent card: {}", e))
        })?;

        let agent_card: AgentCard = response
            .json()
            .await
            .map_err(|e| AstrBotError::Protocol(format!("Failed to parse agent card: {}", e)))?;

        Ok(agent_card)
    }

    /// Send a message to an agent
    pub async fn send_message(
        &mut self,
        message: Message,
        task_id: Option<&str>,
        session_id: Option<&str>,
    ) -> Result<A2AResponse, AstrBotError> {
        let client = self
            .client
            .as_ref()
            .ok_or_else(|| AstrBotError::NotConnected("A2A client not connected".into()))?;

        let request = A2ARequest::new(
            &uuid::Uuid::new_v4().to_string(),
            "SendMessage",
            serde_json::to_value(SendMessageParams {
                message,
                task_id: task_id.map(String::from),
                session_id: session_id.map(String::from),
            })
            .map_err(|e| AstrBotError::Json(e))?,
        );

        let response = client
            .post(&self.server_url)
            .header("Content-Type", "application/json")
            .header("A2A-Version", "1.0.0")
            .json(&request)
            .send()
            .await
            .map_err(|e| AstrBotError::ConnectionFailed(format!("SendMessage failed: {}", e)))?;

        let result: serde_json::Value = response
            .json()
            .await
            .map_err(|e| AstrBotError::Protocol(format!("Failed to parse response: {}", e)))?;

        // Parse into A2AResponse
        let a2a_response: A2AResponse =
            serde_json::from_value(result).map_err(|e| AstrBotError::Json(e))?;

        Ok(a2a_response)
    }

    /// Send a streaming message
    pub async fn send_streaming_message(
        &mut self,
        message: Message,
    ) -> Result<String, AstrBotError> {
        let client = self
            .client
            .as_ref()
            .ok_or_else(|| AstrBotError::NotConnected("A2A client not connected".into()))?;

        let request = A2ARequest::new(
            &uuid::Uuid::new_v4().to_string(),
            "SendStreamingMessage",
            serde_json::to_value(SendStreamingMessageParams { message })
                .map_err(|e| AstrBotError::Json(e))?,
        );

        // For streaming, we return the task ID and let the caller handle SSE
        let response = client
            .post(&self.server_url)
            .header("Content-Type", "application/json")
            .header("A2A-Version", "1.0.0")
            .json(&request)
            .send()
            .await
            .map_err(|e| {
                AstrBotError::ConnectionFailed(format!("SendStreamingMessage failed: {}", e))
            })?;

        // Parse streaming response to get task ID
        let result: serde_json::Value = response.json().await.map_err(|e| {
            AstrBotError::Protocol(format!("Failed to parse streaming response: {}", e))
        })?;

        let task_id = result
            .get("task")
            .and_then(|t| t.get("id"))
            .and_then(|id| id.as_str())
            .map(String::from)
            .ok_or_else(|| AstrBotError::Protocol("No task ID in streaming response".into()))?;

        Ok(task_id)
    }

    /// Get task status and result
    pub async fn get_task(&mut self, task_id: &str) -> Result<Task, AstrBotError> {
        let client = self
            .client
            .as_ref()
            .ok_or_else(|| AstrBotError::NotConnected("A2A client not connected".into()))?;

        let request = A2ARequest::new(
            &uuid::Uuid::new_v4().to_string(),
            "GetTask",
            serde_json::json!({ "id": task_id }),
        );

        let response = client
            .post(&self.server_url)
            .header("Content-Type", "application/json")
            .header("A2A-Version", "1.0.0")
            .json(&request)
            .send()
            .await
            .map_err(|e| AstrBotError::ConnectionFailed(format!("GetTask failed: {}", e)))?;

        let result: serde_json::Value = response
            .json()
            .await
            .map_err(|e| AstrBotError::Protocol(format!("Failed to parse task: {}", e)))?;

        let task: Task = serde_json::from_value(result).map_err(|e| AstrBotError::Json(e))?;

        self.tasks.insert(task.id.clone(), task.clone());

        Ok(task)
    }

    /// Cancel a task
    pub async fn cancel_task(&mut self, task_id: &str) -> Result<Task, AstrBotError> {
        let client = self
            .client
            .as_ref()
            .ok_or_else(|| AstrBotError::NotConnected("A2A client not connected".into()))?;

        let request = A2ARequest::new(
            &uuid::Uuid::new_v4().to_string(),
            "CancelTask",
            serde_json::json!({ "id": task_id }),
        );

        let response = client
            .post(&self.server_url)
            .header("Content-Type", "application/json")
            .header("A2A-Version", "1.0.0")
            .json(&request)
            .send()
            .await
            .map_err(|e| AstrBotError::ConnectionFailed(format!("CancelTask failed: {}", e)))?;

        let result: serde_json::Value = response
            .json()
            .await
            .map_err(|e| AstrBotError::Protocol(format!("Failed to parse canceled task: {}", e)))?;

        let task: Task = serde_json::from_value(result).map_err(|e| AstrBotError::Json(e))?;

        Ok(task)
    }

    /// Check if agent is connected
    pub fn is_connected(&self) -> bool {
        self.client.is_some()
    }
}

// ============================================================================
// A2A Request/Response Types
// ============================================================================

#[derive(Debug, Serialize, Deserialize)]
struct A2ARequest {
    #[serde(rename = "jsonrpc")]
    json_rpc: String,
    id: String,
    method: String,
    params: serde_json::Value,
}

impl A2ARequest {
    fn new(id: &str, method: &str, params: serde_json::Value) -> Self {
        Self {
            json_rpc: "2.0".to_string(),
            id: id.to_string(),
            method: method.to_string(),
            params,
        }
    }
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct SendMessageParams {
    message: Message,
    #[serde(skip_serializing_if = "Option::is_none")]
    task_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    session_id: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct SendStreamingMessageParams {
    message: Message,
}

// ============================================================================
// Protocol Client Trait Implementation
// ============================================================================

#[async_trait]
impl crate::protocol::ProtocolClient for A2AClient {
    fn name(&self) -> &'static str {
        "a2a"
    }

    fn is_connected(&self) -> bool {
        self.is_connected()
    }

    async fn connect(&mut self) -> Result<(), AstrBotError> {
        A2AClient::connect(self).await
    }

    async fn disconnect(&mut self) -> Result<(), AstrBotError> {
        self.client = None;
        self.tasks.clear();
        tracing::info!("A2A client disconnected");
        Ok(())
    }
}
