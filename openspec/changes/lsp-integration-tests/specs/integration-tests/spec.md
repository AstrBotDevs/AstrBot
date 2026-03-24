# LSP Integration Tests Specification

## ADDED Requirements

### Requirement: LSP client initialization

The LSP client (`AstrbotLspClient`) SHALL be instantiated with proper initial state.

#### Scenario: LSP client initialization
- **WHEN** `AstrbotLspClient` is instantiated
- **THEN** `connected = False`
- **AND** `_reader = None`
- **AND** `_writer = None`
- **AND** `_server_process = None`
- **AND** `_pending_requests = {}`
- **AND** `_request_id = 0`

### Requirement: LSP client connect_to_server()

The LSP client SHALL establish a connection to a stdio-based LSP server.

#### Scenario: LSP client connects to stdio server
- **WHEN** `connect_to_server(command, workspace_uri)` is called
- **THEN** LSP server subprocess is started with the given command
- **AND** `_reader` and `_writer` are set to server's stdout/stdin
- **AND** `_connected = True`
- **AND** initialize request is sent to server
- **AND** initialized notification is sent to server
- **AND** background response reader task is started

### Requirement: LSP client send_request()

The LSP client SHALL send JSON-RPC requests and wait for responses.

#### Scenario: LSP client sends request and waits for response
- **WHEN** `send_request(method, params)` is called on connected client
- **THEN** a JSON-RPC request is sent with proper Content-Length header
- **AND** request id is incremented
- **AND** response is received within 30 second timeout
- **AND** response is returned to caller

#### Scenario: LSP client send_request raises when not connected
- **WHEN** `send_request()` is called on disconnected client
- **THEN** `RuntimeError` is raised with message "LSP client not connected"

### Requirement: LSP client send_notification()

The LSP client SHALL send JSON-RPC notifications without waiting for response.

#### Scenario: LSP client sends notification without waiting
- **WHEN** `send_notification(method, params)` is called on connected client
- **THEN** a JSON-RPC notification is sent with proper Content-Length header
- **AND** method returns immediately without waiting for response

#### Scenario: LSP client send_notification raises when not connected
- **WHEN** `send_notification()` is called on disconnected client
- **THEN** `RuntimeError` is raised with message "LSP client not connected"

### Requirement: LSP client shutdown()

The LSP client SHALL cleanly terminate the LSP server connection.

#### Scenario: LSP client shuts down cleanly
- **WHEN** `shutdown()` is called on connected client
- **THEN** `_connected = False`
- **AND** task group is cancelled
- **AND** shutdown notification is sent to server
- **AND** server process is terminated
- **AND** pending requests are cleared

### Requirement: LSP echo server fixture

The integration test fixture SHALL provide a stdio-based LSP echo server for testing.

#### Scenario: Echo LSP server handles initialize request
- **WHEN** LSP server receives `initialize` request on stdin
- **THEN** responds with `initialize` result containing server capabilities
- **AND** responds with `initialized` notification

#### Scenario: Echo LSP server handles textDocument/didOpen notification
- **WHEN** LSP server receives `textDocument/didOpen` notification
- **THEN** stores the opened document information
- **AND** returns without error

#### Scenario: Echo LSP server handles shutdown request
- **WHEN** LSP server receives `shutdown` request
- **THEN** responds with `null` result
- **AND** on subsequent `exit` notification, terminates cleanly
