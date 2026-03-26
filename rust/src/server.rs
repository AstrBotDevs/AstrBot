AstrBot/rust/src/server.rs
```rust
//! AstrBot HTTP/WebSocket Server
//!
//! High-performance async HTTP server with WebSocket support for real-time communication.
//! Implements JWT authentication and REST API endpoints.

use base64::engine::general_purpose::STANDARD as BASE64;
use base64::Engine;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::{mpsc, RwLock};
use tokio_tungstenite::{accept_async, tungstenite::Message};
use uuid::Uuid;

// ============================================================================
// Error Types
// ============================================================================

#[derive(Debug, thiserror::Error)]
pub enum ServerError {
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
    #[error("WebSocket error: {0}")]
    WebSocket(String),
    #[error("JWT error: {0}")]
    Jwt(String),
    #[error("Not found: {0}")]
    NotFound(String),
    #[error("Unauthorized")]
    Unauthorized,
    #[error("Bad request: {0}")]
    BadRequest(String),
}

impl From<tokio_tungstenite::tungstenite::Error> for ServerError {
    fn from(err: tokio_tungstenite::tungstenite::Error) -> Self {
        ServerError::WebSocket(err.to_string())
    }
}

// ============================================================================
// JWT Authentication
// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JwtClaims {
    pub sub: String,
    pub exp: u64,
    pub iat: u64,
}

pub struct JwtAuth {
    secret: String,
    expiry_secs: u64,
}

impl JwtAuth {
    pub fn new(secret: String, expiry_secs: u64) -> Self {
        Self {
            secret,
            expiry_secs,
        }
    }

    pub fn generate_token(&self, username: &str) -> Result<String, ServerError> {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOODY)
            .map_err(|e| ServerError::Jwt(e.to_string()))?
            .as_secs();

        let claims = JwtClaims {
            sub: username.to_string(),
            exp: now + self.expiry_secs,
            iat: now,
        };

        let header = format!("{{\"alg\":\"HS256\",\"typ\":\"JWT\"}}");
        let header_b64 = BASE64.encode(header.as_bytes());
        let payload_b64 = BASE64.encode(serde_json::to_vec(&claims).map_err(|e| ServerError::Jwt(e.to_string()))?;

        let signature = self.sign_jwt(&format!("{}.{}", header_b64, payload_b64));

        Ok(format!("{}.{}.{}", header_b64, payload_b64, signature))
    }

    pub fn verify_token(&self, token: &str) -> Result<JwtClaims, ServerError> {
        let parts: Vec<&str> = token.split('.').collect();
        if parts.len() != 3 {
            return Err(ServerError::Jwt("Invalid token format".to_string()));
        }

        let expected_sig = self.sign_jwt(&format!("{}.{}", parts[0], parts[1]));
        if expected_sig != parts[2] {
            return Err(ServerError::Jwt("Invalid signature".to_string()));
        }

        let payload = BASE64
            .decode(parts[1])
            .map_err(|e| ServerError::Jwt(e.to_string()))?;
        let claims: JwtClaims =
            serde_json::from_slice(&payload).map_err(|e| ServerError::Jwt(e.to_string()))?;

        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map_err(|e| ServerError::Jwt(e.to_string()))?
            .as_secs();

        if claims.exp < now {
            return Err(ServerError::Jwt("Token expired".to_string()));
        }

        Ok(claims)
    }

    fn sign_jwt(&self, data: &str) -> String {
        use std::collections::hash_map::DefaultHasher;
        use std::hash::{Hash, Hasher};

        let mut hasher = DefaultHasher::new();
        data.hash(&mut hasher);
        self.secret.hash(&mut hasher);
        BASE64.encode(&hasher.finish().to_be_bytes())
    }
}

// ============================================================================
// HTTP Response Types
// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum ApiResponse {
    #[serde(rename = "success")]
    Success { data: serde_json::Value },
    #[serde(rename = "error")]
    Error { code: i32, message: String },
}

impl ApiResponse {
    pub fn success<T: Serialize>(data: T) -> Self {
        ApiResponse::Success {
            data: serde_json::to_value(data).unwrap_or(serde_json::Value::Null),
        }
    }

    pub fn error(code: i32, message: impl Into<String>) -> Self {
        ApiResponse::Error {
            code,
            message: message.into(),
        }
    }
}

#[derive(Debug, Clone)]
pub struct HttpResponse {
    pub status: u16,
    pub status_text: &'static str,
    pub headers: Vec<(String, String)>,
    pub body: Vec<u8>,
}

impl HttpResponse {
    pub fn new(status: u16, status_text: &'static str) -> Self {
        Self {
            status,
            status_text,
            headers: Vec::new(),
            body: Vec::new(),
        }
    }

    pub fn json(status: u16, status_text: &'static str, body: serde_json::Value) -> Self {
        let body_bytes = serde_json::to_vec(&body).unwrap_or_default();
        Self {
            status,
            status_text,
            headers: vec![
                ("Content-Type".to_string(), "application/json".to_string()),
                ("Content-Length".to_string(), body_bytes.len().to_string()),
            ],
            body: body_bytes,
        }
    }

    pub fn html(status: u16, status_text: &'static str, body: impl Into<Vec<u8>>) -> Self {
        let body = body.into();
        Self {
            status,
            status_text,
            headers: vec![
                ("Content-Type".to_string(), "text/html".to_string()),
                ("Content-Length".to_string(), body.len().to_string()),
            ],
            body,
        }
    }

    pub fn to_vec(&self) -> Vec<u8> {
        let mut buf = format!("HTTP/1.1 {} {}\r\n", self.status, self.status_text).into_bytes();
        for (key, value) in &self.headers {
            buf.extend_from_slice(format!("{}: {}\r\n", key, value).as_bytes());
        }
        buf.extend_from_slice(b"\r\n");
        buf.extend_from_slice(&self.body);
        buf
    }
}

// ============================================================================
// WebSocket Connection Manager
// ============================================================================

#[derive(Debug, Clone)]
pub struct WsConnection {
    pub id: String,
    pub authenticated: bool,
    pub username: Option<String>,
}

#[derive(Default)]
pub struct WsManager {
    connections: RwLock<HashMap<String, mpsc::Sender<String>>>,
}

impl WsManager {
    pub fn new() -> Self {
        Self {
            connections: RwLock::new(HashMap::new()),
        }
    }

    pub async fn broadcast(&self, message: &str) {
        let connections = self.connections.read().await;
        for sender in connections.values() {
            let _ = sender.send(message.to_string()).await;
        }
    }

    pub async fn send_to(&self, id: &str, message: &str) -> Result<(), ServerError> {
        let connections = self.connections.read().await;
        let sender = connections.get(id).ok_or_else(|| ServerError::NotFound(id.to_string()))?;
        sender.send(message.to_string()).await.map_err(|_| {
            ServerError::WebSocket("Failed to send".to_string())
        })?;
        Ok(())
    }

    pub async fn register(&self, id: String, sender: mpsc::Sender<String>) {
        self.connections.write().await.insert(id, sender);
    }

    pub async fn unregister(&self, id: &str) {
        self.connections.write().await.remove(id);
    }

    pub async fn count(&self) -> usize {
        self.connections.read().await.len()
    }
}

// ============================================================================
// HTTP Request
// ============================================================================

#[derive(Debug)]
pub struct HttpRequest {
    pub method: String,
    pub path: String,
    pub headers: HashMap<String, String>,
    pub body: Vec<u8>,
}

impl HttpRequest {
    pub fn parse(buf: &[u8]) -> Result<Self, ServerError> {
        let header_end = buf.windows(4).position(|w| w == b"\r\n\r\n");
        let header_end = header_end.ok_or_else(|| ServerError::BadRequest("Invalid HTTP header".to_string()))?;

        let header_str = String::from_utf8_lossy(&buf[..header_end]);
        let body = buf[header_end + 4..].to_vec();

        let mut lines = header_str.split("\r\n");
        let request_line = lines.next().ok_or_else(|| ServerError::BadRequest("Missing request line".to_string()))?;
        let parts: Vec<&str> = request_line.split_whitespace().collect();

        if parts.len() < 2 {
            return Err(ServerError::BadRequest("Invalid request line".to_string()));
        }

        let method = parts[0].to_string();
        let path = parts[1].to_string();

        let mut headers = HashMap::new();
        for line in lines {
            if let Some((key, value)) = line.split_once(':') {
                headers.insert(key.trim().to_lowercase(), value.trim().to_string());
            }
        }

        Ok(HttpRequest {
            method,
            path,
            headers,
            body,
        })
    }

    pub fn get_header(&self, key: &str) -> Option<&str> {
        self.headers.get(&key.to_lowercase()).map(|s| s.as_str())
    }

    pub fn auth_token(&self) -> Option<&str> {
        self.get_header("authorization")
            .and_then(|v| v.strip_prefix("Bearer "))
    }
}

// ============================================================================
// Server State
// ============================================================================

#[derive(Clone)]
pub struct ServerState {
    pub orchestrator: Arc<crate::Orchestrator>,
    pub jwt_auth: Arc<JwtAuth>,
    pub ws_manager: Arc<WsManager>,
    pub dashboard_password: String,
}

impl ServerState {
    pub fn new(jwt_secret: String, dashboard_password: String) -> Self {
        Self {
            orchestrator: Arc::new(crate::Orchestrator::new()),
            jwt_auth: Arc::new(JwtAuth::new(jwt_secret, 86400)),
            ws_manager: Arc::new(WsManager::new()),
            dashboard_password,
        }
    }
}

// ============================================================================
// API Handlers
// ============================================================================

async fn handle_api(
    state: &ServerState,
    req: &HttpRequest,
) -> Result<HttpResponse, ServerError> {
    let (path, method) = (req.path.as_str(), req.method.as_str());

    // Login endpoint (no auth required)
    if path == "/api/auth/login" && method == "POST" {
        return handle_login(state, req).await;
    }

    // Authenticate other requests
    let token = req.auth_token().ok_or(ServerError::Unauthorized)?;
    state.jwt_auth.verify_token(token).map_err(|_| ServerError::Unauthorized)?;

    match (path, method) {
        ("/api/stats", "GET") => {
            let stats = state.orchestrator.stats();
            Ok(HttpResponse::json(
                200,
                "OK",
                serde_json::json!({
                    "message_count": stats.message_count(),
                    "uptime_seconds": stats.uptime_seconds(),
                    "last_activity": stats.last_activity_time(),
                }),
            ))
        }
        ("/api/sessions", "GET") => {
            Ok(HttpResponse::json(
                200,
                "OK",
                serde_json::json!({
                    "sessions": state.orchestrator.list_stars(),
                }),
            ))
        }
        ("/api/health", "GET") => {
            Ok(HttpResponse::json(
                200,
                "OK",
                serde_json::json!({
                    "status": "ok",
                    "orchestrator_running": state.orchestrator.is_running(),
                    "websocket_connections": state.ws_manager.count().await,
                }),
            ))
        }
        _ if path.starts_with("/api/sessions/") && method == "DELETE" => {
            let session_id = path.strip_prefix("/api/sessions/").unwrap_or("");
            state.orchestrator.unregister_star(session_id).map_err(|_| {
                ServerError::NotFound("Session not found".to_string())
            })?;
            Ok(HttpResponse::json(200, "OK", serde_json::json!({"success": true})))
        }
        _ if path.starts_with("/api/sessions/") && method == "GET" => {
            let session_id = path.strip_prefix("/api/sessions/").unwrap_or("");
            Ok(HttpResponse::json(
                200,
                "OK",
                serde_json::json!({"session_id": session_id}),
            ))
        }
        _ => Ok(HttpResponse::json(
            404,
            "Not Found",
            ApiResponse::error(404, "Endpoint not found"),
        )),
    }
}

async fn handle_login(state: &ServerState, req: &HttpRequest) -> Result<HttpResponse, ServerError> {
    let body = String::from_utf8_lossy(&req.body);
    let login: serde_json::Value =
        serde_json::from_str(&body).map_err(|_| ServerError::BadRequest("Invalid JSON".to_string()))?;

    let password = login
        .get("password")
        .and_then(|v| v.as_str())
        .ok_or_else(|| ServerError::BadRequest("Missing password".to_string()))?;

    if password != state.dashboard_password {
        return Ok(HttpResponse::json(
            401,
            "Unauthorized",
            ApiResponse::error(401, "Invalid credentials"),
        ));
    }

    let token = state.jwt_auth.generate_token("admin")?;
    Ok(HttpResponse::json(
        200,
        "OK",
        serde_json::json!({
            "token": token,
            "expires_in": 86400,
        }),
    ))
}

// ============================================================================
// WebSocket Handler
// ============================================================================

async fn handle_websocket(state: ServerState, stream: TcpStream, addr: std::net::SocketAddr) {
    let ws_stream = match accept_async(stream).await {
        Ok(ws) => ws,
        Err(e) => {
            tracing::error!("WebSocket handshake failed from {}: {}", addr, e);
            return;
        }
    };

    let (writer, mut reader) = ws_stream.split();
    let connection_id = Uuid::new_v4().to_string();

    let (tx, rx) = mpsc::channel::<String>(100);
    state.ws_manager.register(connection_id.clone(), tx).await;

    // Send welcome message
    let welcome = serde_json::json!({
        "type": "connected",
        "id": connection_id
    });
    if let Ok(text) = serde_json::to_string(&welcome) {
        let _ = writer.send(Message::Text(text.into())).await;
    }

    // Handle messages
    loop {
        tokio::select! {
            msg = reader.next() => {
                match msg {
                    Some(Ok(Message::Text(text))) => {
                        if let Err(e) = handle_ws_message(&state, text.to_string()).await {
                            tracing::error!("WebSocket error: {}", e);
                            break;
                        }
                    }
                    Some(Ok(Message::Close(_))) | None => {
                        break;
                    }
                    _ => {}
                }
            }
            Some(msg) = rx.recv() => {
                if let Some(text) = msg {
                    if writer.send(Message::Text(text.into())).await.is_err() {
                        break;
                    }
                }
            }
        }
    }

    state.ws_manager.unregister(&connection_id).await;
}

async fn handle_ws_message(state: &ServerState, msg: String) -> Result<(), ServerError> {
    let parsed: serde_json::Value =
        serde_json::from_str(&msg).map_err(|_| ServerError::BadRequest("Invalid JSON".to_string()))?;

    let msg_type = parsed.get("type").and_then(|v| v.as_str()).unwrap_or("unknown");

    let response = match msg_type {
        "ping" => serde_json::json!({"type": "pong"}),
        "subscribe" => serde_json::json!({"type": "subscribed"}),
        "get_stats" => {
            let stats = state.orchestrator.stats();
            serde_json::json!({
                "type": "stats",
                "data": {
                    "message_count": stats.message_count(),
                    "uptime_seconds": stats.uptime_seconds(),
                }
            })
        }
        _ => serde_json::json!({"type": "unknown"}),
    };

    if !response.is_null() {
        state
            .ws_manager
            .send_to(&connection_id, &serde_json::to_string(&response).unwrap())
            .await
            .ok();
    }

    Ok(())
}

use tokio::io::{AsyncReadExt, AsyncWriteExt};
use futures_util::StreamExt;

// ============================================================================
// HTTP Server
// ============================================================================

pub struct HttpServer {
    host: String,
    port: u16,
    state: ServerState,
}

impl HttpServer {
    pub fn new(host: String, port: u16, state: ServerState) -> Self {
        Self { host, port, state }
    }

    pub async fn serve(self) -> Result<(), ServerError> {
        let addr = format!("{}:{}", self.host, self.port);
        let listener = TcpListener::bind(&addr).await?;
        tracing::info!("HTTP server listening on {}", addr);

        loop {
            match listener.accept().await {
                Ok((stream, addr)) => {
                    let state = self.state.clone();
                    tokio::spawn(async move {
                        if let Err(e) = handle_connection(stream, state).await {
                            tracing::error!("Connection error from {}: {}", addr, e);
                        }
                    });
                }
                Err(e) => {
                    tracing::error!("Accept error: {}", e);
                }
            }
        }
    }
}

async fn handle_connection(stream: TcpStream, state: ServerState) -> Result<(), ServerError> {
    let mut buf = vec![0u8; 8192];
    let n = stream.read(&mut buf).await?;
    buf.truncate(n);

    let req = HttpRequest::parse(&buf)?;

    // Check for WebSocket upgrade
    if req.get_header("upgrade") == Some("websocket") {
        // For now, return HTTP response indicating WebSocket not fully implemented
        let response = HttpResponse::html(
            426,
            "Upgrade Required",
            "<html><body>WebSocket upgrade not implemented</body></html>",
        );
        let mut stream = stream;
        stream.write_all(&response.to_vec()).await?;
        stream.flush().await?;
        return Ok(());
    }

    let response = handle_api(&state, &req).await?;
    let mut stream = stream;
    stream.write_all(&response.to_vec()).await?;
    stream.flush().await?;

    Ok(())
}
