## 1. Rust Core Infrastructure

- [x] 1.1 Create `astrbot/rust/src/abp/` directory structure (already exists with abp.rs)
- [x] 1.2 Add ABP dependencies to `astrbot/rust/Cargo.toml` (tokio, serde, etc. already present)
- [x] 1.3 Define ABP error types and codes (-32700 to -32211)

## 2. ABP Protocol Core (abp-protocol)

- [x] 2.1 Implement Initialize handshake (C→P: protocolVersion, clientInfo, capabilities, pluginConfig, dataDirs)
- [x] 2.2 Implement Initialize Response (P→C: protocolVersion, serverInfo, capabilities, configSchema, metadata)
- [x] 2.3 Implement Plugin lifecycle methods (plugin.start, plugin.stop, plugin.reload, plugin.config_update)
- [x] 2.4 Implement plugin.error_handler (PluginNotFound, PluginNotReady, PluginCrashed - via error codes)

## 3. Transport Layer (abp-transport)

- [x] 3.1 Implement Stdio transport (single-line JSON messages) - in Python transport.py
- [x] 3.2 Implement Unix Socket transport (Content-Length framing) - in Rust abp.rs and Python
- [x] 3.3 Implement HTTP/SSE transport (POST requests, SSE streams) - in Rust abp.rs and Python
- [ ] 3.4 Add connection pooling for Unix Socket

## 4. Plugin Loader (abp-plugin-loader)

- [ ] 4.1 Implement PluginLoader trait
- [ ] 4.2 Implement InProcessPluginLoader (Python module loading)
- [x] 4.3 Implement OutOfProcessPluginLoader (process spawning + transport)
- [x] 4.4 Implement plugin config parsing (name, load_mode, command, args, transport, url) - in Rust abp.rs
- [x] 4.5 Implement data directory allocation (dataDirs.root, dataDirs.plugin_data, dataDirs.temp)

## 5. Tool Router (abp-tool-router)

- [ ] 5.1 Implement tools/list endpoint (return tool definitions)
- [x] 5.2 Implement tools/call endpoint (execute tool with arguments) - in Rust abp.rs
- [x] 5.3 Implement tool result formatting (content array with type/text) - in Rust abp.rs
- [ ] 5.4 Add tool schema validation (JSON Schema Draft-07)
- [ ] 5.5 Implement cross-plugin tool discovery

## 6. Event System (abp-event-system)

- [x] 6.1 Implement plugin.subscribe (register event subscription) - Python client
- [x] 6.2 Implement plugin.unsubscribe (remove event subscription) - Python client
- [x] 6.3 Implement plugin.notify (bidirectional event notification) - Python client
- [x] 6.4 Define event types (llm_request, tool_called, message_received) - in Rust abp.rs
- [x] 6.5 Implement event routing (P→C and C→P notifications) - Python client

## 7. Python Glue Layer

- [x] 7.1 Create `astrbot/core/plugin/` Python package
- [ ] 7.2 Implement FFI bindings to Rust ABP core (_core.so)
- [x] 7.3 Create PluginManager Python class (wraps Rust PluginLoader)
- [x] 7.4 Create PluginClient Python class (wraps transport)
- [x] 7.5 Add type stubs in `astrbot/rust/_core.pyi`

## 8. Integration & Configuration

- [ ] 8.1 Add plugins section to config.yaml schema
- [ ] 8.2 Implement PluginRegistry (plugin discovery and registration)
- [ ] 8.3 Add ABP initialization to AstrBot startup
- [ ] 8.4 Integrate with existing Star plugin system (backward compatibility)
- [ ] 8.5 Add WebUI support for plugin configuration

## 9. Testing

- [ ] 9.1 Write unit tests for ABP protocol core
- [ ] 9.2 Write integration tests for transport layer
- [ ] 9.3 Write tests for plugin loading (in-process and out-of-process)
- [ ] 9.4 Write tests for tool router
- [ ] 9.5 Write tests for event system
- [x] 9.6 Run `ruff check .` and `ruff format .`
- [ ] 9.7 Run `uvx ty check` for type validation
- [x] 9.8 Run `cargo check` and `cargo fmt` for Rust code
