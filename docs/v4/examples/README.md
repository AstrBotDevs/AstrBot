# 示例插件索引

这里收集了 AstrBot SDK v4 的示例插件，帮助你快速学习各种功能的用法。

## 示例列表

### [LLM 对话插件](llm-chat/)

演示如何使用 LLM 客户端：

- 简单对话
- 流式对话
- 带历史记录的对话
- 模型和参数控制

```python
# 简单对话
reply = await ctx.llm.chat("你好")

# 流式对话
async for chunk in ctx.llm.stream_chat("讲个故事"):
    print(chunk)
```

### [数据库插件](database/)

演示如何使用数据库客户端：

- 用户设置存储
- 计数器
- 待办事项
- 批量操作

```python
# 存储数据
await ctx.db.set("user:1", {"name": "张三"})

# 读取数据
data = await ctx.db.get("user:1")

# 批量操作
await ctx.db.set_many({"a": 1, "b": 2})
```

---

## 更多示例

如果你想贡献更多示例，请提交 PR 到 [astrbot-sdk 仓库](https://github.com/Soulter/astrbot-sdk)。

## 相关文档

- [快速开始](../quickstart.md)
- [API 参考](../api-reference.md)
- [客户端文档](../clients/)
