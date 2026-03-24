//! Core orchestrator for AstrBot runtime

use crate::error::AstrBotError;
use crate::stats::RuntimeStats;
use std::collections::HashMap;
use std::sync::RwLock;

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

#[derive(Debug, Default)]
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
    #[must_use]
    pub fn new() -> Self {
        Self::default()
    }

    pub fn start(&self) -> Result<(), AstrBotError> {
        let mut running = self.running.write().map_err(|_| {
            AstrBotError::InvalidState("Failed to acquire write lock".into())
        })?;
        *running = true;
        Ok(())
    }

    pub fn stop(&self) -> Result<(), AstrBotError> {
        let mut running = self.running.write().map_err(|_| {
            AstrBotError::InvalidState("Failed to acquire write lock".into())
        })?;
        *running = false;
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
        self.stats.record_message();
    }

    #[must_use]
    pub fn stats(&self) -> RuntimeStats {
        self.stats.clone()
    }

    #[must_use]
    pub fn get_protocol_status(&self, protocol: &str) -> Option<ProtocolStatus> {
        match protocol {
            "lsp" => self.protocol_lsp.read().ok().map(|p| p.clone()),
            "mcp" => self.protocol_mcp.read().ok().map(|p| p.clone()),
            "acp" => self.protocol_acp.read().ok().map(|p| p.clone()),
            "abp" => self.protocol_abp.read().ok().map(|p| p.clone()),
            _ => None,
        }
    }

    pub fn set_protocol_connected(&self, protocol: &str, connected: bool) -> Result<(), AstrBotError> {
        let status = match protocol {
            "lsp" => &self.protocol_lsp,
            "mcp" => &self.protocol_mcp,
            "acp" => &self.protocol_acp,
            "abp" => &self.protocol_abp,
            _ => return Err(AstrBotError::InvalidState(format!("Unknown protocol: {protocol}"))),
        };

        let mut lock = status.write().map_err(|_| {
            AstrBotError::InvalidState("Failed to acquire write lock".into())
        })?;
        lock.connected = connected;
        Ok(())
    }
}
