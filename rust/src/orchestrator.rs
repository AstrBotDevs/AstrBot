//! Core orchestrator for AstrBot runtime
//!
//! Manages lifecycle of all protocol clients and stars (plugins).

use crate::abp::{AbpClient, PluginConfig, PluginLoadMode};
use crate::error::AstrBotError;
use crate::protocol::{AcpClient, LspClient, McpClient, ProtocolClient};
use crate::stats::RuntimeStats;
use std::collections::HashMap;
use std::sync::{Arc, RwLock};
use tokio::sync::broadcast;
use tokio::time::{Duration, interval};
use tracing::{debug, info, warn};

// ============================================================================
// Orchestrator
// ============================================================================

/// Main orchestrator coordinating all protocol clients and stars
pub struct Orchestrator {
    /// Running state
    running: RwLock<bool>,
    /// Shutdown signal sender
    shutdown_tx: Arc<RwLock<Option<broadcast::Sender<()>>>>,
    /// Protocol clients
    lsp: RwLock<LspClient>,
    mcp: RwLock<McpClient>,
    acp: RwLock<AcpClient>,
    abp: RwLock<AbpClient>,
    /// Star registry
    stars: RwLock<HashMap<String, StarRegistration>>,
    /// Runtime statistics
    stats: RuntimeStats,
}

/// Star registration entry
#[derive(Debug, Clone)]
pub struct StarRegistration {
    pub name: String,
    pub handler: String,
}

impl Default for Orchestrator {
    fn default() -> Self {
        Self::new()
    }
}

impl Orchestrator {
    /// Create a new Orchestrator instance
    #[must_use]
    pub fn new() -> Self {
        Self {
            running: RwLock::new(false),
            shutdown_tx: Arc::new(RwLock::new(None)),
            lsp: RwLock::new(LspClient::new()),
            mcp: RwLock::new(McpClient::new()),
            acp: RwLock::new(AcpClient::new()),
            abp: RwLock::new(AbpClient::new()),
            stars: RwLock::new(HashMap::new()),
            stats: RuntimeStats::new(),
        }
    }

    /// Start the orchestrator and all protocol clients (sync version)
    pub fn start_sync(&self) -> Result<(), AstrBotError> {
        {
            let mut running = self
                .running
                .write()
                .map_err(|_| AstrBotError::InvalidState("Failed to acquire write lock".into()))?;
            if *running {
                return Err(AstrBotError::InvalidState(
                    "Orchestrator already started".into(),
                ));
            }
            *running = true;
        }

        let (tx, _rx) = broadcast::channel(1);
        {
            let mut shutdown_tx = self
                .shutdown_tx
                .write()
                .map_err(|_| AstrBotError::InvalidState("Failed to acquire write lock".into()))?;
            *shutdown_tx = Some(tx);
        }

        // Connect all protocol clients (sync)
        self.connect_protocols_sync()?;

        info!("Orchestrator started");
        Ok(())
    }

    /// Connect all protocol clients (sync version for Python binding)
    fn connect_protocols_sync(&self) -> Result<(), AstrBotError> {
        // Connect LSP
        {
            let mut lsp = self
                .lsp
                .write()
                .map_err(|_| AstrBotError::InvalidState("Failed to acquire write lock".into()))?;
            // For now, just mark as connected (actual connection is async)
            lsp.set_connected(true);
        }

        // Connect MCP
        {
            let mut mcp = self
                .mcp
                .write()
                .map_err(|_| AstrBotError::InvalidState("Failed to acquire write lock".into()))?;
            mcp.set_connected(true);
        }

        // Connect ACP
        {
            let mut acp = self
                .acp
                .write()
                .map_err(|_| AstrBotError::InvalidState("Failed to acquire write lock".into()))?;
            acp.set_connected(true);
        }

        // Connect ABP
        {
            let mut abp = self
                .abp
                .write()
                .map_err(|_| AstrBotError::InvalidState("Failed to acquire write lock".into()))?;
            abp.set_connected(true);
        }

        Ok(())
    }

    /// Start the orchestrator and all protocol clients (async)
    pub async fn start(&self) -> Result<(), AstrBotError> {
        self.start_sync()
    }

    /// Main event loop
    pub async fn run_loop(&self) -> Result<(), AstrBotError> {
        if !self.is_running() {
            return Err(AstrBotError::InvalidState(
                "Orchestrator not started".into(),
            ));
        }

        info!("Orchestrator event loop started");
        let mut tick_interval = interval(Duration::from_secs(5));

        loop {
            tokio::select! {
                _ = tick_interval.tick() => {
                    self.periodic_health_check();
                }
                _ = self.wait_for_shutdown() => {
                    info!("Orchestrator shutdown signal received");
                    break;
                }
            }

            if !self.is_running() {
                break;
            }
        }

        info!("Orchestrator event loop stopped");
        Ok(())
    }

    /// Wait for shutdown signal
    async fn wait_for_shutdown(&self) {
        let tx_guard = self.shutdown_tx.read().ok();
        let tx = tx_guard.as_ref().and_then(|t| t.as_ref());

        if let Some(tx) = tx {
            let mut rx = tx.subscribe();
            let _ = rx.recv().await;
        } else {
            tokio::time::sleep(Duration::MAX).await;
        }
    }

    /// Periodic health check for all protocol clients
    fn periodic_health_check(&self) {
        debug!("Running periodic health check");

        if let Ok(lsp) = self.lsp.read()
            && !lsp.is_connected() {
                warn!("LSP client disconnected");
            }

        if let Ok(mcp) = self.mcp.read()
            && !mcp.is_connected() {
                warn!("MCP client disconnected");
            }

        if let Ok(acp) = self.acp.read()
            && !acp.is_connected() {
                warn!("ACP client disconnected");
            }
    }

    /// Stop the orchestrator (sync version)
    pub fn stop_sync(&self) -> Result<(), AstrBotError> {
        {
            let mut running = self
                .running
                .write()
                .map_err(|_| AstrBotError::InvalidState("Failed to acquire write lock".into()))?;
            *running = false;
        }

        if let Ok(tx_guard) = self.shutdown_tx.read()
            && let Some(tx) = tx_guard.as_ref() {
                let _ = tx.send(());
            }

        self.shutdown_protocols_sync()?;
        info!("Orchestrator stopped");
        Ok(())
    }

    /// Shutdown all protocol clients (sync version)
    fn shutdown_protocols_sync(&self) -> Result<(), AstrBotError> {
        {
            let mut lsp = self
                .lsp
                .write()
                .map_err(|_| AstrBotError::InvalidState("Failed to acquire write lock".into()))?;
            lsp.set_connected(false);
        }

        {
            let mut mcp = self
                .mcp
                .write()
                .map_err(|_| AstrBotError::InvalidState("Failed to acquire write lock".into()))?;
            mcp.set_connected(false);
        }

        {
            let mut acp = self
                .acp
                .write()
                .map_err(|_| AstrBotError::InvalidState("Failed to acquire write lock".into()))?;
            acp.set_connected(false);
        }

        {
            let mut abp = self
                .abp
                .write()
                .map_err(|_| AstrBotError::InvalidState("Failed to acquire write lock".into()))?;
            abp.set_connected(false);
        }

        Ok(())
    }

    /// Stop the orchestrator (async)
    pub async fn stop(&self) -> Result<(), AstrBotError> {
        self.stop_sync()
    }

    /// Check if orchestrator is running
    #[must_use]
    pub fn is_running(&self) -> bool {
        self.running.read().map(|r| *r).unwrap_or(false)
    }

    /// Register a star (plugin)
    pub fn register_star(&self, name: &str, handler: &str) -> Result<(), AstrBotError> {
        let mut stars = self
            .stars
            .write()
            .map_err(|_| AstrBotError::InvalidState("Failed to acquire write lock".into()))?;

        let registration = StarRegistration {
            name: name.to_string(),
            handler: handler.to_string(),
        };

        stars.insert(name.to_string(), registration);

        // 根据 handler 判断加载模式：包含 "/" 视为 Unix Socket 路径，否则为模块名
        if handler.starts_with('/') || handler.contains(".sock") {
            // 跨进程加载
            if let Ok(mut abp) = self.abp.write() {
                let config = PluginConfig {
                    name: name.to_string(),
                    version: "1.0.0".to_string(),
                    load_mode: PluginLoadMode::OutOfProcess,
                    command: Some(handler.to_string()),
                    ..Default::default()
                };
                abp.register_out_of_process_plugin(config);
            }
        } else {
            // 进程内加载
            if let Ok(mut abp) = self.abp.write() {
                let config = PluginConfig {
                    name: name.to_string(),
                    version: "1.0.0".to_string(),
                    load_mode: PluginLoadMode::InProcess,
                    ..Default::default()
                };
                abp.register_in_process_plugin(config);
            }
        }

        info!("Star '{}' registered", name);
        Ok(())
    }

    /// Unregister a star (plugin)
    pub fn unregister_star(&self, name: &str) -> Result<(), AstrBotError> {
        let mut stars = self
            .stars
            .write()
            .map_err(|_| AstrBotError::InvalidState("Failed to acquire write lock".into()))?;

        stars.remove(name);

        if let Ok(mut abp) = self.abp.write() {
            abp.unregister_plugin(name);
        }

        info!("Star '{}' unregistered", name);
        Ok(())
    }

    /// List all registered stars
    #[must_use]
    pub fn list_stars(&self) -> Vec<String> {
        self.stars
            .read()
            .map(|s| s.keys().cloned().collect())
            .unwrap_or_default()
    }

    /// Record a message activity
    pub fn record_activity(&self) {
        self.stats.record_message();
    }

    /// Get runtime statistics
    #[must_use]
    pub fn stats(&self) -> RuntimeStats {
        self.stats.clone()
    }

    /// Set protocol connection status
    pub fn set_protocol_connected(
        &self,
        protocol: &str,
        connected: bool,
    ) -> Result<(), AstrBotError> {
        match protocol {
            "lsp" => {
                let mut lsp = self.lsp.write().map_err(|_| {
                    AstrBotError::InvalidState("Failed to acquire write lock".into())
                })?;
                lsp.set_connected(connected);
            }
            "mcp" => {
                let mut mcp = self.mcp.write().map_err(|_| {
                    AstrBotError::InvalidState("Failed to acquire write lock".into())
                })?;
                mcp.set_connected(connected);
            }
            "acp" => {
                let mut acp = self.acp.write().map_err(|_| {
                    AstrBotError::InvalidState("Failed to acquire write lock".into())
                })?;
                acp.set_connected(connected);
            }
            "abp" => {
                let mut abp = self.abp.write().map_err(|_| {
                    AstrBotError::InvalidState("Failed to acquire write lock".into())
                })?;
                abp.set_connected(connected);
            }
            _ => {
                return Err(AstrBotError::InvalidState(format!(
                    "Unknown protocol: {protocol}"
                )));
            }
        }
        Ok(())
    }

    /// Get protocol status
    #[must_use]
    pub fn get_protocol_status(&self, protocol: &str) -> Option<crate::protocol::ProtocolStatus> {
        match protocol {
            "lsp" => self
                .lsp
                .read()
                .ok()
                .map(|lsp| crate::protocol::ProtocolStatus {
                    connected: lsp.is_connected(),
                    name: "lsp".to_string(),
                }),
            "mcp" => self
                .mcp
                .read()
                .ok()
                .map(|mcp| crate::protocol::ProtocolStatus {
                    connected: mcp.is_connected(),
                    name: "mcp".to_string(),
                }),
            "acp" => self
                .acp
                .read()
                .ok()
                .map(|acp| crate::protocol::ProtocolStatus {
                    connected: acp.is_connected(),
                    name: "acp".to_string(),
                }),
            "abp" => self
                .abp
                .read()
                .ok()
                .map(|abp| crate::protocol::ProtocolStatus {
                    connected: abp.is_connected(),
                    name: "abp".to_string(),
                }),
            _ => None,
        }
    }
}

