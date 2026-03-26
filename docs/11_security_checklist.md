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

当前版本没有已知的 SDK 框架级高风险未修复项。以下历史回归已经关闭，
保留在这里帮助开发者理解为什么这些约束存在：

- `ProviderManagerClient.register_provider_change_hook()` 现在必须和
  `unregister_provider_change_hook()` 配对使用，避免残留订阅任务。
- `PlatformCompatFacade` 内部已经串行化状态刷新，插件侧不需要再额外为
  `refresh()` / `clear_errors()` 套一层锁来规避 SDK 自身竞态。
- Provider 管理路径会先复制 provider payload，再做 merge，避免污染共享缓存。

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
2. 通过项目官方联系渠道私下报告，例如 qq向Soulter反馈
3. 提供详细的复现步骤
4. 等待修复后再公开

---

## 相关文档

- [错误处理与调试](./06_error_handling.md)
- [高级主题](./07_advanced_topics.md)
- [测试指南](./08_testing_guide.md)
