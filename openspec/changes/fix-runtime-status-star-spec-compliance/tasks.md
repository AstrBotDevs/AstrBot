# Tasks: Fix RuntimeStatusStar Spec Compliance

## Implementation Tasks

### 1. Update Orchestrator for message tracking

- [x] Add `_message_count: int = 0` to `__init__`
- [x] Add `_last_activity_timestamp: float | None = None` to `__init__`
- [x] Add `record_activity()` method that increments count and updates timestamp
- [x] Add `record_activity()` method (infrastructure ready, caller integration separate)

### 2. Update RuntimeStatusStar.get_protocol_status

- [x] Add `name` field to each protocol's return dict
- [x] Verify format matches: `{"connected": bool, "name": "xxx-client"}`

### 3. Update RuntimeStatusStar.get_stats

- [x] Import `datetime` for timestamp formatting
- [x] Return `total_messages` from orchestrator's `_message_count`
- [x] Return `last_activity` as ISO formatted timestamp from `_last_activity_timestamp`
- [x] Keep `uptime_seconds` for backward compatibility

### 4. Update Tests

- [x] Update `test_get_protocol_status` to verify `name` field exists and has correct value
- [x] Update `test_get_stats` to verify `total_messages` and `last_activity` fields exist
- [x] Add test for `record_activity()` method

### 5. Verification

- [x] Run `uv run pytest tests/unit/test_runtime_status_star.py -v`
- [x] Run `uv run pytest tests/unit/test_internal_runtime.py -v`
- [x] Run full test suite: `uv run pytest --cov=astrbot tests/`
