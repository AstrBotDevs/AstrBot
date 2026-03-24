# RuntimeStatusStar Specification (Corrected)

## Overview

RuntimeStatusStar is an internal ABP (AstrBot Protocol) star plugin that exposes runtime state information via callable tools. It provides diagnostic capabilities for monitoring the AstrBot core runtime health.

## Tool Interface

### Tools Exposed

All tools follow the ABP tool calling convention via `call_tool(tool_name, arguments)`.

#### 1. get_runtime_status

Returns the current runtime state.

**Arguments:** None

**Returns:**
```json
{
  "running": true,
  "uptime_seconds": 12345.67
}
```

#### 2. get_protocol_status

Returns the connection state of each protocol client.

**Arguments:** None

**Returns:**
```json
{
  "lsp": {"connected": true, "name": "lsp-client"},
  "mcp": {"connected": false, "name": "mcp-client"},
  "acp": {"connected": true, "name": "acp-client"},
  "abp": {"connected": true, "name": "abp-client"}
}
```

#### 3. get_star_registry

Returns the list of registered star names.

**Arguments:** None

**Returns:**
```json
{
  "stars": ["runtime-status-star", "star-1", "star-2"]
}
```

#### 4. get_stats

Returns runtime statistics and metrics.

**Arguments:** None

**Returns:**
```json
{
  "total_messages": 100,
  "last_activity": "2024-01-01T00:00:00Z",
  "uptime_seconds": 12345.67
}
```

## Architecture

### Component Hierarchy

```
AstrbotOrchestrator
  └── RuntimeStatusStar (auto-registered)
        └── Tools: get_runtime_status, get_protocol_status, get_star_registry, get_stats
```

### Message Tracking

The orchestrator tracks:
- `_message_count`: Total number of messages processed
- `_last_activity_timestamp`: ISO timestamp of last activity

### Auto-Registration

RuntimeStatusStar is instantiated and registered in `AstrbotOrchestrator.__init__()`:

```python
from astrbot._internal.stars.runtime_status_star import RuntimeStatusStar

class AstrbotOrchestrator:
    def __init__(self):
        self._stars: dict[str, Star] = {}
        self._message_count = 0
        self._last_activity_timestamp: float | None = None
        # Auto-register RuntimeStatusStar
        self._runtime_status_star = RuntimeStatusStar()
        self._runtime_status_star.set_orchestrator(self)
        self._stars["runtime-status-star"] = self._runtime_status_star
```

### Orchestrator Reference

RuntimeStatusStar holds a reference to the orchestrator to query state:

```python
class RuntimeStatusStar:
    def __init__(self):
        self._orchestrator = None
        
    def set_orchestrator(self, orchestrator):
        self._orchestrator = orchestrator
```

## Implementation Notes

1. **Thread Safety:** The orchestrator may be accessed from multiple contexts. All state queries should be read-only.

2. **Latency:** Tool calls should return immediately without blocking. No polling or long-running operations.

3. **Error Handling:** If any status query fails, return an error message rather than raising an exception.

4. **Future Extensibility:** Additional stats can be added by extending the `get_stats` tool response structure.
