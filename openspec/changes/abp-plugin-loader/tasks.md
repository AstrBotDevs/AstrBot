## 1. PluginLoader Trait & InProcessPluginLoader

- [ ] 1.1 Define `PluginLoader` abstract base class in `astrbot/core/plugin/loader.py`
- [ ] 1.2 Define `PluginInstance` dataclass (plugin_id, instance, metadata)
- [ ] 1.3 Implement `InProcessPluginLoader.load()` (Python module import)
- [ ] 1.4 Implement `InProcessPluginLoader.unload()` (remove from registry)
- [ ] 1.5 Implement `InProcessPluginLoader.reload()` (reload module)
- [ ] 1.6 Create `PluginRegistry` class (Dict[str, PluginInstance] + singleton)
- [ ] 1.7 Add `register()` and `unregister()` methods to PluginRegistry

## 2. Tool Discovery & Registry

- [ ] 2.1 Create `astrbot/core/plugin/tool_registry.py`
- [ ] 2.2 Implement `ToolDef` dataclass (name, description, parameters schema)
- [ ] 2.3 Implement `ToolRegistry.register(plugin_id, tools)` with Schema validation
- [ ] 2.4 Implement `ToolRegistry.list_tools()` (aggregate all plugins)
- [ ] 2.5 Implement `ToolRegistry.call_tool(tool_name, args)`
- [ ] 2.6 Implement `tools/list` JSON-RPC endpoint in plugin base class
- [ ] 2.7 Add JSON Schema Draft-07 validation (jsonschema library)

## 3. FFI Bindings

- [ ] 3.1 Audit existing `_core.pyi` for missing ABP types
- [ ] 3.2 Add `plugin_loader_*` FFI function signatures to rust-ffi.md (if missing)
- [ ] 3.3 Implement Python → Rust plugin loader calls via ctypes
- [ ] 3.4 Add async wrapper using `run_in_executor` for FFI calls
- [ ] 3.5 Update `plugin_manager.py` to use FFI bindings

## 4. Configuration Integration

- [ ] 4.1 Define `plugins` section in `config.yaml` schema
- [ ] 4.2 Implement `PluginConfig` dataclass parsing
- [ ] 4.3 Integrate PluginRegistry initialization into AstrBot startup
- [ ] 4.4 Add connection pooling for Unix Socket transport (task 3.4 from original)
- [ ] 4.5 Write integration test for config → plugin loading flow

## 5. Testing

- [ ] 5.1 Write unit tests for PluginLoader trait
- [ ] 5.2 Write unit tests for InProcessPluginLoader
- [ ] 5.3 Write unit tests for ToolRegistry
- [ ] 5.4 Write integration tests for in-process plugin loading
- [ ] 5.5 Write integration tests for tools/list + tools/call flow
- [ ] 5.6 Run `ruff check .` and `ruff format .`
- [ ] 5.7 Run `uvx ty check` for type validation
