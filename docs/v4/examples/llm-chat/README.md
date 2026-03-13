# LLM 对话插件示例

本示例演示如何创建一个功能完整的 AI 对话插件。

## 完整代码

### plugin.yaml

```yaml
name: llm_chat_demo
display_name: LLM 对话演示
desc: 一个支持上下文对话的 AI 聊天插件
author: your-name
version: 1.0.0
runtime:
  python: "3.12"
components:
  - class: main:LLMChatPlugin
```

### main.py

```python
"""LLM 对话插件示例。

功能演示：
- 简单对话
- 流式对话
- 带历史记录的对话
- 模型和参数控制
"""

from __future__ import annotations

from astrbot_sdk import Context, MessageEvent, Star, on_command
from astrbot_sdk.clients.llm import ChatMessage


class LLMChatPlugin(Star):
    """LLM 对话插件。"""

    @on_command("chat", description="与 AI 对话")
    async def chat(self, event: MessageEvent, ctx: Context) -> None:
        """简单对话示例。"""
        prompt = event.text.removeprefix("/chat").strip()

        if not prompt:
            await event.reply("用法: /chat <问题>")
            return

        # 调用 LLM
        reply = await ctx.llm.chat(prompt)
        await event.reply(reply)

    @on_command("stream", description="流式对话")
    async def stream_chat(self, event: MessageEvent, ctx: Context) -> None:
        """流式对话示例。"""
        prompt = event.text.removeprefix("/stream").strip()

        if not prompt:
            await event.reply("用法: /stream <问题>")
            return

        # 收集流式响应
        chunks = []
        async for chunk in ctx.llm.stream_chat(prompt):
            chunks.append(chunk)

        # 发送完整响应
        full_response = "".join(chunks)
        await event.reply(full_response)

    @on_command("creative", description="创造性写作")
    async def creative_chat(self, event: MessageEvent, ctx: Context) -> None:
        """使用更高温度的创造性对话。"""
        prompt = event.text.removeprefix("/creative").strip()

        if not prompt:
            await event.reply("用法: /creative <主题>")
            return

        # 使用更高的温度增加创造性
        reply = await ctx.llm.chat(
            prompt,
            temperature=0.9,
            system="你是一个富有创意的作家，善于用生动的语言创作内容"
        )
        await event.reply(reply)

    @on_command("ask", description="带历史的对话")
    async def ask_with_history(self, event: MessageEvent, ctx: Context) -> None:
        """带对话历史的聊天。"""
        prompt = event.text.removeprefix("/ask").strip()

        if not prompt:
            await event.reply("用法: /ask <问题>")
            return

        user_id = event.user_id or "unknown"
        history_key = f"chat_history:{user_id}"

        # 加载历史记录
        history_data = await ctx.db.get(history_key) or []
        history = [
            ChatMessage(role=item["role"], content=item["content"])
            for item in history_data
        ]

        # 调用 LLM
        reply = await ctx.llm.chat(prompt, history=history)

        # 保存历史
        history_data.append({"role": "user", "content": prompt})
        history_data.append({"role": "assistant", "content": reply})

        # 只保留最近 10 轮对话
        if len(history_data) > 20:
            history_data = history_data[-20:]

        await ctx.db.set(history_key, history_data)

        await event.reply(reply)

    @on_command("clear", description="清除对话历史")
    async def clear_history(self, event: MessageEvent, ctx: Context) -> None:
        """清除用户的对话历史。"""
        user_id = event.user_id or "unknown"
        history_key = f"chat_history:{user_id}"

        await ctx.db.delete(history_key)
        await event.reply("对话历史已清除")

    @on_command("raw", description="获取完整响应信息")
    async def raw_chat(self, event: MessageEvent, ctx: Context) -> None:
        """获取 LLM 的完整响应。"""
        prompt = event.text.removeprefix("/raw").strip()

        if not prompt:
            await event.reply("用法: /raw <问题>")
            return

        # 获取完整响应
        response = await ctx.llm.chat_raw(prompt)

        # 构建响应信息
        lines = [
            f"📝 响应: {response.text}",
            f"",
            f"📊 Token 使用:",
            f"  - 输入: {response.usage.get('input_tokens', 'N/A') if response.usage else 'N/A'}",
            f"  - 输出: {response.usage.get('output_tokens', 'N/A') if response.usage else 'N/A'}",
            f"",
            f"🏁 结束原因: {response.finish_reason or 'N/A'}",
        ]

        if response.tool_calls:
            lines.append(f"🔧 工具调用: {len(response.tool_calls)} 个")

        await event.reply("\n".join(lines))
```

### requirements.txt

```
# 无额外依赖
```

## 功能说明

### 1. 简单对话 (`/chat`)

```bash
用户: /chat 你好
机器人: 你好！有什么可以帮助你的？
```

### 2. 流式对话 (`/stream`)

```bash
用户: /stream 讲一个短故事
机器人: [流式输出的故事内容...]
```

### 3. 创造性写作 (`/creative`)

```bash
用户: /creative 写一首关于春天的诗
机器人: [生成的诗歌...]
```

### 4. 带历史的对话 (`/ask`)

```bash
用户: /ask 我叫小明
机器人: 你好小明！

用户: /ask 你记得我的名字吗
机器人: 当然记得，你叫小明！
```

### 5. 完整响应信息 (`/raw`)

```bash
用户: /raw hello
机器人:
📝 响应: Hello! How can I help you today?

📊 Token 使用:
  - 输入: 5
  - 输出: 12

🏁 结束原因: stop
```

## 本地测试

```bash
# 创建插件目录
astrbot-sdk init llm-chat-demo

# 复制上述代码到对应文件

# 本地运行
astrbot-sdk dev --local --plugin-dir llm-chat-demo --interactive

# 在交互模式中测试
> /chat 你好
> /creative 写一首诗
```

## 测试代码

### tests/test_plugin.py

```python
import pytest
from pathlib import Path

from astrbot_sdk.testing import (
    MockContext,
    MockMessageEvent,
    PluginHarness,
    LocalRuntimeConfig,
)


class TestLLMChatPlugin:
    """LLM 对话插件测试。"""

    @pytest.mark.asyncio
    async def test_simple_chat(self):
        """测试简单对话。"""
        from main import LLMChatPlugin

        plugin = LLMChatPlugin()
        ctx = MockContext(plugin_id="test")
        event = MockMessageEvent(text="/chat 你好", context=ctx)

        # 模拟 LLM 响应
        ctx.llm.mock_response("你好！有什么可以帮助你的？")

        await plugin.chat(event, ctx)

        # 验证回复
        assert "你好" in event.replies[0]
        ctx.platform.assert_sent("你好！有什么可以帮助你的？")

    @pytest.mark.asyncio
    async def test_creative_chat(self):
        """测试创造性对话。"""
        from main import LLMChatPlugin

        plugin = LLMChatPlugin()
        ctx = MockContext(plugin_id="test")
        event = MockMessageEvent(text="/creative 写一首诗", context=ctx)

        ctx.llm.mock_response("春风吹绿柳枝头...")

        await plugin.creative_chat(event, ctx)

        assert len(event.replies) == 1

    @pytest.mark.asyncio
    async def test_chat_with_history(self):
        """测试带历史的对话。"""
        from main import LLMChatPlugin

        plugin = LLMChatPlugin()
        ctx = MockContext(plugin_id="test")

        # 第一次对话
        event1 = MockMessageEvent(text="/ask 我叫小明", context=ctx, user_id="user1")
        ctx.llm.mock_response("你好小明！")
        await plugin.ask_with_history(event1, ctx)

        # 验证历史被保存
        history = await ctx.db.get("chat_history:user1")
        assert history is not None
        assert len(history) == 2

        # 第二次对话
        ctx.llm.mock_response("你叫小明")
        event2 = MockMessageEvent(text="/ask 我叫什么", context=ctx, user_id="user1")
        await plugin.ask_with_history(event2, ctx)

    @pytest.mark.asyncio
    async def test_full_harness(self):
        """使用完整 harness 测试。"""
        plugin_dir = Path(__file__).parent.parent

        harness = PluginHarness(
            LocalRuntimeConfig(plugin_dir=plugin_dir)
        )

        async with harness:
            harness.router.enqueue_llm_response("测试响应")
            records = await harness.dispatch_text("chat 测试")

        assert any("测试响应" in (r.text or "") for r in records)
```

## 扩展建议

1. **添加更多系统提示词**：支持用户选择不同的 AI 人设
2. **支持图片输入**：使用 `image_urls` 参数
3. **工具调用**：结合 `tool_calls` 实现功能扩展
4. **多模型支持**：让用户选择不同的模型

## 相关文档

- [LLM 客户端文档](../clients/llm.md)
- [API 参考](../api-reference.md)
- [快速开始](../quickstart.md)
