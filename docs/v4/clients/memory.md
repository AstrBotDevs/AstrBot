# 记忆客户端

记忆客户端提供 AI 记忆存储能力，支持语义搜索。

## 概述

```python
from astrbot_sdk import Context

# 通过 Context 访问
ctx.memory  # MemoryClient 实例
```

### Memory vs DB 的区别

| 特性 | DBClient | MemoryClient |
|------|----------|--------------|
| 存储方式 | 键值存储 | 语义向量存储 |
| 检索方式 | 精确匹配 | 语义搜索 |
| 适用场景 | 配置、计数器、简单数据 | AI 上下文、用户偏好、对话记忆 |

**选择建议**：
- 需要精确键查找 → 使用 `db`
- 需要语义搜索 → 使用 `memory`

---

## 方法

### save()

保存记忆项。

```python
async def save(
    self,
    key: str,
    value: dict[str, Any] | None = None,
    **extra: Any,
) -> None
```

**参数**：
- `key: str` - 记忆项的唯一标识键
- `value: dict | None` - 要存储的数据字典
- `**extra: Any` - 额外的键值对

**示例**：

```python
# 保存用户偏好
await ctx.memory.save("user_pref", {
    "theme": "dark",
    "language": "zh",
    "interests": ["游戏", "音乐"]
})

# 使用关键字参数
await ctx.memory.save(
    "note:1",
    None,
    content="重要笔记",
    tags=["work", "urgent"],
    created_at="2024-01-01"
)

# 保存对话摘要
await ctx.memory.save("conversation:session_123", {
    "summary": "用户询问了天气，推荐了晴天出行",
    "topics": ["天气", "出行"],
    "sentiment": "positive"
})
```

---

### get()

精确获取单个记忆项。

```python
async def get(self, key: str) -> dict[str, Any] | None
```

**参数**：
- `key: str` - 记忆项的唯一键

**返回**：`dict | None` - 记忆内容，不存在则返回 `None`

**示例**：

```python
# 获取用户偏好
pref = await ctx.memory.get("user_pref")
if pref:
    print(f"用户偏好主题: {pref.get('theme')}")
    print(f"用户兴趣: {pref.get('interests')}")
```

---

### search()

语义搜索记忆项。

```python
async def search(self, query: str) -> list[dict[str, Any]]
```

**参数**：
- `query: str` - 搜索查询文本

**返回**：`list[dict]` - 匹配的记忆项列表，按相关度排序

**示例**：

```python
# 搜索用户偏好相关记忆
results = await ctx.memory.search("用户喜欢什么颜色")
for item in results:
    print(f"键: {item['key']}")
    print(f"内容: {item['content']}")
    print(f"相关度: {item.get('score', 0)}")
    print("---")

# 搜索对话历史
results = await ctx.memory.search("之前讨论过天气吗")
if results:
    await event.reply("是的，我们之前讨论过天气话题")
```

---

### delete()

删除记忆项。

```python
async def delete(self, key: str) -> None
```

**示例**：

```python
# 删除过期记忆
await ctx.memory.delete("old_note")

# 删除用户数据
await ctx.memory.delete(f"user_data:{user_id}")
```

---

## 使用场景

### 场景 1：用户偏好记忆

```python
@on_command("remember")
async def remember_preference(self, event: MessageEvent, ctx: Context):
    """记住用户偏好"""
    preference = event.text.removeprefix("/remember").strip()

    # 保存偏好
    key = f"pref:{event.user_id}"
    prefs = await ctx.memory.get(key) or {"items": []}
    prefs["items"].append(preference)
    await ctx.memory.save(key, prefs)

    await event.reply(f"已记住：{preference}")

@on_command("what_do_i_like")
async def recall_preference(self, event: MessageEvent, ctx: Context):
    """回忆用户偏好"""
    query = "用户偏好 喜欢"
    results = await ctx.memory.search(query)

    if results:
        lines = ["您之前告诉过我："]
        for item in results[:3]:
            lines.append(f"- {item.get('content', '未知')}")
        await event.reply("\n".join(lines))
    else:
        await event.reply("我还没有记住您的偏好")
```

### 场景 2：对话上下文记忆

```python
@on_message(keywords=["我"])
async def track_context(self, event: MessageEvent, ctx: Context):
    """跟踪用户提到的个人信息"""
    # 保存到记忆
    await ctx.memory.save(
        f"user_info:{event.user_id}:{event.session_id}",
        {
            "message": event.text,
            "timestamp": "2024-01-01",
            "type": "personal_info"
        }
    )

@on_command("recall")
async def recall_context(self, event: MessageEvent, ctx: Context):
    """回忆对话内容"""
    query = event.text.removeprefix("/recall").strip() or "用户说过什么"

    results = await ctx.memory.search(query)
    if results:
        await event.reply(f"您之前提到：{results[0].get('message', '未知')}")
    else:
        await event.reply("我没有找到相关记忆")
```

### 场景 3：智能推荐

```python
@on_command("recommend")
async def recommend(self, event: MessageEvent, ctx: Context):
    """基于记忆的智能推荐"""
    # 搜索用户兴趣相关的记忆
    interests = await ctx.memory.search(f"{event.user_id} 兴趣 爱好")

    if not interests:
        await event.reply("告诉我您的兴趣，我可以给您推荐内容！")
        return

    # 基于兴趣生成推荐
    interest_text = ", ".join(
        item.get("content", "")
        for item in interests[:3]
    )

    prompt = f"用户喜欢 {interest_text}，推荐一些相关内容"
    recommendation = await ctx.llm.chat(prompt)
    await event.reply(recommendation)
```

---

## 最佳实践

### 1. 使用结构化键名

```python
# 推荐：有层次结构的键名
"user:{user_id}:preferences"
"user:{user_id}:history:{session_id}"
"conversation:{session_id}:summary"

# 避免：无组织的键名
"data"
"info"
"temp"
```

### 2. 为搜索优化内容

```python
# 好：包含可搜索的描述性文本
await ctx.memory.save("user_pref", {
    "description": "用户喜欢玩游戏和听音乐",
    "interests": ["游戏", "音乐"],
    "level": "advanced"
})

# 不好：过于抽象，难以语义搜索
await ctx.memory.save("user_pref", {
    "a": ["x", "y"],
    "b": 2
})
```

### 3. 结合 DB 和 Memory

```python
# DB：存储精确配置
await ctx.db.set("config:theme", "dark")

# Memory：存储语义可搜索的内容
await ctx.memory.save("user_interests", {
    "description": "用户对游戏开发感兴趣",
    "tags": ["游戏", "开发", "Unity"]
})
```

---

## 注意事项

1. **值必须是字典**：`memory.save()` 的 value 参数必须是 `dict` 类型

```python
# 正确
await ctx.memory.save("key", {"value": 123})

# 错误
await ctx.memory.save("key", 123)  # TypeError
```

2. **语义搜索依赖宿主实现**：搜索质量取决于宿主的向量存储配置

---

## 相关文档

- [API 参考](../api-reference.md)
- [DB 客户端](db.md) - 精确键值存储
- [LLM 客户端](llm.md) - 结合 AI 能力
