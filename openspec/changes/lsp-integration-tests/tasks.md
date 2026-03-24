# Implementation Tasks

## 1. Test Fixture Directory

- [ ] 1.1 Create tests/integration/fixtures/ directory

## 2. LSP Echo Server Fixture

- [ ] 2.1 Create tests/integration/fixtures/echo_lsp_server.py
- [ ] 2.2 Implement stdio-based server with Content-Length header parsing
- [ ] 2.3 Handle `initialize` request - respond with capabilities
- [ ] 2.4 Handle `initialized` notification - no response needed
- [ ] 2.5 Handle `textDocument/didOpen` notification - store document
- [ ] 2.6 Handle `shutdown` request - respond with null result
- [ ] 2.7 Handle `exit` notification - terminate cleanly

## 3. LSP Integration Test File

- [ ] 3.1 Create tests/integration/test_lsp_integration.py

## 4. LSP Client Initialization Test

- [ ] 4.1 Add test for LSP client initial state (connected=False, etc.)

## 5. LSP Client connect_to_server() Test

- [ ] 5.1 Add test for connecting to echo LSP server
- [ ] 5.2 Verify subprocess is started
- [ ] 5.3 Verify reader and writer are set
- [ ] 5.4 Verify initialize/initialized handshake completes

## 6. LSP Client send_request() Test

- [ ] 6.1 Add test for sending request and receiving response
- [ ] 6.2 Add test for RuntimeError when not connected

## 7. LSP Client send_notification() Test

- [ ] 7.1 Add test for sending notification without waiting
- [ ] 7.2 Add test for RuntimeError when not connected

## 8. LSP Client shutdown() Test

- [ ] 8.1 Add test for clean shutdown

## 9. Verification

- [ ] 9.1 Run `uv run pytest tests/integration/ -v`
- [ ] 9.2 Verify all LSP integration tests pass
