# 平台客户端

平台客户端提供向聊天平台发送消息和获取信息的能力。

## 概述

```python
from astrbot_sdk import Context

# 通过 Context 访问
ctx.platform  # PlatformClient 实例
```

支持的平台能力：
- `send()` - 发送文本消息
- `send_image()` - 发送图片
- `send_chain()` - 发送富消息链
- `get_members()` - 获取群成员

---

## 方法

### send()

发送文本消息。

```python
async def send(
    self,
    session: str | SessionRef,
    text: str
) -> dict[str, Any]
```

**参数**：
- `session: str | SessionRef` - 目标会话标识
- `text: str` - 要发送的文本内容

**返回**：`dict` - 发送结果，可能包含消息 ID 等

**示例**：

```python
# 发送到当前会话
await ctx.platform.send(event.session_id, "收到您的消息！")

# 发送到指定用户（需要知道 session_id）
await ctx.platform.send("qq:bot:123456", "私信消息")

# 使用 event.target
if event.target:
    await ctx.platform.send(event.target, "回复到引用的消息来源")
```

---

### send_image()

发送图片消息。

```python
async def send_image(
    self,
    session: str | SessionRef,
    image_url: str
) -> dict[str, Any]
```

**参数**：
- `session: str | SessionRef` - 目标会话标识
- `image_url: str` - 图片 URL 或本地文件路径

**返回**：`dict` - 发送结果

**示例**：

```python
# 发送网络图片
await ctx.platform.send_image(
    event.session_id,
    "https://example.com/image.png"
)

# 发送本地图片
await ctx.platform.send_image(
    event.session_id,
    "/path/to/local/image.jpg"
)
```

---

### send_chain()

发送富消息链。

```python
async def send_chain(
    self,
    session: str | SessionRef,
    chain: list[dict[str, Any]]
) -> dict[str, Any]
```

**参数**：
- `session: str | SessionRef` - 目标会话标识
- `chain: list[dict]` - 消息组件数组

**返回**：`dict` - 发送结果

**消息组件格式**：

```python
# 纯文本
{"type": "Plain", "text": "文本内容"}

# 图片
{"type": "Image", "file": "https://example.com/img.png"}

# @某人
{"type": "At", "user_id": "123456"}

# 表情
{"type": "Face", "id": "123"}
```

**示例**：

```python
# 发送混合内容
await ctx.platform.send_chain(event.session_id, [
    {"type": "Plain", "text": "你好！"},
    {"type": "Image", "file": "https://example.com/welcome.png"},
    {"type": "Plain", "text": "欢迎加入群组"}
])

# @用户并发送消息
await ctx.platform.send_chain(event.session_id, [
    {"type": "At", "user_id": event.user_id},
    {"type": "Plain", "text": " 这是一条通知消息"}
])
```

---

### get_members()

获取群组成员列表。

```python
async def get_members(
    self,
    session: str | SessionRef
) -> list[dict[str, Any]]
```

**参数**：
- `session: str | SessionRef` - 群组会话标识

**返回**：`list[dict]` - 成员信息列表

**成员信息格式**：
```python
{
    "user_id": str,      # 用户 ID
    "nickname": str,     # 昵称
    "role": str,         # 角色: "owner", "admin", "member"
}
```

**示例**：

```python
@on_command("members")
async def list_members(self, event: MessageEvent, ctx: Context):
    # 仅群聊有效
    if not event.group_id:
        await event.reply("此命令仅在群聊中可用")
        return

    members = await ctx.platform.get_members(event.session_id)

    lines = [f"群成员 ({len(members)} 人):"]
    for member in members[:10]:  # 只显示前 10 个
        role = f"[{member.get('role', 'member')}]"
        name = member.get('nickname', member.get('user_id', '未知'))
        lines.append(f"  {role} {name}")

    if len(members) > 10:
        lines.append(f"  ... 还有 {len(members) - 10} 人")

    await event.reply("\n".join(lines))
```

---

## SessionRef

结构化会话引用，用于精确指定消息目标。

```python
from astrbot_sdk.protocol.descriptors import SessionRef

ref = SessionRef(
    platform="qq",        # 平台名称
    instance="bot1",      # 实例标识
    user_id="123456",     # 用户 ID
    group_id="654321",    # 群组 ID（可选）
)
```

---

## 使用场景

### 场景 1：自动回复

```python
@on_message(keywords=["hello", "hi"])
async def auto_reply(self, event: MessageEvent, ctx: Context):
    await ctx.platform.send(event.session_id, "你好！我是机器人")
```

### 场景 2：命令响应

```python
@on_command("status")
async def status(self, event: MessageEvent, ctx: Context):
    # 发送状态信息
    await ctx.platform.send(event.session_id, "系统状态：正常运行")

    # 发送状态图片
    await ctx.platform.send_image(
        event.session_id,
        "https://example.com/status.png"
    )
```

### 场景 3：群管理

```python
@on_command("admin")
@require_admin
async def admin_cmd(self, event: MessageEvent, ctx: Context):
    if not event.group_id:
        await event.reply("此命令仅在群聊中可用")
        return

    # 获取成员列表
    members = await ctx.platform.get_members(event.session_id)

    # 统计
    admins = [m for m in members if m.get('role') in ('owner', 'admin')]
    await event.reply(f"群管理员数量: {len(admins)}")
```

### 场景 4：富消息回复

```python
@on_command("card")
async def send_card(self, event: MessageEvent, ctx: Context):
    # 发送复杂的富消息
    await ctx.platform.send_chain(event.session_id, [
        {"type": "Plain", "text": "📊 统计报告\n\n"},
        {"type": "Plain", "text": "用户数: 1000\n"},
        {"type": "Plain", "text": "消息数: 50000\n"},
        {"type": "Image", "file": "https://example.com/chart.png"},
        {"type": "Plain", "text": "\n— 来自 AstrBot"},
    ])
```

---

## 注意事项

### 1. 私聊 vs 群聊

```python
if event.group_id:
    # 群聊消息
    await ctx.platform.send(event.session_id, "群消息")
else:
    # 私聊消息
    await ctx.platform.send(event.session_id, "私聊消息")
```

### 2. 发送频率

避免频繁发送消息，部分平台有频率限制：

```python
import asyncio

for msg in messages:
    await ctx.platform.send(event.session_id, msg)
    await asyncio.sleep(1)  # 间隔 1 秒
```

### 3. 错误处理

```python
from astrbot_sdk import AstrBotError

try:
    await ctx.platform.send(event.session_id, "消息")
except AstrBotError as e:
    if e.code == "permission_denied":
        print("没有发送权限")
    else:
        print(f"发送失败: {e.message}")
```

---

## 相关文档

- [API 参考](../api-reference.md)
- [MessageEvent 消息事件](../api-reference.md#messageevent-消息事件)
- [快速开始](../quickstart.md)
