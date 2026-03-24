# Design: Fix RuntimeStatusStar Spec Compliance

## Problem

The RuntimeStatusStar implementation does not match its specification:

1. `get_protocol_status` should return protocol name along with connected state
2. `get_stats` should return `total_messages` and `last_activity` not just `uptime_seconds`

## Solution

### 1. Update `get_protocol_status`

**Current implementation:**
```python
return {
    "lsp": {"connected": getattr(self._orchestrator.lsp, "connected", False)},
    "mcp": {"connected": getattr(self._orchestrator.mcp, "connected", False)},
    ...
}
```

**Fixed implementation:**
```python
return {
    "lsp": {
        "connected": getattr(self._orchestrator.lsp, "connected", False),
        "name": "lsp-client"
    },
    "mcp": {
        "connected": getattr(self._orchestrator.mcp, "connected", False),
        "name": "mcp-client"
    },
    ...
}
```

### 2. Update `get_stats` and add message tracking

**Orchestrator changes:**
```python
def __init__(self) -> None:
    ...
    self._message_count = 0
    self._last_activity_timestamp: float | None = None

def record_activity(self) -> None:
    """Record a message activity for stats tracking."""
    self._message_count += 1
    self._last_activity_timestamp = time.time()
```

**RuntimeStatusStar changes:**
```python
def _get_stats(self) -> dict[str, Any]:
    last_activity = None
    if self._orchestrator and self._orchestrator._last_activity_timestamp:
        last_activity = datetime.fromtimestamp(
            self._orchestrator._last_activity_timestamp
        ).isoformat()
    
    return {
        "total_messages": getattr(self._orchestrator, "_message_count", 0),
        "last_activity": last_activity,
        "uptime_seconds": time.time() - self._start_time,
    }
```

## Files to Modify

1. `astrbot/_internal/runtime/orchestrator.py`:
   - Add `_message_count: int = 0`
   - Add `_last_activity_timestamp: float | None = None`
   - Add `record_activity()` method

2. `astrbot/_internal/stars/runtime_status_star.py`:
   - Update `_get_protocol_status()` to include `name` field
   - Update `_get_stats()` to return `total_messages` and `last_activity`

3. `tests/unit/test_runtime_status_star.py`:
   - Update `test_get_protocol_status` to verify `name` field
   - Update `test_get_stats` to verify `total_messages` and `last_activity`
