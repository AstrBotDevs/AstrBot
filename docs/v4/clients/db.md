# 数据库客户端

数据库客户端提供键值存储能力，用于持久化插件数据。

## 概述

```python
from astrbot_sdk import Context

# 通过 Context 访问
ctx.db  # DBClient 实例
```

特点：
- 数据永久存储，除非显式删除
- 支持任意 JSON 数据类型
- 支持前缀查询
- 支持批量读写
- 支持变更订阅

---

## 方法

### get()

获取指定键的值。

```python
async def get(self, key: str) -> Any | None
```

**参数**：
- `key: str` - 数据键名

**返回**：`Any | None` - 存储的值，不存在则返回 `None`

**示例**：

```python
# 获取数据
data = await ctx.db.get("user_settings")
if data:
    print(data["theme"])

# 获取不存在的键
value = await ctx.db.get("nonexistent")  # None
```

---

### set()

设置键值对。

```python
async def set(self, key: str, value: Any) -> None
```

**参数**：
- `key: str` - 数据键名
- `value: Any` - 要存储的 JSON 值

**示例**：

```python
# 存储字典
await ctx.db.set("user_settings", {
    "theme": "dark",
    "lang": "zh",
    "notifications": True
})

# 存储列表
await ctx.db.set("history", ["msg1", "msg2", "msg3"])

# 存储简单值
await ctx.db.set("greeted", True)
await ctx.db.set("count", 42)
```

---

### delete()

删除指定键的数据。

```python
async def delete(self, key: str) -> None
```

**示例**：

```python
await ctx.db.delete("user_settings")
await ctx.db.delete("temp_data")
```

---

### list()

列出匹配前缀的所有键。

```python
async def list(self, prefix: str | None = None) -> list[str]
```

**参数**：
- `prefix: str | None` - 键前缀过滤，`None` 表示列出所有键

**返回**：`list[str]` - 匹配的键名列表

**示例**：

```python
# 列出所有键
all_keys = await ctx.db.list()
# ["settings", "user:1", "user:2", "temp"]

# 列出前缀为 "user:" 的键
user_keys = await ctx.db.list("user:")
# ["user:1", "user:2"]

# 使用前缀组织数据
await ctx.db.set("user:1", {"name": "张三"})
await ctx.db.set("user:2", {"name": "李四"})
await ctx.db.set("config:theme", "dark")

user_keys = await ctx.db.list("user:")    # ["user:1", "user:2"]
config_keys = await ctx.db.list("config:")  # ["config:theme"]
```

---

### get_many()

批量获取多个键的值。

```python
async def get_many(self, keys: Sequence[str]) -> dict[str, Any | None]
```

**参数**：
- `keys: Sequence[str]` - 要读取的键列表

**返回**：`dict[str, Any | None]` - 键值对字典，不存在的键值为 `None`

**示例**：

```python
# 批量读取
values = await ctx.db.get_many(["user:1", "user:2", "user:3"])

for key, value in values.items():
    if value is None:
        print(f"{key} 不存在")
    else:
        print(f"{key}: {value['name']}")

# 处理部分缺失的情况
values = await ctx.db.get_many(["a", "b", "c"])
# {"a": {"data": 1}, "b": None, "c": {"data": 3}}
```

---

### set_many()

批量写入多个键值对。

```python
async def set_many(
    self,
    items: Mapping[str, Any] | Sequence[tuple[str, Any]]
) -> None
```

**参数**：
- `items` - 键值对集合（字典或二元组列表）

**示例**：

```python
# 使用字典
await ctx.db.set_many({
    "user:1": {"name": "张三", "age": 25},
    "user:2": {"name": "李四", "age": 30},
    "user:3": {"name": "王五", "age": 28}
})

# 使用二元组列表
await ctx.db.set_many([
    ("counter:page_views", 100),
    ("counter:unique_visitors", 42)
])
```

---

### watch()

订阅 KV 变更事件（流式）。

```python
def watch(self, prefix: str | None = None) -> AsyncIterator[dict[str, Any]]
```

**参数**：
- `prefix: str | None` - 键前缀过滤，`None` 表示订阅所有键

**返回**：`AsyncIterator[dict]` - 变更事件流

**事件格式**：
```python
{
    "op": "set" | "delete",  # 操作类型
    "key": str,               # 变更的键
    "value": Any | None       # 新值（delete 时为 None）
}
```

**示例**：

```python
# 订阅所有变更
async for event in ctx.db.watch():
    if event["op"] == "set":
        print(f"设置 {event['key']} = {event['value']}")
    else:
        print(f"删除 {event['key']}")

# 只订阅特定前缀
async for event in ctx.db.watch("user:"):
    print(f"用户数据变更: {event['key']}")
```

---

## 使用场景

### 场景 1：用户设置存储

```python
@on_command("settheme")
async def set_theme(self, event: MessageEvent, ctx: Context):
    theme = event.text.split()[-1]
    user_id = event.user_id

    # 读取现有设置
    settings = await ctx.db.get(f"settings:{user_id}") or {}
    settings["theme"] = theme

    # 保存设置
    await ctx.db.set(f"settings:{user_id}", settings)
    await event.reply(f"已将主题设置为 {theme}")

@on_command("mytheme")
async def get_theme(self, event: MessageEvent, ctx: Context):
    settings = await ctx.db.get(f"settings:{event.user_id}") or {}
    theme = settings.get("theme", "默认")
    await event.reply(f"当前主题: {theme}")
```

### 场景 2：计数器

```python
@on_command("count")
async def count(self, event: MessageEvent, ctx: Context):
    key = f"counter:{event.user_id}"

    # 读取并增加计数
    count = await ctx.db.get(key) or 0
    count += 1
    await ctx.db.set(key, count)

    await event.reply(f"您已使用此命令 {count} 次")
```

### 场景 3：批量用户管理

```python
@on_command("listusers")
async def list_users(self, event: MessageEvent, ctx: Context):
    # 列出所有用户键
    user_keys = await ctx.db.list("user:")

    if not user_keys:
        await event.reply("暂无用户数据")
        return

    # 批量获取用户数据
    users = await ctx.db.get_many(user_keys)

    lines = ["用户列表:"]
    for key, data in users.items():
        if data:
            lines.append(f"- {data.get('name', '未知')}")

    await event.reply("\n".join(lines))
```

### 场景 4：缓存层

```python
async def get_user_info(self, user_id: str, ctx: Context):
    # 先查缓存
    cache_key = f"cache:user:{user_id}"
    cached = await ctx.db.get(cache_key)
    if cached:
        return cached

    # 模拟从外部获取数据
    data = await self._fetch_from_api(user_id)

    # 写入缓存
    await ctx.db.set(cache_key, data)
    return data
```

---

## 最佳实践

### 1. 使用前缀组织数据

```python
# 推荐：使用有意义的键前缀
"settings:{user_id}"    # 用户设置
"cache:{type}:{id}"     # 缓存数据
"counter:{name}"        # 计数器
"temp:{session_id}"     # 临时数据

# 避免：无组织的键名
"data"
"info"
"temp"
```

### 2. 处理空值

```python
# 使用 or 提供默认值
data = await ctx.db.get("key") or {}
count = await ctx.db.get("counter") or 0

# 或显式检查
data = await ctx.db.get("key")
if data is None:
    data = self._get_default()
```

### 3. 批量操作减少调用

```python
# 不好：多次单独调用
for key, value in items:
    await ctx.db.set(key, value)

# 好：批量写入
await ctx.db.set_many(items)
```

---

## 相关文档

- [API 参考](../api-reference.md)
- [Memory 客户端](memory.md) - 语义搜索存储
- [示例：数据库插件](../examples/database/)
