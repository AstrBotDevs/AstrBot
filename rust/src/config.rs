//! Configuration management for AstrBot Core

use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// AstrBot Core configuration
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct Config {
    /// Runtime settings
    pub runtime: RuntimeConfig,
    /// Protocol client settings
    pub protocols: ProtocolsConfig,
    /// Logging settings
    pub logging: LoggingConfig,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RuntimeConfig {
    /// Whether the runtime is in debug mode
    pub debug: bool,
    /// Data directory path
    pub data_dir: PathBuf,
    /// Config directory path
    pub config_dir: PathBuf,
    /// Temporary directory path
    pub temp_dir: PathBuf,
}

impl Default for RuntimeConfig {
    fn default() -> Self {
        Self {
            debug: false,
            data_dir: PathBuf::from("~/.astrbot/data"),
            config_dir: PathBuf::from("~/.astrbot/config"),
            temp_dir: PathBuf::from("~/.astrbot/temp"),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct ProtocolsConfig {
    /// LSP protocol settings
    pub lsp: ProtocolSettings,
    /// MCP protocol settings
    pub mcp: ProtocolSettings,
    /// ACP protocol settings
    pub acp: ProtocolSettings,
    /// ABP protocol settings
    pub abp: ProtocolSettings,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProtocolSettings {
    /// Whether this protocol is enabled
    pub enabled: bool,
    /// Connection timeout in seconds
    pub timeout_secs: u64,
    /// Retry settings
    pub retry: RetrySettings,
}

impl Default for ProtocolSettings {
    fn default() -> Self {
        Self {
            enabled: true,
            timeout_secs: 30,
            retry: RetrySettings::default(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RetrySettings {
    /// Maximum number of retries
    pub max_retries: u32,
    /// Initial backoff delay in milliseconds
    pub initial_delay_ms: u64,
    /// Maximum backoff delay in milliseconds
    pub max_delay_ms: u64,
}

impl Default for RetrySettings {
    fn default() -> Self {
        Self {
            max_retries: 3,
            initial_delay_ms: 100,
            max_delay_ms: 5000,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LoggingConfig {
    /// Log level (trace, debug, info, warn, error)
    pub level: String,
    /// Whether to use structured logging
    pub structured: bool,
    /// Log file path
    pub file: Option<PathBuf>,
}

impl Default for LoggingConfig {
    fn default() -> Self {
        Self {
            level: "info".to_string(),
            structured: true,
            file: None,
        }
    }
}

impl Config {
    /// Load configuration from a file
    pub fn load(path: &PathBuf) -> anyhow::Result<Self> {
        let content = std::fs::read_to_string(path)?;
        let config: Config = toml::from_str(&content)?;
        Ok(config)
    }

    /// Save configuration to a file
    pub fn save(&self, path: &PathBuf) -> anyhow::Result<()> {
        let content = toml::to_string_pretty(self)?;
        std::fs::write(path, content)?;
        Ok(())
    }
}
