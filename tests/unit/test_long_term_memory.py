"""Tests for LTM v2 — long_term_memory.py"""

import json
from collections import deque

import pytest

from astrbot.builtin_stars.astrbot.long_term_memory import (
    _build_segments,
    _extract_bot_content,
    _extract_tag_content,
    _parse_tool_call,
    _parse_tool_result,
    _truncate_user_segment,
)


# =============================================================================
# _extract_tag_content
# =============================================================================

class TestExtractTagContent:
    def test_normal(self):
        assert _extract_tag_content("<T:CALL>hello</T:CALL>", "<T:CALL>", "</T:CALL>") == "hello"

    def test_json(self):
        line = '<T:CALL>{"id":"x","name":"f"}</T:CALL>'
        assert _extract_tag_content(line, "<T:CALL>", "</T:CALL>") == '{"id":"x","name":"f"}'

    def test_no_end_tag(self):
        assert _extract_tag_content("<T:CALL>hello", "<T:CALL>", "</T:CALL>") is None

    def test_wrong_end_tag(self):
        assert _extract_tag_content("<T:CALL>hello</T:RES>", "<T:CALL>", "</T:CALL>") is None


# =============================================================================
# _extract_bot_content
# =============================================================================

class TestExtractBotContent:
    def test_normal(self):
        assert _extract_bot_content("<BOT/14:30>: 你好呀~") == "你好呀~"

    def test_multiline_inline(self):
        assert _extract_bot_content("<BOT/09:15>: reply text") == "reply text"

    def test_no_separator(self):
        assert _extract_bot_content("<BOT/14:30>no colon space") is None

    def test_empty_content(self):
        assert _extract_bot_content("<BOT/14:30>: ") == ""


# =============================================================================
# _parse_tool_call
# =============================================================================

class TestParseToolCall:
    def test_single(self):
        line = '<T:CALL>{"id":"call_001","name":"get_weather","args":{"location":"北京"}}</T:CALL>'
        result = _parse_tool_call(line)
        assert result is not None
        assert result["id"] == "call_001"
        assert result["type"] == "function"
        assert result["function"]["name"] == "get_weather"
        assert json.loads(result["function"]["arguments"]) == {"location": "北京"}

    def test_no_args(self):
        line = '<T:CALL>{"id":"c2","name":"ping","args":{}}</T:CALL>'
        result = _parse_tool_call(line)
        assert result["function"]["arguments"] == "{}"

    def test_bad_json(self):
        assert _parse_tool_call("<T:CALL>not json</T:CALL>") is None

    def test_missing_end_tag(self):
        assert _parse_tool_call('<T:CALL>{"id":"x"}</T') is None


# =============================================================================
# _parse_tool_result
# =============================================================================

class TestParseToolResult:
    def test_normal(self):
        line = "<T:RES id=call_001>晴天 25°C</T:RES>"
        result = _parse_tool_result(line)
        assert result == {
            "role": "tool",
            "tool_call_id": "call_001",
            "content": "晴天 25°C",
        }

    def test_multiline_content(self):
        line = "<T:RES id=abc>line1\nline2</T:RES>"
        result = _parse_tool_result(line)
        assert result["content"] == "line1\nline2"

    def test_no_id(self):
        assert _parse_tool_result("<T:RES>content</T:RES>") is None

    def test_bad_prefix(self):
        assert _parse_tool_result("garbage") is None


# =============================================================================
# _truncate_user_segment
# =============================================================================

class TestTruncateUserSegment:
    def test_under_limit(self):
        lines = ["[小明/14:30]: hi", "[小红/14:31]: hello"]
        result = _truncate_user_segment(lines)
        assert result == lines

    def test_exceeds_msg_count(self):
        """最多保留 50 条"""
        lines = [f"[user{i}/14:00]: msg{i}" for i in range(60)]
        result = _truncate_user_segment(lines)
        assert len(result) == 50
        # 保留最近的
        assert result[0] == "[user10/14:00]: msg10"
        assert result[-1] == "[user59/14:00]: msg59"

    def test_exceeds_char_limit(self):
        """超过 3000 字符时从最早开始丢弃"""
        lines = [f"[user{i}/14:00]: {'x' * 80}" for i in range(50)]  # 50 × 100 ≈ 5000 chars
        result = _truncate_user_segment(lines)
        total = sum(len(l) + 1 for l in result)
        assert total <= 3000
        # 保留最近的
        assert result[-1] == lines[-1]

    def test_empty(self):
        assert _truncate_user_segment([]) == []

    def test_single_long_line(self):
        """单条超长行也被保留"""
        line = "x" * 5000
        result = _truncate_user_segment([line])
        assert result == [line]  # 至少保留一条


# =============================================================================
# _build_segments
# =============================================================================

class TestBuildSegments:
    def test_empty(self):
        assert _build_segments([]) == []

    def test_simple_user_only(self):
        lines = [
            "[小明/14:30]: hi",
            "[小红/14:31]: hello",
        ]
        result = _build_segments(lines)
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert "[小明/14:30]: hi" in result[0]["content"]
        assert "[小红/14:31]: hello" in result[0]["content"]

    def test_user_bot_user(self):
        lines = [
            "[小明/14:30]: hi",
            "<BOT/14:30>: 你好呀~",
            "[小红/14:31]: 哈哈",
        ]
        result = _build_segments(lines)
        assert len(result) == 3
        assert result[0]["role"] == "user"
        assert "[小明/14:30]: hi" in result[0]["content"]
        assert result[1] == {"role": "assistant", "content": "你好呀~"}
        assert result[2]["role"] == "user"
        assert "[小红/14:31]: 哈哈" in result[2]["content"]

    def test_multiple_bot_replies(self):
        """多次 @bot 交互"""
        lines = [
            "[小明/14:00]: @bot 1+1",
            "<BOT/14:00>: 等于2",
            "[小红/14:01]: 哈哈",
            "[小明/14:02]: @bot 2+2呢",
            "<BOT/14:02>: 等于4",
            "[小红/14:03]: 不错",
        ]
        result = _build_segments(lines)
        assert len(result) == 5
        assert result[0]["role"] == "user"
        assert result[1] == {"role": "assistant", "content": "等于2"}
        assert result[2]["role"] == "user"
        assert result[3] == {"role": "assistant", "content": "等于4"}
        assert result[4]["role"] == "user"

    def test_bot_first(self):
        """首行即 <BOT/>"""
        lines = [
            "<BOT/14:00>: 你们好",
            "[小明/14:01]: hello",
        ]
        result = _build_segments(lines)
        assert len(result) == 2
        assert result[0] == {"role": "assistant", "content": "你们好"}
        assert result[1]["role"] == "user"

    def test_tool_call_then_result_then_bot(self):
        """工具调用链：T:CALL → T:RES → BOT"""
        lines = [
            "[小明/14:30]: @bot 查天气",
            '<T:CALL>{"id":"call_001","name":"get_weather","args":{"location":"北京"}}</T:CALL>',
            "<T:RES id=call_001>晴天 25°C</T:RES>",
            "<BOT/14:30>: 北京今天晴天，25°C",
        ]
        result = _build_segments(lines)
        assert len(result) == 4

        assert result[0]["role"] == "user"
        assert "[小明/14:30]: @bot 查天气" in result[0]["content"]

        assert result[1]["role"] == "assistant"
        assert result[1]["content"] is None
        assert len(result[1]["tool_calls"]) == 1
        assert result[1]["tool_calls"][0]["id"] == "call_001"

        assert result[2] == {
            "role": "tool",
            "tool_call_id": "call_001",
            "content": "晴天 25°C",
        }

        assert result[3] == {
            "role": "assistant",
            "content": "北京今天晴天，25°C",
        }

    def test_parallel_tool_calls(self):
        """并行工具调用合并为一条 assistant(tool_calls)"""
        lines = [
            "[小明/14:30]: @bot 查天气和空气",
            '<T:CALL>{"id":"call_001","name":"get_weather","args":{"location":"北京"}}</T:CALL>',
            '<T:CALL>{"id":"call_002","name":"get_air_quality","args":{"location":"北京"}}</T:CALL>',
            "<T:RES id=call_001>晴天 25°C</T:RES>",
            "<T:RES id=call_002>AQI 50 优</T:RES>",
            "<BOT/14:30>: 北京晴天，AQI 50 优",
        ]
        result = _build_segments(lines)
        assert result[1]["role"] == "assistant"
        assert result[1]["content"] is None
        assert len(result[1]["tool_calls"]) == 2
        assert result[1]["tool_calls"][0]["id"] == "call_001"
        assert result[1]["tool_calls"][1]["id"] == "call_002"
        assert result[2]["role"] == "tool"
        assert result[2]["tool_call_id"] == "call_001"
        assert result[3]["role"] == "tool"
        assert result[3]["tool_call_id"] == "call_002"

    def test_multi_step_tool(self):
        """多步工具调用"""
        lines = [
            "[小明/14:30]: @bot 帮我查",
            '<T:CALL>{"id":"c1","name":"search","args":{"q":"x"}}</T:CALL>',
            "<T:RES id=c1>found A</T:RES>",
            '<T:CALL>{"id":"c2","name":"get_detail","args":{"id":"A"}}</T:CALL>',
            "<T:RES id=c2>detail of A</T:RES>",
            "<BOT/14:30>: A 的详情是...",
        ]
        result = _build_segments(lines)
        # tool round 1
        assert result[1]["role"] == "assistant"
        assert len(result[1]["tool_calls"]) == 1
        assert result[1]["tool_calls"][0]["id"] == "c1"
        assert result[2]["role"] == "tool"
        assert result[2]["tool_call_id"] == "c1"
        # tool round 2
        assert result[3]["role"] == "assistant"
        assert len(result[3]["tool_calls"]) == 1
        assert result[3]["tool_calls"][0]["id"] == "c2"
        assert result[4]["role"] == "tool"
        assert result[4]["tool_call_id"] == "c2"

    def test_extreme_dense_group_chat(self):
        """100 条纯群聊，无人 @bot → 全部合并为单条 user"""
        lines = [f"[user{i}/14:{i:02d}]: 消息内容{i}" for i in range(100)]
        result = _build_segments(lines)
        assert len(result) == 1
        assert result[0]["role"] == "user"
        # 段内已裁剪
        lines_in_content = result[0]["content"].split("\n")
        assert len(lines_in_content) <= 50

    def test_extreme_bot_between_group_chat(self):
        """100条群聊中间夹了一次 @bot → user + asst + user"""
        lines = (
            [f"[user{i}/14:{i:02d}]: 消息{i}" for i in range(40)]
            + ["<BOT/14:40>: 我来了"]
            + [f"[user{i}/14:{i:02d}]: 消息{i}" for i in range(40, 100)]
        )
        result = _build_segments(lines)
        assert len(result) == 3
        assert result[0]["role"] == "user"
        assert result[1] == {"role": "assistant", "content": "我来了"}
        assert result[2]["role"] == "user"
        # 段内都做了裁剪
        assert len(result[0]["content"].split("\n")) <= 50
        assert len(result[2]["content"].split("\n")) <= 50

    def test_image_and_at_messages(self):
        """图片和 @ 消息作为普通行参与合并"""
        lines = [
            "[小明/14:30]: hi [Image: 一只猫]",
            "[小红/14:31]: [At: 小明] 好看",
        ]
        result = _build_segments(lines)
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert "[Image: 一只猫]" in result[0]["content"]
        assert "[At: 小明]" in result[0]["content"]


# =============================================================================
# LongTermMemory integration (mocked)
# =============================================================================

class TestLongTermMemoryIntegration:
    """轻量集成测试 — 模拟 handle_message → on_req_llm → on_agent_done 流程"""

    @pytest.fixture
    def mock_event(self):
        from unittest.mock import MagicMock
        from astrbot.api.event import AstrMessageEvent
        from astrbot.api.platform import MessageType
        event = MagicMock(spec=AstrMessageEvent)
        event.unified_msg_origin = "group_123"
        event.get_message_type.return_value = MessageType.GROUP_MESSAGE
        event.get_messages.return_value = []
        event.message_obj = MagicMock()
        event.message_obj.sender.nickname = "小明"
        event.get_extra.return_value = -1
        return event

    @pytest.fixture
    def mock_context(self):
        from unittest.mock import MagicMock
        from astrbot.api import star
        ctx = MagicMock(spec=star.Context)
        cfg = {
            "provider_ltm_settings": {
                "image_caption": False,
                "image_caption_provider_id": "",
                "image_caption_prompt": "",
                "active_reply": {
                    "enable": False,
                    "method": "possibility_reply",
                    "possibility_reply": 0.0,
                    "prompt": "",
                    "whitelist": [],
                },
            },
            "provider_settings": {
                "image_caption_prompt": "",
            },
        }
        ctx.get_config.return_value = cfg
        return ctx

    @pytest.fixture
    def ltm(self, mock_context):
        from unittest.mock import MagicMock
        from astrbot.builtin_stars.astrbot.long_term_memory import LongTermMemory

        acm = MagicMock()
        ltm = LongTermMemory(acm, mock_context)
        return ltm

    @pytest.mark.asyncio
    async def test_empty_flow(self, ltm, mock_event):
        """空 raw_records 时 on_req_llm 应直接返回"""
        from astrbot.api.provider import ProviderRequest
        req = ProviderRequest()

        mock_event.get_extra.return_value = -1  # no raw idx
        await ltm.on_req_llm(mock_event, req)
        # No exception, no modification
        assert req.contexts == []

    @pytest.mark.asyncio
    async def test_handle_then_on_req_no_bot_yet(self, ltm, mock_event):
        """handle message → on_req_llm（bot 还没回）"""
        from unittest.mock import MagicMock
        from astrbot.api.provider import ProviderRequest
        from astrbot.api.message_components import Plain

        comp = Plain(text="你好")
        mock_event.get_messages.return_value = [comp]

        recorded_idx = [0]

        def _get_extra(key, default=None):
            if key == "_ltm_raw_idx":
                return recorded_idx[0]
            return default

        mock_event.get_extra = _get_extra

        await ltm.handle_message(mock_event)
        req = ProviderRequest()
        await ltm.on_req_llm(mock_event, req)

        assert len(req.contexts) <= 0 or all(
            isinstance(c, dict) for c in req.contexts
        )

    @pytest.mark.asyncio
    async def test_full_roundtrip(self, ltm, mock_event):
        """完整一轮：handle → on_req → on_agent_done → on_req"""
        from unittest.mock import MagicMock
        from astrbot.api.provider import ProviderRequest, LLMResponse
        from astrbot.api.message_components import Plain

        comp = Plain(text="@bot hi")
        mock_event.get_messages.return_value = [comp]

        raw_idx = 0

        def _get_extra(key, default=None):
            if key == "_ltm_raw_idx":
                return raw_idx
            return default

        mock_event.get_extra = _get_extra

        await ltm.handle_message(mock_event)

        req = ProviderRequest()
        await ltm.on_req_llm(mock_event, req)
        assert isinstance(req.contexts, list)
        assert "chatroom" in req.system_prompt.lower()
        assert req.conversation is None

        raw_idx += 1
        mock_run_ctx = MagicMock()
        mock_run_ctx.messages = []
        resp = LLMResponse(role="assistant", completion_text="你好呀~")

        await ltm.on_agent_done(mock_event, mock_run_ctx, resp)

        # BOT 回复被构建进 contexts，cursor 推进后 trim 归零，raw_records 被裁剪清空
        ctx_list = ltm.contexts["group_123"]
        bot_ctx = [c for c in ctx_list if c.get("role") == "assistant"]
        assert len(bot_ctx) == 1
        assert "你好呀~" in bot_ctx[0]["content"]
        # cursor 在 trim 后归零（所有已消费条目被清除）
        assert ltm._raw_cursor["group_123"] == 0

    @pytest.mark.asyncio
    async def test_toggle_cleanup(self, ltm, mock_event):
        """测试开关切换时的惰性清理"""
        ltm.raw_records["group_123"].append("[小明/14:30]: hello")
        ltm._raw_cursor["group_123"] = 1

        await ltm.remove_session(mock_event)

        assert "group_123" not in ltm.raw_records
        assert "group_123" not in ltm.contexts
        assert "group_123" not in ltm._raw_cursor

    def test_trim_raw_records_preserves_unconsumed(self, ltm):
        """_trim_raw_records 只淘汰 cursor 之前的条目"""
        umo = "group_123"
        for i in range(100):
            ltm.raw_records[umo].append(f"[user{i}/14:00]: msg{i}")
        ltm._raw_cursor[umo] = 50  # 50 条已消费

        ltm._trim_raw_records(umo)

        # cursor 之前的 50 条被清掉
        remaining = list(ltm.raw_records[umo])
        assert len(remaining) == 50
        # 保留的是 cursor 之后的
        assert remaining[0] == "[user50/14:00]: msg50"
        assert remaining[-1] == "[user99/14:00]: msg99"
        assert ltm._raw_cursor[umo] == 0  # 所有剩余条目在 cursor 之前被清除后归零
