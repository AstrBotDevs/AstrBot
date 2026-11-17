# Sessions and Conversations

A session is identified by the message source, `event.unified_msg_origin` (UMO). A conversation is identified by `cid` and stores a model message history. A session can create and switch between conversations.

To wait for a user's next message, see [Session Control](../session-control.md). This page covers reading and writing conversation history.

## Conversation Manager

Use `self.context.conversations` to create, read, update, switch, and delete conversations. `Conversation.history` is a JSON string containing model messages.

`_no_save` excludes a message or content part from future model context, but does not prevent its raw content from being stored.

> [!TIP]
> Starting with v4.30.0, the conversation API changes as follows:
>
> - `self.context.conversation_manager` remains a compatibility alias for `self.context.conversations`.
> - Replace `event.conversation_events` and `get_conversation_events()` with `append_message()` or `append_plugin_event()`.
> - Replace `update_conversation_title()` and `update_conversation_persona_id()` with `update_conversation(..., title=...)` and `update_conversation(..., persona_id=...)`.
> - Replace platform history links using `llm_checkpoint_id` with `turn_id` and `context_event_id`.

### Appending Model Messages

```py
conversations = self.context.conversations
message_id = await conversations.append_message(
    "The user prefers concise answers.",
    cid=target_cid,
)
```

`content` accepts text or a list of AstrBot `ContentPart` objects:

```py
from astrbot.core.agent.message import ImageURLPart, TextPart

await conversations.append_message(
    [
        TextPart(text="Describe this image."),
        ImageURLPart(
            image_url=ImageURLPart.ImageURL(url="https://example.com/image.png")
        ),
    ],
    cid=target_cid,
)
```

Messages are stored with `role="user"` and included in future context. They do not change a running agent's context. The returned string is the saved message ID; pass `message_id` to identify a retry of the same submission.

### Appending Plugin Events

```py
event_id = await conversations.append_plugin_event(
    event_type="my_plugin.retrieval_completed",
    data={"document_ids": ["document-1"]},
    cid=target_cid,
)
```

Plugin events are stored with the conversation but do not enter model context. Use a plugin-prefixed `event_type` and a JSON-serializable dict for `data`. The returned string is the saved event ID; pass `event_id` to identify a retry of the same submission.

For mutable state that does not need an event history, use [plugin KV storage](../storage.md). Include `cid` in the key for per-conversation state.

Both append methods require `cid` for an existing conversation and raise `ValueError` if it is invalid or missing from storage. Neither starts an agent turn.

To change the current execution's context, edit the relevant hook's `ProviderRequest.contexts` or runtime messages. Direct conversation writes, including `update_conversation()` and `add_message_pair()`, do not update a running agent's context and can cause `ConversationConflictError` if its stored history changes concurrently.

### Getting the Current LLM Conversation History for a Session

```py
# Before AstrBot v4.30.0:
# from astrbot.core.conversation_mgr import Conversation
from astrbot.api.provider import Conversation

uid = event.unified_msg_origin
conv_mgr = self.context.conversations
curr_cid = await conv_mgr.get_curr_conversation_id(uid)
conversation = await conv_mgr.get_conversation(uid, curr_cid)  # Conversation
```

::: details Conversation Type Definition

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

### Quickly Adding LLM Records to a Conversation `add_message_pair`

```py
# Before AstrBot v4.30.0:
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
    chat_provider_id=provider_id,  # Chat model ID
    contexts=[
        user_msg
    ],  # When prompt is not specified, contexts is used as input; if both prompt and contexts are provided, prompt is appended to the end of the LLM input
)
await conv_mgr.add_message_pair(
    cid=curr_cid,
    user_message=user_msg,
    assistant_message=AssistantMessageSegment(
        content=[TextPart(text=llm_resp.completion_text)]
    ),
)
```

