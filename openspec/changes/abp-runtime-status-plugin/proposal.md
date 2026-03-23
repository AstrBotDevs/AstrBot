## Why

Currently the core runtime (_internal package) has no way to expose its internal state (protocol client status, star registry, message counts, etc.) to external consumers. We need an ABP plugin that exposes runtime status as tools that can be called via the ABP protocol.

## What Changes

- Create an ABP plugin (`RuntimeStatusStar`) that registers with the orchestrator via ABP
- Expose runtime status as tools callable via ABP protocol:
  - `get_runtime_status`: Returns overall runtime state
  - `get_protocol_status`: Returns LSP, MCP, ACP, ABP client states
  - `get_star_registry`: Returns list of registered stars
  - `get_stats`: Returns message counts, uptime, etc.
- Plugin implements the Star interface required by ABP

## Capabilities

### New Capabilities
- `runtime-status-star`: ABP plugin that exposes core runtime internal state as callable tools

### Modified Capabilities
- (none)

## Impact

- New file: `astrbot/_internal/stars/runtime_status_star.py`
- Modifies: `astrbot/_internal/runtime/orchestrator.py` to register the star
- ABP protocol now can query runtime internals
