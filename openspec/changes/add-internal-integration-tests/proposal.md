# Add Internal Integration Tests

## Problem

The `_internal` architecture claims to support MCP (Model Context Protocol) and ACP (AstrBot Communication Protocol) clients, but these have never been tested with real connections. The ABP demo works, but MCP and ACP remain unverified.

## Solution

Create comprehensive integration tests that:
1. Start a real MCP server (using a simple echo server)
2. Connect the MCP client to it
3. Verify tool listing and calling works
4. Do the same for ACP client

## Why This Matters

- Architecture claims must be validated through tests
- MCP/ACP functionality is blocked by untested assumptions
- Integration tests catch regressions that unit tests miss
- Demonstrates the architecture works in practice

## Scope

- Create `tests/integration/test_mcp_integration.py`
- Create `tests/integration/test_acp_integration.py`
- Use real subprocess servers for testing
- Ensure tests can run in CI
