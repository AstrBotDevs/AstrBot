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

### 核心测试组件

SDK 提供以下测试组件（从 `astrbot_sdk.testing` 导入）：

| 组件 | 用途 |
|------|------|
| `PluginHarness` | 插件测试运行器 |
| `LocalRuntimeConfig` | 本地运行时配置 |
| `SDKTestEnvironment` | 测试环境管理 |
| `InMemoryDB` | 内存数据库模拟 |
| `InMemoryMemory` | 内存记忆存储模拟 |
| `MockLLMClient` | LLM 客户端模拟 |
| `MockContext` | Context 模拟 |
| `MockMessageEvent` | 消息事件模拟 |
| `RecordedSend` | 发送记录 |

### 配置 pytest

```python
# conftest.py
import pytest
import pytest_asyncio
from astrbot_sdk.testing import PluginHarness, SDKTestEnvironment

@pytest.fixture
def test_env(tmp_path):
    """提供测试环境"""
    return SDKTestEnvironment(root=tmp_path)

@pytest_asyncio.fixture
async def harness(test_env):
    """提供测试 harness"""
    plugin_dir = test_env.plugin_dir("my_plugin")
    # 创建最小插件结构（如果需要），至少包含：
    # - plugin.yaml（含 _schema_version 与 runtime.python）
    # - main.py
    # - requirements.txt

    h = PluginHarness.from_plugin_dir(plugin_dir)
    async with h:
        yield h
```

---

## 单元测试

### 测试命令处理器

```python
import pytest
from pathlib import Path
from astrbot_sdk.testing import PluginHarness

@pytest.mark.asyncio
async def test_hello_command():
    """测试 hello 命令"""
    # 使用 from_plugin_dir 创建 harness
    plugin_dir = Path("path/to/my_plugin")

    async with PluginHarness.from_plugin_dir(plugin_dir) as harness:
        # dispatch_text 发送消息并返回发送记录列表
        sent = await harness.dispatch_text("hello")

        # 验证结果 - sent 是 list[RecordedSend]
        assert len(sent) >= 1
        # RecordedSend 有 .text, .image_url, .chain 等属性
        assert "Hello" in sent[0].text
```

### 测试消息处理器

```python
@pytest.mark.asyncio
async def test_message_handler():
    """测试消息处理器"""
    plugin_dir = Path("path/to/my_plugin")

    async with PluginHarness.from_plugin_dir(plugin_dir) as harness:
        # dispatch_text 可指定更多参数
        sent = await harness.dispatch_text(
            "你好",
            user_id="12345",
            session_id="session_1",
            platform="qq"
        )

        # 验证响应
        assert len(sent) >= 1
        assert "你好" in sent[0].text
```

### 测试装饰器行为

```python
from astrbot_sdk.errors import AstrBotError, ErrorCodes
from astrbot_sdk.decorators import rate_limit

@pytest.mark.asyncio
async def test_rate_limit():
    """测试速率限制"""
    plugin_dir = Path("path/to/my_plugin")

    async with PluginHarness.from_plugin_dir(plugin_dir) as harness:
        # 第一次调用应该成功
        sent1 = await harness.dispatch_text("limited")
        assert len(sent1) >= 1

        # 只有在插件使用 @rate_limit(..., behavior="error") 时，
        # 第二次调用才会抛出 RATE_LIMITED；默认 behavior="hint" 会直接回复提示消息
        with pytest.raises(AstrBotError) as exc_info:
            await harness.dispatch_text("limited")

        # 验证错误码
        assert exc_info.value.code == ErrorCodes.RATE_LIMITED
```

---

## 集成测试

### 测试数据库操作

使用 `InMemoryDB` 进行数据库模拟：

```python
from astrbot_sdk.testing import InMemoryDB

@pytest.mark.asyncio
async def test_database_operations():
    """测试数据库操作"""
    # 创建内存存储
    store = {}
    db = InMemoryDB(store)

    # 设置数据
    db.set("user:123", {"name": "Alice"})

    # 读取数据
    data = db.get("user:123")
    assert data["name"] == "Alice"

    # 列出键
    keys = db.list("user:")
    assert "user:123" in keys

    # 删除数据
    db.delete("user:123")
    assert db.get("user:123") is None
```

### 测试记忆存储

使用 `InMemoryMemory` 进行记忆模拟：

```python
from astrbot_sdk.testing import InMemoryMemory

def test_memory_operations():
    """测试记忆存储"""
    store = {}
    memory = InMemoryMemory(store)

    # 保存记忆
    memory.save("user_pref", {"theme": "dark", "lang": "zh"})

    # 获取记忆
    pref = memory.get("user_pref")
    assert pref["theme"] == "dark"

    # 搜索记忆
    results = memory.search("dark")
    assert len(results) >= 1
    assert results[0]["key"] == "user_pref"

    # 删除记忆
    memory.delete("user_pref")
    assert memory.get("user_pref") is None
```

### 测试 LLM 调用

使用 `MockLLMClient` 模拟 LLM 响应（通过 `MockContext`）：

```python
from astrbot_sdk.testing import MockContext, MockMessageEvent

@pytest.mark.asyncio
async def test_llm_integration():
    """测试 LLM 调用"""
    # 创建 mock context（包含 mock LLM 客户端）
    ctx = MockContext()

    # 设置 mock 响应
    ctx.llm.mock_response("这是模拟的 LLM 回复")

    # 调用 chat
    response = await ctx.llm.chat("你好")
    assert response == "这是模拟的 LLM 回复"

    # 也可以设置流式响应
    ctx.llm.mock_stream_response("流式响应内容")
```

### 测试平台发送

```python
@pytest.mark.asyncio
async def test_platform_send():
    """测试平台消息发送"""
    plugin_dir = Path("path/to/my_plugin")

    async with PluginHarness.from_plugin_dir(plugin_dir) as harness:
        # 模拟命令
        await harness.dispatch_text("broadcast 大家好")

        # 使用 sent_messages 属性获取发送记录
        messages = harness.sent_messages

        # 验证发送记录
        assert len(messages) >= 1
        assert "大家好" in messages[0].text

        # 清空发送记录（用于下一个测试）
        harness.clear_sent_messages()

        # 验证已清空
        assert len(harness.sent_messages) == 0
```

### 测试 Capability 调用

```python
@pytest.mark.asyncio
async def test_capability_invocation():
    """测试 Capability 调用"""
    plugin_dir = Path("path/to/my_plugin")

    async with PluginHarness.from_plugin_dir(plugin_dir) as harness:
        # 直接调用 capability
        result = await harness.invoke_capability(
            "my_plugin.custom_capability",
            {"param": "value"}
        )

        # 验证结果
        assert result["status"] == "success"
```

---

## Mock 使用

### MockContext

```python
from astrbot_sdk.testing import MockContext

@pytest.fixture
def mock_ctx():
    """创建 mock Context"""
    ctx = MockContext()

    # 配置 mock LLM 响应
    ctx.llm.mock_response("Mocked response")

    return ctx

@pytest.mark.asyncio
async def test_with_mock_ctx(mock_ctx):
    """使用 mock Context 测试"""
    # 调用需要 LLM 的方法
    response = await mock_ctx.llm.chat("test")

    # 验证
    assert response == "Mocked response"

    # 如需验证发送，可配合 MockMessageEvent 或直接调用 platform.send(...)
    event = MockMessageEvent(text="test", session_id="session_1", context=mock_ctx)
    await event.reply(response)
    mock_ctx.platform.assert_sent("Mocked response")
```

### MockMessageEvent

```python
from astrbot_sdk.testing import MockMessageEvent, MockContext

@pytest.fixture
def mock_event():
    """创建 mock 事件"""
    event = MockMessageEvent(
        text="测试消息",
        user_id="12345",
        session_id="session_1",
        platform="qq"
    )
    return event

@pytest.mark.asyncio
async def test_with_mock_event(mock_event):
    """使用 mock 事件测试"""
    # 验证事件属性
    assert mock_event.text == "测试消息"
    assert mock_event.user_id == "12345"

    # 调用 reply（MockMessageEvent 会记录到 replies 列表）
    await mock_event.reply("回复内容")

    # 验证 replies 列表
    assert len(mock_event.replies) == 1
    assert "回复内容" in mock_event.replies[0]
```

### Mock 时间

```python
import time
from astrbot_sdk.testing import MockClock

def test_with_mock_time():
    """使用 mock 时间测试"""
    clock = MockClock(now=1234567890.0)

    # 获取当前时间
    assert clock.time() == 1234567890.0

    # 推进时间
    clock.advance(60.0)
    assert clock.time() == 1234567950.0
```

### Mock 外部 API

```python
import aiohttp
# 需要额外安装: pip install aioresponses
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
from pathlib import Path
from astrbot_sdk.testing import PluginHarness, SDKTestEnvironment

@pytest.fixture
def sample_user_data():
    """提供测试用户数据"""
    return {
        "user_id": "123",
        "name": "Alice",
        "email": "alice@example.com"
    }

@pytest.fixture
async def harness_with_plugin(tmp_path):
    """提供已启动的 harness"""
    env = SDKTestEnvironment(root=tmp_path)
    plugin_dir = env.plugin_dir("test_plugin")

    # 创建最小插件结构
    (plugin_dir / "plugin.yaml").write_text("""
_schema_version: 2
name: test_plugin
version: 1.0.0
author: test
desc: Test plugin

runtime:
  python: "3.12"

components:
  - class: main:TestPlugin
""")

    (plugin_dir / "main.py").write_text("""
from astrbot_sdk import Star, MessageEvent, Context
from astrbot_sdk.decorators import on_command

class TestPlugin(Star):
    @on_command("hello")
    async def hello(self, event: MessageEvent, ctx: Context):
        await event.reply("Hello!")
""")
    (plugin_dir / "requirements.txt").write_text("")

    harness = PluginHarness.from_plugin_dir(plugin_dir)
    async with harness:
        yield harness

# 测试中使用
@pytest.mark.asyncio
async def test_with_fixture(sample_user_data, harness_with_plugin):
    sent = await harness_with_plugin.dispatch_text("hello")
    assert len(sent) >= 1
    assert "Hello" in sent[0].text
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
    ("help", "可用命令"),
    ("about", "关于"),
    ("version", "版本"),
])
async def test_commands(harness_with_plugin, command, expected_response):
    sent = await harness_with_plugin.dispatch_text(command)
    assert len(sent) >= 1
    assert expected_response in sent[0].text
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
from pathlib import Path
from astrbot_sdk.testing import PluginHarness

async def run_with_timeout(coro, timeout=5):
    """带超时运行协程"""
    return await asyncio.wait_for(coro, timeout=timeout)

@asynccontextmanager
async def temporary_harness(plugin_dir: Path):
    """临时 harness 上下文"""
    harness = PluginHarness.from_plugin_dir(plugin_dir)
    async with harness:
        yield harness

def create_minimal_plugin(
    plugin_dir: Path,
    name: str = "test_plugin",
    code: str = ""
) -> Path:
    """创建最小插件结构"""
    plugin_dir.mkdir(parents=True, exist_ok=True)

    (plugin_dir / "plugin.yaml").write_text(f"""
_schema_version: 2
name: {name}
version: 1.0.0
author: test
desc: Test plugin

runtime:
  python: "3.12"

components:
  - class: main:TestPlugin
""")
    (plugin_dir / "requirements.txt").write_text("")

    default_code = """
from astrbot_sdk import Star, MessageEvent, Context
from astrbot_sdk.decorators import on_command

class TestPlugin(Star):
    @on_command("test")
    async def test(self, event: MessageEvent, ctx: Context):
        await event.reply("Test!")
"""
    (plugin_dir / "main.py").write_text(code or default_code)

    return plugin_dir
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
