## Why

The RuntimeStatusStar was implemented based on a spec, but the implementation does not match the specification:

1. `get_protocol_status` spec requires a `name` field per protocol, but implementation only returns `connected`
2. `get_stats` spec requires `total_messages` and `last_activity` fields, but implementation only returns `uptime_seconds`

This spec-implementation mismatch means external consumers cannot rely on the documented interface.

## What Changes

- Update `get_protocol_status` to include `name` field for each protocol client (lsp, mcp, acp, abp)
- Update `get_stats` to return `total_messages` and `last_activity` as specified
- Add message tracking infrastructure to the orchestrator to support `total_messages` and `last_activity`
- Update tests to verify spec compliance

## Capabilities

### Modified Capabilities
- `RuntimeStatusStar.get_protocol_status`: Now returns `{"lsp": {"connected": bool, "name": "lsp-client"}, ...}`
- `RuntimeStatusStar.get_stats`: Now returns `{"total_messages": int, "last_activity": str, "uptime_seconds": float}`

### New Infrastructure
- Orchestrator message tracking: `_message_count` and `_last_activity_timestamp`

## Impact

- Modifies: `astrbot/_internal/stars/runtime_status_star.py` - add name fields and message stats
- Modifies: `astrbot/_internal/runtime/orchestrator.py` - add message tracking counters
- Modifies: `tests/unit/test_runtime_status_star.py` - update tests to verify spec compliance
