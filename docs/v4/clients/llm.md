# LLM 客户端

LLM 客户端提供与大语言模型交互的能力。

## 概述

```python
from astrbot_sdk import Context

# 通过 Context 访问
ctx.llm  # LLMClient 实例
```

LLM 客户端支持三种调用模式：
- `chat()` - 简单对话，返回文本
- `chat_raw()` - 完整响应，包含 usage 和 tool_calls
- `stream_chat()` - 流式对话，逐块返回

---

## 方法

### chat()

发送聊天请求并返回文本响应。

```python
async def chat(
    self,
    prompt: str,
    *,
    system: str | None = None,
    history: Sequence[ChatHistoryItem] | None = None,
    model: str | None = None,
    temperature: float | None = None,
    **kwargs: Any,
) -> str
```

**参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `prompt` | `str` | 用户输入的提示文本 |
| `system` | `str \| None` | 系统提示词 |
| `history` | `list \| None` | 对话历史 |
| `model` | `str \| None` | 指定模型名称 |
| `temperature` | `float \| None` | 生成温度 (0-1) |
| `**kwargs` | `Any` | 额外参数 |

**返回**：`str` - 生成的文本内容

**示例**：

```python
# 简单对话
reply = await ctx.llm.chat("你好")
print(reply)  # "你好！有什么可以帮助你的？"

# 带系统提示词
reply = await ctx.llm.chat(
    "介绍一下自己",
    system="你是一个友好的助手，用简洁的语言回答"
)

# 带历史对话
history = [
    ChatMessage(role="user", content="我叫小明"),
    ChatMessage(role="assistant", content="你好小明！"),
]
reply = await ctx.llm.chat("你记得我的名字吗？", history=history)

# 控制生成温度
reply = await ctx.llm.chat("写一首诗", temperature=0.8)
```

---

### chat_raw()

发送聊天请求并返回完整响应。

```python
async def chat_raw(
    self,
    prompt: str,
    **kwargs: Any,
) -> LLMResponse
```

**返回**：`LLMResponse` - 完整响应对象

```python
class LLMResponse:
    text: str                      # 生成的文本
    usage: dict | None             # Token 使用统计
    finish_reason: str | None      # 结束原因
    tool_calls: list[dict]         # 工具调用列表
```

**示例**：

```python
response = await ctx.llm.chat_raw(
    "写一首关于春天的诗",
    temperature=0.7
)

print(f"生成文本: {response.text}")
print(f"Token 使用: {response.usage}")
# {'input_tokens': 15, 'output_tokens': 120}

print(f"结束原因: {response.finish_reason}")
# "stop"

if response.tool_calls:
    for tool in response.tool_calls:
        print(f"工具调用: {tool['name']}")
```

---

### stream_chat()

流式聊天，逐块返回响应文本。

```python
async def stream_chat(
    self,
    prompt: str,
    *,
    system: str | None = None,
    history: Sequence[ChatHistoryItem] | None = None,
    model: str | None = None,
    temperature: float | None = None,
    **kwargs: Any,
) -> AsyncGenerator[str, None]
```

**返回**：`AsyncGenerator[str, None]` - 文本块迭代器

**示例**：

```python
# 实时输出生成内容
async for chunk in ctx.llm.stream_chat("讲一个短故事"):
    print(chunk, end="", flush=True)
print()  # 换行

# 收集完整响应
chunks = []
async for chunk in ctx.llm.stream_chat("写一首诗"):
    chunks.append(chunk)
full_text = "".join(chunks)
```

---

## ChatMessage

对话消息模型，用于构建历史。

```python
from astrbot_sdk.clients.llm import ChatMessage

message = ChatMessage(
    role="user",      # "user", "assistant", "system"
    content="消息内容"
)
```

**示例**：

```python
from astrbot_sdk.clients.llm import ChatMessage

history = [
    ChatMessage(role="user", content="你好"),
    ChatMessage(role="assistant", content="你好！"),
    ChatMessage(role="user", content="今天天气怎么样？"),
]

reply = await ctx.llm.chat("继续聊", history=history)
```

---

## 使用场景

### 场景 1：智能问答

```python
@on_command("ask")
async def ask(self, event: MessageEvent, ctx: Context):
    question = event.text.removeprefix("/ask").strip()
    if not question:
        await event.reply("请输入问题，如：/ask 什么是人工智能？")
        return

    reply = await ctx.llm.chat(question)
    await event.reply(reply)
```

### 场景 2：流式回复

```python
@on_command("chat")
async def chat(self, event: MessageEvent, ctx: Context):
    prompt = event.text.removeprefix("/chat").strip()

    # 流式回复，实时显示
    reply_text = ""
    async for chunk in ctx.llm.stream_chat(prompt):
        reply_text += chunk
        # 可以选择实时更新消息或最后一次性发送
        pass

    await event.reply(reply_text)
```

### 场景 3：带上下文的对话

```python
@on_command("continue")
async def continue_chat(self, event: MessageEvent, ctx: Context):
    # 从数据库加载历史
    history = await ctx.db.get("chat_history") or []

    # 添加当前消息
    prompt = event.text.removeprefix("/continue").strip()
    reply = await ctx.llm.chat(prompt, history=history)

    # 保存更新后的历史
    history.append({"role": "user", "content": prompt})
    history.append({"role": "assistant", "content": reply})
    await ctx.db.set("chat_history", history[-10:])  # 保留最近 10 条

    await event.reply(reply)
```

### 场景 4：指定模型和参数

```python
@on_command("creative")
async def creative(self, event: MessageEvent, ctx: Context):
    prompt = event.text.removeprefix("/creative").strip()

    # 使用更高的温度增加创造性
    reply = await ctx.llm.chat(
        prompt,
        temperature=0.9,
        system="你是一个富有创意的作家"
    )
    await event.reply(reply)
```

---

## 注意事项

1. **Token 限制**：注意对话历史不要过长，可能会超出模型上下文限制
2. **错误处理**：LLM 调用可能失败，建议添加错误处理
3. **超时**：长文本生成可能需要较长时间

```python
from astrbot_sdk import AstrBotError

try:
    reply = await ctx.llm.chat("hello")
except AstrBotError as e:
    if e.code == "llm_not_configured":
        await event.reply("LLM 未配置，请联系管理员")
    else:
        await event.reply(f"LLM 调用失败: {e.message}")
```

---

## 相关文档

- [API 参考](../api-reference.md)
- [快速开始](../quickstart.md)
- [示例：LLM 对话插件](../examples/llm-chat/)
