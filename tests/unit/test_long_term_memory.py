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
    _rounds_to_text,
    _split_into_rounds,
    _truncate_tool_result_for_history,
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

    def test_valid_json_missing_keys(self):
        """合法 JSON 但缺 id/name/args 时应安全返回 None。"""
        # 缺 name
        assert _parse_tool_call('<T:CALL>{"id":"x","args":{}}</T:CALL>') is None
        # 缺 id
        assert _parse_tool_call('<T:CALL>{"name":"f","args":{}}</T:CALL>') is None
        # 全缺
        assert _parse_tool_call('<T:CALL>{"foo":1}</T:CALL>') is None
        # 非 dict JSON（json.loads 返回 int）
        assert _parse_tool_call("<T:CALL>123</T:CALL>") is None


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
# _truncate_tool_result_for_history
# =============================================================================

class TestTruncateToolResultForHistory:
    def test_under_limit(self):
        text = "short result"
        assert _truncate_tool_result_for_history(text, 100) == text

    def test_over_limit(self):
        text = "x" * 50
        result = _truncate_tool_result_for_history(text, 40)
        assert len(result) <= 40
        assert "TRUNCATED" in result

    def test_non_positive_limit_keeps_original(self):
        text = "x" * 50
        assert _truncate_tool_result_for_history(text, 0) == text


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


# =============================================================================
# 多轮累积
# =============================================================================

class TestMultiRoundAccumulation:
    """验证多轮对话中 contexts 累积行为。"""

    @pytest.fixture
    def mock_event(self):
        from unittest.mock import MagicMock
        from astrbot.api.event import AstrMessageEvent
        from astrbot.api.platform import MessageType
        event = MagicMock(spec=AstrMessageEvent)
        event.unified_msg_origin = "group_123"
        event.get_message_type.return_value = MessageType.GROUP_MESSAGE
        event.message_obj = MagicMock()
        event.message_obj.sender.nickname = "小明"
        event.get_extra.return_value = -1
        return event

    @pytest.fixture
    def ltm(self):
        from unittest.mock import MagicMock
        from astrbot.builtin_stars.astrbot.long_term_memory import LongTermMemory
        ctx = MagicMock()
        ctx.get_config.return_value = {
            "provider_ltm_settings": {
                "image_caption": False, "image_caption_provider_id": "",
                "image_caption_prompt": "",
                "active_reply": {"enable": False, "method": "possibility_reply",
                               "possibility_reply": 0.0, "prompt": "", "whitelist": []},
            },
            "provider_settings": {"image_caption_prompt": ""},
        }
        return LongTermMemory(MagicMock(), ctx)

    @pytest.mark.asyncio
    async def test_three_rounds_contexts_grow(self, ltm, mock_event):
        """三轮 @bot 对话后 contexts 累积 3 条 user + 3 条 assistant（含 prompt）。"""
        from unittest.mock import MagicMock
        from astrbot.api.provider import ProviderRequest, LLMResponse
        from astrbot.api.message_components import Plain

        for user_text, bot_text in [
            ("@bot 你好", "你好呀~"),
            ("@bot 1+1", "等于2"),
            ("@bot 再见", "拜拜~"),
        ]:
            def _get_extra(key, default=None):
                if key == "_ltm_raw_idx":
                    return len(ltm.raw_records["group_123"])
                return default
            mock_event.get_extra = _get_extra
            comp = Plain(text=user_text)
            mock_event.get_messages.return_value = [comp]

            await ltm.handle_message(mock_event)

            req = ProviderRequest()
            await ltm.on_req_llm(mock_event, req)
            assert req.conversation is None

            mock_run_ctx = MagicMock(messages=[])
            resp = LLMResponse(role="assistant", completion_text=bot_text)
            await ltm.on_agent_done(mock_event, mock_run_ctx, resp)

        ctxs = ltm.contexts["group_123"]
        roles = [c["role"] for c in ctxs]
        # on_agent_done 从 cursor 起构建（含 @bot prompt） → user 段也进 contexts
        assert roles == ["user", "assistant", "user", "assistant", "user", "assistant"]
        assert "你好呀~" in ctxs[1]["content"]
        assert "等于2" in ctxs[3]["content"]
        assert "拜拜~" in ctxs[5]["content"]

    @pytest.mark.asyncio
    async def test_contexts_only_appended_never_rebuilt(self, ltm, mock_event):
        """验证 contexts 是追加式，不会被重建。"""
        from unittest.mock import MagicMock
        from astrbot.api.provider import ProviderRequest, LLMResponse
        from astrbot.api.message_components import Plain

        # Round 1
        def _get_extra_r1(key, default=None):
            return 0 if key == "_ltm_raw_idx" else default
        mock_event.get_extra = _get_extra_r1
        mock_event.get_messages.return_value = [Plain(text="@bot hi")]
        await ltm.handle_message(mock_event)
        req = ProviderRequest()
        await ltm.on_req_llm(mock_event, req)
        await ltm.on_agent_done(
            mock_event,
            MagicMock(messages=[]),
            LLMResponse(role="assistant", completion_text="hello"),
        )
        ctx_after_r1 = list(ltm.contexts["group_123"])
        assert len(ctx_after_r1) >= 1  # 至少有 assistant

        # Round 2
        def _get_extra_r2(key, default=None):
            return 2 if key == "_ltm_raw_idx" else default
        mock_event.get_extra = _get_extra_r2
        mock_event.get_messages.return_value = [Plain(text="@bot again")]
        await ltm.handle_message(mock_event)
        req = ProviderRequest()
        await ltm.on_req_llm(mock_event, req)
        await ltm.on_agent_done(
            mock_event,
            MagicMock(messages=[]),
            LLMResponse(role="assistant", completion_text="world"),
        )
        ctx_after_r2 = list(ltm.contexts["group_123"])
        # 旧条目保留，新条目追加
        assert len(ctx_after_r2) >= len(ctx_after_r1)
        assert ctx_after_r2[:len(ctx_after_r1)] == ctx_after_r1


# =============================================================================
# on_agent_done 工具链
# =============================================================================

class TestAgentDoneToolChains:
    """验证 on_agent_done 正确记录工具调用链。"""

    @pytest.fixture
    def mock_event(self):
        from unittest.mock import MagicMock
        from astrbot.api.event import AstrMessageEvent
        from astrbot.api.platform import MessageType
        event = MagicMock(spec=AstrMessageEvent)
        event.unified_msg_origin = "group_123"
        event.get_message_type.return_value = MessageType.GROUP_MESSAGE
        event.message_obj = MagicMock()
        event.message_obj.sender.nickname = "小明"
        event.get_extra.return_value = 0
        event.get_messages.return_value = [MagicMock()]
        return event

    @pytest.fixture
    def ltm(self):
        from unittest.mock import MagicMock
        from astrbot.builtin_stars.astrbot.long_term_memory import LongTermMemory
        ctx = MagicMock()
        ctx.get_config.return_value = {
            "provider_ltm_settings": {
                "image_caption": False, "image_caption_provider_id": "",
                "image_caption_prompt": "",
                "active_reply": {"enable": False, "method": "possibility_reply",
                               "possibility_reply": 0.0, "prompt": "", "whitelist": []},
            },
            "provider_settings": {"image_caption_prompt": ""},
        }
        return LongTermMemory(MagicMock(), ctx)

    @pytest.mark.asyncio
    async def test_tool_call_recorded_in_raw(self, ltm, mock_event):
        """工具调用被记录到 contexts 中的 assistant(tool_calls) + tool 消息。"""
        from astrbot.api.provider import LLMResponse
        from astrbot.api.message_components import Plain

        mock_event.get_messages.return_value = [Plain(text="@bot weather")]
        await ltm.handle_message(mock_event)

        from unittest.mock import MagicMock
        tc_msg = MagicMock()
        tc_msg.role = "assistant"
        tc_msg.tool_calls = [{"id": "c1", "function": {"name": "weather", "arguments": '{"city":"bj"}'}}]
        tool_msg = MagicMock()
        tool_msg.role = "tool"
        tool_msg.tool_call_id = "c1"
        tool_msg.content = "sunny"

        run_ctx = MagicMock()
        run_ctx.messages = [tc_msg, tool_msg]
        resp = LLMResponse(role="assistant", completion_text="今天晴天")

        await ltm.on_agent_done(mock_event, run_ctx, resp)

        # on_agent_done 构建 contexts 后 trim raw_records，检查 contexts
        ctxs = ltm.contexts["group_123"]
        roles = [c["role"] for c in ctxs]
        has_tool_call = any(c.get("tool_calls") for c in ctxs if c["role"] == "assistant")
        has_tool_result = any(c["role"] == "tool" for c in ctxs)
        has_final_asst = any(
            c["role"] == "assistant" and c.get("content") == "今天晴天"
            for c in ctxs
        )
        assert has_tool_call, f"expected assistant with tool_calls in contexts"
        assert has_tool_result, f"expected tool message in contexts"
        assert has_final_asst, f"expected final assistant text in contexts"

    @pytest.mark.asyncio
    async def test_tool_call_no_final_text(self, ltm, mock_event):
        """工具调用后没有最终文本回复时 contexts 有 tool_calls 但没有最终 assistant 文本。"""
        from astrbot.api.provider import LLMResponse
        from astrbot.api.message_components import Plain

        mock_event.get_messages.return_value = [Plain(text="@bot task")]
        await ltm.handle_message(mock_event)

        from unittest.mock import MagicMock
        tc_msg = MagicMock()
        tc_msg.role = "assistant"
        tc_msg.tool_calls = [{"id": "c2", "function": {"name": "calc", "arguments": "{}"}}]

        run_ctx = MagicMock()
        run_ctx.messages = [tc_msg]
        resp = LLMResponse(role="assistant")  # 无 completion_text

        await ltm.on_agent_done(mock_event, run_ctx, resp)

        ctxs = ltm.contexts["group_123"]
        has_tool_call = any(c.get("tool_calls") for c in ctxs if c["role"] == "assistant")
        has_final_text = any(
            c["role"] == "assistant" and c.get("content")
            for c in ctxs
        )
        assert has_tool_call
        assert not has_final_text

    @pytest.mark.asyncio
    async def test_tool_call_dedup_across_rounds(self, ltm, mock_event):
        """历史工具调用不应被重复持久化——防重复注入的核心回归测试。"""
        from astrbot.api.provider import LLMResponse
        from unittest.mock import MagicMock

        umo = "group_123"

        # 确保 raw_records 存在（on_agent_done 前置条件）
        ltm.raw_records[umo].append("[dummy/00:00]: hi")
        ltm._raw_cursor[umo] = 1

        tc_msg = MagicMock()
        tc_msg.role = "assistant"
        tc_msg.tool_calls = [
            {"id": "c1", "function": {"name": "tool_a", "arguments": "{}"}}
        ]
        tool_msg = MagicMock()
        tool_msg.role = "tool"
        tool_msg.tool_call_id = "c1"
        tool_msg.content = "result_a"

        run_ctx = MagicMock(messages=[tc_msg, tool_msg])
        resp = LLMResponse(role="assistant", completion_text="ok")

        # Round 1 — 首次记录
        await ltm.on_agent_done(mock_event, run_ctx, resp)
        assert ltm._persisted_tool_call_ids[umo] == {"c1"}
        assert ltm._persisted_tool_result_ids[umo] == {"c1"}

        # Round 2 — 模拟历史注入：run_context.messages 仍包含 c1
        ltm.raw_records[umo].append("[dummy2/00:01]: hi2")
        resp2 = LLMResponse(role="assistant", completion_text="ok2")
        await ltm.on_agent_done(mock_event, run_ctx, resp2)

        # 去重集不变 — c1 未被重复持久化
        assert ltm._persisted_tool_call_ids[umo] == {"c1"}
        assert ltm._persisted_tool_result_ids[umo] == {"c1"}

        # Round 3 — 历史 c1 + 新调用 c2 混合
        ltm.raw_records[umo].append("[dummy3/00:02]: hi3")
        new_tc = MagicMock()
        new_tc.role = "assistant"
        new_tc.tool_calls = [
            {"id": "c2", "function": {"name": "tool_b", "arguments": "{}"}}
        ]
        new_tool = MagicMock()
        new_tool.role = "tool"
        new_tool.tool_call_id = "c2"
        new_tool.content = "result_b"

        mixed_ctx = MagicMock(messages=[tc_msg, tool_msg, new_tc, new_tool])
        resp3 = LLMResponse(role="assistant", completion_text="ok3")
        await ltm.on_agent_done(mock_event, mixed_ctx, resp3)

        # c1 不变，c2 被添加
        assert ltm._persisted_tool_call_ids[umo] == {"c1", "c2"}
        assert ltm._persisted_tool_result_ids[umo] == {"c1", "c2"}


# =============================================================================
# 极端数据
# =============================================================================

class TestExtremeData:
    """边界和极端输入。"""

    @pytest.fixture
    def ltm(self):
        from unittest.mock import MagicMock
        from astrbot.builtin_stars.astrbot.long_term_memory import LongTermMemory
        ctx = MagicMock()
        ctx.get_config.return_value = {
            "provider_ltm_settings": {
                "image_caption": False, "image_caption_provider_id": "",
                "image_caption_prompt": "",
                "active_reply": {"enable": False, "method": "possibility_reply",
                               "possibility_reply": 0.0, "prompt": "", "whitelist": []},
            },
            "provider_settings": {"image_caption_prompt": ""},
        }
        return LongTermMemory(MagicMock(), ctx)

    def test_emoji_and_unicode_user_segment(self):
        """emoji 和 Unicode 在 user 段中正确处理。"""
        lines = [
            "[小明/14:30]: 😂😂😂 哈哈哈哈",
            "[小红/14:31]: 你好世界 🌍 ！",
            "[小刚/14:32]: 日本語テスト \u3067\u3059",
        ]
        result = _build_segments(lines)
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert "😂😂😂" in result[0]["content"]
        assert "🌍" in result[0]["content"]
        assert "日本語テスト" in result[0]["content"]

    def test_mixed_image_at_plain(self):
        """Image + At + Plain 混合行。"""
        # 模拟 handle_message 构建的 raw line
        raw_lines = [
            "[小明/14:30]:  hi [Image: 一只猫] [At: 小红] ok",
            "[小红/14:31]: 收到",
        ]
        result = _build_segments(raw_lines)
        assert len(result) == 1
        assert "[Image: 一只猫]" in result[0]["content"]
        assert "[At: 小红]" in result[0]["content"]
        assert "ok" in result[0]["content"]

    def test_max_raw_bytes_triggers_cursor_trim(self, ltm):
        """MAX_RAW_BYTES 超限时淘汰已消费条目。"""
        umo = "big_group"
        # 塞入 60KB 已消费 + 10KB 未消费
        consumed = "x" * 6000  # ~6KB per line
        for i in range(10):
            ltm.raw_records[umo].append(consumed + f" consumed{i}")
            ltm._raw_cursor[umo] += 1
        unconsumed = "y" * 1000  # ~1KB per line
        for i in range(10):
            ltm.raw_records[umo].append(unconsumed + f" unconsumed{i}")

        ltm._trim_raw_records(umo)

        remaining = list(ltm.raw_records[umo])
        assert len(remaining) > 0
        assert all("unconsumed" in s or "consumed" in s for s in remaining)
        # cursor 归零（所有已消费全部清掉）
        assert ltm._raw_cursor[umo] == 0

    def test_size_based_trim_actually_activates(self, ltm):
        """size-based 淘汰在超限时真正触发，且不依赖 cursor > 0。"""
        umo = "overflow_group"
        # 20 条 unconsumed，每条 ~55 bytes → ~1100 bytes >> 100
        for i in range(20):
            ltm.raw_records[umo].append("x" * 50 + f" msg{i}")
        ltm._raw_cursor[umo] = 0

        ltm._trim_raw_records(umo, max_bytes=100)

        remaining = list(ltm.raw_records[umo])
        total = sum(len(s.encode()) for s in remaining)
        assert total <= 100, f"expected ≤100 bytes, got {total}"
        assert ltm._raw_cursor[umo] == 0

    def test_size_based_trim_with_mixed_consumed(self, ltm):
        """size-based 淘汰在混合 consumed/unconsumed 时正确工作。"""
        umo = "mixed_group"
        # 5 consumed (cursor=5) + 15 unconsumed → 先清 consumed，再按 size 淘汰 unconsumed
        for i in range(5):
            ltm.raw_records[umo].append("x" * 50 + f" consumed{i}")
            ltm._raw_cursor[umo] = i + 1
        for i in range(15):
            ltm.raw_records[umo].append("y" * 50 + f" unconsumed{i}")

        ltm._trim_raw_records(umo, max_bytes=100)

        remaining = list(ltm.raw_records[umo])
        total = sum(len(s.encode()) for s in remaining)
        assert total <= 100, f"expected ≤100 bytes, got {total}"
        assert ltm._raw_cursor[umo] == 0
        # consumed 条目不应残留（排除 unconsumed 子串匹配）
        assert not any(" consumed" in s for s in remaining)


# =============================================================================
# Persona begin_dialogs 前置保留
# =============================================================================

class TestPersonaBeginDialogs:
    """验证 req.contexts 已有内容时 LTM 前置保留。"""

    @pytest.fixture
    def mock_event(self):
        from unittest.mock import MagicMock
        from astrbot.api.event import AstrMessageEvent
        from astrbot.api.platform import MessageType
        event = MagicMock(spec=AstrMessageEvent)
        event.unified_msg_origin = "group_123"
        event.get_message_type.return_value = MessageType.GROUP_MESSAGE
        event.message_obj = MagicMock()
        event.message_obj.sender.nickname = "小明"
        event.get_extra.return_value = 0
        event.get_messages.return_value = [MagicMock()]
        return event

    @pytest.fixture
    def ltm(self):
        from unittest.mock import MagicMock
        from astrbot.builtin_stars.astrbot.long_term_memory import LongTermMemory
        ctx = MagicMock()
        ctx.get_config.return_value = {
            "provider_ltm_settings": {
                "image_caption": False, "image_caption_provider_id": "",
                "image_caption_prompt": "",
                "active_reply": {"enable": False, "method": "possibility_reply",
                               "possibility_reply": 0.0, "prompt": "", "whitelist": []},
            },
            "provider_settings": {"image_caption_prompt": ""},
        }
        return LongTermMemory(MagicMock(), ctx)

    @pytest.mark.asyncio
    async def test_existing_contexts_preserved(self, ltm, mock_event):
        """Persona 注入的 begin_dialogs 在 contexts 之前。"""
        from astrbot.api.provider import ProviderRequest
        from astrbot.api.message_components import Plain

        mock_event.get_messages.return_value = [Plain(text="@bot hi")]
        await ltm.handle_message(mock_event)

        # 模拟 Persona 已注入的内容
        persona_dialogs = [
            {"role": "system", "content": "sample-only"},
            {"role": "user", "content": "sample-only"},
            {"role": "assistant", "content": "sample-only"},
        ]
        req = ProviderRequest(contexts=persona_dialogs)
        await ltm.on_req_llm(mock_event, req)

        # Persona 内容在 LTM 内容之前
        assert req.contexts[:3] == persona_dialogs


# =============================================================================
# 并发安全
# =============================================================================

class TestConcurrentSafety:
    """验证 asyncio.Lock 下的并发安全性。"""

    @pytest.fixture
    def mock_event_factory(self):
        from unittest.mock import MagicMock
        from astrbot.api.event import AstrMessageEvent
        from astrbot.api.platform import MessageType

        def _make(umo="group_123", raw_idx=0, text="hi"):
            event = MagicMock(spec=AstrMessageEvent)
            event.unified_msg_origin = umo
            event.get_message_type.return_value = MessageType.GROUP_MESSAGE
            event.message_obj = MagicMock()
            event.message_obj.sender.nickname = "小明"

            def _ge(key, default=None):
                return raw_idx if key == "_ltm_raw_idx" else default
            event.get_extra = _ge
            from astrbot.api.message_components import Plain
            event.get_messages.return_value = [Plain(text=text)]
            return event
        return _make

    @pytest.fixture
    def ltm(self):
        from unittest.mock import MagicMock
        from astrbot.builtin_stars.astrbot.long_term_memory import LongTermMemory
        ctx = MagicMock()
        ctx.get_config.return_value = {
            "provider_ltm_settings": {
                "image_caption": False, "image_caption_provider_id": "",
                "image_caption_prompt": "",
                "active_reply": {"enable": False, "method": "possibility_reply",
                               "possibility_reply": 0.0, "prompt": "", "whitelist": []},
            },
            "provider_settings": {"image_caption_prompt": ""},
        }
        return LongTermMemory(MagicMock(), ctx)

    @pytest.mark.asyncio
    async def test_concurrent_handle_same_umo(self, ltm, mock_event_factory):
        """同一群并发 handle_message 不会丢失消息。"""
        import asyncio

        texts = ["msg1", "msg2", "msg3", "msg4", "msg5"]
        tasks = [
            ltm.handle_message(mock_event_factory(raw_idx=i, text=t))
            for i, t in enumerate(texts)
        ]
        await asyncio.gather(*tasks)

        raw = list(ltm.raw_records["group_123"])
        assert len(raw) == 5
        for t in texts:
            assert any(t in s for s in raw)

    @pytest.mark.asyncio
    async def test_concurrent_handle_keeps_lock_integrity(self, ltm, mock_event_factory):
        """并发 handle 后 raw_records 无交错损坏。"""
        import asyncio

        async def record_with_delay(text, delay: float = 0):
            await asyncio.sleep(delay)
            await ltm.handle_message(
                mock_event_factory(raw_idx=0, text=text)
            )

        await asyncio.gather(
            record_with_delay("a", 0.01),
            record_with_delay("b", 0.02),
            record_with_delay("c", 0.0),
        )

        raw = list(ltm.raw_records["group_123"])
        assert len(raw) == 3
        assert all(any(t in s for s in raw) for t in ["a", "b", "c"])


# =============================================================================
# _split_into_rounds
# =============================================================================


class TestSplitIntoRounds:
    def test_empty(self):
        assert _split_into_rounds([]) == []

    def test_single_user(self):
        rounds = _split_into_rounds([{"role": "user", "content": "hi"}])
        assert len(rounds) == 1
        assert len(rounds[0]) == 1

    def test_user_assistant_single_round(self):
        ctxs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        rounds = _split_into_rounds(ctxs)
        assert len(rounds) == 1
        assert len(rounds[0]) == 2

    def test_multi_round(self):
        ctxs = [
            {"role": "user", "content": "r1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "r2"},
            {"role": "assistant", "content": "a2"},
        ]
        rounds = _split_into_rounds(ctxs)
        assert len(rounds) == 2
        assert len(rounds[0]) == 2
        assert len(rounds[1]) == 2
        assert rounds[0][0]["content"] == "r1"
        assert rounds[1][0]["content"] == "r2"

    def test_tool_chain_single_round(self):
        ctxs = [
            {"role": "user", "content": "@bot weather"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]},
            {"role": "tool", "tool_call_id": "c1", "content": "sunny"},
            {"role": "assistant", "content": "it's sunny"},
        ]
        rounds = _split_into_rounds(ctxs)
        assert len(rounds) == 1
        assert len(rounds[0]) == 4  # tool chain stays together

    def test_multi_step_tool_chain(self):
        ctxs = [
            {"role": "user", "content": "@bot complex"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]},
            {"role": "tool", "tool_call_id": "c1", "content": "r1"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c2"}]},
            {"role": "tool", "tool_call_id": "c2", "content": "r2"},
            {"role": "assistant", "content": "done"},
        ]
        rounds = _split_into_rounds(ctxs)
        assert len(rounds) == 1
        assert len(rounds[0]) == 6  # multi-step tool chain in one round

    def test_two_rounds_with_tools(self):
        ctxs = [
            {"role": "user", "content": "@bot weather"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]},
            {"role": "tool", "tool_call_id": "c1", "content": "sunny"},
            {"role": "assistant", "content": "it's sunny"},
            {"role": "user", "content": "@bot search"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c2"}]},
            {"role": "tool", "tool_call_id": "c2", "content": "results"},
            {"role": "assistant", "content": "done"},
        ]
        rounds = _split_into_rounds(ctxs)
        assert len(rounds) == 2
        assert len(rounds[0]) == 4
        assert len(rounds[1]) == 4

    def test_starts_with_assistant(self):
        """Defensive: first segment isn't user."""
        rounds = _split_into_rounds([{"role": "assistant", "content": "orphan"}])
        assert len(rounds) == 1
        assert rounds[0][0]["role"] == "assistant"

    def test_consecutive_users(self):
        """Two user segments in a row → second starts new round."""
        ctxs = [
            {"role": "user", "content": "u1"},
            {"role": "user", "content": "u2"},
            {"role": "assistant", "content": "a1"},
        ]
        rounds = _split_into_rounds(ctxs)
        assert len(rounds) == 2
        assert rounds[0] == [{"role": "user", "content": "u1"}]
        assert rounds[1] == [
            {"role": "user", "content": "u2"},
            {"role": "assistant", "content": "a1"},
        ]


# =============================================================================
# _rounds_to_text
# =============================================================================


class TestRoundsToText:
    def test_empty(self):
        assert _rounds_to_text([]) == ""

    def test_single_round(self):
        rounds = [
            [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ],
        ]
        text = _rounds_to_text(rounds)
        assert "--- Round 1 ---" in text
        assert "[user] hi" in text
        assert "[assistant] hello" in text

    def test_multi_round(self):
        rounds = [
            [{"role": "user", "content": "r1"}],
            [{"role": "assistant", "content": "a1"}],
        ]
        text = _rounds_to_text(rounds)
        assert "--- Round 1 ---" in text
        assert "--- Round 2 ---" in text

    def test_tool_calls_serialized(self):
        """tool_calls (list) is json.dumps-ed, not crashing."""
        rounds = [
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{"id": "c1", "function": {"name": "f"}}],
                },
            ],
        ]
        text = _rounds_to_text(rounds)
        assert '"id"' in text  # json-serialized
        assert "c1" in text


# =============================================================================
# LTM truncation compaction
# =============================================================================


class TestLTMTruncationCompaction:
    @pytest.fixture
    def mock_event(self):
        from unittest.mock import MagicMock
        from astrbot.api.event import AstrMessageEvent
        from astrbot.api.platform import MessageType
        event = MagicMock(spec=AstrMessageEvent)
        event.unified_msg_origin = "group_123"
        event.get_message_type.return_value = MessageType.GROUP_MESSAGE
        event.get_extra.return_value = 0
        event.get_messages.return_value = []
        event.message_obj = MagicMock()
        event.message_obj.sender_nickname = "小明"
        return event

    def make_contexts(self, n_rounds: int) -> list[dict]:
        """Build N simple user→assistant rounds."""
        ctxs = []
        for i in range(n_rounds):
            ctxs.append({"role": "user", "content": f"q{i}"})
            ctxs.append({"role": "assistant", "content": f"a{i}"})
        return ctxs

    @pytest.mark.asyncio
    async def test_no_truncation_when_under_limit(self, mock_event):
        from astrbot.builtin_stars.astrbot.long_term_memory import LongTermMemory
        from unittest.mock import MagicMock

        ctx = MagicMock()
        ctx.get_config.return_value = {
            "provider_ltm_settings": {
                "image_caption": False, "image_caption_provider_id": "",
                "active_reply": {"enable": False, "method": "possibility_reply",
                                 "possibility_reply": 0.0, "prompt": "", "whitelist": []},
                "ltm_compaction_strategy": "truncate",
                "ltm_max_rounds": 10,
                "ltm_truncate_drop_rounds": 5,
            },
            "provider_settings": {"image_caption_prompt": ""},
        }
        ltm = LongTermMemory(MagicMock(), ctx)
        umo = mock_event.unified_msg_origin

        # 5 rounds → not over 10 limit
        ltm.contexts[umo] = self.make_contexts(5)
        rounds_before = _split_into_rounds(ltm.contexts[umo])

        cfg = ltm.cfg(mock_event)
        if len(rounds_before) > cfg["ltm_max_rounds"]:
            kept = rounds_before[cfg["ltm_truncate_drop_rounds"] :]
            ltm.contexts[umo] = [seg for rnd in kept for seg in rnd]

        rounds_after = _split_into_rounds(ltm.contexts[umo])
        assert len(rounds_after) == 5
        assert rounds_after[0][0]["content"] == "q0"

    @pytest.mark.asyncio
    async def test_truncation_burst_drop(self, mock_event):
        """超过 ltm_max_rounds 时从前面弹掉 ltm_truncate_drop_rounds 轮。"""
        from astrbot.builtin_stars.astrbot.long_term_memory import LongTermMemory
        from unittest.mock import MagicMock

        ctx = MagicMock()
        ctx.get_config.return_value = {
            "provider_ltm_settings": {
                "image_caption": False, "image_caption_provider_id": "",
                "active_reply": {"enable": False, "method": "possibility_reply",
                                 "possibility_reply": 0.0, "prompt": "", "whitelist": []},
                "ltm_compaction_strategy": "truncate",
                "ltm_max_rounds": 10,
                "ltm_truncate_drop_rounds": 4,
            },
            "provider_settings": {"image_caption_prompt": ""},
        }
        ltm = LongTermMemory(MagicMock(), ctx)
        umo = mock_event.unified_msg_origin

        # 12 rounds → over 10 → drop 4 from front → 8 remain
        ltm.contexts[umo] = self.make_contexts(12)
        rounds_before = _split_into_rounds(ltm.contexts[umo])

        cfg = ltm.cfg(mock_event)
        if len(rounds_before) > cfg["ltm_max_rounds"]:
            kept = rounds_before[cfg["ltm_truncate_drop_rounds"] :]
            ltm.contexts[umo] = [seg for rnd in kept for seg in rnd]

        rounds_after = _split_into_rounds(ltm.contexts[umo])
        assert len(rounds_after) == 8
        # first retained should be q4 (index 4 after dropping 0-3)
        assert rounds_after[0][0]["content"] == "q4"

    @pytest.mark.asyncio
    async def test_truncation_burst_drop_huge_drop(self, mock_event):
        """drop_rounds >= total 时保留最后 1 轮（防御边界）。"""
        from astrbot.builtin_stars.astrbot.long_term_memory import LongTermMemory
        from unittest.mock import MagicMock

        ctx = MagicMock()
        ctx.get_config.return_value = {
            "provider_ltm_settings": {
                "image_caption": False, "image_caption_provider_id": "",
                "active_reply": {"enable": False, "method": "possibility_reply",
                                 "possibility_reply": 0.0, "prompt": "", "whitelist": []},
                "ltm_compaction_strategy": "truncate",
                "ltm_max_rounds": 5,
                "ltm_truncate_drop_rounds": 50,
            },
            "provider_settings": {"image_caption_prompt": ""},
        }
        ltm = LongTermMemory(MagicMock(), ctx)
        umo = mock_event.unified_msg_origin

        ltm.contexts[umo] = self.make_contexts(10)
        rounds_before = _split_into_rounds(ltm.contexts[umo])

        cfg = ltm.cfg(mock_event)
        if len(rounds_before) > cfg["ltm_max_rounds"]:
            safe_drop = min(cfg["ltm_truncate_drop_rounds"], len(rounds_before) - 1)
            kept = rounds_before[safe_drop:]
            ltm.contexts[umo] = [seg for rnd in kept for seg in rnd]

        rounds_after = _split_into_rounds(ltm.contexts[umo])
        # drop=50 but only 10 exist → safe_drop=9, keeps last 1 round
        assert len(rounds_after) == 1

    @pytest.mark.asyncio
    async def test_tool_chain_not_split(self, mock_event):
        """截断不应拆散工具链。"""
        from astrbot.builtin_stars.astrbot.long_term_memory import LongTermMemory
        from unittest.mock import MagicMock

        ctx = MagicMock()
        ctx.get_config.return_value = {
            "provider_ltm_settings": {
                "image_caption": False, "image_caption_provider_id": "",
                "active_reply": {"enable": False, "method": "possibility_reply",
                                 "possibility_reply": 0.0, "prompt": "", "whitelist": []},
                "ltm_compaction_strategy": "truncate",
                "ltm_max_rounds": 2,
                "ltm_truncate_drop_rounds": 2,
            },
            "provider_settings": {"image_caption_prompt": ""},
        }
        ltm = LongTermMemory(MagicMock(), ctx)
        umo = mock_event.unified_msg_origin

        # 3 rounds, last one has tool chain
        ctxs = [
            {"role": "user", "content": "q0"},
            {"role": "assistant", "content": "a0"},
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]},
            {"role": "tool", "tool_call_id": "c1", "content": "result"},
            {"role": "assistant", "content": "final"},
        ]
        ltm.contexts[umo] = ctxs

        rounds_before = _split_into_rounds(ltm.contexts[umo])
        cfg = ltm.cfg(mock_event)
        if len(rounds_before) > cfg["ltm_max_rounds"]:
            kept = rounds_before[cfg["ltm_truncate_drop_rounds"] :]
            ltm.contexts[umo] = [seg for rnd in kept for seg in rnd]

        rounds_after = _split_into_rounds(ltm.contexts[umo])
        assert len(rounds_after) == 1
        # round preserved should have all 4 tool-chain segs intact
        assert len(rounds_after[0]) == 4
        # verify the tool message is there
        assert rounds_after[0][2]["tool_call_id"] == "c1"


# =============================================================================
# Summary injection (on_req_llm)
# =============================================================================


class TestSummaryInjection:
    @pytest.mark.asyncio
    async def test_summary_injected_when_present(self):
        from unittest.mock import MagicMock
        from astrbot.api.provider import ProviderRequest
        from astrbot.builtin_stars.astrbot.long_term_memory import LongTermMemory

        ctx = MagicMock()
        ctx.get_config.return_value = {
            "provider_ltm_settings": {
                "image_caption": False, "image_caption_provider_id": "",
                "active_reply": {"enable": False, "method": "possibility_reply",
                                 "possibility_reply": 0.0, "prompt": "", "whitelist": []},
                "ltm_compaction_strategy": "truncate",
                "ltm_max_rounds": 80,
            },
            "provider_settings": {"image_caption_prompt": ""},
        }
        ltm = LongTermMemory(MagicMock(), ctx)
        umo = "group_123"
        ltm.raw_records[umo].append("[小明/14:30]: @bot hi")
        ltm._raw_cursor[umo] = 0
        ltm.summaries[umo] = "Test summary text"

        event = MagicMock()
        event.unified_msg_origin = umo
        event.get_extra.return_value = 0

        req = ProviderRequest()
        req.contexts = [{"role": "user", "content": "persona dial"}]

        # simulate on_req_llm injection
        existing = req.contexts or []
        ctxs = list(existing)
        summary = ltm.summaries.get(umo, "")
        if summary:
            ctxs.append({
                "role": "system",
                "content": "Long-term group memory summary:\n" + summary,
            })
        ctxs.extend(ltm.contexts.get(umo, []))
        req.contexts = ctxs

        # persona dialog still present
        assert req.contexts[0]["role"] == "user"
        assert req.contexts[0]["content"] == "persona dial"
        # summary injected after persona, before LTM contexts
        assert req.contexts[1]["role"] == "system"
        assert "Test summary text" in req.contexts[1]["content"]

    @pytest.mark.asyncio
    async def test_no_summary_when_empty(self):
        from unittest.mock import MagicMock
        from astrbot.api.provider import ProviderRequest
        from astrbot.builtin_stars.astrbot.long_term_memory import LongTermMemory

        ctx = MagicMock()
        ctx.get_config.return_value = {
            "provider_ltm_settings": {
                "image_caption": False, "image_caption_provider_id": "",
                "active_reply": {"enable": False, "method": "possibility_reply",
                                 "possibility_reply": 0.0, "prompt": "", "whitelist": []},
                "ltm_compaction_strategy": "truncate",
                "ltm_max_rounds": 80,
            },
            "provider_settings": {"image_caption_prompt": ""},
        }
        ltm = LongTermMemory(MagicMock(), ctx)
        umo = "group_123"
        ltm.raw_records[umo].append("[小明/14:30]: @bot hi")
        ltm._raw_cursor[umo] = 0

        event = MagicMock()
        event.unified_msg_origin = umo
        event.get_extra.return_value = 0

        req = ProviderRequest()
        req.contexts = [{"role": "user", "content": "persona dial"}]

        existing = req.contexts or []
        ctxs = list(existing)
        summary = ltm.summaries.get(umo, "")
        if summary:
            ctxs.append({"role": "system", "content": "..."})
        ctxs.extend(ltm.contexts.get(umo, []))
        req.contexts = ctxs

        # no system summary injected
        assert all(s["role"] != "system" for s in req.contexts)


# =============================================================================
# remove_session cleanup
# =============================================================================


class TestRemoveSessionCleanup:
    @pytest.mark.asyncio
    async def test_summaries_cleaned(self, mock_event):
        from astrbot.builtin_stars.astrbot.long_term_memory import LongTermMemory
        from unittest.mock import MagicMock

        ctx = MagicMock()
        ctx.get_config.return_value = {
            "provider_ltm_settings": {
                "image_caption": False, "image_caption_provider_id": "",
                "active_reply": {"enable": False, "method": "possibility_reply",
                                 "possibility_reply": 0.0, "prompt": "", "whitelist": []},
                "ltm_compaction_strategy": "truncate",
                "ltm_max_rounds": 80,
            },
            "provider_settings": {"image_caption_prompt": ""},
        }
        ltm = LongTermMemory(MagicMock(), ctx)
        umo = mock_event.unified_msg_origin
        ltm.summaries[umo] = "test"
        ltm._persisted_tool_call_ids[umo].add("c1")
        ltm._persisted_tool_result_ids[umo].add("c1")
        ltm.raw_records[umo].append("[小明/14:30]: hi")

        await ltm.remove_session(mock_event)

        assert umo not in ltm.summaries
        assert umo not in ltm._persisted_tool_call_ids
        assert umo not in ltm._persisted_tool_result_ids
        assert umo not in ltm.raw_records


# =============================================================================
# LLM summary error paths
# =============================================================================


class TestLLMSummaryErrorPath:
    @pytest.mark.asyncio
    async def test_missing_provider_does_not_crash(self, mock_event):
        """provider_id 不存在时打 warning，不崩。"""
        from astrbot.builtin_stars.astrbot.long_term_memory import LongTermMemory
        from unittest.mock import MagicMock

        ctx = MagicMock()
        ctx.get_config.return_value = {
            "provider_ltm_settings": {
                "image_caption": False, "image_caption_provider_id": "",
                "active_reply": {"enable": False, "method": "possibility_reply",
                                 "possibility_reply": 0.0, "prompt": "", "whitelist": []},
                "ltm_compaction_strategy": "llm_summary",
                "ltm_summary_provider_id": "nonexistent",
                "ltm_summary_keep_recent_rounds": 2,
                "ltm_summary_prompt": "",
            },
            "provider_settings": {"image_caption_prompt": ""},
        }
        ctx.get_provider_by_id.return_value = None

        ltm = LongTermMemory(MagicMock(), ctx)
        umo = mock_event.unified_msg_origin
        ltm.raw_records[umo].append("[小明/14:30]: hi")
        ltm._raw_cursor[umo] = 0

        # Build 5 rounds of contexts
        ctxs = []
        for i in range(5):
            ctxs.append({"role": "user", "content": f"q{i}"})
            ctxs.append({"role": "assistant", "content": f"a{i}"})
        ltm.contexts[umo] = ctxs

        rounds = _split_into_rounds(ctxs)
        # Should NOT crash — just return without modifying
        await ltm._compact_with_llm_summary(
            event=mock_event,
            provider_id="nonexistent",
            keep_recent=2,
            prompt="",
            rounds=rounds,
        )
        # contexts unchanged after failed summary attempt
        assert len(ltm.contexts[umo]) == 10

    @pytest.mark.asyncio
    async def test_below_keep_recent_no_op(self, mock_event):
        """rounds <= keep_recent 时不触发压缩。"""
        from astrbot.builtin_stars.astrbot.long_term_memory import LongTermMemory
        from unittest.mock import MagicMock

        ctx = MagicMock()
        ctx.get_config.return_value = {}
        ltm = LongTermMemory(MagicMock(), ctx)
        umo = mock_event.unified_msg_origin

        ctxs = [
            {"role": "user", "content": "q0"},
            {"role": "assistant", "content": "a0"},
        ]
        ltm.contexts[umo] = ctxs
        original_len = len(ltm.contexts[umo])

        rounds = _split_into_rounds(ctxs)
        await ltm._compact_with_llm_summary(
            event=mock_event,
            provider_id="some_id",
            keep_recent=5,
            prompt="",
            rounds=rounds,
        )
        # 1 round < 5 keep_recent → no-op
        assert len(ltm.contexts[umo]) == original_len

    @pytest.mark.asyncio
    async def test_empty_summary_response_is_no_op(self, mock_event):
        """LLM 返回空文本时不得覆盖 context/summary，并设置冷却期。"""
        from astrbot.builtin_stars.astrbot.long_term_memory import (
            LongTermMemory,
            SUMMARY_RETRY_COOLDOWN,
        )
        from astrbot.api.provider import Provider
        from unittest.mock import MagicMock, AsyncMock

        fake_resp = MagicMock()
        fake_resp.completion_text = "   "  # whitespace-only

        fake_provider = MagicMock(spec=Provider)
        fake_provider.text_chat = AsyncMock(return_value=fake_resp)

        ctx = MagicMock()
        ctx.get_config.return_value = {}
        ctx.get_provider_by_id.return_value = fake_provider

        ltm = LongTermMemory(MagicMock(), ctx)
        umo = mock_event.unified_msg_origin

        old_ctxs = [
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "old reply"},
            {"role": "user", "content": "new"},
            {"role": "assistant", "content": "new reply"},
        ]
        ltm.contexts[umo] = old_ctxs
        ltm.summaries[umo] = "existing summary"

        rounds = _split_into_rounds(old_ctxs)  # 2 rounds

        # keep_recent=1 → old_rounds has 1 round, provider will be called
        await ltm._compact_with_llm_summary(
            event=mock_event,
            provider_id="test_provider",
            keep_recent=1,
            prompt="",
            rounds=rounds,
        )

        # Both must be untouched
        assert ltm.contexts[umo] is old_ctxs
        assert ltm.summaries[umo] == "existing summary"
        # Cooldown set
        assert ltm._summary_next_retry[umo] == len(rounds) + SUMMARY_RETRY_COOLDOWN

    @pytest.mark.asyncio
    async def test_summary_exception_sets_cooldown(self, mock_event):
        """LLM 调用抛异常时设置冷却期。"""
        from astrbot.builtin_stars.astrbot.long_term_memory import (
            LongTermMemory,
            SUMMARY_RETRY_COOLDOWN,
        )
        from astrbot.api.provider import Provider
        from unittest.mock import MagicMock, AsyncMock

        fake_provider = MagicMock(spec=Provider)
        fake_provider.text_chat = AsyncMock(side_effect=RuntimeError("boom"))

        ctx = MagicMock()
        ctx.get_config.return_value = {}
        ctx.get_provider_by_id.return_value = fake_provider

        ltm = LongTermMemory(MagicMock(), ctx)
        umo = mock_event.unified_msg_origin

        ctxs = [
            {"role": "user", "content": "q0"},
            {"role": "assistant", "content": "a0"},
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
        ]
        ltm.contexts[umo] = ctxs
        ltm.summaries[umo] = "existing summary"

        rounds = _split_into_rounds(ctxs)  # 2 rounds

        await ltm._compact_with_llm_summary(
            event=mock_event,
            provider_id="test_provider",
            keep_recent=1,
            prompt="",
            rounds=rounds,
        )

        assert ltm.contexts[umo] is ctxs
        assert ltm.summaries[umo] == "existing summary"
        assert ltm._summary_next_retry[umo] == len(rounds) + SUMMARY_RETRY_COOLDOWN

    @pytest.mark.asyncio
    async def test_summary_success_clears_cooldown(self, mock_event):
        """LLM 调用成功时清除冷却标记。"""
        from astrbot.builtin_stars.astrbot.long_term_memory import LongTermMemory
        from astrbot.api.provider import Provider
        from unittest.mock import MagicMock, AsyncMock

        fake_resp = MagicMock()
        fake_resp.completion_text = "good summary"

        fake_provider = MagicMock(spec=Provider)
        fake_provider.text_chat = AsyncMock(return_value=fake_resp)

        ctx = MagicMock()
        ctx.get_config.return_value = {}
        ctx.get_provider_by_id.return_value = fake_provider

        ltm = LongTermMemory(MagicMock(), ctx)
        umo = mock_event.unified_msg_origin
        # Pre-set cooldown to simulate a previous failure
        ltm._summary_next_retry[umo] = 999

        ctxs = [
            {"role": "user", "content": "q0"},
            {"role": "assistant", "content": "a0"},
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
        ]
        rounds = _split_into_rounds(ctxs)  # 2 rounds

        await ltm._compact_with_llm_summary(
            event=mock_event,
            provider_id="test_provider",
            keep_recent=1,
            prompt="",
            rounds=rounds,
        )

        # Cooldown cleared
        assert umo not in ltm._summary_next_retry
        assert ltm.summaries[umo] == "good summary"


# =============================================================================
# Config defaults
# =============================================================================


class TestConfigDefaults:
    @pytest.mark.asyncio
    async def test_defaults(self, mock_event):
        from astrbot.builtin_stars.astrbot.long_term_memory import LongTermMemory
        from unittest.mock import MagicMock

        ctx = MagicMock()
        ctx.get_config.return_value = {
            "provider_ltm_settings": {
                "image_caption": False, "image_caption_provider_id": "",
                "active_reply": {"enable": False, "method": "possibility_reply",
                                 "possibility_reply": 0.0, "prompt": "", "whitelist": []},
            },
            "provider_settings": {"image_caption_prompt": ""},
        }
        ltm = LongTermMemory(MagicMock(), ctx)
        cfg = ltm.cfg(mock_event)

        assert cfg["ltm_compaction_strategy"] == "truncate"
        assert cfg["ltm_max_rounds"] == 80
        assert cfg["ltm_truncate_drop_rounds"] == 50
        assert cfg["ltm_summary_trigger_rounds"] == 80
        assert cfg["ltm_summary_keep_recent_rounds"] == 30
        assert cfg["ltm_summary_provider_id"] == ""
        assert cfg["ltm_summary_prompt"] == ""
        assert cfg["ltm_raw_records_max_bytes"] == 500000
