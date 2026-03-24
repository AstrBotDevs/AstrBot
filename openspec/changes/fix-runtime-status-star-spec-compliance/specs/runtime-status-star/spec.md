# Runtime Status Star Specification (Spec Compliance Fix)

## MODIFIED Requirements

### Requirement: RuntimeStatusStar provides diagnostic tools

The RuntimeStatusStar SHALL provide callable tools that expose core runtime internal state for diagnostic purposes.

#### Scenario: Get runtime status
- **WHEN** ABP client calls `get_runtime_status` tool
- **THEN** returns `{"running": bool, "uptime_seconds": float}`

#### Scenario: Get protocol status
- **WHEN** ABP client calls `get_protocol_status` tool
- **THEN** returns status of each protocol client (lsp, mcp, acp, abp)
- **AND** each protocol includes `connected: bool` AND `name: string` fields
- **EXAMPLE**: `{"lsp": {"connected": true, "name": "lsp-client"}, ...}`

#### Scenario: Get star registry
- **WHEN** ABP client calls `get_star_registry` tool
- **THEN** returns list of registered star names

#### Scenario: Get stats
- **WHEN** ABP client calls `get_stats` tool
- **THEN** returns `{"total_messages": int, "last_activity": string, "uptime_seconds": float}`
- **AND** `last_activity` is ISO8601 formatted timestamp string

### Requirement: Auto-registration with orchestrator

The RuntimeStatusStar SHALL be automatically registered with the orchestrator on initialization.

#### Scenario: Orchestrator initialization
- **WHEN** AstrbotOrchestrator is created
- **THEN** RuntimeStatusStar instance is created and registered with name "runtime-status-star"

### Requirement: Orchestrator message tracking

The orchestrator SHALL track message counts and last activity timestamp for stats reporting.

#### Scenario: Message tracking
- **WHEN** orchestrator processes a message
- **THEN** `_message_count` is incremented
- **AND** `_last_activity_timestamp` is updated to current time

#### Scenario: Stats retrieval
- **WHEN** RuntimeStatusStar.get_stats is called
- **THEN** returns `total_messages` from orchestrator's `_message_count`
- **AND** returns `last_activity` as ISO8601 string from `_last_activity_timestamp`

### Requirement: Error handling

The RuntimeStatusStar tools SHALL handle errors gracefully without exposing internal exceptions.

#### Scenario: Orchestrator unavailable
- **WHEN** orchestrator reference is None
- **THEN** returns appropriate error message instead of raising exception
