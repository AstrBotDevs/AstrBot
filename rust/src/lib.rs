//! AstrBot Core - High-performance runtime in Rust
//!
//! This crate provides the core runtime for AstrBot, with Rust as the core
//! and Python modules as plugins via PyO3.

// RULES:
// - NO unsafe blocks allowed
// - NO .unwrap() without message - use ? or expect()
// - All errors must be handled properly via Result

#![deny(clippy::all)]
#![deny(unsafe_code)]
#![allow(clippy::module_name_repetitions)]
#![allow(clippy::too_many_lines)]
#![allow(clippy::struct_excessive_bools)]
#![allow(clippy::cast_sign_loss)]
#![allow(clippy::cast_possible_truncation)]
#![allow(clippy::cast_lossless)]
#![allow(clippy::unnecessary_struct_initialization)]
#![allow(clippy::missing_errors_doc)]
#![allow(clippy::missing_panics_doc)]
#![allow(clippy::doc_markdown)]
#![allow(clippy::return_self_not_must_use)]
#![allow(clippy::must_use_candidate)]

pub mod a2a;
pub mod abp;
pub mod cli;
pub mod config;
pub mod error;
pub mod message;
pub mod orchestrator;
pub mod protocol;
pub mod server;
pub mod stats;

#[cfg(feature = "python")]
pub mod python;

pub use a2a::{AgentCard, Task, TaskState};
pub use abp::{PluginCapabilities, PluginConfig, PluginLoadMode};
pub use error::AstrBotError;
pub use message::Message;
pub use orchestrator::Orchestrator;
pub use protocol::ProtocolStatus;
pub use server::{ApiResponse, HttpServer, WsManager};
pub use stats::RuntimeStats;

// Re-export CLI for Python bindings
#[cfg(feature = "python")]
pub use cli::cli_with_args;
