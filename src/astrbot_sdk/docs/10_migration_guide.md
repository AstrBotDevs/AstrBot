# AstrBot SDK 迁移指南

本文档帮助开发者从旧版本或其他框架迁移到 AstrBot SDK v4。

## 目录

- [从 v3 迁移](#从-v3-迁移)
- [从其他框架迁移](#从其他框架迁移)
- [破坏性变更](#破坏性变更)
- [迁移检查清单](#迁移检查清单)

---

## 从 v3 迁移

### 插件类定义

**v3 (旧版本)**:
```python
from astrbot.api import star

@star.register("my_plugin")
class MyPlugin(star.Star):
    def __init__(self, context):
        super().__init__(context)
```

**v4 (新版本)**:
```python
from astrbot_sdk import Star

class MyPlugin(Star):
    async def on_start(self, ctx):
        pass
    
    async def on_stop(self, ctx):
        pass
```

### 装饰器变更

**v3**:
```python
from astrbot.api import filter

@filter.command("hello")
async def hello(self, event):
    await event.reply("Hello!")
```

**v4**:
```python
from astrbot_sdk.decorators import on_command

@on_command("hello")
async def hello(self, event, ctx):
    await event.reply("Hello!")
```

### Context 访问

**v3**:
```python
# 通过 self.context
config = self.context.get_config()
reply = await self.context.llm_generate("prompt")
```

**v4**:
```python
# 通过参数注入
async def handler(self, event, ctx):
    config = await ctx.metadata.get_plugin_config()
    reply = await ctx.llm.chat("prompt")
```

### 数据存储

**v3**:
```python
# 通过 context
await self.context.put_kv_data("key", value)
data = await self.context.get_kv_data("key", default)
```

**v4**:
```python
# 通过 db 客户端
await ctx.db.set("key", value)
data = await ctx.db.get("key")

# 或使用 Mixin
from astrbot_sdk import PluginKVStoreMixin

class MyPlugin(Star, PluginKVStoreMixin):
    async def save(self):
        await self.put_kv_data("key", value)
```

### 消息发送

**v3**:
```python
# 通过 event
await event.reply("消息")

# 主动发送
await self.context.send_message(session, chain)
```

**v4**:
```python
# 通过 event
await event.reply("消息")

# 主动发送
await ctx.platform.send(session, "消息")
await ctx.platform.send_chain(session, chain)
```

### 生命周期

**v3**:
```python
class MyPlugin(Star):
    async def initialize(self):
        # 初始化
        pass
    
    async def terminate(self):
        # 清理
        pass
```

**v4**:
```python
class MyPlugin(Star):
    async def on_start(self, ctx):
        # 启动时
        await super().on_start(ctx)
    
    async def on_stop(self, ctx):
        # 停止时
        await super().on_stop(ctx)
    
    # 仍然支持
    async def initialize(self):
        pass
    
    async def terminate(self):
        pass
```

### 配置获取

**v3**:
```python
config = self.context.get_config()
```

**v4**:
```python
config = await ctx.metadata.get_plugin_config()
```

### LLM 调用

**v3**:
```python
reply = await self.context.llm_generate("prompt")

# 带历史
reply = await self.context.llm_generate(
    "prompt",
    contexts=[{"role": "user", "content": "历史"}]
)
```

**v4**:
```python
from astrbot_sdk.clients.llm import ChatMessage

reply = await ctx.llm.chat("prompt")

# 带历史
history = [
    ChatMessage(role="user", content="历史"),
]
reply = await ctx.llm.chat("prompt", history=history)
```

### 错误处理

**v3**:
```python
try:
    result = await operation()
except Exception as e:
    await event.reply(f"错误: {e}")
```

**v4**:
```python
from astrbot_sdk.errors import AstrBotError

try:
    result = await operation()
except AstrBotError as e:
    # 使用 SDK 提供的用户友好提示
    await event.reply(e.hint or e.message)
except Exception as e:
    ctx.logger.error(f"错误: {e}")
    await event.reply("操作失败")
```

---

## 从其他框架迁移

### 从 NoneBot2 迁移

**NoneBot2**:
```python
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Event

matcher = on_command("hello")

@matcher.handle()
async def hello(bot: Bot, event: Event):
    await matcher.send("Hello!")
```

**AstrBot SDK**:
```python
from astrbot_sdk import Star, MessageEvent, Context
from astrbot_sdk.decorators import on_command

class MyPlugin(Star):
    @on_command("hello")
    async def hello(self, event: MessageEvent, ctx: Context):
        await event.reply("Hello!")
```

### 从 Koishi 迁移

**Koishi**:
```javascript
ctx.command('hello')
  .action(() => 'Hello!')
```

**AstrBot SDK**:
```python
from astrbot_sdk import Star, MessageEvent, Context
from astrbot_sdk.decorators import on_command

class MyPlugin(Star):
    @on_command("hello")
    async def hello(self, event: MessageEvent, ctx: Context):
        await event.reply("Hello!")
```

### 从 python-telegram-bot 迁移

**python-telegram-bot**:
```python
from telegram import Update
from telegram.ext import ContextTypes

async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello!")
```

**AstrBot SDK**:
```python
from astrbot_sdk import Star, MessageEvent, Context
from astrbot_sdk.decorators import on_command

class MyPlugin(Star):
    @on_command("hello")
    @platforms("telegram")
    async def hello(self, event: MessageEvent, ctx: Context):
        await event.reply("Hello!")
```

---

## 破坏性变更

### v3 → v4 主要变更

1. **注册方式**
   - v3: `@star.register()` + `@filter.command()`
   - v4: `@on_command()` 直接在类方法上

2. **Context 获取**
   - v3: `self.context`
   - v4: `ctx` 参数注入

3. **数据存储**
   - v3: `self.context.put_kv_data()`
   - v4: `ctx.db.set()` 或 `PluginKVStoreMixin`

4. **配置获取**
   - v3: `self.context.get_config()`
   - v4: `ctx.metadata.get_plugin_config()`

5. **LLM 调用**
   - v3: `self.context.llm_generate()`
   - v4: `ctx.llm.chat()`

6. **生命周期**
   - v3: `initialize()` / `terminate()`
   - v4: `on_start()` / `on_stop()`（仍然支持旧方法）

7. **错误类型**
   - v3: 标准 Python 异常
   - v4: `AstrBotError` 体系

### 已弃用的功能

| v3 功能 | v4 替代方案 | 状态 |
|---------|-------------|------|
| `@star.register()` | 继承 `Star` 类 | 已移除 |
| `self.context` | `ctx` 参数 | 已变更 |
| `filter.command()` | `on_command()` | 已更名 |
| `filter.regex()` | `on_message(regex=...)` | 已变更 |
| `llm_generate()` | `ctx.llm.chat()` | 已更名 |
| `send_message()` | `ctx.platform.send()` | 已更名 |

---

## 迁移检查清单

### 代码迁移

- [ ] 更新导入语句
- [ ] 移除 `@star.register()` 装饰器
- [ ] 将 `@filter.command()` 改为 `@on_command()`
- [ ] 添加 `ctx` 参数到所有 handler
- [ ] 更新 Context 访问方式
- [ ] 更新数据存储调用
- [ ] 更新 LLM 调用
- [ ] 更新配置获取
- [ ] 更新错误处理

### 配置迁移

- [ ] 更新 `plugin.yaml` 格式
- [ ] 检查 `support_platforms` 配置
- [ ] 更新 `runtime` 配置

### 测试迁移

- [ ] 更新测试导入
- [ ] 更新测试 mock
- [ ] 运行测试验证

### 文档更新

- [ ] 更新 README
- [ ] 更新使用文档
- [ ] 更新 CHANGELOG

---

## 迁移工具

### 自动迁移脚本（示例）

```python
#!/usr/bin/env python3
"""v3 到 v4 迁移辅助脚本"""

import re
import sys
from pathlib import Path

def migrate_file(file_path: Path):
    """迁移单个文件"""
    content = file_path.read_text(encoding="utf-8")
    
    # 替换导入
    content = re.sub(
        r'from astrbot\.api import star',
        'from astrbot_sdk import Star, Context, MessageEvent',
        content
    )
    
    # 替换装饰器
    content = re.sub(
        r'@star\.register\([^)]*\)',
        '',
        content
    )
    
    content = re.sub(
        r'@filter\.command\(([^)]*)\)',
        r'@on_command(\1)',
        content
    )
    
    # 替换类定义
    content = re.sub(
        r'class (\w+)\(star\.Star\)',
        r'class \1(Star)',
        content
    )
    
    # 替换 context 访问
    content = re.sub(
        r'self\.context\.get_config\(\)',
        'await ctx.metadata.get_plugin_config()',
        content
    )
    
    content = re.sub(
        r'self\.context\.llm_generate\(',
        'ctx.llm.chat(',
        content
    )
    
    # 添加 ctx 参数
    content = re.sub(
        r'async def (\w+)\(self, event\)',
        r'async def \1(self, event, ctx)',
        content
    )
    
    # 写回文件
    file_path.write_text(content, encoding="utf-8")
    print(f"已迁移: {file_path}")

def main():
    if len(sys.argv) < 2:
        print("用法: python migrate.py <plugin_directory>")
        sys.exit(1)
    
    plugin_dir = Path(sys.argv[1])
    
    for py_file in plugin_dir.rglob("*.py"):
        migrate_file(py_file)
    
    print("迁移完成！请手动检查并测试。")

if __name__ == "__main__":
    main()
```

---

## 常见问题

### Q: v3 插件能在 v4 运行吗？

**A**: 不能，需要进行迁移。但是 SDK 提供了兼容层，可以简化迁移过程。

### Q: 可以同时支持 v3 和 v4 吗？

**A**: 不推荐。建议为 v4 创建新的插件版本。

### Q: 迁移后测试失败怎么办？

**A**: 
1. 检查导入是否正确
2. 确认 `ctx` 参数已添加
3. 验证异步函数使用 `await`
4. 查看错误日志获取详细信息

### Q: 如何逐步迁移？

**A**:
1. 先迁移插件结构和装饰器
2. 再迁移业务逻辑
3. 最后更新测试
4. 每个阶段都进行测试

---

## 获取帮助

- 查看完整文档：[docs/](./)
- 提交问题：[GitHub Issues](https://github.com/your-repo/issues)
- 迁移示例：[examples/migration/](./examples/migration/)

---

## 相关文档

- [README](./README.md)
- [Context API 参考](./01_context_api.md)
- [Star 类与生命周期](./04_star_lifecycle.md)
- [错误处理与调试](./06_error_handling.md)
