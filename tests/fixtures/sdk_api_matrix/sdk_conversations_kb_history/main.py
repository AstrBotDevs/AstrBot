"""Dedicated new-SDK plugin covering Conversations, KB, and MessageHistory."""

from __future__ import annotations

import json

from astrbot_sdk import MessageEvent, Plugin, on
from astrbot_sdk.conversations import (
    AudioPart,
    Conversation,
    ConversationPage,
    ConversationPatch,
    ImagePart,
    Message,
    TextPart,
)
from astrbot_sdk.llm import ProviderKind


class SdkConversationsKbHistoryPlugin(Plugin):
    """Exercise all methods and DTOs of conversations, kb, and history."""

    @on.command("ckh run", description="Run conversation, KB, and history CRUD")
    async def ckh_run(self, event: MessageEvent):
        """Exercise Conversation CRUD (multimodal + tools), KB CRUD, and History."""
        img_asset = await self.ctx.assets.upload(
            b"PNG-CONV",
            filename="conv.png",
            media_type="image/png",
        )
        c1: Conversation = await self.ctx.conversations.create(
            event.umo,
            title="conv-one",
            messages=(
                Message(
                    role="user",
                    content=(
                        TextPart("hi"),
                        ImagePart(source=img_asset),
                        AudioPart(source="https://astrbot.app/a.wav"),
                    ),
                ),
            ),
        )
        c2 = await self.ctx.conversations.create(event.umo, title="conv-two")
        cur = await self.ctx.conversations.current(event.umo)
        fetched = await self.ctx.conversations.get(event.umo, c1.id)
        page1: ConversationPage = await self.ctx.conversations.list(event.umo, limit=1)
        page2 = (
            await self.ctx.conversations.list(
                event.umo,
                cursor=page1.next_cursor,
                limit=5,
            )
            if page1.next_cursor is not None
            else ConversationPage(items=())
        )
        await self.ctx.conversations.append(
            event.umo,
            c1.id,
            (
                Message(
                    role="assistant",
                    content=None,
                    tool_calls=({"id": "tc-1", "type": "function"},),
                ),
                Message(role="tool", content="done", tool_call_id="tc-1"),
            ),
        )
        updated = await self.ctx.conversations.update(
            event.umo,
            c1.id,
            ConversationPatch(title="conv-one-upd"),
        )
        await self.ctx.conversations.set_current(event.umo, c1.id)
        cur_after = await self.ctx.conversations.current(event.umo)
        await self.ctx.conversations.delete(event.umo, c1.id)
        await self.ctx.conversations.delete(event.umo, c2.id)
        after_del = await self.ctx.conversations.get(event.umo, c1.id)

        emb = await self.ctx.llm.list_providers(ProviderKind.EMBEDDING)
        kb = await self.ctx.kb.create("ckh_kb", embedding_provider_id=emb[0].id)
        kb_list = await self.ctx.kb.list()
        kb_by_id = await self.ctx.kb.get(str(kb["kb_id"]))
        kb_by_name = await self.ctx.kb.get_by_name("ckh_kb")
        kb_del = await self.ctx.kb.delete(str(kb["kb_id"]))

        r1 = await self.ctx.history.insert(
            "webchat",
            "ckh-u",
            {"role": "user", "text": "h1"},
            sender_id="ckh-u",
            sender_name="CKH",
        )
        await self.ctx.history.insert_chain("webchat", "ckh-u", "h2", role="bot")
        cnt_before = await self.ctx.history.count("webchat", "ckh-u")
        rows = await self.ctx.history.get("webchat", "ckh-u")
        await self.ctx.history.update(
            int(r1["id"]), content={"role": "user", "text": "h1b"}
        )
        await self.ctx.history.delete_by_id(int(r1["id"]))
        cnt_mid = await self.ctx.history.count("webchat", "ckh-u")
        await self.ctx.history.delete("webchat", "ckh-u")
        cnt_end = await self.ctx.history.count("webchat", "ckh-u")

        yield event.reply(
            json.dumps(
                {
                    "conv_ok": (
                        cur is not None
                        and cur.id == c2.id
                        and fetched is not None
                        and len(page1.items) == 1
                        and len(page2.items) >= 1
                        and updated.title == "conv-one-upd"
                        and len(updated.messages) == 3
                        and cur_after is not None
                        and cur_after.id == c1.id
                        and after_del is None
                    ),
                    "kb_ok": (
                        any(k.get("kb_id") == kb.get("kb_id") for k in kb_list)
                        and kb_by_id is not None
                        and kb_by_name is not None
                        and kb_del is True
                    ),
                    "history_ok": (
                        cnt_before == 2
                        and len(rows) == 2
                        and cnt_mid == 1
                        and cnt_end == 0
                    ),
                },
                sort_keys=True,
            )
        )
