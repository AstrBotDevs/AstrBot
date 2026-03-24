//! Core orchestrator for AstrBot runtime

use crate::error::AstrBotError;
use crate::stats::RuntimeStats;
use std::collections::HashMap;
use std::sync::{Arc, RwLock};
use tokio::sync::broadcast;
use tokio::time::{interval, Duration};

#[derive(Debug, Clone)]
pub struct ProtocolStatus {
    pub connected: bool,
    pub name: String,
}

impl Default for ProtocolStatus {
    fn default() -> Self {
        Self {
            connected: false,
            name: String::new(),
        }
    }
}

/// Main orchestrator coordinating all protocol clients
pub struct Orchestrator {
    running: RwLock<bool>,
    shutdown_tx: Arc<RwLock<Option<broadcast::Sender<()>>>>,
    stars: RwLock<HashMap<String, String>>,
    stats: RwLock<RuntimeStats>,
}

impl Default for Orchestrator {
    fn default() -> Self {
        Self::new()
    }
}

impl Orchestrator {
    #[must_use]
    pub fn new() -> Self {
        Self {
            running: RwLock::new(false),
            shutdown_tx: Arc::new(RwLock::new(None)),
            stars: RwLock::new(HashMap::new()),
            stats: RwLock::new(RuntimeStats::default()),
        }
    }

    /// Start the orchestrator
    pub fn start(&self) -> Result<(), AstrBotError> {
        {
            let mut running = self.running.write().map_err(|_| {
                AstrBotError::InvalidState("Failed to acquire write lock".into())
            })?;
            *running = true;
        }

        let (tx, _rx) = broadcast::channel(1);
        {
            let mut shutdown_tx = self.shutdown_tx.write().map_err(|_| {
                AstrBotError::InvalidState("Failed to acquire write lock".into())
            })?;
            *shutdown_tx = Some(tx);
        }

        tracing::info!("Orchestrator started");
        Ok(())
    }

    /// Bootstrap all protocol clients
    pub async fn bootstrap(&self) -> Result<(), AstrBotError> {
        self.start()?;
        tracing::info!("Protocol clients would be started here");
        tokio::time::sleep(Duration::from_millis(500)).await;
        Ok(())
    }

    /// Main event loop
    pub async fn run_loop(&self) -> Result<(), AstrBotError> {
        if !self.is_running() {
            return Err(AstrBotError::InvalidState("Orchestrator not started".into()));
        }

        tracing::info!("Orchestrator event loop started");
        let mut tick_interval = interval(Duration::from_secs(5));

        loop {
            tokio::select! {
                _ = tick_interval.tick() => {
                    self.periodic_health_check();
                }
                _ = self.wait_for_shutdown() => {
                    tracing::info!("Orchestrator shutdown signal received");
                    break;
                }
            }

            if !self.is_running() {
                break;
            }
        }

        tracing::info!("Orchestrator event loop stopped");
        Ok(())
    }

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

    fn periodic_health_check(&self) {
        tracing::debug!("Orchestrator health check");
    }

    /// Stop the orchestrator
    pub fn stop(&self) -> Result<(), AstrBotError> {
        {
            let mut running = self.running.write().map_err(|_| {
                AstrBotError::InvalidState("Failed to acquire write lock".into())
            })?;
            *running = false;
        }

        if let Ok(tx_guard) = self.shutdown_tx.read() {
            if let Some(tx) = tx_guard.as_ref() {
                let _ = tx.send(());
            }
        }

        tracing::info!("Orchestrator stopped");
        Ok(())
    }

    #[must_use]
    pub fn is_running(&self) -> bool {
        self.running.read().map(|r| *r).unwrap_or(false)
    }

    pub fn register_star(&self, name: &str, _handler: &str) -> Result<(), AstrBotError> {
        let mut stars = self.stars.write().map_err(|_| {
            AstrBotError::InvalidState("Failed to acquire write lock".into())
        })?;
        stars.insert(name.to_string(), name.to_string());
        Ok(())
    }

    pub fn unregister_star(&self, name: &str) -> Result<(), AstrBotError> {
        let mut stars = self.stars.write().map_err(|_| {
            AstrBotError::InvalidState("Failed to acquire write lock".into())
        })?;
        stars.remove(name);
        Ok(())
    }

    #[must_use]
    pub fn list_stars(&self) -> Vec<String> {
        self.stars
            .read()
            .map(|s| s.keys().cloned().collect())
            .unwrap_or_default()
    }

    pub fn record_activity(&self) {
        if let Ok(stats) = self.stats.write() {
            stats.record_message();
        }
    }

    #[must_use]
    pub fn stats(&self) -> RuntimeStats {
        self.stats.read().map(|s| s.clone()).unwrap_or_default()
    }

    #[must_use]
    pub fn get_protocol_status(&self, _protocol: &str) -> Option<ProtocolStatus> {
        Some(ProtocolStatus {
            connected: true,
            name: _protocol.to_string(),
        })
    }

    pub fn set_protocol_connected(&self, _protocol: &str, _connected: bool) -> Result<(), AstrBotError> {
        Ok(())
    }
}
