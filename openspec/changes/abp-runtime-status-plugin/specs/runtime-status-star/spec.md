# Runtime Status Star Specification

## ADDED Requirements

### Requirement: RuntimeStatusStar provides diagnostic tools

The RuntimeStatusStar SHALL provide callable tools that expose core runtime internal state for diagnostic purposes.

#### Scenario: Get runtime status
- **WHEN** ABP client calls `get_runtime_status` tool
- **THEN** returns `{"running": bool, "uptime_seconds": float}`

#### Scenario: Get protocol status
- **WHEN** ABP client calls `get_protocol_status` tool
- **THEN** returns status of each protocol client (lsp, mcp, acp, abp)

#### Scenario: Get star registry
- **WHEN** ABP client calls `get_star_registry` tool
- **THEN** returns list of registered star names

#### Scenario: Get stats
- **WHEN** ABP client calls `get_stats` tool
- **THEN** returns runtime statistics including message counts

### Requirement: Auto-registration with orchestrator

The RuntimeStatusStar SHALL be automatically registered with the orchestrator on initialization.

#### Scenario: Orchestrator initialization
- **WHEN** AstrbotOrchestrator is created
- **THEN** RuntimeStatusStar instance is created and registered with name "runtime-status-star"

### Requirement: Error handling

The RuntimeStatusStar tools SHALL handle errors gracefully without exposing internal exceptions.

#### Scenario: Orchestrator unavailable
- **WHEN** orchestrator reference is None
- **THEN** returns appropriate error message instead of raising exception
