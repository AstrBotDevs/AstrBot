//! Configuration management for AstrBot Core
//!
//! Configuration follows these principles:
//! - Separation of concerns: configs organized by functional domain
//! - Sensitive info isolation: keys stored in separate secrets file
//! - Environment variable priority: keys injected via env vars
//! - Layered config: system -> platform -> provider -> agent -> plugins
//!
//! Reference: openspec/config.md

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::Path;
use std::path::PathBuf;

// ============================================================================
// Main Config
// ============================================================================

/// Main configuration entry
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
#[derive(Default)]
pub struct AstrBotConfig {
    #[serde(default)]
    pub system: SystemConfig,
    #[serde(default)]
    pub platform: PlatformConfig,
    #[serde(default)]
    pub providers: ProvidersConfig,
    #[serde(default)]
    pub agent: AgentConfig,
    #[serde(default)]
    pub plugins: HashMap<String, serde_json::Value>,
}


impl AstrBotConfig {
    /// Load all config files from config directory
    pub fn load_from_dir(config_dir: &Path) -> anyhow::Result<Self> {
        let mut config = AstrBotConfig::default();

        let system_path = config_dir.join("system.yaml");
        if system_path.exists() {
            let content = std::fs::read_to_string(&system_path)?;
            config.system = toml::from_str(&content)?;
        }

        let platform_path = config_dir.join("platform.yaml");
        if platform_path.exists() {
            let content = std::fs::read_to_string(&platform_path)?;
            config.platform = toml::from_str(&content)?;
        }

        let providers_path = config_dir.join("providers.yaml");
        if providers_path.exists() {
            let content = std::fs::read_to_string(&providers_path)?;
            config.providers = toml::from_str(&content)?;
        }

        let agent_path = config_dir.join("agent.yaml");
        if agent_path.exists() {
            let content = std::fs::read_to_string(&agent_path)?;
            config.agent = toml::from_str(&content)?;
        }

        let plugins_dir = config_dir.join("plugins");
        if plugins_dir.is_dir()
            && let Ok(entries) = std::fs::read_dir(plugins_dir) {
                for entry in entries.flatten() {
                    let path = entry.path();
                    if path.extension().and_then(|s| s.to_str()) == Some("yaml")
                        && let Some(name) = path.file_stem().and_then(|s| s.to_str())
                            && let Ok(content) = std::fs::read_to_string(&path)
                                && let Ok(plugin_config) =
                                    serde_json::from_str::<serde_json::Value>(&content)
                                {
                                    config.plugins.insert(name.to_string(), plugin_config);
                                }
                }
            }

        Ok(config)
    }
}

// ============================================================================
// System Config (system.yaml)
// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SystemConfig {
    #[serde(default)]
    pub log: LogConfig,
    #[serde(default)]
    pub proxy: ProxyConfig,
    #[serde(default)]
    pub trace: TraceConfig,
    #[serde(default)]
    pub temp: TempConfig,
    #[serde(default)]
    pub timezone: String,
    #[serde(default)]
    pub pypi_index_url: String,
    #[serde(default)]
    pub pip_install_arg: String,
    #[serde(default)]
    pub callback_api_base: String,
}

impl Default for SystemConfig {
    fn default() -> Self {
        Self {
            log: LogConfig::default(),
            proxy: ProxyConfig::default(),
            trace: TraceConfig::default(),
            temp: TempConfig::default(),
            timezone: "Asia/Shanghai".to_string(),
            pypi_index_url: String::new(),
            pip_install_arg: String::new(),
            callback_api_base: String::new(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LogConfig {
    #[serde(default)]
    pub level: String,
    #[serde(default)]
    pub file_enable: bool,
    #[serde(default)]
    pub file_path: String,
    #[serde(default)]
    pub file_max_mb: u32,
    #[serde(default)]
    pub disable_access_log: bool,
}

impl Default for LogConfig {
    fn default() -> Self {
        Self {
            level: "INFO".to_string(),
            file_enable: false,
            file_path: String::new(),
            file_max_mb: 20,
            disable_access_log: true,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProxyConfig {
    #[serde(default)]
    pub http_proxy: String,
    #[serde(default)]
    pub https_proxy: String,
    #[serde(default)]
    pub no_proxy: Vec<String>,
}

impl Default for ProxyConfig {
    fn default() -> Self {
        Self {
            http_proxy: String::new(),
            https_proxy: String::new(),
            no_proxy: vec!["localhost".to_string(), "127.0.0.1".to_string()],
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
#[derive(Default)]
pub struct TraceConfig {
    #[serde(default)]
    pub enable: bool,
    #[serde(default)]
    pub log_enable: bool,
    #[serde(default)]
    pub log_path: String,
}


#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TempConfig {
    #[serde(default)]
    pub dir_max_size: u64,
}

impl Default for TempConfig {
    fn default() -> Self {
        Self { dir_max_size: 1024 }
    }
}

// ============================================================================
// Platform Config (platform.yaml)
// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
#[derive(Default)]
pub struct PlatformConfig {
    #[serde(default)]
    pub platform_settings: PlatformSettings,
    #[serde(default)]
    pub platforms: Vec<PlatformAdapterConfig>,
    #[serde(default)]
    pub platform_specific: PlatformSpecificConfig,
}


#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PlatformSettings {
    #[serde(default)]
    pub unique_session: bool,
    #[serde(default)]
    pub rate_limit: RateLimitConfig,
    #[serde(default)]
    pub reply_prefix: String,
    #[serde(default)]
    pub forward_threshold: u32,
    #[serde(default)]
    pub enable_id_white_list: bool,
    #[serde(default)]
    pub id_whitelist: Vec<String>,
    #[serde(default)]
    pub id_whitelist_log: bool,
    #[serde(default)]
    pub wl_ignore_admin_on_group: bool,
    #[serde(default)]
    pub wl_ignore_admin_on_friend: bool,
    #[serde(default)]
    pub reply_with_mention: bool,
    #[serde(default)]
    pub reply_with_quote: bool,
    #[serde(default)]
    pub path_mapping: Vec<PathMapping>,
    #[serde(default)]
    pub segmented_reply: SegmentedReplyConfig,
    #[serde(default)]
    pub no_permission_reply: bool,
    #[serde(default)]
    pub empty_mention_waiting: bool,
    #[serde(default)]
    pub empty_mention_waiting_need_reply: bool,
    #[serde(default)]
    pub friend_message_needs_wake_prefix: bool,
    #[serde(default)]
    pub ignore_bot_self_message: bool,
    #[serde(default)]
    pub ignore_at_all: bool,
}

impl Default for PlatformSettings {
    fn default() -> Self {
        Self {
            unique_session: false,
            rate_limit: RateLimitConfig::default(),
            reply_prefix: String::new(),
            forward_threshold: 1500,
            enable_id_white_list: true,
            id_whitelist: Vec::new(),
            id_whitelist_log: true,
            wl_ignore_admin_on_group: true,
            wl_ignore_admin_on_friend: true,
            reply_with_mention: false,
            reply_with_quote: false,
            path_mapping: Vec::new(),
            segmented_reply: SegmentedReplyConfig::default(),
            no_permission_reply: true,
            empty_mention_waiting: true,
            empty_mention_waiting_need_reply: true,
            friend_message_needs_wake_prefix: false,
            ignore_bot_self_message: true,
            ignore_at_all: false,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RateLimitConfig {
    #[serde(default)]
    pub time: u32,
    #[serde(default)]
    pub count: u32,
    #[serde(default)]
    pub strategy: String,
}

impl Default for RateLimitConfig {
    fn default() -> Self {
        Self {
            time: 60,
            count: 30,
            strategy: "stall".to_string(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PathMapping {
    pub from: String,
    pub to: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SegmentedReplyConfig {
    #[serde(default)]
    pub enable: bool,
    #[serde(default)]
    pub only_llm_result: bool,
    #[serde(default)]
    pub interval_method: String,
    #[serde(default)]
    pub interval: String,
    #[serde(default)]
    pub words_count_threshold: u32,
    #[serde(default)]
    pub split_mode: String,
    #[serde(default)]
    pub regex: String,
    #[serde(default)]
    pub split_words: Vec<String>,
}

impl Default for SegmentedReplyConfig {
    fn default() -> Self {
        Self {
            enable: false,
            only_llm_result: true,
            interval_method: "random".to_string(),
            interval: "1.5,3.5".to_string(),
            words_count_threshold: 150,
            split_mode: "regex".to_string(),
            regex: String::new(),
            split_words: vec![
                "。".to_string(),
                "？".to_string(),
                "！".to_string(),
                "~".to_string(),
                "…".to_string(),
            ],
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PlatformAdapterConfig {
    pub platform_type: String,
    #[serde(default)]
    pub enabled: bool,
    #[serde(default)]
    pub config: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
#[derive(Default)]
pub struct PlatformSpecificConfig {
    #[serde(default)]
    pub lark: PlatformSpecificSettings,
    #[serde(default)]
    pub telegram: PlatformSpecificSettings,
    #[serde(default)]
    pub discord: PlatformSpecificSettings,
}


#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
#[derive(Default)]
pub struct PlatformSpecificSettings {
    #[serde(default)]
    pub pre_ack_emoji: PreAckEmojiConfig,
}


#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
#[derive(Default)]
pub struct PreAckEmojiConfig {
    #[serde(default)]
    pub enable: bool,
    #[serde(default)]
    pub emojis: Vec<String>,
}


// ============================================================================
// Providers Config (providers.yaml)
// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
#[derive(Default)]
pub struct ProvidersConfig {
    #[serde(default)]
    pub provider_settings: ProviderSettings,
}


#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProviderSettings {
    #[serde(default)]
    pub enable: bool,
    #[serde(default)]
    pub default_provider_id: String,
    #[serde(default)]
    pub fallback_chat_models: Vec<String>,
    #[serde(default)]
    pub default_image_caption_provider_id: String,
    #[serde(default)]
    pub image_caption_prompt: String,
    #[serde(default)]
    pub provider_pool: Vec<String>,
}

impl Default for ProviderSettings {
    fn default() -> Self {
        Self {
            enable: true,
            default_provider_id: String::new(),
            fallback_chat_models: Vec::new(),
            default_image_caption_provider_id: String::new(),
            image_caption_prompt: "Please describe the image using Chinese.".to_string(),
            provider_pool: vec!["*".to_string()],
        }
    }
}

// ============================================================================
// Agent Config (agent.yaml)
// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
#[derive(Default)]
pub struct AgentConfig {
    #[serde(default)]
    pub agent_settings: AgentSettings,
    #[serde(default)]
    pub subagent_orchestrator: SubagentOrchestratorConfig,
    #[serde(default)]
    pub provider_stt_settings: ProviderSttSettings,
    #[serde(default)]
    pub provider_tts_settings: ProviderTtsSettings,
    #[serde(default)]
    pub provider_ltm_settings: ProviderLtmSettings,
}


#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AgentSettings {
    #[serde(default)]
    pub wake_prefix: Vec<String>,
    #[serde(default)]
    pub default_personality: String,
    #[serde(default)]
    pub persona_pool: Vec<String>,
    #[serde(default)]
    pub prompt_prefix: String,
    #[serde(default)]
    pub context_limit_reached_strategy: String,
    #[serde(default)]
    pub llm_compress_instruction: String,
    #[serde(default)]
    pub llm_compress_keep_recent: u32,
    #[serde(default)]
    pub llm_compress_provider_id: String,
    #[serde(default)]
    pub max_context_length: i32,
    #[serde(default)]
    pub dequeue_context_length: u32,
    #[serde(default)]
    pub streaming_response: bool,
    #[serde(default)]
    pub show_tool_use_status: bool,
    #[serde(default)]
    pub show_tool_call_result: bool,
    #[serde(default)]
    pub sanitize_context_by_modalities: bool,
    #[serde(default)]
    pub max_quoted_fallback_images: u32,
    #[serde(default)]
    pub web_search: bool,
    #[serde(default)]
    pub websearch_provider: String,
    #[serde(default)]
    pub web_search_link: bool,
    #[serde(default)]
    pub identifier: bool,
    #[serde(default)]
    pub group_name_display: bool,
    #[serde(default)]
    pub datetime_system_prompt: bool,
    #[serde(default)]
    pub agent_runner_type: String,
    #[serde(default)]
    pub dify_agent_runner_provider_id: String,
    #[serde(default)]
    pub coze_agent_runner_provider_id: String,
    #[serde(default)]
    pub dashscope_agent_runner_provider_id: String,
    #[serde(default)]
    pub deerflow_agent_runner_provider_id: String,
    #[serde(default)]
    pub unsupported_streaming_strategy: String,
    #[serde(default)]
    pub reachability_check: bool,
    #[serde(default)]
    pub max_agent_step: u32,
    #[serde(default)]
    pub tool_call_timeout: u32,
    #[serde(default)]
    pub tool_schema_mode: String,
    #[serde(default)]
    pub llm_safety_mode: bool,
    #[serde(default)]
    pub safety_mode_strategy: String,
    #[serde(default)]
    pub proactive_capability: ProactiveCapability,
    #[serde(default)]
    pub computer_use_runtime: String,
    #[serde(default)]
    pub computer_use_require_admin: bool,
    #[serde(default)]
    pub image_compress_enabled: bool,
    #[serde(default)]
    pub image_compress_options: ImageCompressOptions,
}

impl Default for AgentSettings {
    fn default() -> Self {
        Self {
            wake_prefix: vec!["/".to_string()],
            default_personality: "default".to_string(),
            persona_pool: vec!["*".to_string()],
            prompt_prefix: "{{prompt}}".to_string(),
            context_limit_reached_strategy: "truncate_by_turns".to_string(),
            llm_compress_instruction: String::new(),
            llm_compress_keep_recent: 6,
            llm_compress_provider_id: String::new(),
            max_context_length: -1,
            dequeue_context_length: 1,
            streaming_response: false,
            show_tool_use_status: false,
            show_tool_call_result: false,
            sanitize_context_by_modalities: false,
            max_quoted_fallback_images: 20,
            web_search: false,
            websearch_provider: "default".to_string(),
            web_search_link: false,
            identifier: false,
            group_name_display: false,
            datetime_system_prompt: true,
            agent_runner_type: "local".to_string(),
            dify_agent_runner_provider_id: String::new(),
            coze_agent_runner_provider_id: String::new(),
            dashscope_agent_runner_provider_id: String::new(),
            deerflow_agent_runner_provider_id: String::new(),
            unsupported_streaming_strategy: "realtime_segmenting".to_string(),
            reachability_check: false,
            max_agent_step: 30,
            tool_call_timeout: 60,
            tool_schema_mode: "full".to_string(),
            llm_safety_mode: true,
            safety_mode_strategy: "system_prompt".to_string(),
            proactive_capability: ProactiveCapability::default(),
            computer_use_runtime: "none".to_string(),
            computer_use_require_admin: true,
            image_compress_enabled: true,
            image_compress_options: ImageCompressOptions::default(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProactiveCapability {
    #[serde(default)]
    pub add_cron_tools: bool,
}

impl Default for ProactiveCapability {
    fn default() -> Self {
        Self {
            add_cron_tools: true,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ImageCompressOptions {
    #[serde(default)]
    pub max_size: u32,
    #[serde(default)]
    pub quality: u32,
}

impl Default for ImageCompressOptions {
    fn default() -> Self {
        Self {
            max_size: 1024,
            quality: 95,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
#[derive(Default)]
pub struct SubagentOrchestratorConfig {
    #[serde(default)]
    pub main_enable: bool,
    #[serde(default)]
    pub remove_main_duplicate_tools: bool,
    #[serde(default)]
    pub router_system_prompt: String,
    #[serde(default)]
    pub agents: Vec<AgentDefinition>,
}


#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AgentDefinition {
    pub name: String,
    #[serde(default)]
    pub provider_id: String,
    #[serde(default)]
    pub system_prompt: String,
    #[serde(default)]
    pub tools: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
#[derive(Default)]
pub struct ProviderSttSettings {
    #[serde(default)]
    pub enable: bool,
    #[serde(default)]
    pub provider_id: String,
}


#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProviderTtsSettings {
    #[serde(default)]
    pub enable: bool,
    #[serde(default)]
    pub provider_id: String,
    #[serde(default)]
    pub dual_output: bool,
    #[serde(default)]
    pub use_file_service: bool,
    #[serde(default)]
    pub trigger_probability: f32,
}

impl Default for ProviderTtsSettings {
    fn default() -> Self {
        Self {
            enable: false,
            provider_id: String::new(),
            dual_output: false,
            use_file_service: false,
            trigger_probability: 1.0,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProviderLtmSettings {
    #[serde(default)]
    pub group_icl_enable: bool,
    #[serde(default)]
    pub group_message_max_cnt: u32,
    #[serde(default)]
    pub image_caption: bool,
    #[serde(default)]
    pub image_caption_provider_id: String,
    #[serde(default)]
    pub active_reply: ActiveReplyConfig,
}

impl Default for ProviderLtmSettings {
    fn default() -> Self {
        Self {
            group_icl_enable: false,
            group_message_max_cnt: 300,
            image_caption: false,
            image_caption_provider_id: String::new(),
            active_reply: ActiveReplyConfig::default(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ActiveReplyConfig {
    #[serde(default)]
    pub enable: bool,
    #[serde(default)]
    pub method: String,
    #[serde(default)]
    pub possibility_reply: f32,
    #[serde(default)]
    pub whitelist: Vec<String>,
}

impl Default for ActiveReplyConfig {
    fn default() -> Self {
        Self {
            enable: false,
            method: "possibility_reply".to_string(),
            possibility_reply: 0.1,
            whitelist: Vec::new(),
        }
    }
}

// ============================================================================
// Secrets Config (secrets.yaml)
// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct SecretsConfig {
    #[serde(default)]
    pub dashboard: DashboardSecrets,
    #[serde(default)]
    pub providers: ProviderSecrets,
    #[serde(default)]
    pub platforms: PlatformSecrets,
    #[serde(default)]
    pub third_party: ThirdPartySecrets,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct DashboardSecrets {
    #[serde(default)]
    pub password: String,
    #[serde(default)]
    pub jwt_secret: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct ProviderSecrets {
    #[serde(default)]
    pub openai: ProviderApiKey,
    #[serde(default)]
    pub anthropic: ProviderApiKey,
    #[serde(default)]
    pub dashscope: ProviderApiKey,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct ProviderApiKey {
    #[serde(default)]
    pub api_key: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlatformSecrets {
    #[serde(default)]
    pub telegram: PlatformBotToken,
    #[serde(default)]
    pub discord: PlatformBotToken,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PlatformBotToken {
    #[serde(default)]
    pub bot_token: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct ThirdPartySecrets {
    #[serde(default)]
    pub baidu_aip: BaiduAipSecrets,
    #[serde(default)]
    pub moonshotai: MoonshotAiSecrets,
    #[serde(default)]
    pub coze: CozeSecrets,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct BaiduAipSecrets {
    #[serde(default)]
    pub app_id: String,
    #[serde(default)]
    pub api_key: String,
    #[serde(default)]
    pub secret_key: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct MoonshotAiSecrets {
    #[serde(default)]
    pub api_key: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct CozeSecrets {
    #[serde(default)]
    pub api_key: String,
    #[serde(default)]
    pub bot_id: String,
}

// ============================================================================
// GPG Config (gpg.yaml)
// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
#[derive(Default)]
pub struct GpgConfig {
    #[serde(default)]
    pub security: GpgSecurity,
}


#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct GpgSecurity {
    #[serde(default)]
    pub enable: bool,
    #[serde(default)]
    pub verify_mode: String,
    #[serde(default)]
    pub trusted_keys: Vec<String>,
    #[serde(default)]
    pub signed_configs: Vec<String>,
    #[serde(default)]
    pub signature_suffix: String,
    #[serde(default)]
    pub gnupg_home: String,
}

impl Default for GpgSecurity {
    fn default() -> Self {
        Self {
            enable: false,
            verify_mode: "warn".to_string(),
            trusted_keys: Vec::new(),
            signed_configs: vec![
                "secrets.yaml".to_string(),
                "agent.yaml".to_string(),
                "platform.yaml".to_string(),
            ],
            signature_suffix: ".sig".to_string(),
            gnupg_home: String::new(),
        }
    }
}

// ============================================================================
// Config Directory Paths (XDG Base Directory + Windows)
// ============================================================================

/// Get AstrBot config directory
/// - Linux/macOS: $XDG_CONFIG_HOME/astrbot or ~/.config/astrbot
/// - Windows: %APPDATA%/AstrBot
pub fn get_config_dir() -> PathBuf {
    if let Ok(path) = std::env::var("ASTRBOT_CONFIG_DIR") {
        return PathBuf::from(path).join("astrbot");
    }
    if let Ok(path) = std::env::var("ASTRBOT_ROOT") {
        return PathBuf::from(path).join("config");
    }

    #[cfg(target_os = "windows")]
    {
        if let Ok(path) = std::env::var("APPDATA") {
            return PathBuf::from(path).join("AstrBot");
        }
        return PathBuf::from("C:/Users/Default/AppData/Roaming/AstrBot");
    }

    #[cfg(not(target_os = "windows"))]
    {
        if let Ok(path) = std::env::var("XDG_CONFIG_HOME") {
            return PathBuf::from(path).join("astrbot");
        }
        if let Some(dir) = dirs::config_dir() {
            return dir.join("astrbot");
        }
        if let Ok(home) = std::env::var("HOME") {
            return PathBuf::from(home).join(".config").join("astrbot");
        }
        PathBuf::from("/root/.config/astrbot")
    }
}

/// Get AstrBot data directory
/// - Linux/macOS: $XDG_DATA_HOME/astrbot or ~/.local/share/astrbot
/// - Windows: %LOCALAPPDATA%/AstrBot
pub fn get_data_dir() -> PathBuf {
    if let Ok(path) = std::env::var("ASTRBOT_DATA_DIR") {
        return PathBuf::from(path);
    }
    if let Ok(path) = std::env::var("ASTRBOT_ROOT") {
        return PathBuf::from(path);
    }

    #[cfg(target_os = "windows")]
    {
        if let Ok(path) = std::env::var("LOCALAPPDATA") {
            return PathBuf::from(path).join("AstrBot");
        }
        return PathBuf::from("C:/Users/Default/AppData/Local/AstrBot");
    }

    #[cfg(not(target_os = "windows"))]
    {
        if let Ok(path) = std::env::var("XDG_DATA_HOME") {
            return PathBuf::from(path).join("astrbot");
        }
        if let Some(dir) = dirs::data_dir() {
            return dir.join("astrbot");
        }
        if let Ok(home) = std::env::var("HOME") {
            return PathBuf::from(home).join(".local/share").join("astrbot");
        }
        PathBuf::from("/root/.local/share/astrbot")
    }
}

/// Get AstrBot cache directory
/// - Linux/macOS: $XDG_CACHE_HOME/astrbot or ~/.cache/astrbot
/// - Windows: %TEMP%/AstrBot
pub fn get_cache_dir() -> PathBuf {
    if let Ok(path) = std::env::var("ASTRBOT_CACHE_DIR") {
        return PathBuf::from(path);
    }

    #[cfg(target_os = "windows")]
    {
        return std::env::temp_dir().join("AstrBot");
    }

    #[cfg(not(target_os = "windows"))]
    {
        if let Ok(path) = std::env::var("XDG_CACHE_HOME") {
            return PathBuf::from(path).join("astrbot");
        }
        if let Some(dir) = dirs::cache_dir() {
            return dir.join("astrbot");
        }
        if let Ok(home) = std::env::var("HOME") {
            return PathBuf::from(home).join(".cache").join("astrbot");
        }
        PathBuf::from("/root/.cache/astrbot")
    }
}

/// Get AstrBot runtime directory
/// - Linux/macOS: /run/user/<UID>/astrbot or $XDG_RUNTIME_DIR/astrbot
/// - Windows: uses temp directory
pub fn get_runtime_dir() -> PathBuf {
    if let Ok(path) = std::env::var("ASTRBOT_RUNTIME_DIR") {
        return PathBuf::from(path);
    }

    #[cfg(target_os = "windows")]
    {
        return std::env::temp_dir().join("AstrBot");
    }

    #[cfg(not(target_os = "windows"))]
    {
        if let Ok(path) = std::env::var("XDG_RUNTIME_DIR") {
            return PathBuf::from(path).join("astrbot");
        }
        if let Some(dir) = dirs::runtime_dir() {
            return dir.join("astrbot");
        }
        if let Ok(home) = std::env::var("HOME") {
            return PathBuf::from(home).join(".local/run").join("astrbot");
        }
        PathBuf::from("/run/astrbot")
    }
}
