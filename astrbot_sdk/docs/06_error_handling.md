# AstrBot SDK 错误处理与调试指南

本文档详细介绍 SDK 中的错误处理机制、错误类型、调试技巧和常见问题解决方案。

## 目录

- [错误处理概述](#错误处理概述)
- [AstrBotError 错误体系](#astrboterror-错误体系)
- [错误码参考](#错误码参考)
- [错误处理模式](#错误处理模式)
- [调试技巧](#调试技巧)
- [常见问题](#常见问题)

---

## 错误处理概述

AstrBot SDK 使用统一的错误体系 `AstrBotError`，支持跨进程传递（通过 to_payload/from_payload 序列化）。

### 错误处理流程

```
1. 运行时抛出 AstrBotError 子类或实例
2. 错误被捕获并序列化为 payload
3. 跨进程传输后反序列化
4. 在 on_error 钩子中统一处理
```

### 基本使用

```python
from astrbot_sdk.errors import AstrBotError, ErrorCodes

# 抛出错误
raise AstrBotError.invalid_input("参数不能为空")

# 捕获并处理
try:
    await some_operation()
except AstrBotError as e:
    if e.retryable:
        # 可重试的错误
        await retry()
    else:
        # 不可重试的错误
        await event.reply(e.hint or e.message)
```

---

## AstrBotError 错误体系

### AstrBotError 类

```python
@dataclass(slots=True)
class AstrBotError(Exception):
    code: str           # 错误码
    message: str        # 错误消息（面向开发者）
    hint: str = ""      # 用户提示（面向终端用户）
    retryable: bool = False  # 是否可重试
    docs_url: str = ""  # 文档链接
    details: dict[str, Any] | None = None  # 详细信息
```

### 工厂方法

#### 1. invalid_input - 输入无效错误

**场景**：参数格式错误、缺少必需参数等

```python
raise AstrBotError.invalid_input(
    message="参数格式错误",
    hint="请使用 JSON 格式",
    docs_url="https://docs.example.com/api"
)
```

**属性**：
- `retryable`: False
- 应该在修复输入后重试

#### 2. capability_not_found - 能力未找到

**场景**：调用的 capability 不存在或未注册

```python
raise AstrBotError.capability_not_found("unknown_capability")
```

**属性**：
- `retryable`: False
- 通常是配置或版本不匹配问题

#### 3. network_error - 网络错误

**场景**：连接超时、DNS 解析失败等

```python
raise AstrBotError.network_error(
    message="连接超时",
    hint="请检查网络连接后重试"
)
```

**属性**：
- `retryable`: True
- 通常可以重试

#### 4. internal_error - 内部错误

**场景**：SDK 或 Core 内部错误

```python
raise AstrBotError.internal_error(
    message="数据库连接失败",
    hint="请联系插件作者"
)
```

**属性**：
- `retryable`: False
- 需要开发者介入

#### 5. cancelled - 取消错误

**场景**：操作被取消

```python
raise AstrBotError.cancelled("用户取消了操作")
```

**属性**：
- `retryable`: False

#### 6. protocol_version_mismatch - 协议版本不匹配

**场景**：SDK 和 Core 协议版本不兼容

```python
raise AstrBotError.protocol_version_mismatch("协议版本不匹配: v4 vs v5")
```

**属性**：
- `retryable`: False
- 需要升级 SDK 或 Core

---

## 错误码参考

### 不可重试错误（retryable=False）

| 错误码 | 说明 | 处理方式 |
|--------|------|----------|
| `LLM_NOT_CONFIGURED` | LLM 未配置 | 配置 LLM Provider |
| `CAPABILITY_NOT_FOUND` | 能力未找到 | 检查 capability 名称 |
| `PERMISSION_DENIED` | 权限不足 | 检查用户权限 |
| `LLM_ERROR` | LLM 错误 | 查看详细错误信息 |
| `INVALID_INPUT` | 输入无效 | 修正输入参数 |
| `CANCELLED` | 操作被取消 | 无需处理 |
| `PROTOCOL_VERSION_MISMATCH` | 协议版本不匹配 | 升级 SDK |
| `PROTOCOL_ERROR` | 协议错误 | 检查实现 |
| `INTERNAL_ERROR` | 内部错误 | 联系开发者 |
| `RATE_LIMITED` | 速率限制 | 等待后重试 |
| `COOLDOWN_ACTIVE` | 冷却中 | 等待冷却结束 |

### 可重试错误（retryable=True）

| 错误码 | 说明 | 处理方式 |
|--------|------|----------|
| `CAPABILITY_TIMEOUT` | 能力调用超时 | 重试或增加超时时间 |
| `NETWORK_ERROR` | 网络错误 | 重试 |
| `LLM_TEMPORARY_ERROR` | LLM 临时错误 | 重试 |

---

## 对话相关异常

### ConversationClosed

对话已关闭异常。

**场景**：会话被显式关闭或超时时抛出

```python
from astrbot_sdk.conversation import ConversationClosed

@conversation_command("demo")
async def demo_handler(self, event, ctx, session):
    try:
        # 处理对话...
        session.close()  # 关闭会话
    except ConversationClosed:
        await event.reply("对话已结束")
```

**属性**：
- 继承自 `RuntimeError`
- 表示对话会话已结束，无法再接收消息

### ConversationReplaced

对话被替换异常。

**场景**：用户开始新对话，当前对话被替换时抛出

```python
from astrbot_sdk.conversation import ConversationReplaced

@conversation_command("survey")
async def survey_handler(self, event, ctx, session):
    try:
        # 处理对话...
        pass
    except ConversationReplaced:
        # 用户开始了新对话
        await event.reply("已切换到新对话")
```

**属性**：
- 继承自 `RuntimeError`
- 表示当前对话被新对话替换

---

## 错误处理模式

### 模式 1：基本错误处理

```python
@on_command("risky")
async def risky_handler(self, event: MessageEvent, ctx: Context):
    try:
        result = await risky_operation()
        await event.reply(f"成功: {result}")
    except AstrBotError as e:
        # SDK 错误包含用户友好的提示
        await event.reply(e.hint or e.message)
        ctx.logger.error(f"操作失败: {e}")
    except Exception as e:
        # 未知错误
        ctx.logger.exception("未知错误")
        await event.reply("操作失败，请稍后重试")
```

### 模式 2：分层错误处理

```python
async def fetch_data(ctx: Context, url: str) -> dict:
    """获取数据，处理网络错误"""
    try:
        return await ctx.http.get(url)
    except AstrBotError as e:
        if e.code == ErrorCodes.NETWORK_ERROR:
            # 网络错误可以重试
            ctx.logger.warning(f"网络错误，重试: {e}")
            await asyncio.sleep(1)
            return await ctx.http.get(url)
        raise

@on_command("data")
async def data_handler(self, event: MessageEvent, ctx: Context):
    try:
        data = await self.fetch_data(ctx, "https://api.example.com/data")
        await event.reply(f"数据: {data}")
    except AstrBotError as e:
        if e.retryable:
            await event.reply(f"暂时无法获取数据，请稍后重试")
        else:
            await event.reply(f"获取数据失败: {e.hint}")
```

### 模式 3：on_error 生命周期钩子

```python
class MyPlugin(Star):
    async def on_error(self, error: Exception, event, ctx) -> None:
        """统一错误处理"""
        from astrbot_sdk.errors import AstrBotError

        if isinstance(error, AstrBotError):
            # SDK 错误
            if error.code == ErrorCodes.RATE_LIMITED:
                await event.reply("操作过于频繁，请稍后再试")
            elif error.code == ErrorCodes.PERMISSION_DENIED:
                await event.reply("你没有权限执行此操作")
            else:
                await event.reply(error.hint or "操作失败")
        elif isinstance(error, ValueError):
            # 参数错误
            await event.reply(f"参数错误: {error}")
        else:
            # 未知错误
            ctx.logger.exception("未处理的错误")
            await event.reply("发生未知错误，请联系管理员")
```

### 模式 4：重试机制

```python
from astrbot_sdk.errors import AstrBotError, ErrorCodes

async def with_retry(
    operation,
    max_retries: int = 3,
    delay: float = 1.0
):
    """带重试的操作"""
    last_error = None
    
    for attempt in range(max_retries):
        try:
            return await operation()
        except AstrBotError as e:
            last_error = e
            if not e.retryable:
                raise  # 不可重试错误直接抛出
            
            ctx.logger.warning(f"第 {attempt + 1} 次尝试失败: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(delay * (attempt + 1))  # 指数退避
    
    raise last_error

# 使用
@on_command("fetch")
async def fetch_handler(self, event: MessageEvent, ctx: Context):
    try:
        result = await with_retry(
            lambda: ctx.llm.chat("生成内容"),
            max_retries=3
        )
        await event.reply(result)
    except AstrBotError as e:
        await event.reply(f"请求失败: {e.hint}")
```

### 模式 5：取消处理

```python
@on_command("long_task")
async def long_task_handler(self, event: MessageEvent, ctx: Context):
    try:
        for i in range(100):
            # 检查是否取消
            ctx.cancel_token.raise_if_cancelled()
            
            await do_work(i)
            await asyncio.sleep(0.1)
        
        await event.reply("任务完成")
    except asyncio.CancelledError:
        await event.reply("任务已取消")
        raise  # 重新抛出以便框架处理
    except AstrBotError as e:
        if e.code == ErrorCodes.CANCELLED:
            await event.reply("操作已取消")
        else:
            raise
```

---

## 调试技巧

### 1. 启用详细日志

```python
# 在插件中记录详细日志
@on_command("debug")
async def debug_handler(self, event: MessageEvent, ctx: Context):
    ctx.logger.debug(f"收到消息: {event.text}")
    ctx.logger.debug(f"用户ID: {event.user_id}")
    ctx.logger.debug(f"会话ID: {event.session_id}")
    ctx.logger.debug(f"平台: {event.platform}")
    
    # 记录组件信息
    components = event.get_messages()
    for comp in components:
        ctx.logger.debug(f"组件: {comp.type} - {comp}")
```

### 2. 使用测试框架调试

```python
from astrbot_sdk.testing import PluginTestHarness

async def test_with_debug():
    harness = PluginTestHarness()
    plugin = harness.load_plugin("my_plugin.main:MyPlugin")
    
    # 启用详细日志
    harness.enable_debug_logging()
    
    # 模拟事件
    result = await harness.simulate_command("/hello")
    print(f"结果: {result}")
    
    # 查看调用历史
    for call in harness.get_call_history():
        print(f"调用: {call}")
```

### 3. 使用 PDB 调试

```python
import pdb

@on_command("debug")
async def debug_handler(self, event: MessageEvent, ctx: Context):
    # 设置断点
    pdb.set_trace()
    
    result = await ctx.llm.chat("测试")
    await event.reply(result)
```

### 4. 记录完整错误信息

```python
import traceback

@on_command("risky")
async def risky_handler(self, event: MessageEvent, ctx: Context):
    try:
        result = await risky_operation()
        await event.reply(f"成功: {result}")
    except Exception as e:
        # 记录完整堆栈
        ctx.logger.error(f"错误: {e}")
        ctx.logger.error(f"堆栈: {traceback.format_exc()}")
        
        # 发送简化信息给用户
        await event.reply("操作失败，请查看日志")
```

### 5. 使用 Context 的 cancel_token 调试

```python
@on_command("timeout_test")
async def timeout_test(self, event: MessageEvent, ctx: Context):
    ctx.logger.info(f"取消状态: {ctx.cancel_token.cancelled}")
    
    try:
        # 长时间运行的操作
        for i in range(10):
            ctx.logger.debug(f"步骤 {i}, 取消状态: {ctx.cancel_token.cancelled}")
            ctx.cancel_token.raise_if_cancelled()
            await asyncio.sleep(1)
        
        await event.reply("完成")
    except asyncio.CancelledError:
        ctx.logger.info("操作被取消")
        raise
```

---

## 常见问题

### Q1: 如何处理 "CAPABILITY_NOT_FOUND" 错误？

**原因**：调用的 capability 不存在或未注册

**解决方案**：
```python
# 检查 Core 版本是否支持
# 确认 capability 名称正确
# 检查插件是否正确加载

try:
    result = await ctx._proxy.call("unknown.capability", {})
except AstrBotError as e:
    if e.code == ErrorCodes.CAPABILITY_NOT_FOUND:
        ctx.logger.error("当前 AstrBot 版本不支持此功能")
        await event.reply("请升级 AstrBot 到最新版本")
```

### Q2: 如何处理速率限制？

**解决方案**：
```python
from astrbot_sdk.errors import ErrorCodes

@on_command("api_call")
async def api_call_handler(self, event: MessageEvent, ctx: Context):
    try:
        result = await call_api()
        await event.reply(result)
    except AstrBotError as e:
        if e.code == ErrorCodes.RATE_LIMITED:
            # 获取重试时间（如果有）
            retry_after = e.details.get("retry_after", 60)
            await event.reply(f"操作过于频繁，请 {retry_after} 秒后再试")
        else:
            raise
```

### Q3: 如何区分用户错误和系统错误？

**解决方案**：
```python
@on_command("process")
async def process_handler(self, event: MessageEvent, ctx: Context):
    try:
        result = await process(event.text)
        await event.reply(result)
    except AstrBotError as e:
        if e.code in {
            ErrorCodes.INVALID_INPUT,
            ErrorCodes.PERMISSION_DENIED
        }:
            # 用户错误，直接提示
            await event.reply(e.hint or e.message)
        else:
            # 系统错误，记录并提示
            ctx.logger.error(f"系统错误: {e}")
            await event.reply("系统错误，请稍后重试")
```

### Q4: 如何在 on_error 中避免无限循环？

**注意**：如果 `on_error` 中抛出异常，会导致递归调用

**解决方案**：
```python
class MyPlugin(Star):
    async def on_error(self, error: Exception, event, ctx) -> None:
        try:
            # 错误处理逻辑
            await event.reply("发生错误")
        except Exception as e:
            # 避免递归，只记录不回复
            ctx.logger.exception("on_error 失败")
```

### Q5: 如何调试跨进程通信问题？

**解决方案**：
```python
# 启用 SDK 调试日志
import logging
logging.getLogger("astrbot_sdk").setLevel(logging.DEBUG)

# 在关键位置添加日志
@on_command("debug_comm")
async def debug_comm_handler(self, event: MessageEvent, ctx: Context):
    ctx.logger.debug("开始调用 capability")
    
    try:
        result = await ctx._proxy.call("test.capability", {"key": "value"})
        ctx.logger.debug(f"调用成功: {result}")
    except Exception as e:
        ctx.logger.error(f"调用失败: {e}")
        raise
```

---

## 最佳实践

### 1. 始终处理可重试错误

```python
# 好的做法
async def reliable_operation(ctx):
    max_retries = 3
    for i in range(max_retries):
        try:
            return await ctx.llm.chat("prompt")
        except AstrBotError as e:
            if e.retryable and i < max_retries - 1:
                await asyncio.sleep(2 ** i)  # 指数退避
            else:
                raise
```

### 2. 提供用户友好的错误提示

```python
# 好的做法
try:
    result = await operation()
except AstrBotError as e:
    # 使用 SDK 提供的 hint
    await event.reply(e.hint or "操作失败，请稍后重试")
```

### 3. 区分日志级别

```python
# 好的做法
try:
    result = await operation()
except AstrBotError as e:
    if e.retryable:
        ctx.logger.warning(f"临时错误: {e}")
    else:
        ctx.logger.error(f"严重错误: {e}")
```

### 4. 在 on_stop 中处理清理错误

```python
class MyPlugin(Star):
    async def on_stop(self, ctx):
        try:
            await self.cleanup()
        except Exception as e:
            # 清理错误不应阻止停止流程
            ctx.logger.error(f"清理失败: {e}")
```

---

## 相关文档

- [Context API 参考](./01_context_api.md)
- [Star 类与生命周期](./04_star_lifecycle.md)
- [高级主题](./07_advanced_topics.md)
