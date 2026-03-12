# AstrBot SDK Test Framework

## Overview

This test suite uses **pytest** with `pytest-asyncio` for testing the AstrBot SDK v4 implementation.

## Test Structure

```
tests_v4/
├── conftest.py              # Shared fixtures and configuration
├── pytest.ini               # Pytest configuration
├── test_api_contract.py     # API contract tests
├── test_api_decorators.py   # Decorator and Star class tests
├── test_context.py          # Context and CancelToken tests
├── test_entrypoints.py      # CLI entrypoint tests (requires installation)
├── test_events.py           # MessageEvent and PlainTextResult tests
├── test_legacy_adapter.py   # Legacy API compatibility tests
├── test_peer.py             # Peer communication tests
├── test_protocol.py         # Protocol message tests
├── test_runtime.py          # Supervisor/Worker runtime tests
├── test_script_migrations.py # Migration script tests
└── test_supervisor_migration.py # Supervisor migration tests
```

## Running Tests

### All Tests

```bash
# Using the runner script
python run_tests.py

# Or directly with pytest
python -m pytest tests_v4/ -v
```

### Specific Tests

```bash
# Run specific file
python -m pytest tests_v4/test_peer.py -v

# Run specific test class
python -m pytest tests_v4/test_peer.py::PeerRuntimeTest -v

# Run specific test
python -m pytest tests_v4/test_peer.py::PeerRuntimeTest::test_initialize_and_call_builtin_capabilities -v

# Run tests matching pattern
python -m pytest tests_v4/ -k "peer" -v
```

### With Coverage

```bash
python run_tests.py --cov

# Or directly
python -m pytest tests_v4/ --cov=src-new/astrbot_sdk --cov-report=term-missing
```

### Skip Slow Tests

```bash
python -m pytest tests_v4/ -m "not slow"
```

### Integration Tests Only

```bash
python -m pytest tests_v4/ -m integration
```

## Test Markers

| Marker | Description |
|--------|-------------|
| `@pytest.mark.unit` | Unit tests (fast, no external dependencies) |
| `@pytest.mark.integration` | Integration tests (may require setup) |
| `@pytest.mark.slow` | Slow tests (can be skipped with `-m "not slow"`) |

## Available Fixtures

The `conftest.py` provides these fixtures:

### Transport Fixtures

- `transport_pair`: Creates a connected pair of in-memory transports for testing peer communication
- `core_peer`: Creates a core peer with default handlers
- `plugin_peer`: Creates a plugin peer connected to core_peer

### Helper Fixtures

- `fake_env_manager`: Provides a fake environment manager for testing
- `temp_plugin_dir`: Creates a temporary directory for plugin testing
- `test_plugin`: Creates a minimal test plugin

### Usage Example

```python
async def test_my_feature(core_peer, plugin_peer):
    """Test using pytest fixtures."""
    await plugin_peer.initialize([])
    result = await plugin_peer.invoke("llm.chat", {"prompt": "hello"})
    assert result["text"] == "Echo: hello"
```

## Writing New Tests

### Test File Naming

- Test files should start with `test_`
- Test classes should start with `Test`
- Test functions should start with `test_`

### Async Tests

Use `@pytest.mark.asyncio` or rely on auto mode:

```python
# Both work due to asyncio_mode = auto
async def test_async_auto():
    await asyncio.sleep(0)

@pytest.mark.asyncio
async def test_async_explicit():
    await asyncio.sleep(0)
```

### Using Fixtures

```python
def test_with_fixture(transport_pair):
    left, right = transport_pair
    # Use transports...

async def test_async_fixture(core_peer):
    # core_peer is already started
    await core_peer.invoke(...)
```

## Dependencies

Install test dependencies:

```bash
pip install pytest pytest-asyncio pytest-cov
```

Or use the optional dependency group:

```bash
pip install -e ".[test]"
```

## Test Categories

### Unit Tests (Fast)

- `test_context.py` - CancelToken and Context tests
- `test_events.py` - MessageEvent and PlainTextResult tests
- `test_api_decorators.py` - Decorator tests
- `test_protocol.py` - Protocol message tests

### Integration Tests (Slower)

- `test_peer.py` - Peer communication with real transports
- `test_runtime.py` - Supervisor/Worker process tests
- `test_legacy_adapter.py` - Legacy API compatibility
- `test_script_migrations.py` - Migration script tests
