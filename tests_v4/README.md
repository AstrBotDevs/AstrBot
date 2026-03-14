# AstrBot SDK Tests

## Overview

当前测试集使用 `pytest` + `pytest-asyncio`，覆盖 v4 原生协议、运行时、客户端和本地开发入口。

## Test Structure

```
tests_v4/
├── conftest.py                  # 共享 fixtures 和路径引导
├── helpers.py                   # 内存传输等测试辅助
├── test_api_decorators.py       # 装饰器元数据与 API 入口
├── test_capability_proxy.py     # CapabilityProxy 调用与校验
├── test_capability_router.py    # 内建 capability 与 schema 验证
├── test_clients_module.py       # clients 包导出
├── test_conftest_fixtures.py    # conftest fixtures 行为
├── test_context.py              # Context 与 CancelToken
├── test_db_client.py            # DBClient
├── test_decorators.py           # 顶层 decorators 模块
├── test_entrypoints.py          # 已安装环境下的 CLI 入口
├── test_events.py               # MessageEvent
├── test_handler_dispatcher.py   # handler/capability 参数注入与分发
├── test_http_metadata_clients.py # HTTPClient 与 MetadataClient
├── test_llm_client.py           # LLMClient
├── test_memory_client.py        # MemoryClient
├── test_peer.py                 # Peer 握手、调用、取消、连接失败
├── test_platform_client.py      # PlatformClient
├── test_protocol.py             # 协议级冒烟测试
├── test_protocol_descriptors.py # 描述符与 schema 模型
├── test_protocol_messages.py    # 协议消息模型
├── test_testing_module.py       # 本地 harness / testing 入口
└── test_transport.py            # stdio / websocket transport
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

## Coverage Focus

- 协议层：`test_protocol_messages.py`、`test_protocol_descriptors.py`、`test_peer.py`
- 运行时调度：`test_capability_router.py`、`test_handler_dispatcher.py`
- 客户端 facade：`test_llm_client.py`、`test_db_client.py`、`test_memory_client.py`、`test_platform_client.py`、`test_http_metadata_clients.py`
- 本地开发入口：`test_testing_module.py`、`test_entrypoints.py`
