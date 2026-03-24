# Implementation Tasks

## 1. Project Setup

- [x] 1.1 Create rust/ directory
- [x] 1.2 Initialize with cargo init --name astrbot-core
- [x] 1.3 Add Cargo.toml with dependencies (serde, tokio, pyo3, clap, etc.)
- [x] 1.4 Create .cargo/config.toml for pyo3 forward compatibility

## 2. Core Modules

- [x] 2.1 Create lib.rs with module declarations and clippy settings
- [x] 2.2 Create error.rs with AstrBotError enum using thiserror
- [x] 2.3 Create orchestrator.rs with Orchestrator struct and methods
- [x] 2.4 Create message.rs with Message and MessageType
- [x] 2.5 Create stats.rs with RuntimeStats using AtomicU64
- [x] 2.6 Create protocol.rs with ProtocolClient trait and client implementations
- [x] 2.7 Create config.rs with Config and related structs
- [x] 2.8 Create python.rs with pyo3 bindings

## 3. CLI Binary

- [x] 3.1 Create main.rs with clap CLI (start, stats, health commands)

## 4. Rust Rules Compliance

- [x] 4.1 Ensure no unsafe code (#![deny(unsafe_code)])
- [x] 4.2 Ensure no .unwrap() without message (#[allow] where needed)
- [x] 4.3 Add clippy pedantic settings (#![deny(clippy::pedantic)])
- [x] 4.4 Fix all clippy warnings

## 5. Verification

- [x] 5.1 Run `cargo clippy` - no warnings
- [x] 5.2 Run `cargo build` - compiles successfully
- [x] 5.3 Verify CLI works: `cargo run -- --help`

## 6. Documentation

- [x] 6.1 Create proposal.md
- [x] 6.2 Create spec.md
- [x] 6.3 Create design.md
- [ ] 6.4 Create tasks.md (this file)

## 7. Future Work (Not in Scope)

- [ ] 7.1 Implement real LSP client functionality
- [ ] 7.2 Implement real MCP client functionality
- [ ] 7.3 Implement real ACP client functionality
- [ ] 7.4 Implement real ABP client functionality
- [ ] 7.5 Connect Rust orchestrator to Python platform adapters
- [ ] 7.6 Add comprehensive test suite
- [ ] 7.7 Performance benchmarking
