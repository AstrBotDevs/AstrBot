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

pub mod error;
pub mod orchestrator;
pub mod message;
pub mod stats;

#[cfg(feature = "python")]
pub mod python;

pub use error::AstrBotError;
pub use orchestrator::Orchestrator;
pub use message::Message;
pub use stats::RuntimeStats;
