# AstrBot SDK 测试指南

本文档介绍如何测试 AstrBot SDK 插件，包括单元测试、集成测试和使用测试框架。

## 目录

- [测试概述](#测试概述)
- [测试框架](#测试框架)
- [单元测试](#单元测试)
- [集成测试](#集成测试)
- [Mock 使用](#mock-使用)
- [测试最佳实践](#测试最佳实践)

---

## 测试概述

### 为什么需要测试？

1. **确保功能正确性**：验证插件按预期工作
2. **防止回归**：修改代码时不破坏现有功能
3. **文档化**：测试用例展示了如何使用代码
4. **提高信心**：放心地重构和优化代码

### 测试类型

```
单元测试 ──→ 集成测试 ──→ 端到端测试
(最快)      (中等)       (最慢)
```

---

## 测试框架

### 安装测试依赖

```bash
pip install pytest pytest-asyncio pytest-cov
```

### 配置 pytest

```python
# conftest.py
import pytest
from astrbot_sdk.testing import PluginTestHarness

@pytest.fixture
async def harness():
    """提供测试 harness"""
    h = PluginTestHarness()
    yield h
    await h.cleanup()

@pytest.fixture
async def plugin(harness):
    """加载插件"""
    return await harness.load_plugin("my_plugin.main:MyPlugin")
```

---

## 单元测试

### 测试命令处理器

```python
import pytest
from astrbot_sdk.testing import PluginTestHarness

@pytest.mark.asyncio
async def test_hello_command():
    """测试 hello 命令"""
    harness = PluginTestHarness()
    plugin = await harness.load_plugin("my_plugin.main:MyPlugin")
    
    # 模拟命令调用
    result = await harness.simulate_command("/hello")
    
    # 验证结果
    assert result.text == "Hello, World!"
    
    await harness.cleanup()
```

### 测试消息处理器

```python
@pytest.mark.asyncio
async def test_message_handler():
    """测试消息处理器"""
    harness = PluginTestHarness()
    plugin = await harness.load_plugin("my_plugin.main:MyPlugin")
    
    # 模拟消息
    result = await harness.simulate_message(
        text="你好",
        user_id="12345",
        session_id="session_1"
    )
    
    # 验证响应
    assert "你好" in result.text
    
    await harness.cleanup()
```

### 测试装饰器

```python
@pytest.mark.asyncio
async def test_rate_limit():
    """测试速率限制"""
    harness = PluginTestHarness()
    plugin = await harness.load_plugin("my_plugin.main:MyPlugin")
    
    # 第一次调用应该成功
    result1 = await harness.simulate_command("/limited")
    assert result1.success
    
    # 快速第二次调用应该被限制
    result2 = await harness.simulate_command("/limited")
    assert result2.error.code == "rate_limited"
    
    await harness.cleanup()
```

---

## 集成测试

### 测试数据库操作

```python
@pytest.mark.asyncio
async def test_database_operations():
    """测试数据库操作"""
    harness = PluginTestHarness()
    plugin = await harness.load_plugin("my_plugin.main:MyPlugin")
    
    # 模拟事件以获取 ctx
    event = harness.create_mock_event(text="test")
    
    # 设置数据
    await plugin.save_user_data(
        event,
        event.ctx,
        user_id="123",
        data={"name": "Alice"}
    )
    
    # 读取数据
    data = await plugin.get_user_data(
        event,
        event.ctx,
        user_id="123"
    )
    
    assert data["name"] == "Alice"
    
    await harness.cleanup()
```

### 测试 LLM 调用

```python
@pytest.mark.asyncio
async def test_llm_integration():
    """测试 LLM 调用"""
    harness = PluginTestHarness()
    
    # 配置 mock LLM 响应
    harness.mock_llm_response("模拟的 LLM 回复")
    
    plugin = await harness.load_plugin("my_plugin.main:MyPlugin")
    
    # 调用需要 LLM 的命令
    result = await harness.simulate_command("/ask 问题")
    
    assert "模拟的 LLM 回复" in result.text
    
    await harness.cleanup()
```

### 测试平台发送

```python
@pytest.mark.asyncio
async def test_platform_send():
    """测试平台消息发送"""
    harness = PluginTestHarness()
    plugin = await harness.load_plugin("my_plugin.main:MyPlugin")
    
    # 模拟命令
    await harness.simulate_command("/broadcast 大家好")
    
    # 验证发送记录
    sent_messages = harness.get_sent_messages()
    assert len(sent_messages) >= 1
    assert "大家好" in sent_messages[0].text
    
    await harness.cleanup()
```

---

## Mock 使用

### Mock Context

```python
from unittest.mock import AsyncMock, MagicMock
from astrbot_sdk import Context

@pytest.fixture
def mock_ctx():
    """创建 mock Context"""
    ctx = MagicMock(spec=Context)
    
    # Mock LLM 客户端
    ctx.llm = AsyncMock()
    ctx.llm.chat.return_value = "Mocked response"
    
    # Mock DB 客户端
    ctx.db = AsyncMock()
    ctx.db.get.return_value = {"key": "value"}
    
    # Mock Logger
    ctx.logger = MagicMock()
    
    return ctx

@pytest.mark.asyncio
async def test_with_mock_ctx(mock_ctx):
    """使用 mock Context 测试"""
    plugin = MyPlugin()
    
    result = await plugin.some_method(mock_ctx)
    
    # 验证调用
    mock_ctx.llm.chat.assert_called_once()
    assert result == "expected"
```

### Mock 事件

```python
from astrbot_sdk import MessageEvent

@pytest.fixture
def mock_event():
    """创建 mock 事件"""
    event = MagicMock(spec=MessageEvent)
    event.text = "测试消息"
    event.user_id = "12345"
    event.session_id = "session_1"
    event.platform = "qq"
    
    # Mock 回复方法
    event.reply = AsyncMock()
    
    return event

@pytest.mark.asyncio
async def test_with_mock_event(mock_event, mock_ctx):
    """使用 mock 事件测试"""
    plugin = MyPlugin()
    
    await plugin.handle_message(mock_event, mock_ctx)
    
    # 验证回复
    mock_event.reply.assert_called_once()
```

### Mock 时间

```python
import time
from unittest.mock import patch

@pytest.mark.asyncio
async def test_with_mock_time():
    """使用 mock 时间测试"""
    with patch('time.time', return_value=1234567890):
        result = await plugin.time_sensitive_operation()
        
    assert result.timestamp == 1234567890
```

### Mock 外部 API

```python
import aiohttp
from aioresponses import aioresponses

@pytest.mark.asyncio
async def test_external_api():
    """测试外部 API 调用"""
    with aioresponses() as mocked:
        # Mock API 响应
        mocked.get(
            'https://api.example.com/data',
            payload={'result': 'success'},
            status=200
        )
        
        result = await plugin.fetch_external_data()
        
        assert result['result'] == 'success'
```

---

## 测试最佳实践

### 1. 测试命名规范

```python
# 好的命名
def test_calculate_sum_with_positive_numbers():
    """测试正数相加"""
    pass

def test_calculate_sum_with_negative_numbers():
    """测试负数相加"""
    pass

# 不好的命名
def test1():
    pass

def test_sum():
    pass
```

### 2. 一个测试一个概念

```python
# 好的做法：每个测试一个断言
def test_user_creation():
    user = create_user("alice")
    assert user.name == "alice"

def test_user_creation_sets_default_role():
    user = create_user("alice")
    assert user.role == "user"

# 不好的做法：多个概念混在一起
def test_user():
    user = create_user("alice")
    assert user.name == "alice"
    assert user.role == "user"
    assert user.created_at is not None
```

### 3. 使用 Fixtures

```python
# conftest.py
import pytest

@pytest.fixture
def sample_user_data():
    """提供测试用户数据"""
    return {
        "user_id": "123",
        "name": "Alice",
        "email": "alice@example.com"
    }

@pytest.fixture
async def initialized_plugin():
    """提供已初始化的插件"""
    plugin = MyPlugin()
    harness = PluginTestHarness()
    await plugin.on_start(harness.create_mock_ctx())
    yield plugin
    await plugin.on_stop(None)

# 测试中使用
def test_with_fixture(sample_user_data, initialized_plugin):
    result = initialized_plugin.process_user(sample_user_data)
    assert result.success
```

### 4. 参数化测试

```python
import pytest

@pytest.mark.parametrize("input,expected", [
    ("hello", "Hello"),
    ("world", "World"),
    ("", ""),
])
def test_capitalize(input, expected):
    assert input.capitalize() == expected

@pytest.mark.asyncio
@pytest.mark.parametrize("command,expected_response", [
    ("/help", "可用命令..."),
    ("/about", "关于信息..."),
    ("/version", "版本号..."),
])
async def test_commands(command, expected_response):
    harness = PluginTestHarness()
    plugin = await harness.load_plugin("my_plugin.main:MyPlugin")
    
    result = await harness.simulate_command(command)
    assert expected_response in result.text
```

### 5. 测试隔离

```python
# 每个测试使用独立的数据
@pytest.fixture(autouse=True)
def reset_state():
    """每个测试前重置状态"""
    MyPlugin._instance_counter = 0
    yield
    # 测试后清理
    MyPlugin._instance_counter = 0

@pytest.mark.asyncio
async def test_isolated():
    # 这个测试不会受其他测试影响
    plugin = MyPlugin()
    assert plugin.id == 1
```

### 6. 异步测试模式

```python
import asyncio
import pytest

@pytest.mark.asyncio
async def test_async_operation():
    """测试异步操作"""
    result = await async_function()
    assert result == expected

@pytest.mark.asyncio
async def test_async_timeout():
    """测试超时"""
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            slow_function(),
            timeout=0.1
        )

@pytest.mark.asyncio
async def test_async_exception():
    """测试异常"""
    with pytest.raises(ValueError) as exc_info:
        await function_that_raises()
    
    assert "expected error" in str(exc_info.value)
```

### 7. 覆盖率检查

```bash
# 运行测试并生成覆盖率报告
pytest --cov=my_plugin --cov-report=html

# 检查覆盖率
pytest --cov=my_plugin --cov-fail-under=80
```

```ini
# .coveragerc
[run]
source = my_plugin
omit = 
    */tests/*
    */venv/*
    */__pycache__/*

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise NotImplementedError
```

---

## 测试工具函数

### 常用测试辅助函数

```python
# test_utils.py
import asyncio
from contextlib import asynccontextmanager

async def run_with_timeout(coro, timeout=5):
    """带超时运行协程"""
    return await asyncio.wait_for(coro, timeout=timeout)

@asynccontextmanager
async def temporary_database():
    """临时数据库上下文"""
    db = await create_test_db()
    try:
        yield db
    finally:
        await db.cleanup()

def create_test_event(**kwargs):
    """创建测试事件"""
    defaults = {
        "text": "test",
        "user_id": "12345",
        "session_id": "test_session",
        "platform": "qq",
    }
    defaults.update(kwargs)
    return MockEvent(**defaults)
```

---

## 持续集成

### GitHub Actions 配置

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.12'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install -r requirements-dev.txt
    
    - name: Run tests
      run: |
        pytest --cov=my_plugin --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
```

---

## 调试测试

### 使用 pdb

```python
import pytest
import pdb

def test_with_debug():
    result = some_function()
    
    # 设置断点
    pdb.set_trace()
    
    assert result.success
```

### 使用 pytest 的 --pdb

```bash
# 失败时自动进入 pdb
pytest --pdb

# 在第一个失败时停止
pytest -x --pdb
```

### 详细输出

```bash
# 详细输出
pytest -v

# 最详细输出
pytest -vv

# 显示 print 输出
pytest -s
```

---

## 相关文档

- [错误处理与调试](./06_error_handling.md)
- [高级主题](./07_advanced_topics.md)
