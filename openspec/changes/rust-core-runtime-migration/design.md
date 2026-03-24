## Context

AstrBot's core runtime is currently implemented in Python. While Python provides flexibility and rapid development, performance-critical components (orchestration, protocol management, message processing) would benefit from Rust's:
- Memory safety without garbage collection
- Zero-cost abstractions
- Native performance for concurrent operations
- Strong type safety at compile time

The Rust implementation provides a high-performance foundation that can be exposed to Python via pyo3 bindings.

## Goals / Non-Goals

**Goals:**
- Create a `astrbot-core` Rust crate with core runtime components
- Implement thread-safe Orchestrator using RwLock
- Define ProtocolClient trait for LSP, MCP, ACP, ABP clients
- Provide TOML-based configuration management
- Expose Python bindings via pyo3
- CLI binary using clap

**Non-Goals:**
- Not replacing the Python implementation immediately (coexistence)
- Not implementing anyio (uses native Rust async/tokio)
- Not creating a full ABP protocol implementation in Rust
- Not implementing platform adapters or message pipeline

## Decisions

### 1. Architecture: Stub with Python Integration

The initial Rust implementation is a **stub** that provides:
- Structural definitions matching the expected interfaces
- Thread-safe state management (RwLock)
- Python bindings verification via pyo3

This allows:
- Validating the pyo3 integration works
- Ensuring clippy pedantic compliance
- Establishing the project structure

### 2. Concurrency Model: RwLock for Thread Safety

```rust
pub struct Orchestrator {
    running: RwLock<bool>,
    stars: RwLock<HashMap<String, String>>,
    protocol_lsp: RwLock<ProtocolStatus>,
    // ...
}
```

Using `RwLock` allows:
- Multiple readers concurrently (most operations are reads)
- Exclusive writer (state changes)
- No deadlocks (standard read-write lock pattern)

### 3. Error Handling: thiserror for Ergonomic Errors

```rust
#[derive(Error, Debug)]
pub enum AstrBotError {
    #[error("Not connected: {0}")]
    NotConnected(String),
    // ...
}
```

Using `thiserror` provides:
- Compile-time error message generation
- `?` operator compatibility
- Debug output for development

### 4. Python Bindings: GILOnceCell Singleton

```rust
static ORCHESTRATOR: GILOnceCell<Py<PythonOrchestrator>> = GILOnceCell::new();

#[pyfunction]
pub fn get_orchestrator(py: Python<'_>) -> PyResult<&'static Py<PythonOrchestrator>> {
    if ORCHESTRATOR.get(py).is_none() {
        ORCHESTRATOR.set(py, Py::new(py, PythonOrchestrator::new())?)?;
    }
    Ok(ORCHESTRATOR.get(py).expect("initialized"))
}
```

Using `GILOnceCell` provides:
- Thread-safe global singleton
- GIL-aware initialization
- Lazy initialization on first Python access

### 5. Rust Rules Enforcement

```rust
#![deny(unsafe_code)]
#![deny(clippy::all)]
#![deny(clippy::pedantic)]
```

- **No unsafe**: All memory access is safe by construction
- **No unwrap()**: Errors propagated via `?` or expect with messages
- **Clippy pedantic**: Catches style issues and potential bugs

### 6. ProtocolClient Trait: Static Lifetime for Names

```rust
#[async_trait]
pub trait ProtocolClient: Send + Sync {
    fn name(&self) -> &'static str;
    // ...
}
```

Using `&'static str` ensures:
- No lifetime issues from borrowed data
- Compile-time guaranteed string validity
- Simple implementation for hardcoded client names

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| pyo3 compatibility with Python 3.14 | Use `PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1` |
| Two implementations to maintain | Rust is opt-in via feature flag |
| Performance overhead of bindings | Rust called only for core operations |
| Clippy pedantic false positives | Use `#[allow(...)]` for intentional patterns |

## File Structure

```
rust/
├── Cargo.toml
├── src/
│   ├── lib.rs           # Crate root with module declarations
│   ├── main.rs          # CLI binary
│   ├── error.rs         # AstrBotError enum
│   ├── orchestrator.rs  # Core orchestrator
│   ├── message.rs       # Message types
│   ├── stats.rs         # RuntimeStats
│   ├── protocol.rs      # ProtocolClient trait + implementations
│   ├── config.rs        # Configuration structs
│   └── python.rs        # pyo3 bindings
└── target/              # Build output (gitignored)
```

## Cargo Features

```toml
[features]
default = ["python"]
python = ["pyo3"]
```

- Default enables Python bindings
- Can build pure Rust library without Python

## Verification

| Check | Command |
|-------|---------|
| Clippy | `PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 cargo clippy` |
| Build | `PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 cargo build` |
| Python import | `python -c "from astrbot_core import PythonOrchestrator"` |
| CLI help | `cargo run -- --help` |

## Current Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| error.rs | ✅ Complete | thiserror-based errors |
| orchestrator.rs | ✅ Complete | Thread-safe with RwLock |
| message.rs | ✅ Complete | serde serialization |
| stats.rs | ✅ Complete | AtomicU64 message count |
| protocol.rs | ✅ Complete | Trait + 4 client stubs |
| config.rs | ✅ Complete | TOML load/save |
| python.rs | ✅ Complete | pyo3 bindings |
| main.rs | ✅ Complete | clap CLI |
| lib.rs | ✅ Complete | Module declarations |
| Clippy | ✅ Passing | No warnings |
| Build | ✅ Passing | Compiles successfully |

## Next Steps (Future Work)

1. **Real Protocol Implementations**: Replace stub clients with actual LSP/MCP/ACP/ABP implementations
2. **Python Integration**: Connect Rust orchestrator to Python platform adapters
3. **Performance Benchmarking**: Compare Python vs Rust performance
4. **Feature Parity**: Match all Python orchestrator functionality
5. **Production Readiness**: Add more tests, error handling, edge cases
