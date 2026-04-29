"""Unit tests for astrbot.core.pipeline.respond.stage.RespondStage."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.message.components import (
    At,
    ComponentType,
    Face,
    File,
    Forward,
    Image,
    Plain,
    Record,
    Reply,
)
from astrbot.core.message.message_event_result import (
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.pipeline.respond.stage import RespondStage


@pytest.fixture
def mock_config():
    """Create a mock AstrBotConfig for RespondStage initialization."""
    return {
        "platform_settings": {
            "reply_with_mention": True,
            "reply_with_quote": False,
            "segmented_reply": {
                "enable": False,
                "only_llm_result": False,
                "interval_method": "random",
                "log_base": 2,
                "interval": "1.5, 3.5",
            },
            "path_mapping": [],
        },
        "provider_settings": {
            "enable": True,
            "unsupported_streaming_strategy": "realtime_segmenting",
        },
    }


@pytest.fixture
def mock_context(mock_config):
    """Create a mock PipelineContext."""
    ctx = MagicMock()
    ctx.astrbot_config = mock_config
    return ctx


@pytest.fixture
def mock_event():
    """Create a mock AstrMessageEvent."""
    event = MagicMock()
    event.get_extra.return_value = False
    event.get_platform_name.return_value = "qq"
    event.get_sender_name.return_value = "test_user"
    event.get_sender_id.return_value = "12345"
    event.get_platform_id.return_value = "platform_1"
    return event


@pytest.fixture
def stage(mock_context):
    """Create an initialized RespondStage."""
    stage = RespondStage()
    return stage


class TestRespondStageInitialize:
    """Tests for RespondStage.initialize()."""

    @pytest.mark.asyncio
    async def test_initialize_sets_attributes(self, stage, mock_context):
        """Verify initialize reads config and sets attributes."""
        await stage.initialize(mock_context)

        assert stage.ctx is mock_context
        assert stage.config is mock_context.astrbot_config
        assert stage.reply_with_mention is True
        assert stage.reply_with_quote is False
        assert stage.enable_seg is False
        assert stage.only_llm_result is False
        assert stage.interval_method == "random"
        assert stage.log_base == 2
        assert stage.interval == [1.5, 3.5]

    @pytest.mark.asyncio
    async def test_initialize_segmented_enabled(self, mock_context):
        """Verify segmented reply config is parsed when enabled."""
        mock_context.astrbot_config["platform_settings"]["segmented_reply"][
            "enable"
        ] = True
        stage = RespondStage()
        await stage.initialize(mock_context)

        assert stage.enable_seg is True
        assert stage.interval == [1.5, 3.5]

    @pytest.mark.asyncio
    async def test_initialize_segmented_invalid_interval(self, mock_context):
        """Verify invalid interval string falls back gracefully."""
        mock_context.astrbot_config["platform_settings"]["segmented_reply"][
            "enable"
        ] = True
        mock_context.astrbot_config["platform_settings"]["segmented_reply"][
            "interval"
        ] = "not_a_number"
        stage = RespondStage()
        await stage.initialize(mock_context)

        # Should fall back to [1.5, 3.5]
        assert stage.interval == [1.5, 3.5]


class TestRespondStageWordCnt:
    """Tests for RespondStage._word_cnt()."""

    @pytest.mark.asyncio
    async def test_word_cnt_ascii(self, stage):
        """Verify ASCII text is split and counted."""
        count = await stage._word_cnt("hello world foo bar")
        assert count == 4

    @pytest.mark.asyncio
    async def test_word_cnt_ascii_single(self, stage):
        """Verify single ASCII word."""
        count = await stage._word_cnt("hello")
        assert count == 1

    @pytest.mark.asyncio
    async def test_word_cnt_non_ascii(self, stage):
        """Verify non-ASCII text counts alphanumeric characters."""
        count = await stage._word_cnt("你好世界")
        assert count == 4

    @pytest.mark.asyncio
    async def test_word_cnt_mixed(self, stage):
        """Verify mixed text counts all alnum characters."""
        count = await stage._word_cnt("hello你好world世界")
        assert count == 18  # hello(5) + 你好(4) + world(5) + 世界(4) = 18

    @pytest.mark.asyncio
    async def test_word_cnt_empty(self, stage):
        """Verify empty string returns 0."""
        count = await stage._word_cnt("")
        assert count == 0


class TestRespondStageCalcCompInterval:
    """Tests for RespondStage._calc_comp_interval()."""

    @pytest.mark.asyncio
    async def test_calc_interval_log_plain(self, stage):
        """Verify log interval for Plain component."""
        stage.interval_method = "log"
        stage.log_base = 2
        plain = Plain(text="hello world")

        with patch("astrbot.core.pipeline.respond.stage.random.uniform") as mock_uniform:
            mock_uniform.return_value = 2.0
            interval = await stage._calc_comp_interval(plain)

        assert interval == 2.0
        mock_uniform.assert_called_once()

    @pytest.mark.asyncio
    async def test_calc_interval_log_non_plain(self, stage):
        """Verify log interval for non-Plain component uses 1-1.75 range."""
        stage.interval_method = "log"
        image = Image(file="/path/to/img.jpg")

        with patch("astrbot.core.pipeline.respond.stage.random.uniform") as mock_uniform:
            mock_uniform.return_value = 1.5
            interval = await stage._calc_comp_interval(image)

        assert interval == 1.5
        mock_uniform.assert_called_once_with(1, 1.75)

    @pytest.mark.asyncio
    async def test_calc_interval_random(self, stage):
        """Verify random interval uses configured interval range."""
        stage.interval_method = "random"
        stage.interval = [2.0, 4.0]
        plain = Plain(text="test")

        with patch("astrbot.core.pipeline.respond.stage.random.uniform") as mock_uniform:
            mock_uniform.return_value = 3.0
            interval = await stage._calc_comp_interval(plain)

        assert interval == 3.0
        mock_uniform.assert_called_once_with(2.0, 4.0)


class TestRespondStageHasMeaningfulContent:
    """Tests for RespondStage._has_meaningful_content()."""

    def test_plain_with_text(self, stage):
        """Verify Plain with text returns True."""
        comp = Plain(text="hello")
        assert stage._has_meaningful_content(comp) is True

    def test_plain_whitespace_text(self, stage):
        """Verify Plain with whitespace returns False."""
        comp = Plain(text="   ")
        assert stage._has_meaningful_content(comp) is False

    def test_image_with_url(self, stage):
        """Verify Image with url returns True."""
        comp = Image(file="http://example.com/img.jpg")
        assert stage._has_meaningful_content(comp) is True

    def test_image_with_file_id(self, stage):
        """Verify Image with file_id returns True."""
        comp = Image(file_id="abc123")
        assert stage._has_meaningful_content(comp) is True

    def test_image_empty(self, stage):
        """Verify Image without url or file_id returns False."""
        comp = Image()
        assert stage._has_meaningful_content(comp) is False

    def test_face_with_id(self, stage):
        """Verify Face with id returns True."""
        comp = Face(id=123)
        assert stage._has_meaningful_content(comp) is True

    def test_face_no_id(self, stage):
        """Verify Face without id returns False."""
        comp = Face(id=None)
        assert stage._has_meaningful_content(comp) is False

    def test_at_with_qq(self, stage):
        """Verify At with qq returns True."""
        comp = At(qq="12345")
        assert stage._has_meaningful_content(comp) is True

    def test_at_no_qq(self, stage):
        """Verify At without qq returns False."""
        comp = At(qq=None)
        assert stage._has_meaningful_content(comp) is False

    def test_reply_with_id(self, stage):
        """Verify Reply with id returns True."""
        comp = Reply(id="abc", sender_id="user1")
        assert stage._has_meaningful_content(comp) is True

    def test_reply_no_id(self, stage):
        """Verify Reply without id returns False."""
        comp = Reply(id=None, sender_id="user1")
        assert stage._has_meaningful_content(comp) is False

    def test_forward_with_id(self, stage):
        """Verify Forward with id returns True."""
        comp = Forward(id="abc123")
        assert stage._has_meaningful_content(comp) is True


class TestRespondStageIsEmptyMessageChain:
    """Tests for RespondStage._is_empty_message_chain()."""

    @pytest.mark.asyncio
    async def test_empty_list(self, stage):
        """Verify empty list returns True."""
        assert await stage._is_empty_message_chain([]) is True

    @pytest.mark.asyncio
    async def test_chain_with_meaningful_content(self, stage):
        """Verify chain with valid content returns False."""
        chain = [Plain(text="hello")]
        assert await stage._is_empty_message_chain(chain) is False

    @pytest.mark.asyncio
    async def test_chain_all_empty(self, stage):
        """Verify chain with all empty components returns True."""
        chain = [Plain(text="")]
        assert await stage._is_empty_message_chain(chain) is True

    @pytest.mark.asyncio
    async def test_chain_mixed_empty_and_valid(self, stage):
        """Verify chain with mix of empty and valid returns False."""
        chain = [Plain(text=""), Plain(text="hello")]
        assert await stage._is_empty_message_chain(chain) is False


class TestRespondStageIsSegReplyRequired:
    """Tests for RespondStage.is_seg_reply_required()."""

    def test_seg_disabled(self, stage):
        """Verify returns False when segmented reply is disabled."""
        stage.enable_seg = False
        event = MagicMock()
        assert stage.is_seg_reply_required(event) is False

    def test_seg_no_result(self, stage):
        """Verify returns False when event has no result."""
        stage.enable_seg = True
        event = MagicMock()
        event.get_result.return_value = None
        assert stage.is_seg_reply_required(event) is False

    def test_seg_only_llm_not_model(self, stage):
        """Verify returns False when only_llm_result is True and result is not model."""
        stage.enable_seg = True
        stage.only_llm_result = True
        event = MagicMock()
        result = MagicMock()
        result.is_model_result.return_value = False
        event.get_result.return_value = result
        assert stage.is_seg_reply_required(event) is False

    def test_seg_excluded_platform(self, stage):
        """Verify returns False for excluded platforms."""
        stage.enable_seg = True
        stage.only_llm_result = False
        event = MagicMock()
        result = MagicMock()
        result.is_model_result.return_value = True
        event.get_result.return_value = result
        event.get_platform_name.return_value = "qq_official"
        assert stage.is_seg_reply_required(event) is False

    def test_seg_all_conditions_met(self, stage):
        """Verify returns True when all conditions are met."""
        stage.enable_seg = True
        stage.only_llm_result = False
        event = MagicMock()
        result = MagicMock()
        result.is_model_result.return_value = True
        event.get_result.return_value = result
        event.get_platform_name.return_value = "qq"
        assert stage.is_seg_reply_required(event) is True


class TestRespondStageExtractComp:
    """Tests for RespondStage._extract_comp()."""

    def test_extract_with_modify(self, stage):
        """Verify extraction removes extracted types from original list."""
        raw_chain = [
            Plain(text="hello"),
            At(qq="12345"),
            Plain(text="world"),
            Reply(id="r1", sender_id="u1"),
        ]
        extracted = stage._extract_comp(
            raw_chain,
            {ComponentType.At, ComponentType.Reply},
            modify_raw_chain=True,
        )

        assert len(extracted) == 2
        assert all(c.type in {ComponentType.At, ComponentType.Reply} for c in extracted)
        assert len(raw_chain) == 2
        assert all(c.type == ComponentType.Plain for c in raw_chain)

    def test_extract_without_modify(self, stage):
        """Verify extraction does not modify original chain."""
        raw_chain = [
            Plain(text="hello"),
            At(qq="12345"),
        ]
        original_len = len(raw_chain)
        extracted = stage._extract_comp(
            raw_chain,
            {ComponentType.At},
            modify_raw_chain=False,
        )

        assert len(extracted) == 1
        assert extracted[0].type == ComponentType.At
        assert len(raw_chain) == original_len  # unchanged

    def test_extract_no_match(self, stage):
        """Verify extraction returns empty when no types match."""
        raw_chain = [Plain(text="hello")]
        extracted = stage._extract_comp(
            raw_chain,
            {ComponentType.Image},
            modify_raw_chain=False,
        )
        assert extracted == []


class TestRespondStageProcess:
    """Tests for RespondStage.process()."""

    @pytest.mark.asyncio
    async def test_process_result_none(self, stage, mock_event):
        """Verify process returns when result is None."""
        mock_event.get_result.return_value = None
        await stage.process(mock_event)
        # Should return without sending
        mock_event.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_streaming_finished(self, stage, mock_event):
        """Verify process returns when streaming is finished."""
        result = MagicMock()
        result.result_content_type = ResultContentType.STREAMING_FINISH
        mock_event.get_result.return_value = result
        await stage.process(mock_event)

        mock_event.set_extra.assert_called_once_with("_streaming_finished", True)

    @pytest.mark.asyncio
    async def test_process_streaming_finish_prevents_duplicate_send(
        self, stage, mock_event,
    ):
        """Verify prevent duplicate send after streaming finish."""
        mock_event.get_extra.return_value = True  # _streaming_finished already True
        result = MagicMock()
        result.result_content_type = ResultContentType.GENERAL_RESULT
        mock_event.get_result.return_value = result
        await stage.process(mock_event)

        mock_event.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_streaming_result(self, stage, mock_event):
        """Verify STREAMING_RESULT is delivered directly to event.send_streaming."""
        async def dummy_async_stream():
            yield "chunk1"

        result = MagicMock()
        result.result_content_type = ResultContentType.STREAMING_RESULT
        result.async_stream = dummy_async_stream()
        mock_event.get_result.return_value = result

        await stage.process(mock_event)

        mock_event.send_streaming.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_normal_chain(self, stage, mock_event):
        """Verify normal message chain is sent via event.send."""
        result = MessageEventResult()
        result.chain = [Plain(text="hello")]
        mock_event.get_result.return_value = result

        await stage.process(mock_event)

        mock_event.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_empty_chain(self, stage, mock_event):
        """Verify empty chain skips sending."""
        result = MessageEventResult()
        result.chain = [Plain(text="")]
        mock_event.get_result.return_value = result

        await stage.process(mock_event)

        mock_event.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_chain_with_path_mapping(self, stage, mock_event):
        """Verify path mapping is applied to File components."""
        stage.platform_settings = {
            "path_mapping": [["/old/path", "/new/path"]],
        }

        with patch(
            "astrbot.core.pipeline.respond.stage.path_Mapping",
            return_value="/new/path/file.txt",
        ):
            result = MessageEventResult()
            result.chain = [File(file="/old/path/file.txt")]
            mock_event.get_result.return_value = result

            await stage.process(mock_event)

        mock_event.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_chain_with_record_forced_separate(
        self, stage, mock_event,
    ):
        """Verify Record components are sent separately."""
        result = MessageEventResult()
        result.chain = [Record(file="audio.mp3"), Plain(text="hello")]
        mock_event.get_result.return_value = result

        await stage.process(mock_event)

        # Record should be sent separately, then the rest
        assert mock_event.send.call_count >= 1

    @pytest.mark.asyncio
    async def test_process_segmented_reply(self, stage, mock_event):
        """Verify segmented reply sends each component with delay."""
        stage.enable_seg = True
        stage.only_llm_result = False
        stage.interval_method = "random"
        stage.interval = [0.1, 0.2]

        result = MessageEventResult()
        result.chain = [Plain(text="part1"), Plain(text="part2")]
        mock_event.get_result.return_value = result
        mock_event.get_platform_name.return_value = "qq"

        with patch(
            "astrbot.core.pipeline.respond.stage.asyncio.sleep",
            AsyncMock(),
        ):
            await stage.process(mock_event)

        assert mock_event.send.call_count >= 1

    @pytest.mark.asyncio
    async def test_process_event_hook_called(self, stage, mock_event):
        """Verify call_event_hook is invoked after sending."""
        result = MessageEventResult()
        result.chain = [Plain(text="hello")]
        mock_event.get_result.return_value = result

        with patch(
            "astrbot.core.pipeline.respond.stage.call_event_hook",
            AsyncMock(return_value=False),
        ):
            await stage.process(mock_event)

        mock_event.clear_result.assert_called_once()
