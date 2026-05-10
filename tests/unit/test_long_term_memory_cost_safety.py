import pytest

from astrbot.api.provider import ProviderRequest
from astrbot.builtin_stars.astrbot.long_term_memory import LongTermMemory
from astrbot.core.agent.message import TextPart


class DummyContext:
    def get_config(self, umo=None):
        return {
            "provider_settings": {
                "image_caption_prompt": "Describe the image.",
            },
            "provider_ltm_settings": {
                "group_message_max_cnt": 50,
                "group_icl_token_budget": 30,
                "image_caption": False,
                "image_caption_provider_id": "",
                "active_reply": {
                    "enable": False,
                    "method": "possibility_reply",
                    "possibility_reply": 0.1,
                    "whitelist": [],
                },
            },
        }


class DummyEvent:
    unified_msg_origin = "group:test"


@pytest.mark.asyncio
async def test_group_icl_uses_user_context_part_instead_of_system_prompt():
    ltm = LongTermMemory(None, DummyContext())
    ltm.session_chats[DummyEvent.unified_msg_origin] = [
        "[alice/10:00:00]: old message",
        "[bob/10:01:00]: recent message",
    ]
    req = ProviderRequest(prompt="hello", system_prompt="base system")

    await ltm.on_req_llm(DummyEvent(), req)

    assert "old message" not in req.system_prompt
    assert "recent message" not in req.system_prompt
    assert "current user message" in req.system_prompt
    assert len(req.extra_user_content_parts) == 1
    part = req.extra_user_content_parts[0]
    assert isinstance(part, TextPart)
    assert "[Group Chat Context]" in part.text
    assert "recent message" in part.text


def test_group_icl_context_respects_token_budget():
    ltm = LongTermMemory(None, DummyContext())
    chats = [f"[user{i}/10:00:0{i}]: " + ("x" * 80) for i in range(5)]

    chats_str, omitted, estimated_tokens = ltm._build_chats_context(chats, 30)

    assert omitted > 0
    assert "earlier group messages omitted" in chats_str
    assert "user4" in chats_str
    assert estimated_tokens <= 50
