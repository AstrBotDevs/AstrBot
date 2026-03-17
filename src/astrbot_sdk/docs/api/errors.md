# 错误处理 API 完整参考

## 概述

AstrBot SDK 提供了统一的错误处理机制，支持跨进程传递错误信息。所有可预期的错误都应使用 `AstrBotError` 类或其工厂方法创建。

**模块路径**: `astrbot_sdk.errors`

---

## 目录

- [错误处理流程](#错误处理流程)
- [导入方式](#导入方式)
- [ErrorCodes - 错误码常量](#errorcodes---错误码常量)
- [AstrBotError - 错误类](#astrboterror---错误类)
- [使用示例](#使用示例)
- [最佳实践](#最佳实践)

---

## 导入方式

```python
# 从主模块导入
from astrbot_sdk import AstrBotError

# 从 errors 模块导入
from astrbot_sdk.errors import AstrBotError, ErrorCodes
```

---

## 错误处理流程

```python
# 1. 抛出错误
raise AstrBotError.invalid_input("参数不能为空")

# 2. 错误被捕获并序列化为 payload
# 3. 跨进程传输后反序列化
# 4. 在 on_error 钩子中统一处理
```

```python
class MyPlugin(Star):
    async def on_error(self, error: AstrBotError) -> None:
        if error.retryable:
            # 可重试的错误
            ctx.logger.warning(f"可重试错误: {error.message}")
        else:
            # 不可重试的错误
            ctx.logger.error(f"错误: {error.hint or error.message}")
```

---

## ErrorCodes - 错误码常量

稳定的错误码常量，用于标识不同类型的错误。

### 定义

```python
class ErrorCodes:
    """AstrBot v4 的稳定错误码常量。"""
```

### 错误码列表

#### 不可重试错误（retryable=False）

| 错误码 | 说明 | 默认提示 |
|--------|------|----------|
| `UNKNOWN_ERROR` | 未知错误 | - |
| `LLM_NOT_CONFIGURED` | LLM 未配置 | - |
| `CAPABILITY_NOT_FOUND` | 能力未找到 | 请确认 AstrBot Core 是否已注册该 capability |
| `PERMISSION_DENIED` | 权限被拒绝 | - |
| `LLM_ERROR` | LLM 错误 | - |
| `INVALID_INPUT` | 输入无效 | 请检查调用参数 |
| `CANCELLED` | 调用被取消 | - |
| `PROTOCOL_VERSION_MISMATCH` | 协议版本不匹配 | 请升级 astrbot_sdk 至最新版本 |
| `PROTOCOL_ERROR` | 协议错误 | 请检查通信双方的协议实现 |
| `INTERNAL_ERROR` | 内部错误 | 请联系插件作者 |
| `RATE_LIMITED` | 速率限制 | 操作过于频繁，请稍后再试 |
| `COOLDOWN_ACTIVE` | 冷却中 | - |

#### 可重试错误（retryable=True）

| 错误码 | 说明 | 默认提示 |
|--------|------|----------|
| `CAPABILITY_TIMEOUT` | 能力调用超时 | - |
| `NETWORK_ERROR` | 网络错误 | 网络请求失败，请稍后重试 |
| `LLM_TEMPORARY_ERROR` | LLM 临时错误 | - |

---

## AstrBotError - 错误类

AstrBot SDK 的标准错误类型，支持跨进程传递。

### 类定义

```python
@dataclass(slots=True)
class AstrBotError(Exception):
    code: str
    message: str
    hint: str = ""
    retryable: bool = False
    docs_url: str = ""
    details: dict[str, Any] | None = None
```

### 属性说明

| 属性 | 类型 | 说明 |
|------|------|------|
| `code` | `str` | 错误码，来自 ErrorCodes 常量 |
| `message` | `str` | 错误消息，面向开发者 |
| `hint` | `str` | 用户提示，面向终端用户 |
| `retryable` | `bool` | 是否可重试 |
| `docs_url` | `str` | 文档链接 |
| `details` | `dict[str, Any] \| None` | 详细信息 |

---

## 工厂方法

### `cancelled(message)`

创建取消错误。

```python
@classmethod
def cancelled(cls, message: str = "调用被取消") -> AstrBotError
```

**参数**:
- `message` (`str`): 错误消息

**返回**: `AstrBotError` 实例

**示例**:

```python
raise AstrBotError.cancelled("用户取消操作")
```

---

### `capability_not_found(name)`

创建能力未找到错误。

```python
@classmethod
def capability_not_found(cls, name: str) -> AstrBotError
```

**参数**:
- `name` (`str`): 未找到的能力名称

**返回**: `AstrBotError` 实例

**示例**:

```python
raise AstrBotError.capability_not_found("my_plugin.custom_capability")
```

---

### `invalid_input(message, *, hint, docs_url, details)`

创建输入无效错误。

```python
@classmethod
def invalid_input(
    cls,
    message: str,
    *,
    hint: str = "请检查调用参数",
    docs_url: str = "",
    details: dict[str, Any] | None = None,
) -> AstrBotError
```

**参数**:
- `message` (`str`): 详细错误消息
- `hint` (`str`): 用户提示，默认 "请检查调用参数"
- `docs_url` (`str`): 文档链接
- `details` (`dict[str, Any] | None`): 详细信息

**返回**: `AstrBotError` 实例

**示例**:

```python
raise AstrBotError.invalid_input(
    "参数格式错误",
    hint="请使用 JSON 格式",
    details={"expected": "json", "received": "text"}
)
```

---

### `protocol_version_mismatch(message)`

创建协议版本不匹配错误。

```python
@classmethod
def protocol_version_mismatch(cls, message: str) -> AstrBotError
```

**参数**:
- `message` (`str`): 详细错误消息

**返回**: `AstrBotError` 实例

**示例**:

```python
raise AstrBotError.protocol_version_mismatch("SDK 版本 4.0 与 Core 版本 3.9 不兼容")
```

---

### `protocol_error(message)`

创建协议错误。

```python
@classmethod
def protocol_error(cls, message: str) -> AstrBotError
```

**参数**:
- `message` (`str`): 详细错误消息

**返回**: `AstrBotError` 实例

**示例**:

```python
raise AstrBotError.protocol_error("无效的 payload 格式")
```

---

### `internal_error(message, *, hint, docs_url, details)`

创建内部错误。

```python
@classmethod
def internal_error(
    cls,
    message: str,
    *,
    hint: str = "请联系插件作者",
    docs_url: str = "",
    details: dict[str, Any] | None = None,
) -> AstrBotError
```

**参数**:
- `message` (`str`): 详细错误消息
- `hint` (`str`): 用户提示，默认 "请联系插件作者"
- `docs_url` (`str`): 文档链接
- `details` (`dict[str, Any] | None`): 详细信息

**返回**: `AstrBotError` 实例

**示例**:

```python
raise AstrBotError.internal_error(
    "处理逻辑异常",
    hint="请检查日志并联系插件作者",
    details={"traceback": "..."}
)
```

---

### `network_error(message, *, hint, docs_url, details)`

创建网络错误。

```python
@classmethod
def network_error(
    cls,
    message: str,
    *,
    hint: str = "网络请求失败，请稍后重试",
    docs_url: str = "",
    details: dict[str, Any] | None = None,
) -> AstrBotError
```

**参数**:
- `message` (`str`): 详细错误消息
- `hint` (`str`): 用户提示，默认 "网络请求失败，请稍后重试"
- `docs_url` (`str`): 文档链接
- `details` (`dict[str, Any] | None`): 详细信息

**返回**: `AstrBotError` 实例

**特性**: `retryable=True`

**示例**:

```python
raise AstrBotError.network_error(
    "连接超时",
    hint="网络不稳定，请稍后重试",
    details={"url": "...", "timeout": 30}
)
```

---

### `rate_limited(*, hint, details)`

创建速率限制错误。

```python
@classmethod
def rate_limited(
    cls,
    *,
    hint: str = "操作过于频繁，请稍后再试。",
    details: dict[str, Any] | None = None,
) -> AstrBotError
```

**参数**:
- `hint` (`str`): 用户提示，默认 "操作过于频繁，请稍后再试。"
- `details` (`dict[str, Any] | None`): 详细信息

**返回**: `AstrBotError` 实例

**特性**: `retryable=False`

**示例**:

```python
raise AstrBotError.rate_limited(
    hint="每分钟最多调用 5 次",
    details={"limit": 5, "window": 60, "remaining": 0}
)
```

---

### `cooldown_active(*, hint, details)`

创建冷却中错误。

```python
@classmethod
def cooldown_active(
    cls,
    *,
    hint: str,
    details: dict[str, Any] | None = None,
) -> AstrBotError
```

**参数**:
- `hint` (`str`): 用户提示
- `details` (`dict[str, Any] | None`): 详细信息

**返回**: `AstrBotError` 实例

**特性**: `retryable=False`

**示例**:

```python
raise AstrBotError.cooldown_active(
    hint="技能冷却中，还需等待 25 秒",
    details={"cooldown": 30, "remaining": 25}
)
```

---

## 实例方法

### `to_payload()`

序列化为可传输的字典格式，用于跨进程传递错误信息。

```python
def to_payload(self) -> dict[str, object]
```

**返回**: `dict[str, object]` - 包含错误信息的字典

**返回格式**:

```python
{
    "code": "invalid_input",
    "message": "参数格式错误",
    "hint": "请使用 JSON 格式",
    "retryable": False,
    "docs_url": "",
    "details": {"expected": "json", "received": "text"}
}
```

---

### `from_payload(payload)`

从字典反序列化错误实例。

```python
@classmethod
def from_payload(cls, payload: dict[str, object]) -> AstrBotError
```

**参数**:
- `payload` (`dict[str, object]`): 包含错误信息的字典

**返回**: `AstrBotError` 实例

**示例**:

```python
payload = error.to_payload()
restored_error = AstrBotError.from_payload(payload)
```

---

### `__str__()`

返回错误消息。

```python
def __str__(self) -> str
```

**返回**: `str` - `message` 属性的值

---

## 使用示例

### 基本错误处理

```python
from astrbot_sdk import AstrBotError
from astrbot_sdk.errors import ErrorCodes

@on_command("divide")
async def divide(self, event: MessageEvent, a: int, b: int):
    if b == 0:
        raise AstrBotError.invalid_input(
            "除数不能为零",
            hint="请输入非零的除数"
        )
    return event.plain_result(f"{a} / {b} = {a / b}")
```

### 带详细信息的错误

```python
@on_command("search")
async def search(self, event: MessageEvent, keyword: str):
    if not keyword or len(keyword.strip()) == 0:
        raise AstrBotError.invalid_input(
            "搜索关键词不能为空",
            hint="请输入要搜索的关键词",
            details={
                "field": "keyword",
                "constraint": "non_empty",
                "provided": keyword
            }
        )
    # 执行搜索...
```

### 捕获和处理错误

```python
@on_command("risky")
async def risky_operation(self, event: MessageEvent):
    try:
        result = await some_network_request()
        return event.plain_result(f"成功: {result}")
    except AstrBotError as e:
        ctx.logger.error(f"操作失败: {e.message}")
        if e.retryable:
            await event.reply(f"操作失败（可重试）: {e.hint or e.message}")
        else:
            await event.reply(f"操作失败: {e.hint or e.message}")
```

### 在插件中处理错误

```python
class MyPlugin(Star):
    async def on_error(self, error: AstrBotError) -> None:
        """统一处理插件中的所有错误"""
        if error.code == ErrorCodes.CAPABILITY_NOT_FOUND:
            self.logger.error(f"能力未找到: {error.message}")
        elif error.code == ErrorCodes.NETWORK_ERROR:
            self.logger.warning(f"网络错误: {error.message}")
        elif error.retryable:
            self.logger.warning(f"可重试错误: {error.code} - {error.message}")
        else:
            self.logger.error(f"错误: {error.code} - {error.message}")
```

### 检查特定错误码

```python
try:
    await some_capability_call()
except AstrBotError as e:
    if e.code == ErrorCodes.RATE_LIMITED:
        remaining = e.details.get("remaining", 0)
        await event.reply(f"请求过多，请稍后再试。剩余次数: {remaining}")
    elif e.code == ErrorCodes.CAPABILITY_TIMEOUT:
        await event.reply("请求超时，请稍后重试")
    else:
        await event.reply(f"错误: {e.hint or e.message}")
```

### 自定义错误（使用通用构造方法）

```python
# 使用通用构造方法创建自定义错误
error = AstrBotError(
    code="custom_error_code",
    message="自定义错误消息",
    hint="这是给用户的提示",
    retryable=False,
    details={"custom_field": "custom_value"}
)
raise error
```

---

## 最佳实践

### 1. 使用工厂方法而非直接构造

```python
# 推荐
raise AstrBotError.invalid_input("参数错误")

# 不推荐（除非需要自定义错误码）
raise AstrBotError(
    code=ErrorCodes.INVALID_INPUT,
    message="参数错误",
    hint="请检查调用参数"
)
```

### 2. 提供用户友好的提示

```python
# 推荐
raise AstrBotError.invalid_input(
    "参数 'count' 必须为正整数",
    hint="请输入大于 0 的数字"
)

# 不推荐
raise AstrBotError.invalid_input("参数错误")
```

### 3. 使用 details 提供调试信息

```python
raise AstrBotError.invalid_input(
    "参数验证失败",
    hint="请检查输入格式",
    details={
        "field": "email",
        "pattern": "^[\\w\\.-]+@[\\w\\.-]+\\.\\w+$",
        "provided": "invalid-email"
    }
)
```

### 4. 区分可重试和不可重试错误

```python
# 网络错误 - 可重试
raise AstrBotError.network_error("连接失败")

# 参数错误 - 不可重试
raise AstrBotError.invalid_input("参数类型错误")
```

### 5. 在 on_error 中集中处理

```python
class MyPlugin(Star):
    async def on_error(self, error: AstrBotError) -> None:
        # 记录所有错误
        self.logger.error(f"错误: [{error.code}] {error.message}")

        # 可重试错误记录为警告级别
        if error.retryable:
            self.logger.warning(f"可重试错误，考虑实现重试逻辑")

        # 特定错误码的特殊处理
        if error.code == ErrorCodes.CAPABILITY_NOT_FOUND:
            self.logger.critical("请检查 AstrBot Core 配置")
```

### 6. 向用户展示适当的错误信息

```python
try:
    result = await operation()
except AstrBotError as e:
    # 优先使用 hint（面向用户）
    user_message = e.hint or e.message
    await event.reply(user_message)

    # 记录完整的错误信息（面向开发者）
    ctx.logger.error(f"操作失败: {e.code} - {e.message}", extra=e.details)
```

---

## 相关模块

- **事件处理**: `astrbot_sdk.events.MessageEvent`
- **上下文**: `astrbot_sdk.context.Context`
- **插件基类**: `astrbot_sdk.star.Star`

---

**版本**: v4.0
**模块**: `astrbot_sdk.errors`
**最后更新**: 2026-03-17
