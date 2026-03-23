## Context

The AstrBot core runtime (`_internal` package) manages LSP, MCP, ACP, and ABP protocol clients. Currently there is no way to query the internal state of these components from outside the runtime.

The ABP (AstrBot Protocol) is designed for in-process star communication. By creating a RuntimeStatusStar plugin, we can expose runtime state via ABP tools.

## Goals / Non-Goals

**Goals:**
- Create a RuntimeStatusStar that registers with the orchestrator via ABP
- Expose tools: get_runtime_status, get_protocol_status, get_star_registry, get_stats
- Use anyio for async operations as per project standard

**Non-Goals:**
- Not implementing remote ACP/LSP connections (separate concern)
- Not creating a dashboard UI (future work)
- Not modifying existing protocol client implementations

## Decisions

1. **Star Interface**: Use the existing `Star` base class from `astrbot._internal.stars.base`
   - Each star must implement `call_tool(tool_name, arguments)` method
   - Stars are registered with the orchestrator via `register_star(name, star_instance)`

2. **Tool Exposure**: Expose runtime status as ABP-callable tools
   - `get_runtime_status`: Returns `{running: bool, uptime_seconds: float}`
   - `get_protocol_status`: Returns status of each protocol client
   - `get_star_registry`: Returns list of registered star names
   - `get_stats`: Returns message counts, last activity, etc.

3. **Auto-registration**: Register RuntimeStatusStar in orchestrator.__init__
   - This ensures it's available immediately when runtime starts

## Risks / Trade-offs

- **Risk**: Runtime status might be sensitive information
  - **Mitigation**: Initially only expose basic stats; add auth later if needed

- **Trade-off**: Polling vs push model for stats
  - Decision: Use polling (pull) via ABP call_tool for simplicity
