# LSP Integration Tests

## Problem

The `_internal` architecture includes an LSP (Language Server Protocol) client implementation at `astrbot/_internal/protocols/lsp/client.py`, but there are no integration tests validating that it can connect to and communicate with a real LSP server. The orchestrator manages an `AstrbotLspClient` instance (`self.lsp`), but this functionality remains untested.

## Solution

Create integration tests that:
1. Build an LSP echo server fixture (stdio-based)
2. Test the LSP client can connect, send requests, and receive responses
3. Verify the JSON-RPC 2.0 protocol communication works end-to-end

## Why This Matters

- Architecture claims must be validated through tests
- LSP functionality is used by the orchestrator for language intelligence
- Integration tests catch regressions that unit tests miss
- Validates the JSON-RPC 2.0 message framing and async communication

## Scope

- Create `tests/integration/fixtures/echo_lsp_server.py`
- Create `tests/integration/test_lsp_integration.py`
- Ensure tests can run in CI
