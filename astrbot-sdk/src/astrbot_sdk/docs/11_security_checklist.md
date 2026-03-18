# AstrBot SDK 安全检查清单

本文档包含 SDK 安全开发检查清单和已知安全问题，帮助开发者编写安全的插件。

## 目录

- [安全检查清单](#安全检查清单)
- [已知安全问题](#已知安全问题)
- [安全最佳实践](#安全最佳实践)
- [安全审计指南](#安全审计指南)

---

## 安全检查清单

### 输入验证

- [ ] 所有用户输入都经过验证
- [ ] 输入长度有限制
- [ ] 输入内容有白名单过滤
- [ ] 特殊字符被正确转义

```python
# ✅ 好的做法
import re
from astrbot_sdk.errors import AstrBotError

def validate_input(text: str) -> str:
    if len(text) > 1000:
        raise AstrBotError.invalid_input("输入过长")
    if not re.match(r'^[\w\s\-]+$', text):
        raise AstrBotError.invalid_input("包含非法字符")
    return text

# ❌ 不好的做法
async def unsafe_handler(event, ctx):
    result = eval(event.text)  # 危险！
```

### 敏感信息处理

- [ ] API Key 等敏感信息不硬编码
- [ ] 敏感信息从配置或环境变量读取
- [ ] 敏感信息不在日志中打印
- [ ] 敏感信息不存储在不安全的位置

```python
# ✅ 好的做法
import os

class MyPlugin(Star):
    async def on_start(self, ctx):
        config = await ctx.metadata.get_plugin_config()
        self.api_key = config.get("api_key") or os.getenv("MY_API_KEY")
        ctx.logger.info("API Key 已配置")  # 不打印实际值

# ❌ 不好的做法
class UnsafePlugin(Star):
    api_key = "sk-1234567890"  # 硬编码！
    
    async def on_start(self, ctx):
        ctx.logger.info(f"API Key: {self.api_key}")  # 泄露！
```

### 权限检查

- [ ] 管理员命令有权限验证
- [ ] 敏感操作有二次确认
- [ ] 资源访问有权限控制

```python
# ✅ 好的做法
from astrbot_sdk.decorators import require_admin

class MyPlugin(Star):
    @on_command("admin_only")
    @require_admin
    async def admin_cmd(self, event, ctx):
        await event.reply("管理员命令")

# ❌ 不好的做法
class UnsafePlugin(Star):
    @on_command("delete_all")
    async def delete_all(self, event, ctx):
        # 任何人都可以执行危险操作！
        await ctx.db.clear_all()
```

### 速率限制

- [ ] 昂贵的操作有速率限制
- [ ] API 调用有配额控制
- [ ] 资源密集型操作有限制

```python
# ✅ 好的做法
from astrbot_sdk.decorators import rate_limit

class MyPlugin(Star):
    @on_command("generate")
    @rate_limit(limit=5, window=3600, scope="user")
    async def generate(self, event, ctx):
        # 昂贵的 LLM 调用
        result = await ctx.llm.chat("生成内容", model="gpt-4")
        await event.reply(result)
```

### 资源管理

- [ ] 资源正确释放
- [ ] 连接正确关闭
- [ ] 任务正确取消
- [ ] 避免资源泄漏

```python
# ✅ 好的做法
class MyPlugin(Star):
    async def on_start(self, ctx):
        self._session = aiohttp.ClientSession()
        self._task = asyncio.create_task(self.background_task())
    
    async def on_stop(self, ctx):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._session:
            await self._session.close()
```

### 错误处理

- [ ] 错误信息不泄露敏感信息
- [ ] 异常被正确捕获和处理
- [ ] 错误日志不包含敏感数据

```python
# ✅ 好的做法
try:
    result = await operation()
except Exception as e:
    ctx.logger.error(f"操作失败: {type(e).__name__}")
    await event.reply("操作失败，请稍后重试")

# ❌ 不好的做法
try:
    result = await operation()
except Exception as e:
    await event.reply(f"错误: {str(e)}")  # 可能泄露敏感信息
```

---

## 已知安全问题

> **注意**: 以下标记为 ✅ 已修复 的问题已在当前版本中解决，保留作为历史记录供参考。

---

### ✅ 已修复: Provider change hook 资源泄漏

**位置**: `astrbot_sdk/clients/provider.py:269-288`

**原问题描述**:
`register_provider_change_hook()` 返回 Task，但没有对应的 `unregister_provider_change_hook()` 方法。

**修复状态**: ✅ 已修复于 `provider.py:293-303`

```python
# 现在可以安全地注销 hook
async def unregister_provider_change_hook(
    self,
    task: asyncio.Task[None],
) -> None:
    if task not in self._change_hook_tasks:
        return
    self._change_hook_tasks.discard(task)
    if not task.done():
        task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
```

**使用示例**:
```python
class MyPlugin(Star):
    async def on_start(self, ctx):
        self._hook_task = await ctx.provider_manager.register_provider_change_hook(
            self.on_provider_change
        )
    
    async def on_stop(self, ctx):
        # 正确清理资源
        if hasattr(self, '_hook_task'):
            await ctx.provider_manager.unregister_provider_change_hook(self._hook_task)
```

---

### ✅ 已修复: PlatformCompatFacade 并发安全

**位置**: `astrbot_sdk/context.py:69`

**原问题描述**:
从 `frozen=True` 改为可变以支持 `refresh()`，但多个 async 方法可能并发执行状态更新。

**修复状态**: ✅ 已修复于 `context.py:85`

```python
@dataclass(slots=True)
class PlatformCompatFacade:
    _ctx: Context
    id: str
    name: str
    type: str
    status: PlatformStatus = PlatformStatus.PENDING
    errors: list[PlatformError] = field(default_factory=list)
    last_error: PlatformError | None = None
    unified_webhook: bool = False
    _state_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)  # ✅ 已添加
    
    async def refresh(self) -> None:
        async with self._state_lock:  # ✅ 使用锁保护
            await self._refresh_locked()
```

---

### ✅ 已修复: 直接修改 provider dict

**位置**: `astrbot_sdk/runtime/_capability_router_builtins.py:857`

**原问题描述**:
直接修改 `_provider_catalog` 缓存中的 dict。

**修复状态**: ✅ 已修复 - 代码已创建副本

```python
# _managed_provider_record_by_id 方法中 (lines 869-884)
def _managed_provider_record_by_id(self, provider_id: str) -> dict[str, Any] | None:
    provider = self._provider_payload_by_id(provider_id)
    if provider is not None:
        config = self._provider_config_by_id(provider_id) or provider
        merged = dict(provider)  # ✅ 创建副本
        merged.update(           # ✅ 修改副本，不影响原始缓存
            {
                "enable": config.get("enable", True),
                "provider_source_id": config.get("provider_source_id"),
            }
        )
        return self._managed_provider_record(merged, loaded=True)
```

---

### 🔴 High: PlatformCompatFacade 并发安全风险

**位置**: `astrbot_sdk/context.py:69`

**问题描述**:
从 `frozen=True` 改为可变以支持 `refresh()`，但多个 async 方法可能并发执行状态更新，没有锁保护。

**风险等级**: Medium-High

**影响**:
- 竞态条件
- 状态不一致
- 数据损坏

**临时解决方案**:
```python
# 避免并发调用 refresh()
class MyPlugin(Star):
    def __init__(self):
        self._refresh_lock = asyncio.Lock()
    
    async def safe_refresh(self, platform):
        async with self._refresh_lock:
            await platform.refresh()
```

**修复计划**: 在 `PlatformCompatFacade` 中添加 `asyncio.Lock`

---

### 🟡 Medium: 直接修改 provider dict

**位置**: `astrbot_sdk/runtime/_capability_router_builtins.py:857`

**问题描述**:
```python
provider.update({...})  # 直接修改了 _provider_catalog 缓存
```

**风险等级**: Medium

**影响**:
- 缓存污染
- 意外的副作用
- 数据不一致

**临时解决方案**:
```python
# 在调用前创建副本
provider_copy = dict(provider)
provider_copy.update({...})
```

**修复计划**: 使用 `dict()` 创建副本后再修改

---

### 🟡 Medium: 命令参数注入风险

**问题描述**:
插件可能直接使用用户输入作为命令参数，存在注入风险。

**风险等级**: Medium

**示例**:
```python
# ❌ 危险
@on_command("search")
async def search(self, event, ctx, query):
    # 如果 query 包含特殊字符，可能引发问题
    os.system(f"grep {query} data.txt")

# ✅ 安全
@on_command("search")
async def search(self, event, ctx, query):
    # 验证和清理输入
    safe_query = re.sub(r'[^\w\s]', '', query)
    subprocess.run(["grep", safe_query, "data.txt"], capture_output=True)
```

---

### 🟢 Low: 敏感信息可能出现在日志中

**问题描述**:
某些错误日志可能包含敏感信息。

**风险等级**: Low

**建议**:
```python
# ✅ 安全的日志记录
ctx.logger.info(f"用户 {user_id} 执行操作")  # 只记录 ID

# ❌ 不安全的日志记录
ctx.logger.info(f"用户数据: {user_data}")  # 可能包含敏感信息
```

---

## 安全最佳实践

### 1. 最小权限原则

```python
class MyPlugin(Star):
    @on_command("public")
    async def public_cmd(self, event, ctx):
        # 所有人可用
        pass
    
    @on_command("admin")
    @require_admin
    async def admin_cmd(self, event, ctx):
        # 仅管理员可用
        pass
    
    @on_command("owner")
    async def owner_cmd(self, event, ctx):
        # 仅插件所有者可用
        if event.user_id != self.owner_id:
            raise AstrBotError.invalid_input("权限不足")
```

### 2. 输入验证白名单

```python
import re

ALLOWED_COMMANDS = {"help", "status", "info"}

def validate_command(cmd: str) -> str:
    cmd = cmd.lower().strip()
    if cmd not in ALLOWED_COMMANDS:
        raise AstrBotError.invalid_input("未知命令")
    return cmd
```

### 3. 安全的文件操作

```python
import os
from pathlib import Path

BASE_DIR = Path("/safe/directory")

def safe_read_file(filename: str) -> str:
    # 防止目录遍历
    path = (BASE_DIR / filename).resolve()
    if not str(path).startswith(str(BASE_DIR)):
        raise AstrBotError.invalid_input("非法路径")
    
    return path.read_text()
```

### 4. 安全的正则表达式

```python
import re

# ✅ 使用原始字符串和适当的限制
pattern = re.compile(r'^[a-zA-Z0-9_]{1,50}$')

# ❌ 避免复杂的正则，可能导致 ReDoS
# pattern = re.compile(r'(a+)+b')  # 危险！
```

### 5. 安全配置

```python
class MyPlugin(Star):
    async def on_start(self, ctx):
        config = await ctx.metadata.get_plugin_config()
        
        # 验证必需配置
        required = ["api_key", "endpoint"]
        for key in required:
            if key not in config:
                raise ValueError(f"缺少必需配置: {key}")
        
        # 验证配置值
        if not config["api_key"].startswith("sk-"):
            raise ValueError("无效的 API Key 格式")
        
        self.config = config
```

---

## 安全审计指南

### 审计检查清单

1. **代码审查**
   - [ ] 所有输入都经过验证
   - [ ] 没有使用 eval/exec
   - [ ] 没有硬编码的敏感信息
   - [ ] 错误处理不泄露敏感信息

2. **依赖审查**
   ```bash
   # 检查依赖漏洞
   pip install safety
   safety check
   
   # 检查依赖许可证
   pip install pip-licenses
   pip-licenses
   ```

3. **日志审查**
   - [ ] 日志不包含密码、token
   - [ ] 日志不包含个人隐私信息
   - [ ] 日志有适当的级别

4. **权限审查**
   - [ ] 敏感操作有权限检查
   - [ ] 没有特权提升漏洞
   - [ ] 资源访问有控制

### 安全测试

```python
# 测试输入验证
def test_input_validation():
    # SQL 注入测试
    malicious_input = "' OR '1'='1"
    
    # XSS 测试
    xss_input = "<script>alert('xss')</script>"
    
    # 路径遍历测试
    path_input = "../../../etc/passwd"
    
    # 验证这些输入都被正确拒绝
```

### 安全工具

```bash
# 静态分析
pip install bandit
bandit -r my_plugin/

# 类型检查
pip install mypy
mypy my_plugin/

# 代码质量
pip install pylint
pylint my_plugin/
```

---

## 报告安全问题

如果您发现 SDK 或插件的安全问题，请通过以下方式报告：

1. **不要** 在公开 issue 中报告安全问题
2. 发送邮件到 security@example.com
3. 提供详细的复现步骤
4. 等待修复后再公开

---

## 相关文档

- [错误处理与调试](./06_error_handling.md)
- [高级主题](./07_advanced_topics.md)
- [测试指南](./08_testing_guide.md)
