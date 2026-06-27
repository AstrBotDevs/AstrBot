"""Tests for ResultDecorateStage long-reply auto-forward node splitting."""

import re
from unittest.mock import MagicMock, patch

import pytest

from astrbot.core.config.default import (
    FORWARD_NODE_HARD_LIMIT_DEFAULT,
    FORWARD_NODE_MAX_LENGTH_DEFAULT,
)
from astrbot.core.message.components import At, Image, Node, Nodes, Plain, Reply
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.pipeline.result_decorate.stage import ResultDecorateStage
from astrbot.core.platform.message_type import MessageType

DEFAULT_SPLIT_WORDS = ["。", "？", "！", "~", "…"]


def _make_configured_stage(
    forward_threshold: int = 100,
    forward_node_max_length: int = 50,
    forward_node_hard_limit: int = 70,
    split_words: list[str] | None = None,
):
    """Create a ResultDecorateStage with only the attributes needed for tests."""
    stage = ResultDecorateStage()
    stage.forward_threshold = forward_threshold
    stage.forward_node_max_length = forward_node_max_length
    stage.forward_node_hard_limit = forward_node_hard_limit

    _split_words = (
        list(split_words) if split_words is not None else list(DEFAULT_SPLIT_WORDS)
    )
    if "\n" not in _split_words:
        _split_words.append("\n")
    if _split_words:
        _escaped = sorted(
            [re.escape(word) for word in _split_words], key=len, reverse=True
        )
        stage.forward_split_pattern = re.compile(f"(?:{'|'.join(_escaped)})+")
    else:
        stage.forward_split_pattern = None

    # Attributes used by process()
    stage.reply_prefix = ""
    stage.content_safe_check_reply = False
    stage.content_safe_check_stage = None
    stage.show_reasoning = False
    stage.tts_trigger_probability = 0.0
    stage.reply_with_mention = False
    stage.reply_with_quote = False
    stage.t2i_word_threshold = 99999
    stage.t2i_use_network = False
    stage.t2i_active_template = "base"
    stage.enable_segmented_reply = False
    stage.only_llm_result = True
    stage.split_mode = "regex"
    stage.regex = ".*?[。？！~…]+|.+$"
    stage.split_words = list(DEFAULT_SPLIT_WORDS)
    escaped_words = sorted(
        [re.escape(w) for w in stage.split_words], key=len, reverse=True
    )
    stage.split_words_pattern = re.compile(
        f"(.*?({'|'.join(escaped_words)})|.+$)",
        re.DOTALL,
    )
    stage.words_count_threshold = 150
    stage.content_cleanup_rule = ""

    stage.ctx = MagicMock()
    stage.ctx.plugin_manager.context.get_using_tts_provider = MagicMock(
        return_value=None
    )
    stage.ctx.astrbot_config = {
        "provider_tts_settings": {"enable": False},
        "t2i": False,
        "t2i_use_file_service": False,
        "callback_api_base": "",
    }
    return stage


def _make_event(
    chain: list,
    platform_name: str = "aiocqhttp",
    message_type: MessageType = MessageType.FRIEND_MESSAGE,
):
    """Create a minimal mock event for ResultDecorateStage.process()."""
    event = MagicMock()
    event.get_platform_name = MagicMock(return_value=platform_name)
    event.get_self_id = MagicMock(return_value="123456")
    event.get_sender_id = MagicMock(return_value="987654")
    event.get_sender_name = MagicMock(return_value="User")
    event.get_message_type = MagicMock(return_value=message_type)
    event.message_obj.message_id = "msg-id"
    event.get_extra = MagicMock(return_value=None)
    event.is_stopped = MagicMock(return_value=False)
    result = MessageEventResult()
    result.chain = chain
    result.use_t2i_ = None
    result.result_content_type = MagicMock()
    result.result_content_type.value = "TEXT_RESULT"
    event.get_result = MagicMock(return_value=result)
    return event


class TestFindForwardSplitPos:
    """Tests for ResultDecorateStage._find_forward_split_pos."""

    def test_no_split_needed(self):
        pattern = re.compile(r"([。！？\n]+)")
        assert (
            ResultDecorateStage._find_forward_split_pos("short", 10, 20, pattern) == 5
        )

    def test_breakpoint_between_target_and_hard_limit(self):
        pattern = re.compile(r"([。！？\n]+)")
        text = "a" * 45 + "。" + "b" * 100
        # target=40, hard=70 -> should split at the period (position 46)
        pos = ResultDecorateStage._find_forward_split_pos(text, 40, 70, pattern)
        assert pos == 46

    def test_fall_back_to_previous_breakpoint(self):
        pattern = re.compile(r"([。！？\n]+)")
        text = "a" * 30 + "。" + "b" * 100
        # target=40, hard=70 -> no breakpoint between 40 and 70, fall back to position 31
        pos = ResultDecorateStage._find_forward_split_pos(text, 40, 70, pattern)
        assert pos == 31

    def test_hard_cut_when_no_breakpoint(self):
        pattern = re.compile(r"([。！？\n]+)")
        text = "a" * 200
        pos = ResultDecorateStage._find_forward_split_pos(text, 40, 70, pattern)
        assert pos == 70

    def test_newline_is_a_breakpoint(self):
        pattern = re.compile(r"([。！？\n]+)")
        text = "a" * 45 + "\n" + "b" * 100
        pos = ResultDecorateStage._find_forward_split_pos(text, 40, 70, pattern)
        assert pos == 46

    def test_multichar_breakpoint_crossing_target_boundary(self):
        pattern = re.compile(r"(?:END|\n)+")
        text = "a" * 49 + "END" + "b" * 100
        pos = ResultDecorateStage._find_forward_split_pos(text, 50, 70, pattern)
        assert pos == 52


class TestBuildForwardNodes:
    """Tests for ResultDecorateStage._build_forward_nodes."""

    def test_short_text_single_node(self):
        stage = _make_configured_stage()
        nodes = stage._build_forward_nodes([Plain("hello world")], "123", "Bot")
        assert len(nodes.nodes) == 1
        assert len(nodes.nodes[0].content) == 1
        assert nodes.nodes[0].content[0].text == "hello world"

    def test_long_plain_text_multiple_nodes(self):
        stage = _make_configured_stage()
        text = "x" * 200
        nodes = stage._build_forward_nodes([Plain(text)], "123", "Bot")
        assert len(nodes.nodes) > 1
        total = 0
        for node in nodes.nodes:
            plain_len = sum(len(c.text) for c in node.content if isinstance(c, Plain))
            assert plain_len <= stage.forward_node_hard_limit
            total += plain_len
        assert total == len(text)

    def test_breakpoint_before_target_is_used_when_no_later_breakpoint(self):
        stage = _make_configured_stage()
        # 40 chars, then a period, then more text. target=50, hard=70.
        # There is no breakpoint after target, so it falls back to the period.
        text = "x" * 40 + "。" + "y" * 100
        nodes = stage._build_forward_nodes([Plain(text)], "123", "Bot")
        assert len(nodes.nodes) > 1
        first_plain = sum(
            len(c.text) for c in nodes.nodes[0].content if isinstance(c, Plain)
        )
        # Should split after the period (41 chars), not hard-cut at 50 or 70.
        assert first_plain == 41

    def test_fall_back_to_breakpoint_before_target(self):
        stage = _make_configured_stage()
        # Breakpoint at 30, then no breakpoint until past hard limit.
        text = "x" * 30 + "。" + "y" * 200
        nodes = stage._build_forward_nodes([Plain(text)], "123", "Bot")
        first_plain = sum(
            len(c.text) for c in nodes.nodes[0].content if isinstance(c, Plain)
        )
        # Should fall back to the breakpoint at 31.
        assert first_plain == 31

    def test_no_breakpoint_hard_cut(self):
        stage = _make_configured_stage()
        text = "x" * 200
        nodes = stage._build_forward_nodes([Plain(text)], "123", "Bot")
        first_plain = sum(
            len(c.text) for c in nodes.nodes[0].content if isinstance(c, Plain)
        )
        assert first_plain == stage.forward_node_hard_limit

    def test_reply_at_only_in_first_node(self):
        stage = _make_configured_stage()
        text = "x" * 200
        nodes = stage._build_forward_nodes(
            [Reply(id="r1"), At(qq="987"), Plain(text)],
            "123",
            "Bot",
        )
        assert len(nodes.nodes) > 1
        assert any(isinstance(c, Reply) for c in nodes.nodes[0].content)
        assert any(isinstance(c, At) for c in nodes.nodes[0].content)
        for node in nodes.nodes[1:]:
            assert not any(isinstance(c, Reply) for c in node.content)
            assert not any(isinstance(c, At) for c in node.content)

    def test_later_reply_at_are_preserved_once(self):
        stage = _make_configured_stage()
        nodes = stage._build_forward_nodes(
            [Plain("x" * 200), At(qq="987"), Reply(id="r1")],
            "123",
            "Bot",
        )
        at_count = sum(
            1 for node in nodes.nodes for c in node.content if isinstance(c, At)
        )
        reply_count = sum(
            1 for node in nodes.nodes for c in node.content if isinstance(c, Reply)
        )
        assert at_count == 1
        assert reply_count == 1
        assert any(isinstance(c, At) for c in nodes.nodes[-1].content)
        assert any(isinstance(c, Reply) for c in nodes.nodes[-1].content)

    def test_image_not_duplicated(self):
        stage = _make_configured_stage()
        text = "x" * 200
        image = Image(file="http://example.com/img.jpg")
        nodes = stage._build_forward_nodes(
            [Plain(text), image],
            "123",
            "Bot",
        )
        image_count = sum(
            1 for node in nodes.nodes for c in node.content if isinstance(c, Image)
        )
        assert image_count == 1
        # Image should be in the last node because it follows the Plain text.
        assert any(isinstance(c, Image) for c in nodes.nodes[-1].content)

    def test_image_before_text_is_not_duplicated(self):
        stage = _make_configured_stage()
        text = "x" * 200
        image = Image(file="http://example.com/img.jpg")
        nodes = stage._build_forward_nodes(
            [image, Plain(text)],
            "123",
            "Bot",
        )
        image_count = sum(
            1 for node in nodes.nodes for c in node.content if isinstance(c, Image)
        )
        assert image_count == 1
        # Image should be in the first node because it precedes the Plain text.
        assert any(isinstance(c, Image) for c in nodes.nodes[0].content)
        # Text was split across nodes.
        assert len(nodes.nodes) > 1

    def test_chinese_punctuation_and_newline_breakpoints(self):
        stage = _make_configured_stage()
        # 30 chars, question mark, 30 chars, newline, 30 chars, exclamation, then more.
        text = "x" * 30 + "？" + "y" * 30 + "\n" + "z" * 30 + "！" + "w" * 200
        nodes = stage._build_forward_nodes([Plain(text)], "123", "Bot")
        assert len(nodes.nodes) > 1
        first_plain = sum(
            len(c.text) for c in nodes.nodes[0].content if isinstance(c, Plain)
        )
        # The question mark is before target=50, so the algorithm keeps searching
        # and finds the newline at position 62 (within hard=70) first.
        assert first_plain == 62


class TestProcessForward:
    """Tests for ResultDecorateStage.process() forward conversion behavior."""

    @pytest.mark.asyncio
    async def test_below_forward_threshold_no_conversion(self):
        stage = _make_configured_stage(forward_threshold=100)
        event = _make_event([Plain("short")])
        with patch(
            "astrbot.core.pipeline.result_decorate.stage.SessionServiceManager.should_process_tts_request",
            return_value=False,
        ):
            async for _ in stage.process(event):
                pass
        result = event.get_result()
        assert len(result.chain) == 1
        assert isinstance(result.chain[0], Plain)

    @pytest.mark.asyncio
    async def test_above_threshold_single_node_when_under_hard_limit(self):
        stage = _make_configured_stage(
            forward_threshold=10,
            forward_node_max_length=200,
            forward_node_hard_limit=250,
        )
        event = _make_event([Plain("x" * 100)])
        with patch(
            "astrbot.core.pipeline.result_decorate.stage.SessionServiceManager.should_process_tts_request",
            return_value=False,
        ):
            async for _ in stage.process(event):
                pass
        result = event.get_result()
        assert len(result.chain) == 1
        assert isinstance(result.chain[0], Nodes)
        assert len(result.chain[0].nodes) == 1

    @pytest.mark.asyncio
    async def test_above_threshold_multiple_nodes(self):
        stage = _make_configured_stage(
            forward_threshold=10,
            forward_node_max_length=50,
            forward_node_hard_limit=70,
        )
        event = _make_event([Plain("x" * 200)])
        with patch(
            "astrbot.core.pipeline.result_decorate.stage.SessionServiceManager.should_process_tts_request",
            return_value=False,
        ):
            async for _ in stage.process(event):
                pass
        result = event.get_result()
        assert len(result.chain) == 1
        assert isinstance(result.chain[0], Nodes)
        assert len(result.chain[0].nodes) > 1
        for node in result.chain[0].nodes:
            plain_len = sum(len(c.text) for c in node.content if isinstance(c, Plain))
            assert plain_len <= stage.forward_node_hard_limit

    @pytest.mark.asyncio
    async def test_non_aiocqhttp_platform_not_converted(self):
        stage = _make_configured_stage(
            forward_threshold=10,
            forward_node_max_length=50,
            forward_node_hard_limit=70,
        )
        event = _make_event([Plain("x" * 200)], platform_name="telegram")
        with patch(
            "astrbot.core.pipeline.result_decorate.stage.SessionServiceManager.should_process_tts_request",
            return_value=False,
        ):
            async for _ in stage.process(event):
                pass
        result = event.get_result()
        assert len(result.chain) == 1
        assert isinstance(result.chain[0], Plain)

    @pytest.mark.asyncio
    async def test_existing_nodes_are_skipped(self):
        stage = _make_configured_stage(
            forward_threshold=10,
            forward_node_max_length=50,
            forward_node_hard_limit=70,
        )
        existing_node = Node(uin="123", name="Bot", content=[Plain("x" * 200)])
        event = _make_event([existing_node])
        with patch(
            "astrbot.core.pipeline.result_decorate.stage.SessionServiceManager.should_process_tts_request",
            return_value=False,
        ):
            async for _ in stage.process(event):
                pass
        result = event.get_result()
        assert len(result.chain) == 1
        assert isinstance(result.chain[0], Node)

    @pytest.mark.asyncio
    async def test_existing_nodes_object_is_skipped(self):
        stage = _make_configured_stage(
            forward_threshold=10,
            forward_node_max_length=50,
            forward_node_hard_limit=70,
        )
        existing_nodes = Nodes(
            [Node(uin="123", name="Bot", content=[Plain("x" * 200)])]
        )
        event = _make_event([existing_nodes])
        with patch(
            "astrbot.core.pipeline.result_decorate.stage.SessionServiceManager.should_process_tts_request",
            return_value=False,
        ):
            async for _ in stage.process(event):
                pass
        result = event.get_result()
        assert len(result.chain) == 1
        assert isinstance(result.chain[0], Nodes)

    @pytest.mark.asyncio
    async def test_custom_config_affects_splitting(self):
        stage = _make_configured_stage(
            forward_threshold=10,
            forward_node_max_length=30,
            forward_node_hard_limit=40,
        )
        event = _make_event([Plain("x" * 100)])
        with patch(
            "astrbot.core.pipeline.result_decorate.stage.SessionServiceManager.should_process_tts_request",
            return_value=False,
        ):
            async for _ in stage.process(event):
                pass
        result = event.get_result()
        nodes = result.chain[0].nodes
        assert len(nodes) >= 3  # 100 chars with max 40 per node
        for node in nodes:
            plain_len = sum(len(c.text) for c in node.content if isinstance(c, Plain))
            assert plain_len <= 40


class TestConfigSanitization:
    """Tests for invalid forward node config values."""

    def test_max_length_greater_than_hard_limit_is_sanitized(self):
        stage = ResultDecorateStage()
        stage.forward_threshold = 100
        stage.forward_node_max_length = 200
        stage.forward_node_hard_limit = 100
        stage.forward_split_pattern = None
        # Should not raise and should respect hard limit.
        nodes = stage._build_forward_nodes([Plain("x" * 300)], "123", "Bot")
        for node in nodes.nodes:
            plain_len = sum(len(c.text) for c in node.content if isinstance(c, Plain))
            assert plain_len <= stage.forward_node_hard_limit

    def test_zero_or_negative_limits_do_not_crash(self):
        stage = ResultDecorateStage()
        stage.forward_threshold = 100
        stage.forward_node_max_length = 0
        stage.forward_node_hard_limit = 0
        stage.forward_split_pattern = None
        nodes = stage._build_forward_nodes([Plain("x" * 300)], "123", "Bot")
        assert len(nodes.nodes) >= 1

    @pytest.mark.asyncio
    async def test_initialize_sanitizes_invalid_config(self):
        from astrbot.core.pipeline.context import PipelineContext

        cfg = {
            "platform_settings": {
                "reply_prefix": "",
                "reply_with_mention": False,
                "reply_with_quote": False,
                "forward_threshold": 100,
                "forward_node_max_length": -100,
                "forward_node_hard_limit": 0,
                "segmented_reply": {
                    "enable": False,
                    "only_llm_result": True,
                    "words_count_threshold": 150,
                    "split_mode": "regex",
                    "regex": ".*?[。？！~…]+|.+$",
                    "split_words": ["。", "？", "！", "~", "…"],
                    "content_cleanup_rule": "",
                },
            },
            "provider_tts_settings": {"enable": False, "trigger_probability": 1},
            "provider_settings": {"display_reasoning_text": False},
            "content_safety": {"also_use_in_response": False},
            "t2i_word_threshold": 150,
            "t2i_strategy": "remote",
            "t2i": False,
            "t2i_active_template": "base",
        }
        ctx = PipelineContext(
            astrbot_config=cfg,
            plugin_manager=MagicMock(),
            astrbot_config_id="test",
        )
        stage = ResultDecorateStage()
        await stage.initialize(ctx)
        assert stage.forward_node_max_length == FORWARD_NODE_MAX_LENGTH_DEFAULT
        assert stage.forward_node_hard_limit == FORWARD_NODE_HARD_LIMIT_DEFAULT

    @pytest.mark.asyncio
    async def test_initialize_converges_max_greater_than_hard(self):
        from astrbot.core.pipeline.context import PipelineContext

        cfg = {
            "platform_settings": {
                "reply_prefix": "",
                "reply_with_mention": False,
                "reply_with_quote": False,
                "forward_threshold": 100,
                "forward_node_max_length": 5000,
                "forward_node_hard_limit": 100,
                "segmented_reply": {
                    "enable": False,
                    "only_llm_result": True,
                    "words_count_threshold": 150,
                    "split_mode": "regex",
                    "regex": ".*?[。？！~…]+|.+$",
                    "split_words": ["，"],
                    "content_cleanup_rule": "",
                },
            },
            "provider_tts_settings": {"enable": False, "trigger_probability": 1},
            "provider_settings": {"display_reasoning_text": False},
            "content_safety": {"also_use_in_response": False},
            "t2i_word_threshold": 150,
            "t2i_strategy": "remote",
            "t2i": False,
            "t2i_active_template": "base",
        }
        ctx = PipelineContext(
            astrbot_config=cfg,
            plugin_manager=MagicMock(),
            astrbot_config_id="test",
        )
        stage = ResultDecorateStage()
        await stage.initialize(ctx)
        assert stage.forward_node_max_length == 100
        assert stage.forward_node_hard_limit == 100
        # Custom split_words are used and newline is appended.
        assert stage.forward_split_pattern is not None
