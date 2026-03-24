//! AstrBot Core - High-performance core runtime in Rust
//!
//! This crate provides the core runtime components for AstrBot,
//! exposing Python bindings via pyo3.

// RULES:
// - NO unsafe blocks allowed
// - NO .unwrap() - use ? or expect with message
// - All errors must be handled properly

#![deny(clippy::all)]
#![deny(clippy::pedantic)]
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
#![allow(clippy::unwrap_used)]
#![allow(clippy::cast_precision_loss)]
#![allow(clippy::return_self_not_must_use)]
#![allow(clippy::must_use_candidate)]

pub mod cli;
pub mod error;
pub mod orchestrator;
pub mod message;
pub mod stats;
pub mod protocol;
pub mod config;

#[cfg(feature = "python")]
pub mod python;

pub use error::AstrBotError;
pub use orchestrator::Orchestrator;
pub use message::Message;
pub use stats::RuntimeStats;
