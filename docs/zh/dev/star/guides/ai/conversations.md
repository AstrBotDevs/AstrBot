# 会话与对话

会话由消息来源 `event.unified_msg_origin`（UMO）标识；对话由 `cid` 标识，用来保存一组模型消息历史。同一会话可以创建和切换不同的对话。

需要等待用户的后续消息时，参见[会话控制器](../session-control.md)。本页介绍对话历史的读取与写入。

## 对话管理器

通过 `self.context.conversations` 创建、读取、更新、切换和删除对话。`Conversation.history` 是包含模型消息的 JSON 字符串。

`_no_save` 会将消息或内容片段排除在后续模型上下文之外，但不会阻止原文保存。

> [!TIP]
> 从 v4.30.0 开始，对话管理接口有以下调整：
>
> - `self.context.conversation_manager` 保留为 `self.context.conversations` 的兼容别名。
> - 将 `event.conversation_events` 和 `get_conversation_events()` 替换为 `append_message()` 或 `append_plugin_event()`。
> - 将 `update_conversation_title()` 和 `update_conversation_persona_id()` 替换为 `update_conversation(..., title=...)` 和 `update_conversation(..., persona_id=...)`。
> - 平台历史关联中的 `llm_checkpoint_id` 改用 `turn_id` 和 `context_event_id`。

### 追加模型消息 `append_message`

```py
conversations = self.context.conversations
message_id = await conversations.append_message(
    "用户偏好简洁的回答。",
    cid=target_cid,
)
```

`content` 接受文本或 AstrBot 的 `ContentPart` 对象列表：

```py
from astrbot.core.agent.message import ImageURLPart, TextPart

await conversations.append_message(
    [
        TextPart(text="请描述这张图片。"),
        ImageURLPart(
            image_url=ImageURLPart.ImageURL(url="https://example.com/image.png")
        ),
    ],
    cid=target_cid,
)
```

消息以 `role="user"` 保存并进入后续上下文，不会修改正在运行的 Agent 的上下文。返回值是已保存的消息 ID；可传入 `message_id` 标识同一次提交的重试。

### 追加插件自定义事件 `append_plugin_event`

```py
event_id = await conversations.append_plugin_event(
    event_type="my_plugin.retrieval_completed",
    data={"document_ids": ["document-1"]},
    cid=target_cid,
)
```

插件事件与对话一起保存，不会进入模型上下文。`event_type` 建议使用插件名称前缀，`data` 必须是可 JSON 序列化的字典。返回值是已保存的事件 ID；可传入 `event_id` 标识同一次提交的重试。

无需事件历史的可变状态可使用[插件 KV 存储](../storage.md)。按对话区分时，将 `cid` 放入 key。

两个追加接口都必须传入已有对话的 `cid`，无效或不存在时抛出 `ValueError`。它们不会启动 Agent turn。

修改当前执行的上下文，请编辑相应 hook 的 `ProviderRequest.contexts` 或运行时消息列表。直接调用对话写入接口（包括 `update_conversation()` 和 `add_message_pair()`）不会更新正在运行的 Agent 上下文；并发修改已保存的历史可能触发 `ConversationConflictError`。

### 获取会话当前的 LLM 对话历史 `get_conversation`

```py
# AstrBot v4.30.0 之前的导入方式：
# from astrbot.core.conversation_mgr import Conversation
from astrbot.api.provider import Conversation

uid = event.unified_msg_origin
conv_mgr = self.context.conversations
curr_cid = await conv_mgr.get_curr_conversation_id(uid)
conversation = await conv_mgr.get_conversation(uid, curr_cid)  # Conversation
```

::: details Conversation 类型定义

```py
@dataclass
class Conversation:
    """The conversation entity representing a chat session."""

    platform_id: str
    """The platform ID in AstrBot"""
    user_id: str
    """The user ID associated with the conversation."""
    cid: str
    """The conversation ID, in UUID format."""
    history: str = ""
    """The conversation history as a string."""
    title: str | None = ""
    """The title of the conversation. For now, it's only used in WebChat."""
    persona_id: str | None = ""
    """The persona ID associated with the conversation."""
    created_at: int = 0
    """The timestamp when the conversation was created."""
    updated_at: int = 0
    """The timestamp when the conversation was last updated."""
```

:::

### 快速添加 LLM 记录到对话 `add_message_pair`

```py
# AstrBot v4.30.0 之前的导入方式：
# from astrbot.core.agent.message import AssistantMessageSegment, UserMessageSegment, TextPart
from astrbot.api.agents import (
    AssistantMessageSegment,
    UserMessageSegment,
    TextPart,
)

conv_mgr = self.context.conversations
provider_id = await self.context.get_current_chat_provider_id(event.unified_msg_origin)
curr_cid = await conv_mgr.get_curr_conversation_id(event.unified_msg_origin)
user_msg = UserMessageSegment(content=[TextPart(text="hi")])
llm_resp = await self.context.llm_generate(
    chat_provider_id=provider_id,  # 聊天模型 ID
    contexts=[
        user_msg
    ],  # 当未指定 prompt 时，使用 contexts 作为输入；同时指定 prompt 和 contexts 时，prompt 会被添加到 LLM 输入的最后
)
await conv_mgr.add_message_pair(
    cid=curr_cid,
    user_message=user_msg,
    assistant_message=AssistantMessageSegment(
        content=[TextPart(text=llm_resp.completion_text)]
    ),
)
```

> [!WARNING]
> 上面用 `unified_msg_origin` 作为会话历史的存储键。开启**隔离对话**（`platform_settings.unique_session`）后，群消息的 `unified_msg_origin` 会变化（仅限支持隔离的渠道），同一个群在不同开关状态下会解析到不同的会话。需要按群定位时请使用 `event.get_group_id()`，详见[处理消息事件](../listen-message-event.md)。

