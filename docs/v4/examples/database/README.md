# 数据库插件示例

本示例演示如何使用数据库客户端存储和管理插件数据。

## 完整代码

### plugin.yaml

```yaml
name: database_demo
display_name: 数据库演示
desc: 演示数据库客户端的各种用法
author: your-name
version: 1.0.0
runtime:
  python: "3.12"
components:
  - class: main:DatabasePlugin
```

### main.py

```python
"""数据库插件示例。

功能演示：
- 用户设置存储
- 计数器
- 批量操作
- 数据查询
"""

from __future__ import annotations

from astrbot_sdk import Context, MessageEvent, Star, on_command


class DatabasePlugin(Star):
    """数据库演示插件。"""

    # ==================== 用户设置 ====================

    @on_command("set", description="设置用户配置")
    async def set_config(self, event: MessageEvent, ctx: Context) -> None:
        """设置用户配置项。"""
        args = event.text.removeprefix("/set").strip().split(maxsplit=1)

        if len(args) < 2:
            await event.reply("用法: /set <键名> <值>")
            return

        key, value = args
        user_id = event.user_id or "unknown"

        # 获取现有配置
        config_key = f"user_config:{user_id}"
        config = await ctx.db.get(config_key) or {}

        # 更新配置
        config[key] = value
        await ctx.db.set(config_key, config)

        await event.reply(f"已设置 {key} = {value}")

    @on_command("get", description="获取用户配置")
    async def get_config(self, event: MessageEvent, ctx: Context) -> None:
        """获取用户配置项。"""
        key = event.text.removeprefix("/get").strip()

        if not key:
            await event.reply("用法: /get <键名>")
            return

        user_id = event.user_id or "unknown"
        config_key = f"user_config:{user_id}"

        config = await ctx.db.get(config_key) or {}

        if key in config:
            await event.reply(f"{key} = {config[key]}")
        else:
            await event.reply(f"未找到配置项: {key}")

    @on_command("config", description="显示所有配置")
    async def show_config(self, event: MessageEvent, ctx: Context) -> None:
        """显示用户的所有配置。"""
        user_id = event.user_id or "unknown"
        config_key = f"user_config:{user_id}"

        config = await ctx.db.get(config_key)

        if not config:
            await event.reply("您还没有设置任何配置")
            return

        lines = ["📋 您的配置:"]
        for key, value in config.items():
            lines.append(f"  {key} = {value}")

        await event.reply("\n".join(lines))

    # ==================== 计数器 ====================

    @on_command("count", description="计数器 +1")
    async def increment_counter(self, event: MessageEvent, ctx: Context) -> None:
        """计数器增加。"""
        user_id = event.user_id or "unknown"
        key = f"counter:{user_id}"

        # 读取并增加
        count = await ctx.db.get(key) or 0
        count += 1
        await ctx.db.set(key, count)

        await event.reply(f"计数器: {count}")

    @on_command("reset", description="重置计数器")
    async def reset_counter(self, event: MessageEvent, ctx: Context) -> None:
        """重置计数器。"""
        user_id = event.user_id or "unknown"
        key = f"counter:{user_id}"

        await ctx.db.delete(key)
        await event.reply("计数器已重置")

    # ==================== 待办事项 ====================

    @on_command("todo", description="添加待办事项")
    async def add_todo(self, event: MessageEvent, ctx: Context) -> None:
        """添加待办事项。"""
        content = event.text.removeprefix("/todo").strip()

        if not content:
            await event.reply("用法: /todo <事项内容>")
            return

        user_id = event.user_id or "unknown"

        # 获取现有待办列表
        todo_key = f"todos:{user_id}"
        todos = await ctx.db.get(todo_key) or []

        # 添加新事项
        todos.append({
            "id": len(todos) + 1,
            "content": content,
            "done": False
        })
        await ctx.db.set(todo_key, todos)

        await event.reply(f"已添加待办事项 #{len(todos)}")

    @on_command("todos", description="显示待办列表")
    async def show_todos(self, event: MessageEvent, ctx: Context) -> None:
        """显示待办列表。"""
        user_id = event.user_id or "unknown"
        todo_key = f"todos:{user_id}"

        todos = await ctx.db.get(todo_key) or []

        if not todos:
            await event.reply("待办列表为空")
            return

        lines = ["📝 待办事项:"]
        for todo in todos:
            status = "✅" if todo.get("done") else "⬜"
            lines.append(f"  {status} #{todo['id']} {todo['content']}")

        await event.reply("\n".join(lines))

    @on_command("done", description="标记待办完成")
    async def complete_todo(self, event: MessageEvent, ctx: Context) -> None:
        """标记待办事项完成。"""
        arg = event.text.removeprefix("/done").strip()

        if not arg:
            await event.reply("用法: /done <序号>")
            return

        try:
            todo_id = int(arg)
        except ValueError:
            await event.reply("序号必须是数字")
            return

        user_id = event.user_id or "unknown"
        todo_key = f"todos:{user_id}"

        todos = await ctx.db.get(todo_key) or []

        for todo in todos:
            if todo.get("id") == todo_id:
                todo["done"] = True
                await ctx.db.set(todo_key, todos)
                await event.reply(f"已完成 #{todo_id}")
                return

        await event.reply(f"未找到待办事项 #{todo_id}")

    # ==================== 批量操作 ====================

    @on_command("batch_set", description="批量设置测试数据")
    async def batch_set(self, event: MessageEvent, ctx: Context) -> None:
        """批量写入数据演示。"""
        user_id = event.user_id or "unknown"

        # 批量写入
        items = {
            f"test:{user_id}:a": {"value": 1, "desc": "第一项"},
            f"test:{user_id}:b": {"value": 2, "desc": "第二项"},
            f"test:{user_id}:c": {"value": 3, "desc": "第三项"},
        }

        await ctx.db.set_many(items)
        await event.reply(f"已批量写入 {len(items)} 条数据")

    @on_command("batch_get", description="批量读取测试数据")
    async def batch_get(self, event: MessageEvent, ctx: Context) -> None:
        """批量读取数据演示。"""
        user_id = event.user_id or "unknown"

        # 批量读取
        keys = [f"test:{user_id}:a", f"test:{user_id}:b", f"test:{user_id}:c"]
        values = await ctx.db.get_many(keys)

        lines = ["📦 批量读取结果:"]
        for key, value in values.items():
            if value:
                lines.append(f"  {key}: {value.get('value')} - {value.get('desc')}")
            else:
                lines.append(f"  {key}: 不存在")

        await event.reply("\n".join(lines))

    # ==================== 数据管理 ====================

    @on_command("keys", description="列出所有键")
    async def list_keys(self, event: MessageEvent, ctx: Context) -> None:
        """列出用户的所有数据键。"""
        user_id = event.user_id or "unknown"
        prefix = f"{user_id}:"

        keys = await ctx.db.list(prefix)

        if not keys:
            await event.reply("没有找到数据")
            return

        lines = [f"🔑 数据键 ({len(keys)} 个):"]
        for key in keys[:10]:
            lines.append(f"  {key}")

        if len(keys) > 10:
            lines.append(f"  ... 还有 {len(keys) - 10} 个")

        await event.reply("\n".join(lines))

    @on_command("clear", description="清除所有数据")
    async def clear_all(self, event: MessageEvent, ctx: Context) -> None:
        """清除用户的所有数据。"""
        user_id = event.user_id or "unknown"

        # 列出并删除所有键
        keys = await ctx.db.list(f"{user_id}:")

        for key in keys:
            await ctx.db.delete(key)

        await event.reply(f"已清除 {len(keys)} 条数据")
```

### requirements.txt

```
# 无额外依赖
```

## 功能说明

### 用户设置

```bash
# 设置配置
用户: /set theme dark
机器人: 已设置 theme = dark

用户: /set lang zh
机器人: 已设置 lang = zh

# 获取配置
用户: /get theme
机器人: theme = dark

# 显示所有配置
用户: /config
机器人:
📋 您的配置:
  theme = dark
  lang = zh
```

### 计数器

```bash
用户: /count
机器人: 计数器: 1

用户: /count
机器人: 计数器: 2

用户: /reset
机器人: 计数器已重置
```

### 待办事项

```bash
用户: /todo 买菜
机器人: 已添加待办事项 #1

用户: /todo 写作业
机器人: 已添加待办事项 #2

用户: /todos
机器人:
📝 待办事项:
  ⬜ #1 买菜
  ⬜ #2 写作业

用户: /done 1
机器人: 已完成 #1

用户: /todos
机器人:
📝 待办事项:
  ✅ #1 买菜
  ⬜ #2 写作业
```

### 批量操作

```bash
用户: /batch_set
机器人: 已批量写入 3 条数据

用户: /batch_get
机器人:
📦 批量读取结果:
  test:user1:a: 1 - 第一项
  test:user1:b: 2 - 第二项
  test:user1:c: 3 - 第三项
```

## 测试代码

### tests/test_plugin.py

```python
import pytest
from astrbot_sdk.testing import MockContext, MockMessageEvent


class TestDatabasePlugin:
    """数据库插件测试。"""

    @pytest.mark.asyncio
    async def test_set_and_get_config(self):
        """测试配置存取。"""
        from main import DatabasePlugin

        plugin = DatabasePlugin()
        ctx = MockContext(plugin_id="test")

        # 设置配置
        event = MockMessageEvent(text="/set theme dark", context=ctx, user_id="user1")
        await plugin.set_config(event, ctx)

        # 获取配置
        event2 = MockMessageEvent(text="/get theme", context=ctx, user_id="user1")
        await plugin.get_config(event2, ctx)

        assert "dark" in event2.replies[-1]

    @pytest.mark.asyncio
    async def test_counter(self):
        """测试计数器。"""
        from main import DatabasePlugin

        plugin = DatabasePlugin()
        ctx = MockContext(plugin_id="test")

        # 第一次计数
        event1 = MockMessageEvent(text="/count", context=ctx, user_id="user1")
        await plugin.increment_counter(event1, ctx)
        assert "1" in event1.replies[-1]

        # 第二次计数
        event2 = MockMessageEvent(text="/count", context=ctx, user_id="user1")
        await plugin.increment_counter(event2, ctx)
        assert "2" in event2.replies[-1]

    @pytest.mark.asyncio
    async def test_todos(self):
        """测试待办事项。"""
        from main import DatabasePlugin

        plugin = DatabasePlugin()
        ctx = MockContext(plugin_id="test")

        # 添加待办
        event1 = MockMessageEvent(text="/todo 测试事项", context=ctx, user_id="user1")
        await plugin.add_todo(event1, ctx)

        # 显示待办
        event2 = MockMessageEvent(text="/todos", context=ctx, user_id="user1")
        await plugin.show_todos(event2, ctx)

        assert "测试事项" in event2.replies[-1]

        # 完成待办
        event3 = MockMessageEvent(text="/done 1", context=ctx, user_id="user1")
        await plugin.complete_todo(event3, ctx)

    @pytest.mark.asyncio
    async def test_batch_operations(self):
        """测试批量操作。"""
        from main import DatabasePlugin

        plugin = DatabasePlugin()
        ctx = MockContext(plugin_id="test")

        # 批量写入
        event1 = MockMessageEvent(text="/batch_set", context=ctx, user_id="user1")
        await plugin.batch_set(event1, ctx)
        assert "3" in event1.replies[-1]

        # 验证数据
        assert await ctx.router.db.get("test:user1:a") is not None
        assert await ctx.router.db.get("test:user1:b") is not None
        assert await ctx.router.db.get("test:user1:c") is not None
```

## 最佳实践

### 1. 使用有意义的键前缀

```python
# 推荐
"user_config:{user_id}"      # 用户配置
"todos:{user_id}"            # 待办事项
"counter:{user_id}"          # 计数器
"cache:{type}:{id}"          # 缓存数据
"temp:{session_id}"          # 临时数据
```

### 2. 处理空值

```python
# 使用 or 提供默认值
config = await ctx.db.get(key) or {}
count = await ctx.db.get(key) or 0
todos = await ctx.db.get(key) or []
```

### 3. 限制数据大小

```python
# 只保留最近 N 条记录
history = history[-100:]  # 最多 100 条
await ctx.db.set(key, history)
```

## 相关文档

- [DB 客户端文档](../clients/db.md)
- [API 参考](../api-reference.md)
- [快速开始](../quickstart.md)
