# AstrBot Core Runtime (Rust) Specification

## Overview

AstrBot Core Runtime is a high-performance Rust implementation of the core orchestrator, protocol clients, and configuration management. It provides Python bindings via pyo3 for seamless integration with the existing AstrBot Python codebase.

## Module Structure

### Core Modules

#### 1. orchestrator.rs - Runtime Orchestrator

Central coordinator managing protocol clients and star registry.

```rust
pub struct Orchestrator {
    running: RwLock<bool>,
    stars: RwLock<HashMap<String, String>>,
    stats: RuntimeStats,
    protocol_lsp: RwLock<ProtocolStatus>,
    protocol_mcp: RwLock<ProtocolStatus>,
    protocol_acp: RwLock<ProtocolStatus>,
    protocol_abp: RwLock<ProtocolStatus>,
}

impl Orchestrator {
    pub fn new() -> Self;
    pub fn start(&self) -> Result<(), AstrBotError>;
    pub fn stop(&self) -> Result<(), AstrBotError>;
    pub fn is_running(&self) -> bool;
    pub fn register_star(&self, name: &str, handler: &str) -> Result<(), AstrBotError>;
    pub fn unregister_star(&self, name: &str) -> Result<(), AstrBotError>;
    pub fn list_stars(&self) -> Vec<String>;
    pub fn record_activity(&self);
    pub fn stats(&self) -> RuntimeStats;
    pub fn get_protocol_status(&self, protocol: &str) -> Option<ProtocolStatus>;
    pub fn set_protocol_connected(&self, protocol: &str, connected: bool) -> Result<(), AstrBotError>;
}
```

#### 2. protocol.rs - Protocol Client Trait

Unified interface for all protocol clients.

```rust
#[async_trait]
pub trait ProtocolClient: Send + Sync {
    async fn connect(&mut self) -> Result<(), AstrBotError>;
    async fn disconnect(&mut self) -> Result<(), AstrBotError>;
    fn is_connected(&self) -> bool;
    fn name(&self) -> &'static str;
}
```

Implementations:
- `LspClient` - Language Server Protocol client
- `McpClient` - Model Context Protocol client
- `AcpClient` - AstrBot Communication Protocol client
- `AbpClient` - AstrBot Protocol client

#### 3. message.rs - Message Types

Message structures with serde serialization.

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Message {
    pub id: String,
    pub content: String,
    pub sender: String,
    pub timestamp: f64,
    pub message_type: MessageType,
    pub metadata: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Default)]
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
```

#### 4. stats.rs - Runtime Statistics

Thread-safe message counting and uptime tracking.

```rust
#[derive(Debug, Clone)]
pub struct RuntimeStats {
    message_count: AtomicU64,
    start_time: Instant,
    last_activity: Mutex<Option<Instant>>,
}

impl RuntimeStats {
    pub fn new() -> Self;
    pub fn record_message(&self);
    pub fn message_count(&self) -> u64;
    pub fn uptime_seconds(&self) -> f64;
    pub fn last_activity_time(&self) -> Option<f64>;
}
```

#### 5. config.rs - Configuration Management

TOML-based configuration with serde.

```rust
pub struct Config {
    pub runtime: RuntimeConfig,
    pub protocols: ProtocolsConfig,
    pub logging: LoggingConfig,
}

impl Config {
    pub fn load(path: &PathBuf) -> anyhow::Result<Self>;
    pub fn save(&self, path: &PathBuf) -> anyhow::Result<()>;
}
```

#### 6. error.rs - Error Types

Using thiserror for ergonomic error handling.

```rust
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
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),
}
```

#### 7. python.rs - Python Bindings

pyo3 bindings for Python integration.

```rust
#[pyclass]
pub struct PythonOrchestrator {
    inner: Orchestrator,
}

#[pymethods]
impl PythonOrchestrator {
    #[new]
    pub fn new() -> Self;
    pub fn start(&self) -> PyResult<()>;
    pub fn stop(&self) -> PyResult<()>;
    pub fn is_running(&self) -> bool;
    pub fn register_star(&self, name: &str, handler: &str) -> PyResult<()>;
    pub fn unregister_star(&self, name: &str) -> PyResult<()>;
    pub fn list_stars(&self) -> Vec<String>;
    pub fn record_activity(&self);
    pub fn get_stats(&self) -> PyResult<Py<PyAny>>;
    pub fn set_protocol_connected(&self, protocol: &str, connected: bool) -> PyResult<()>;
    pub fn get_protocol_status(&self, protocol: &str) -> Option<Py<PyAny>>;
}

#[pyfunction]
pub fn get_orchestrator(py: Python<'_>) -> PyResult<&'static Py<PythonOrchestrator>>;
```

#### 8. main.rs - CLI Binary

Command-line interface using clap.

```rust
#[derive(Parser, Debug)]
enum Command {
    Start,
    Stats,
    Health,
}
```

Commands:
- `start` - Start the astrbot-core runtime
- `stats` - Display runtime statistics
- `health` - Check runtime health status

## Rust Rules

1. **No unsafe code** - All memory access is safe
2. **No .unwrap()** - Use `?` operator or `expect()` with descriptive messages
3. **Clippy pedantic compliance** - Pass `cargo clippy` with no warnings
4. **Full error handling** - All errors properly propagated

## Python Integration

The module is importable as `astrbot_core`:

```python
from astrbot_core import PythonOrchestrator, get_orchestrator

# Get singleton
orch = get_orchestrator()

# Use methods
orch.start()
orch.register_star("my-star", "handler-id")
stars = orch.list_stars()
```

## Cargo Features

```toml
[features]
default = ["python"]
python = ["pyo3"]
```

- `python`: Enable pyo3 bindings (default)
- Without `python`: Pure Rust library without Python dependencies

## Dependencies

- `serde` + `serde_json` - Serialization
- `toml` - Configuration file parsing
- `tokio` - Async runtime
- `tracing` + `tracing-subscriber` - Logging
- `anyhow` - Error handling
- `thiserror` - Error derive
- `async-trait` - Async trait methods
- `clap` - CLI argument parsing
- `pyo3` - Python bindings (optional)

## Verification Criteria

- [x] `cargo clippy` passes with no warnings
- [x] `cargo build` compiles successfully
- [x] `cargo test` passes (if tests exist)
- [x] Python module imports successfully
- [x] CLI `--help` works correctly
