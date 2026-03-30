//! Protocol client implementations for LSP, MCP, ACP, and ABP

use crate::error::AstrBotError;
use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use tokio::io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;
use tokio::net::UnixStream;
use tokio::process::{Child, Command};

// ============================================================================
// Protocol Status
// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProtocolStatus {
    pub connected: bool,
    pub name: String,
}

impl ProtocolStatus {
    pub fn new(name: &str, connected: bool) -> Self {
        Self {
            connected,
            name: name.to_string(),
        }
    }
}

// ============================================================================
// Protocol Client Trait
// ============================================================================

#[async_trait]
pub trait ProtocolClient: Send + Sync {
    fn name(&self) -> &str;
    fn is_connected(&self) -> bool;
    async fn connect(&mut self) -> Result<(), AstrBotError>;
    async fn disconnect(&mut self) -> Result<(), AstrBotError>;
}

// ============================================================================
// LSP Client - Language Server Protocol
// ============================================================================

pub struct LspClient {
    connected: bool,
    child: Option<Child>,
    stdin: Option<tokio::io::BufWriter<tokio::process::ChildStdin>>,
    stdout: Option<tokio::io::BufReader<tokio::process::ChildStdout>>,
    pending_requests: HashMap<i64, tokio::sync::oneshot::Sender<String>>,
    request_id: i64,
}

impl LspClient {
    pub fn new() -> Self {
        Self {
            connected: false,
            child: None,
            stdin: None,
            stdout: None,
            pending_requests: HashMap::new(),
            request_id: 0,
        }
    }

    pub fn set_connected(&mut self, connected: bool) {
        self.connected = connected;
    }

    /// Connect to an LSP server subprocess
    pub async fn connect_to_server(
        &mut self,
        command: Vec<String>,
        workspace_uri: &str,
    ) -> Result<(), AstrBotError> {
        if command.is_empty() {
            return Err(AstrBotError::InvalidState("LSP command is empty".into()));
        }

        let mut cmd = Command::new(&command[0]);
        if command.len() > 1 {
            cmd.args(&command[1..]);
        }

        cmd.stdin(std::process::Stdio::piped());
        cmd.stdout(std::process::Stdio::piped());
        cmd.stderr(std::process::Stdio::piped());

        let mut child = cmd.spawn().map_err(|e| {
            AstrBotError::ConnectionFailed(format!("Failed to spawn LSP server: {e}"))
        })?;

        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| AstrBotError::ConnectionFailed("Failed to capture stdin".into()))?;

        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| AstrBotError::ConnectionFailed("Failed to capture stdout".into()))?;

        self.stdin = Some(tokio::io::BufWriter::new(stdin));
        self.stdout = Some(tokio::io::BufReader::new(stdout));
        self.child = Some(child);
        self.connected = true;

        // Send initialize request
        let initialize_params = serde_json::json!({
            "processId": std::process::id(),
            "rootUri": workspace_uri,
            "capabilities": {}
        });

        self.send_request("initialize", Some(initialize_params))
            .await?;

        // Send initialized notification
        self.send_notification("initialized", None).await?;

        tracing::info!("LSP client connected to server");
        Ok(())
    }

    /// Send a request and wait for response
    pub async fn send_request(
        &mut self,
        method: &str,
        params: Option<serde_json::Value>,
    ) -> Result<String, AstrBotError> {
        let (tx, rx) = tokio::sync::oneshot::channel();
        let id = self.request_id;
        self.request_id += 1;

        self.pending_requests.insert(id, tx);

        let request = serde_json::json!({
            "jsonrpc": "2.0",
            "id": id,
            "method": method,
            "params": params.unwrap_or(serde_json::Value::Null)
        });

        self.send_json(&request).await?;

        rx.await
            .map_err(|_| AstrBotError::Timeout("LSP request timed out".into()))
    }

    /// Send a notification (no response expected)
    pub async fn send_notification(
        &mut self,
        method: &str,
        params: Option<serde_json::Value>,
    ) -> Result<(), AstrBotError> {
        let notification = serde_json::json!({
            "jsonrpc": "2.0",
            "method": method,
            "params": params.unwrap_or(serde_json::Value::Null)
        });

        self.send_json(&notification).await
    }

    async fn send_json(&mut self, msg: &serde_json::Value) -> Result<(), AstrBotError> {
        let content = serde_json::to_string(msg).map_err(AstrBotError::Json)?;
        let header = format!("Content-Length: {}\r\n\r\n", content.len());

        if let Some(stdin) = &mut self.stdin {
            stdin.write_all(header.as_bytes()).await?;
            stdin.write_all(content.as_bytes()).await?;
            stdin.flush().await?;
        }

        Ok(())
    }

    /// Read responses from LSP server
    pub async fn read_responses(&mut self) -> Result<(), AstrBotError> {
        if let Some(stdout) = &mut self.stdout {
            let mut header_buf = Vec::new();

            loop {
                // Read header line
                header_buf.clear();
                stdout.read_until(b'\n', &mut header_buf).await?;

                let header_str = String::from_utf8_lossy(&header_buf);
                let content_length = header_str
                    .strip_prefix("Content-Length: ")
                    .and_then(|s| s.trim().parse::<usize>().ok())
                    .unwrap_or(0);

                // Skip blank line (\r\n)
                if header_buf.len() >= 2 && header_buf[0] == b'\r' && header_buf[1] == b'\n' {
                    // already at content
                } else {
                    // Read the \r\n after Content-Length
                    let mut crlf = [0u8; 2];
                    stdout.read_exact(&mut crlf).await?;
                }

                // Read content
                let mut content = vec![0u8; content_length];
                stdout.read_exact(&mut content).await?;

                let response: serde_json::Value =
                    serde_json::from_slice(&content).map_err(AstrBotError::Json)?;

                // Handle response
                if let Some(id) = response.get("id").and_then(|v| v.as_i64())
                    && let Some(tx) = self.pending_requests.remove(&id) {
                        let _ = tx.send(response.to_string());
                    }
            }
        }
        Ok(())
    }
}

impl Default for LspClient {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl ProtocolClient for LspClient {
    fn name(&self) -> &'static str {
        "lsp"
    }

    fn is_connected(&self) -> bool {
        self.connected
    }

    async fn connect(&mut self) -> Result<(), AstrBotError> {
        self.connected = true;
        tracing::debug!("LSP client connected");
        Ok(())
    }

    async fn disconnect(&mut self) -> Result<(), AstrBotError> {
        self.connected = false;

        // Try graceful shutdown first
        if self.send_notification("shutdown", None).await.is_err() {
            // Ignore errors during shutdown
        }
        if self.send_notification("exit", None).await.is_err() {
            // Ignore errors during exit
        }

        // Terminate LSP server process
        if let Some(mut child) = self.child.take() {
            let _ = child.kill().await;
        }

        self.stdin = None;
        self.stdout = None;
        tracing::info!("LSP client disconnected");
        Ok(())
    }
}

// ============================================================================
// MCP Client - Model Context Protocol
// ============================================================================

pub struct McpClient {
    connected: bool,
    server_url: Option<String>,
    transport: McpTransport,
}

enum McpTransport {
    Stdio {
        child: Option<Child>,
    },
    Http {
        client: Option<reqwest::Client>,
        base_url: String,
    },
    #[allow(dead_code)]
    Sse {
        client: Option<reqwest::Client>,
        base_url: String,
    },
}

impl McpClient {
    pub fn new() -> Self {
        Self {
            connected: false,
            server_url: None,
            transport: McpTransport::Stdio { child: None },
        }
    }

    pub fn set_connected(&mut self, connected: bool) {
        self.connected = connected;
    }

    /// Connect to MCP server via stdio
    pub async fn connect_to_stdio_server(
        &mut self,
        command: Vec<String>,
    ) -> Result<(), AstrBotError> {
        if command.is_empty() {
            return Err(AstrBotError::InvalidState("MCP command is empty".into()));
        }

        let mut cmd = Command::new(&command[0]);
        if command.len() > 1 {
            cmd.args(&command[1..]);
        }

        cmd.stdin(std::process::Stdio::piped());
        cmd.stdout(std::process::Stdio::piped());
        cmd.stderr(std::process::Stdio::piped());

        let child = cmd.spawn().map_err(|e| {
            AstrBotError::ConnectionFailed(format!("Failed to spawn MCP server: {e}"))
        })?;

        self.transport = McpTransport::Stdio { child: Some(child) };
        self.connected = true;
        self.server_url = Some("stdio".to_string());

        tracing::info!("MCP client connected via stdio");
        Ok(())
    }

    /// Connect to MCP server via HTTP/SSE
    pub async fn connect_to_http_server(&mut self, base_url: &str) -> Result<(), AstrBotError> {
        let client = reqwest::Client::new();
        self.transport = McpTransport::Http {
            client: Some(client),
            base_url: base_url.to_string(),
        };
        self.connected = true;
        self.server_url = Some(base_url.to_string());

        tracing::info!("MCP client connected via HTTP: {}", base_url);
        Ok(())
    }

    /// List available tools on MCP server
    pub async fn list_tools(&self) -> Result<Vec<McpTool>, AstrBotError> {
        match &self.transport {
            McpTransport::Http { client, base_url } => {
                if let Some(client) = client {
                    let url = format!("{}/tools", base_url);
                    let response = client
                        .get(&url)
                        .send()
                        .await
                        .map_err(|e| AstrBotError::ConnectionFailed(e.to_string()))?;

                    let tools: Vec<McpTool> = response
                        .json()
                        .await
                        .map_err(|e| AstrBotError::Protocol(e.to_string()))?;

                    return Ok(tools);
                }
            }
            McpTransport::Stdio { .. } => {
                // Stdio-based tool listing would require JSON-RPC communication
            }
            McpTransport::Sse { .. } => {}
        }
        Ok(vec![])
    }

    /// Call a tool on MCP server
    pub async fn call_tool(
        &self,
        tool_name: &str,
        arguments: serde_json::Value,
    ) -> Result<serde_json::Value, AstrBotError> {
        match &self.transport {
            McpTransport::Http { client, base_url } => {
                if let Some(client) = client {
                    let url = format!("{}/call", base_url);
                    let request = serde_json::json!({
                        "tool": tool_name,
                        "arguments": arguments
                    });

                    let response = client
                        .post(&url)
                        .json(&request)
                        .send()
                        .await
                        .map_err(|e| AstrBotError::ConnectionFailed(e.to_string()))?;

                    let result: serde_json::Value = response
                        .json()
                        .await
                        .map_err(|e| AstrBotError::Protocol(e.to_string()))?;

                    return Ok(result);
                }
            }
            McpTransport::Stdio { child: _ } => {
                // Stdio-based tool calling would require JSON-RPC communication
                tracing::debug!("MCP stdio tool call: {} with {:?}", tool_name, arguments);
            }
            McpTransport::Sse { .. } => {}
        }

        Err(AstrBotError::NotConnected("MCP transport not ready".into()))
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct McpTool {
    pub name: String,
    pub description: String,
    pub input_schema: serde_json::Value,
}

impl Default for McpClient {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl ProtocolClient for McpClient {
    fn name(&self) -> &'static str {
        "mcp"
    }

    fn is_connected(&self) -> bool {
        self.connected
    }

    async fn connect(&mut self) -> Result<(), AstrBotError> {
        self.connected = true;
        tracing::debug!("MCP client connected");
        Ok(())
    }

    async fn disconnect(&mut self) -> Result<(), AstrBotError> {
        self.connected = false;

        if let McpTransport::Stdio { child } = &mut self.transport
            && let Some(mut child) = child.take() {
                let _ = child.kill().await;
            }

        tracing::info!("MCP client disconnected");
        Ok(())
    }
}

// ============================================================================
// ACP Client - Agent Communication Protocol (e.g., Google A2A)
// ============================================================================

pub struct AcpClient {
    connected: bool,
    server_url: Option<String>,
    tcp_stream: Option<TcpStream>,
    pending_requests: HashMap<String, tokio::sync::oneshot::Sender<serde_json::Value>>,
    request_id: u64,
}

impl AcpClient {
    pub fn new() -> Self {
        Self {
            connected: false,
            server_url: None,
            tcp_stream: None,
            pending_requests: HashMap::new(),
            request_id: 0,
        }
    }

    pub fn set_connected(&mut self, connected: bool) {
        self.connected = connected;
    }

    /// Connect to ACP server via TCP
    pub async fn connect_to_tcp(&mut self, host: &str, port: u16) -> Result<(), AstrBotError> {
        let addr = format!("{}:{}", host, port);
        let stream = TcpStream::connect(&addr)
            .await
            .map_err(|e| AstrBotError::ConnectionFailed(format!("TCP connect failed: {e}")))?;

        self.tcp_stream = Some(stream);
        self.connected = true;
        self.server_url = Some(addr.clone());

        tracing::info!("ACP client connected via TCP: {}", addr);
        Ok(())
    }

    /// Connect to ACP server via Unix socket
    /// Note: For now, Unix socket support is simplified - just mark as connected
    pub async fn connect_to_unix_socket(&mut self, socket_path: &str) -> Result<(), AstrBotError> {
        let _stream = UnixStream::connect(socket_path).await.map_err(|e| {
            AstrBotError::ConnectionFailed(format!("Unix socket connect failed: {e}"))
        })?;

        self.connected = true;
        self.server_url = Some(socket_path.to_string());

        tracing::info!("ACP client connected via Unix socket: {}", socket_path);
        Ok(())
    }

    /// Send a request and wait for response
    pub async fn call_tool(
        &mut self,
        server_name: &str,
        tool_name: &str,
        arguments: serde_json::Value,
    ) -> Result<serde_json::Value, AstrBotError> {
        let request_id = format!("{}-{}", self.request_id, server_name);
        self.request_id += 1;

        let (tx, rx) = tokio::sync::oneshot::channel();
        self.pending_requests.insert(request_id.clone(), tx);

        let request = serde_json::json!({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": format!("{}/{}", server_name, tool_name),
            "params": arguments
        });

        self.send_json(&request).await?;

        rx.await
            .map_err(|_| AstrBotError::Timeout("ACP request timed out".into()))
    }

    /// Send a notification
    pub async fn send_notification(
        &mut self,
        method: &str,
        params: Option<serde_json::Value>,
    ) -> Result<(), AstrBotError> {
        let notification = serde_json::json!({
            "jsonrpc": "2.0",
            "method": method,
            "params": params.unwrap_or(serde_json::Value::Null)
        });

        self.send_json(&notification).await
    }

    async fn send_json(&mut self, msg: &serde_json::Value) -> Result<(), AstrBotError> {
        let content = serde_json::to_string(msg).map_err(AstrBotError::Json)?;
        let header = serde_json::to_string(&serde_json::json!({
            "content-length": content.len()
        }))? + "\n";

        if let Some(stream) = &mut self.tcp_stream {
            stream.write_all(header.as_bytes()).await?;
            stream.write_all(content.as_bytes()).await?;
        }

        Ok(())
    }

    /// Read messages from ACP server
    pub async fn read_messages(&mut self) -> Result<(), AstrBotError> {
        // Simplified - actual implementation would use BufReader
        tracing::debug!("ACP read_messages called");
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
    fn name(&self) -> &'static str {
        "acp"
    }

    fn is_connected(&self) -> bool {
        self.connected
    }

    async fn connect(&mut self) -> Result<(), AstrBotError> {
        self.connected = true;
        tracing::debug!("ACP client connected");
        Ok(())
    }

    async fn disconnect(&mut self) -> Result<(), AstrBotError> {
        self.connected = false;
        self.tcp_stream = None;
        tracing::info!("ACP client disconnected");
        Ok(())
    }
}
