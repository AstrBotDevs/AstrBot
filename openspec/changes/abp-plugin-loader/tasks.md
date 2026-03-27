## 1. PluginLoader Trait & Python 聚合层

> **架构边界**：核心加载逻辑在 Rust FFI，Python 胶水层仅做类型转换和聚合

- [ ] 1.1 Define `PluginLoader` abstract base class in `astrbot/_internal/protocols/abp/loader.py`
- [ ] 1.2 Define `PluginInstance` dataclass (plugin_id, instance, metadata)
- [ ] 1.3 Define `PluginRegistry` class in `astrbot/_internal/protocols/abp/registry.py` (Python 聚合层，调用 Rust FFI)
- [ ] 1.4 Add `register()` and `unregister()` methods to PluginRegistry
- [ ] 1.5 Add `load_plugin()` / `unload_plugin()` wrapper calling Rust FFI

## 2. Tool Discovery & Registry

> **架构边界**：`tool_router.rs` 核心在 Rust，Python 层仅做聚合和转发

- [ ] 2.1 Create `astrbot/_internal/protocols/abp/tool_registry.py`
- [ ] 2.2 Implement `ToolDef` dataclass (name, description, parameters schema)
- [ ] 2.3 Implement `ToolRegistry.register(plugin_id, tools)` with Schema validation (Python)
- [ ] 2.4 Implement `ToolRegistry.list_tools()` (aggregate all plugins via Rust FFI `list_tools()`)
- [ ] 2.5 Implement `ToolRegistry.call_tool(tool_name, args)` (delegate to Rust FFI `route_tool_call()`)
- [ ] 2.6 Implement `tools/list` JSON-RPC endpoint in plugin base class
- [ ] 2.7 Add JSON Schema Draft-07 validation (jsonschema library)

## 3. FFI Bindings

> **⚠️ 禁止使用 ctypes**：所有 FFI 必须通过 PyO3 绑定（rust-ffi.md 规范）

- [ ] 3.1 Audit existing `_core.pyi` for missing ABP types
- [ ] 3.2 Add `plugin_loader_*` FFI function signatures to rust-ffi.md (if missing)
- [ ] 3.3 Implement Python → Rust plugin loader calls via **PyO3** binding
- [ ] 3.4 Add async wrapper using `run_in_executor` for PyO3 FFI calls
- [ ] 3.5 Update `astrbot/_internal/protocols/abp/manager.py` to use FFI bindings

## 4. Configuration Integration

- [ ] 4.1 Define `plugins` section in `config.yaml` schema
- [ ] 4.2 Implement `PluginConfig` dataclass parsing
- [ ] 4.3 Integrate PluginRegistry initialization into AstrBot startup
- [ ] 4.4 Add connection pooling for Unix Socket transport
- [ ] 4.5 Write integration test for config → plugin loading flow

## 5. Testing

- [ ] 5.1 Write unit tests for PluginLoader trait
- [ ] 5.2 Write unit tests for Python PluginRegistry (mock Rust FFI)
- [ ] 5.3 Write unit tests for ToolRegistry
- [ ] 5.4 Write integration tests for plugin loading (requires Rust FFI stub)
- [ ] 5.5 Write integration tests for tools/list + tools/call flow
- [ ] 5.6 Run `ruff check .` and `ruff format .`
- [ ] 5.7 Run `uvx ty check` for type validation
