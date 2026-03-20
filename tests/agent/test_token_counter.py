"""Tests for EstimateTokenCounter multimodal support."""

from astrbot.core.agent.context.token_counter import (
    AUDIO_TOKEN_ESTIMATE,
    IMAGE_TOKEN_ESTIMATE,
    EstimateTokenCounter,
)
from astrbot.core.agent.message import (
    AudioURLPart,
    ImageURLPart,
    Message,
    TextPart,
    ThinkPart,
)


counter = EstimateTokenCounter()


def _msg(role: str, content) -> Message:
    return Message(role=role, content=content)


class TestTextCounting:
    def test_plain_string(self):
        tokens = counter.count_tokens([_msg("user", "hello world")])
        assert tokens > 0

    def test_chinese(self):
        # 中文字符权重更高
        en = counter.count_tokens([_msg("user", "abc")])
        zh = counter.count_tokens([_msg("user", "你好啊")])
        assert zh > en

    def test_text_part(self):
        msg = _msg("user", [TextPart(text="hello")])
        assert counter.count_tokens([msg]) > 0


class TestMultimodalCounting:
    def test_image_counted(self):
        msg = _msg("user", [
            ImageURLPart(image_url=ImageURLPart.ImageURL(url="data:image/png;base64,abc")),
        ])
        tokens = counter.count_tokens([msg])
        assert tokens == IMAGE_TOKEN_ESTIMATE

    def test_audio_counted(self):
        msg = _msg("user", [
            AudioURLPart(audio_url=AudioURLPart.AudioURL(url="https://x.com/a.mp3")),
        ])
        tokens = counter.count_tokens([msg])
        assert tokens == AUDIO_TOKEN_ESTIMATE

    def test_think_counted(self):
        msg = _msg("assistant", [ThinkPart(think="let me think about this")])
        tokens = counter.count_tokens([msg])
        assert tokens > 0

    def test_mixed_content(self):
        """文本 + 图片的多模态消息，token 数 = 文本 token + 图片估算。"""
        text_only = _msg("user", [TextPart(text="describe this image")])
        mixed = _msg("user", [
            TextPart(text="describe this image"),
            ImageURLPart(image_url=ImageURLPart.ImageURL(url="data:image/png;base64,x")),
        ])
        text_tokens = counter.count_tokens([text_only])
        mixed_tokens = counter.count_tokens([mixed])
        assert mixed_tokens == text_tokens + IMAGE_TOKEN_ESTIMATE

    def test_multiple_images(self):
        """多张图片应该各自计算。"""
        msg = _msg("user", [
            ImageURLPart(image_url=ImageURLPart.ImageURL(url="data:image/png;base64,a")),
            ImageURLPart(image_url=ImageURLPart.ImageURL(url="data:image/png;base64,b")),
            ImageURLPart(image_url=ImageURLPart.ImageURL(url="data:image/png;base64,c")),
        ])
        tokens = counter.count_tokens([msg])
        assert tokens == IMAGE_TOKEN_ESTIMATE * 3


class TestTrustedUsage:
    def test_trusted_overrides(self):
        """如果 API 返回了 token 数，直接用它不做估算。"""
        msg = _msg("user", [
            TextPart(text="hello"),
            ImageURLPart(image_url=ImageURLPart.ImageURL(url="data:image/png;base64,x")),
        ])
        tokens = counter.count_tokens([msg], trusted_token_usage=42)
        assert tokens == 42


class TestToolCalls:
    def test_tool_calls_counted(self):
        msg = Message(
            role="assistant",
            content="calling tool",
            tool_calls=[{"type": "function", "id": "1", "function": {"name": "get_weather", "arguments": '{"city": "Beijing"}'}}],
        )
        tokens = counter.count_tokens([msg])
        # 文本 + tool call JSON 都应被计算
        text_only = counter.count_tokens([_msg("assistant", "calling tool")])
        assert tokens > text_only
