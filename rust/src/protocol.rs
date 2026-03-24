//! Protocol client implementations for ACP and ABP

use crate::error::AstrBotError;
use async_trait::async_trait;
use std::collections::HashMap;

/// Protocol client trait
#[async_trait]
pub trait ProtocolClient: Send + Sync {
    async fn connect(&mut self) -> Result<(), AstrBotError>;
    async fn disconnect(&mut self) -> Result<(), AstrBotError>;
    fn is_connected(&self) -> bool;
    fn name(&self) -> &str;
}

// ============================================================================
// LSP Client
// ============================================================================

#[derive(Default)]
pub struct LspClient {
    connected: bool,
}

impl LspClient {
    #[must_use]
    pub fn new() -> Self {
        Self { connected: false }
    }

    pub fn set_connected(&mut self, connected: bool) {
        self.connected = connected;
    }
}

#[async_trait]
impl ProtocolClient for LspClient {
    async fn connect(&mut self) -> Result<(), AstrBotError> {
        tracing::debug!("LSP client connecting");
        self.connected = true;
        Ok(())
    }

    async fn disconnect(&mut self) -> Result<(), AstrBotError> {
        tracing::debug!("LSP client disconnecting");
        self.connected = false;
        Ok(())
    }

    fn is_connected(&self) -> bool {
        self.connected
    }

    fn name(&self) -> &'static str {
        "lsp-client"
    }
}

// ============================================================================
// MCP Client
// ============================================================================

#[derive(Default)]
pub struct McpClient {
    connected: bool,
}

impl McpClient {
    #[must_use]
    pub fn new() -> Self {
        Self { connected: false }
    }

    pub fn set_connected(&mut self, connected: bool) {
        self.connected = connected;
    }
}

#[async_trait]
impl ProtocolClient for McpClient {
    async fn connect(&mut self) -> Result<(), AstrBotError> {
        tracing::debug!("MCP client connecting");
        self.connected = true;
        Ok(())
    }

    async fn disconnect(&mut self) -> Result<(), AstrBotError> {
        tracing::debug!("MCP client disconnecting");
        self.connected = false;
        Ok(())
    }

    fn is_connected(&self) -> bool {
        self.connected
    }

    fn name(&self) -> &'static str {
        "mcp-client"
    }
}

// ============================================================================
// ACP Client - AstrBot Communication Protocol
// ============================================================================

#[derive(Debug, Clone)]
pub struct AcpClient {
    connected: bool,
    server_url: Option<String>,
}

impl AcpClient {
    pub fn new() -> Self {
        Self {
            connected: false,
            server_url: None,
        }
    }

    pub fn set_connected(&mut self, connected: bool) {
        self.connected = connected;
    }

    pub async fn connect_to_server(&mut self, host: &str, port: u16) -> Result<(), AstrBotError> {
        self.server_url = Some(format!("{}:{}", host, port));
        self.connected = true;
        tracing::debug!("ACP client connecting to {}:{}", host, port);
        Ok(())
    }

    pub async fn connect_to_unix_socket(&mut self, socket_path: &str) -> Result<(), AstrBotError> {
        self.server_url = Some(format!("unix://{}", socket_path));
        self.connected = true;
        tracing::debug!("ACP client connecting to unix socket:{}", socket_path);
        Ok(())
    }
}

impl Default for AcpClient {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl ProtocolClient for AcpClient {
    async fn connect(&mut self) -> Result<(), AstrBotError> {
        self.connected = true;
        Ok(())
    }

    async fn disconnect(&mut self) -> Result<(), AstrBotError> {
        self.connected = false;
        self.server_url = None;
        Ok(())
    }

    fn is_connected(&self) -> bool {
        self.connected
    }

    fn name(&self) -> &'static str {
        "acp-client"
    }
}

// ============================================================================
// ABP Client - AstrBot Protocol (internal stars)
// ============================================================================

#[derive(Debug, Default)]
pub struct AbpClient {
    connected: bool,
    stars: HashMap<String, String>,
}

impl AbpClient {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn set_connected(&mut self, connected: bool) {
        self.connected = connected;
    }

    pub fn register_star(&mut self, name: &str, _handler: &str) {
        self.stars.insert(name.to_string(), name.to_string());
        tracing::debug!("Star '{}' registered with ABP client", name);
    }

    pub fn unregister_star(&mut self, name: &str) {
        self.stars.remove(name);
        tracing::debug!("Star '{}' unregistered from ABP client", name);
    }

    pub fn list_stars(&self) -> Vec<String> {
        self.stars.keys().cloned().collect()
    }
}

#[async_trait]
impl ProtocolClient for AbpClient {
    async fn connect(&mut self) -> Result<(), AstrBotError> {
        self.connected = true;
        tracing::debug!("ABP client connecting to internal stars");
        Ok(())
    }

    async fn disconnect(&mut self) -> Result<(), AstrBotError> {
        self.connected = false;
        self.stars.clear();
        Ok(())
    }

    fn is_connected(&self) -> bool {
        self.connected
    }

    fn name(&self) -> &'static str {
        "abp-client"
    }
}
