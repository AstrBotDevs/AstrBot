//! ABP (AstrBot Plugin) Protocol Implementation
//!
//! ABP is the plugin communication protocol for AstrBot, supporting:
//! - In-process and out-of-process loading modes
//! - Full plugin lifecycle management
//! - Tool calling, message handling, event subscriptions
//! - JSON-RPC 2.0 communication
//!
//! Reference: openspec/abp.md

use crate::error::AstrBotError;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::UnixStream;

// ============================================================================
// ABP Data Models
// ============================================================================

/// Plugin loading mode
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PluginLoadMode {
    /// In-process: direct function calls, zero serialization overhead
    #[default]
    InProcess,
    /// Out-of-process: separate process, JSON-RPC over Unix Socket/HTTP
    OutOfProcess,
}

impl std::fmt::Display for PluginLoadMode {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            PluginLoadMode::InProcess => write!(f, "in_process"),
            PluginLoadMode::OutOfProcess => write!(f, "out_of_process"),
        }
    }
}

/// Plugin transport type
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PluginTransport {
    /// Stdio transport (for subprocess)
    #[default]
    Stdio,
    /// Unix Socket transport
    UnixSocket,
    /// HTTP transport
    Http,
}

impl std::fmt::Display for PluginTransport {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            PluginTransport::Stdio => write!(f, "stdio"),
            PluginTransport::UnixSocket => write!(f, "unix_socket"),
            PluginTransport::Http => write!(f, "http"),
        }
    }
}

/// Plugin configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PluginConfig {
    pub name: String,
    #[serde(default)]
    pub version: String,
    #[serde(default)]
    pub load_mode: PluginLoadMode,
    #[serde(default)]
    pub command: Option<String>,
    #[serde(default)]
    pub args: Vec<String>,
    #[serde(default)]
    pub env: HashMap<String, String>,
    #[serde(default)]
    pub transport: PluginTransport,
    #[serde(default)]
    pub url: Option<String>,
}

impl Default for PluginConfig {
    fn default() -> Self {
        Self {
            name: String::new(),
            version: "1.0.0".to_string(),
            load_mode: PluginLoadMode::InProcess,
            command: None,
            args: Vec::new(),
            env: HashMap::new(),
            transport: PluginTransport::Stdio,
            url: None,
        }
    }
}

/// Plugin capabilities
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PluginCapabilities {
    #[serde(default)]
    pub tools: bool,
    #[serde(default)]
    pub handlers: bool,
    #[serde(default)]
    pub events: bool,
    #[serde(default)]
    pub resources: bool,
}

/// Plugin metadata
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PluginMetadata {
    #[serde(default)]
    pub display_name: Option<String>,
    #[serde(default)]
    pub description: Option<String>,
    #[serde(default)]
    pub author: Option<String>,
    #[serde(default)]
    pub homepage: Option<String>,
    #[serde(default)]
    pub support_platforms: Vec<String>,
    #[serde(default)]
    pub astrbot_version: Option<String>,
}

/// Initialize result from plugin
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct InitializeResult {
    pub protocol_version: String,
    pub server_info: ServerInfo,
    pub capabilities: PluginCapabilities,
    #[serde(default)]
    pub metadata: Option<PluginMetadata>,
}

/// Server info
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ServerInfo {
    pub name: String,
    pub version: String,
}

/// Tool definition
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Tool {
    pub name: String,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub input_schema: serde_json::Value,
}

/// Tool call result
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ToolResult {
    #[serde(default)]
    pub content: Vec<ToolContent>,
}

/// Tool content
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ToolContent {
    #[serde(rename = "type")]
    pub content_type: String,
    pub text: Option<String>,
}

/// Message event
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct MessageEvent {
    pub message_id: String,
    pub unified_msg_origin: String,
    pub message_str: String,
    pub sender: SenderInfo,
    pub message_chain: Vec<MessageChainItem>,
}

/// Sender info
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SenderInfo {
    pub user_id: String,
    #[serde(default)]
    pub nickname: String,
}

/// Message chain item
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct MessageChainItem {
    #[serde(rename = "type")]
    pub item_type: String,
    #[serde(default)]
    pub text: Option<String>,
}

/// Handle event result
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct HandleEventResult {
    pub handled: bool,
    #[serde(default)]
    pub results: Vec<MessageChainItem>,
    #[serde(default)]
    pub stop_propagation: bool,
}

/// Event notification
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct EventNotification {
    pub event_type: String,
    #[serde(default)]
    pub data: serde_json::Value,
}

// ============================================================================
// ABP Client
// ============================================================================

/// ABP Client for managing plugins
#[derive(Debug)]
pub struct AbpClient {
    /// Connected state
    connected: bool,
    /// In-process plugins registry (name -> handler)
    in_process_plugins: HashMap<String, InProcessPlugin>,
    /// Out-of-process plugins registry (name -> OOP client)
    out_of_process_plugins: HashMap<String, OutOfProcessPlugin>,
}

/// In-process plugin handler
#[derive(Debug, Clone)]
pub struct InProcessPlugin {
    pub config: PluginConfig,
    pub capabilities: PluginCapabilities,
    pub metadata: Option<PluginMetadata>,
    pub tools: Vec<Tool>,
}

/// Out-of-process plugin client
#[derive(Debug)]
pub struct OutOfProcessPlugin {
    pub config: PluginConfig,
    pub capabilities: PluginCapabilities,
    pub metadata: Option<PluginMetadata>,
    pub tools: Vec<Tool>,
    pub socket_path: Option<PathBuf>,
    pub http_url: Option<String>,
}

impl AbpClient {
    /// Create a new ABP client
    pub fn new() -> Self {
        Self {
            connected: false,
            in_process_plugins: HashMap::new(),
            out_of_process_plugins: HashMap::new(),
        }
    }

    /// Connect the ABP client
    pub async fn connect(&mut self) -> Result<(), AstrBotError> {
        self.connected = true;
        tracing::info!(
            "ABP client connected (in_process: {}, out_of_process: {})",
            self.in_process_plugins.len(),
            self.out_of_process_plugins.len()
        );
        Ok(())
    }

    /// Disconnect the ABP client
    pub async fn disconnect(&mut self) -> Result<(), AstrBotError> {
        self.connected = false;
        self.in_process_plugins.clear();
        self.out_of_process_plugins.clear();
        tracing::info!("ABP client disconnected");
        Ok(())
    }

    /// Check if connected
    pub fn is_connected(&self) -> bool {
        self.connected
    }

    /// Set connected state (sync version for orchestrator)
    pub fn set_connected(&mut self, connected: bool) {
        self.connected = connected;
    }

    /// Set connected state without consuming self
    pub fn set_connected_ref(&mut self, connected: bool) {
        self.connected = connected;
    }
    /// Register an in-process plugin
    pub fn register_in_process_plugin(&mut self, config: PluginConfig) {
        let plugin = InProcessPlugin {
            config: config.clone(),
            capabilities: PluginCapabilities::default(),
            metadata: None,
            tools: Vec::new(),
        };
        tracing::debug!("Registered in-process plugin: {}", config.name);
        self.in_process_plugins.insert(config.name, plugin);
    }

    /// Register an out-of-process plugin
    pub fn register_out_of_process_plugin(&mut self, config: PluginConfig) {
        let socket_path = if config.transport == PluginTransport::UnixSocket {
            Some(PathBuf::from(format!(
                "/tmp/astrbot_plugin_{}.sock",
                config.name
            )))
        } else {
            None
        };

        let plugin = OutOfProcessPlugin {
            config: config.clone(),
            capabilities: PluginCapabilities::default(),
            metadata: None,
            tools: Vec::new(),
            socket_path,
            http_url: config.url.clone(),
        };
        tracing::debug!("Registered out-of-process plugin: {}", config.name);
        self.out_of_process_plugins.insert(config.name, plugin);
    }

    /// Unregister a plugin
    pub fn unregister_plugin(&mut self, name: &str) {
        self.in_process_plugins.remove(name);
        self.out_of_process_plugins.remove(name);
        tracing::debug!("Unregistered plugin: {}", name);
    }

    /// List all registered plugin names
    pub fn list_plugins(&self) -> Vec<String> {
        let mut names: Vec<String> = self.in_process_plugins.keys().cloned().collect();
        names.extend(self.out_of_process_plugins.keys().cloned());
        names.sort();
        names.dedup();
        names
    }

    /// Get plugin info
    pub fn get_plugin_info(&self, name: &str) -> Option<PluginInfo> {
        if let Some(plugin) = self.in_process_plugins.get(name) {
            Some(PluginInfo {
                name: plugin.config.name.clone(),
                version: plugin.config.version.clone(),
                load_mode: plugin.config.load_mode,
                capabilities: plugin.capabilities.clone(),
                metadata: plugin.metadata.clone(),
                tools_count: plugin.tools.len(),
            })
        } else { self.out_of_process_plugins.get(name).map(|plugin| PluginInfo {
                name: plugin.config.name.clone(),
                version: plugin.config.version.clone(),
                load_mode: plugin.config.load_mode,
                capabilities: plugin.capabilities.clone(),
                metadata: plugin.metadata.clone(),
                tools_count: plugin.tools.len(),
            }) }
    }

    /// Call a plugin tool (out-of-process)
    pub async fn call_tool(
        &mut self,
        plugin_name: &str,
        tool_name: &str,
        arguments: serde_json::Value,
    ) -> Result<ToolResult, AstrBotError> {
        // Extract transport and connection info first to avoid borrow conflict
        let transport = {
            let plugin = self
                .out_of_process_plugins
                .get(plugin_name)
                .ok_or_else(|| {
                    AstrBotError::NotFound(format!("Plugin '{}' not found", plugin_name))
                })?;
            plugin.config.transport
        };

        match transport {
            PluginTransport::UnixSocket => {
                let socket_path = {
                    let plugin = self
                        .out_of_process_plugins
                        .get(plugin_name)
                        .ok_or_else(|| {
                            AstrBotError::NotFound(format!("Plugin '{}' not found", plugin_name))
                        })?;
                    plugin.socket_path.clone()
                };
                self.call_tool_unix_socket(&socket_path, tool_name, arguments)
                    .await
            }
            PluginTransport::Http => {
                let http_url = {
                    let plugin = self
                        .out_of_process_plugins
                        .get(plugin_name)
                        .ok_or_else(|| {
                            AstrBotError::NotFound(format!("Plugin '{}' not found", plugin_name))
                        })?;
                    plugin.http_url.clone()
                };
                self.call_tool_http(&http_url, tool_name, arguments).await
            }
            PluginTransport::Stdio => Err(AstrBotError::Protocol(
                "Stdio transport not implemented for tool calls".into(),
            )),
        }
    }

    /// Call tool via Unix Socket
    async fn call_tool_unix_socket(
        &self,
        socket_path: &Option<PathBuf>,
        tool_name: &str,
        arguments: serde_json::Value,
    ) -> Result<ToolResult, AstrBotError> {
        let socket_path = socket_path
            .as_ref()
            .ok_or_else(|| AstrBotError::InvalidState("No socket path configured".into()))?;

        let mut stream = UnixStream::connect(socket_path).await.map_err(|e| {
            AstrBotError::ConnectionFailed(format!("Unix socket connect failed: {}", e))
        })?;

        let request = serde_json::json!({
            "jsonrpc": "2.0",
            "id": uuid::Uuid::new_v4().to_string(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        });

        let content = serde_json::to_string(&request).map_err(AstrBotError::Json)?;
        let header = format!("Content-Length: {}\r\n\r\n", content.len());

        stream.write_all(header.as_bytes()).await?;
        stream.write_all(content.as_bytes()).await?;

        // Read response
        let mut buffer = Vec::new();
        stream.read_to_end(&mut buffer).await?;

        let response: serde_json::Value =
            serde_json::from_slice(&buffer).map_err(AstrBotError::Json)?;

        if let Some(error) = response.get("error") {
            return Err(AstrBotError::Protocol(error.to_string()));
        }

        let result: ToolResult =
            serde_json::from_value(response.get("result").cloned().unwrap_or_default())
                .map_err(AstrBotError::Json)?;

        Ok(result)
    }

    /// Call tool via HTTP
    async fn call_tool_http(
        &self,
        http_url: &Option<String>,
        tool_name: &str,
        arguments: serde_json::Value,
    ) -> Result<ToolResult, AstrBotError> {
        let url = http_url
            .as_ref()
            .ok_or_else(|| AstrBotError::InvalidState("No HTTP URL configured".into()))?;

        let client = reqwest::Client::new();
        let request = serde_json::json!({
            "jsonrpc": "2.0",
            "id": uuid::Uuid::new_v4().to_string(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        });

        let response = client
            .post(url)
            .json(&request)
            .send()
            .await
            .map_err(|e| AstrBotError::ConnectionFailed(e.to_string()))?;

        let result: ToolResult = response
            .json()
            .await
            .map_err(|e| AstrBotError::Protocol(e.to_string()))?;

        Ok(result)
    }

    /// Handle an event with a plugin
    pub async fn handle_event(
        &mut self,
        plugin_name: &str,
        event_type: &str,
        event: serde_json::Value,
    ) -> Result<HandleEventResult, AstrBotError> {
        // Extract transport first to avoid borrow conflict
        let transport = {
            let plugin = self
                .out_of_process_plugins
                .get(plugin_name)
                .ok_or_else(|| {
                    AstrBotError::NotFound(format!("Plugin '{}' not found", plugin_name))
                })?;
            plugin.config.transport
        };

        match transport {
            PluginTransport::UnixSocket => {
                let socket_path = {
                    let plugin = self
                        .out_of_process_plugins
                        .get(plugin_name)
                        .ok_or_else(|| {
                            AstrBotError::NotFound(format!("Plugin '{}' not found", plugin_name))
                        })?;
                    plugin.socket_path.clone()
                };
                self.handle_event_unix_socket(&socket_path, event_type, event)
                    .await
            }
            PluginTransport::Http => {
                let http_url = {
                    let plugin = self
                        .out_of_process_plugins
                        .get(plugin_name)
                        .ok_or_else(|| {
                            AstrBotError::NotFound(format!("Plugin '{}' not found", plugin_name))
                        })?;
                    plugin.http_url.clone()
                };
                self.handle_event_http(&http_url, event_type, event).await
            }
            PluginTransport::Stdio => Err(AstrBotError::Protocol(
                "Stdio transport not implemented for events".into(),
            )),
        }
    }

    /// Handle event via Unix Socket
    async fn handle_event_unix_socket(
        &self,
        socket_path: &Option<PathBuf>,
        event_type: &str,
        event: serde_json::Value,
    ) -> Result<HandleEventResult, AstrBotError> {
        let socket_path = socket_path
            .as_ref()
            .ok_or_else(|| AstrBotError::InvalidState("No socket path configured".into()))?;

        let mut stream = UnixStream::connect(socket_path).await.map_err(|e| {
            AstrBotError::ConnectionFailed(format!("Unix socket connect failed: {}", e))
        })?;

        let request = serde_json::json!({
            "jsonrpc": "2.0",
            "id": uuid::Uuid::new_v4().to_string(),
            "method": "plugin.handle_event",
            "params": {
                "event_type": event_type,
                "event": event
            }
        });

        let content = serde_json::to_string(&request).map_err(AstrBotError::Json)?;
        let header = format!("Content-Length: {}\r\n\r\n", content.len());

        stream.write_all(header.as_bytes()).await?;
        stream.write_all(content.as_bytes()).await?;

        // Read response
        let mut buffer = Vec::new();
        stream.read_to_end(&mut buffer).await?;

        let response: serde_json::Value =
            serde_json::from_slice(&buffer).map_err(AstrBotError::Json)?;

        if let Some(error) = response.get("error") {
            return Err(AstrBotError::Protocol(error.to_string()));
        }

        let result: HandleEventResult =
            serde_json::from_value(response.get("result").cloned().unwrap_or_default())
                .map_err(AstrBotError::Json)?;

        Ok(result)
    }

    /// Handle event via HTTP
    async fn handle_event_http(
        &self,
        http_url: &Option<String>,
        event_type: &str,
        event: serde_json::Value,
    ) -> Result<HandleEventResult, AstrBotError> {
        let url = http_url
            .as_ref()
            .ok_or_else(|| AstrBotError::InvalidState("No HTTP URL configured".into()))?;

        let client = reqwest::Client::new();
        let request = serde_json::json!({
            "jsonrpc": "2.0",
            "id": uuid::Uuid::new_v4().to_string(),
            "method": "plugin.handle_event",
            "params": {
                "event_type": event_type,
                "event": event
            }
        });

        let response = client
            .post(url)
            .json(&request)
            .send()
            .await
            .map_err(|e| AstrBotError::ConnectionFailed(e.to_string()))?;

        let result: HandleEventResult = response
            .json()
            .await
            .map_err(|e| AstrBotError::Protocol(e.to_string()))?;

        Ok(result)
    }

    /// Get plugin tools
    pub fn get_plugin_tools(&self, name: &str) -> Option<Vec<Tool>> {
        if let Some(plugin) = self.in_process_plugins.get(name) {
            Some(plugin.tools.clone())
        } else { self.out_of_process_plugins.get(name).map(|plugin| plugin.tools.clone()) }
    }

    /// Health check for a plugin
    pub fn health_check(&self, name: &str) -> bool {
        if self.in_process_plugins.contains_key(name) {
            true
        } else if let Some(plugin) = self.out_of_process_plugins.get(name) {
            if let Some(socket_path) = &plugin.socket_path {
                socket_path.exists()
            } else if plugin.http_url.is_some() {
                true // HTTP plugins are assumed healthy if URL is configured
            } else {
                false
            }
        } else {
            false
        }
    }
}

impl Default for AbpClient {
    fn default() -> Self {
        Self::new()
    }
}

/// Plugin info for listing
#[derive(Debug, Clone)]
pub struct PluginInfo {
    pub name: String,
    pub version: String,
    pub load_mode: PluginLoadMode,
    pub capabilities: PluginCapabilities,
    pub metadata: Option<PluginMetadata>,
    pub tools_count: usize,
}

// ============================================================================
// Protocol Client Trait Implementation
// ============================================================================

use async_trait::async_trait;

#[async_trait]
impl crate::protocol::ProtocolClient for AbpClient {
    fn name(&self) -> &'static str {
        "abp"
    }

    fn is_connected(&self) -> bool {
        self.is_connected()
    }

    async fn connect(&mut self) -> Result<(), AstrBotError> {
        self.connect().await
    }

    async fn disconnect(&mut self) -> Result<(), AstrBotError> {
        self.disconnect().await
    }
}
