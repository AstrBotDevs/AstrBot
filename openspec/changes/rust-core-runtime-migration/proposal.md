## Why

AstrBot's core runtime is currently implemented in Python. Performance-critical components (orchestration, protocol management, message processing) would benefit from Rust's memory safety, zero-cost abstractions, and native performance. Additionally, exposing core functionality via pyo3 allows seamless Python integration while leveraging Rust's strengths.

## What Changes

- Create a new Rust crate `astrbot-core` in `rust/` directory
- Implement core runtime components in Rust:
  - `Orchestrator`: Thread-safe runtime coordinator with RwLock
  - `ProtocolClient` trait: Unified interface for LSP, MCP, ACP, ABP clients
  - `Message` and `MessageType`: Message serialization with serde
  - `RuntimeStats`: Atomic message counting and uptime tracking
  - `Config`: TOML-based configuration management
- Provide Python bindings via pyo3 for seamless integration
- Follow strict Rust best practices:
  - No `unsafe` code
  - No `.unwrap()` - proper error handling
  - Clippy pedantic compliance
  - Full test coverage

## Architecture

```
Python Layer (astrbot/core/)
        │
        ▼ (pyo3 bindings)
┌─────────────────────────────────────────────────┐
│            Rust Core (astrbot-core)              │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────┐ │
│  │ Orchestrator│  │   Config    │  │  Stats   │ │
│  └─────────────┘  └─────────────┘  └──────────┘ │
│  ┌─────────────────────────────────────────────┐│
│  │           Protocol Clients                   ││
│  │  LSP  │  MCP  │  ACP  │  ABP               ││
│  └─────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
```

## Capabilities

### New Capabilities
- `astrbot-core`: Rust-based high-performance core runtime with pyo3 bindings

### Modified Capabilities
- (none - new implementation)

## Impact

- New directory: `rust/` containing Cargo.toml and src/
- New files:
  - `rust/Cargo.toml`
  - `rust/src/lib.rs`
  - `rust/src/main.rs` (CLI binary)
  - `rust/src/error.rs`
  - `rust/src/orchestrator.rs`
  - `rust/src/message.rs`
  - `rust/src/stats.rs`
  - `rust/src/protocol.rs`
  - `rust/src/config.rs`
  - `rust/src/python.rs`
- Python integration via `astrbot_core` Python module
- CLI: `astrbot-core` binary with start/stats/health commands

## Verification

- `cargo clippy` passes with no warnings
- `cargo build` compiles successfully
- Python bindings importable: `from astrbot_core import PythonOrchestrator`
- CLI functional: `astrbot-core --help`

## Relationship to OpenSpec Architecture

This change introduces a new implementation pathway that complements (not replaces) the existing Python architecture defined in `openspec/SPEC.md`. The Rust implementation:

1. Provides a reference implementation of the same interfaces (Orchestrator, ProtocolClient, etc.)
2. Uses Rust idioms (no anyio - uses native Rust async/tokio)
3. Is opt-in via pyo3 feature flag
4. Coexists with Python implementation until Rust is production-ready

## Status

- [x] Proposal created
- [ ] Spec created
- [ ] Design created
- [ ] Tasks created
- [ ] Implementation started
