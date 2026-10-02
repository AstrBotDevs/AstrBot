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
        msg = _msg(
            "user",
            [
                ImageURLPart(
                    image_url=ImageURLPart.ImageURL(url="data:image/png;base64,abc")
                ),
            ],
        )
        tokens = counter.count_tokens([msg])
        assert tokens == IMAGE_TOKEN_ESTIMATE

    def test_audio_counted(self):
        msg = _msg(
            "user",
            [
                AudioURLPart(
                    audio_url=AudioURLPart.AudioURL(url="https://x.com/a.mp3")
                ),
            ],
        )
        tokens = counter.count_tokens([msg])
        assert tokens == AUDIO_TOKEN_ESTIMATE

    def test_think_counted(self):
        msg = _msg("assistant", [ThinkPart(think="let me think about this")])
        tokens = counter.count_tokens([msg])
        assert tokens > 0

    def test_mixed_content(self):
        """文本 + 图片的多模态消息，token 数 = 文本 token + 图片估算。"""
        text_only = _msg("user", [TextPart(text="describe this image")])
        mixed = _msg(
            "user",
            [
                TextPart(text="describe this image"),
                ImageURLPart(
                    image_url=ImageURLPart.ImageURL(url="data:image/png;base64,x")
                ),
            ],
        )
        text_tokens = counter.count_tokens([text_only])
        mixed_tokens = counter.count_tokens([mixed])
        assert mixed_tokens == text_tokens + IMAGE_TOKEN_ESTIMATE

    def test_multiple_images(self):
        """多张图片应该各自计算。"""
        msg = _msg(
            "user",
            [
                ImageURLPart(
                    image_url=ImageURLPart.ImageURL(url="data:image/png;base64,a")
                ),
                ImageURLPart(
                    image_url=ImageURLPart.ImageURL(url="data:image/png;base64,b")
                ),
                ImageURLPart(
                    image_url=ImageURLPart.ImageURL(url="data:image/png;base64,c")
                ),
            ],
        )
        tokens = counter.count_tokens([msg])
        assert tokens == IMAGE_TOKEN_ESTIMATE * 3


class TestEmojiCounting:
    def test_emoji_costs_more_than_ascii(self):
        """一个 emoji 的 token 开销远高于一个 ASCII 字符。"""
        emoji = counter.count_tokens([_msg("user", "🔥" * 1000)])
        ascii_text = counter.count_tokens([_msg("user", "a" * 1000)])
        assert emoji > ascii_text * 5

    def test_emoji_estimate_close_to_real_usage(self):
        """50000 个 🔥 的真实 prompt_tokens 实测为 150082。"""
        tokens = counter.count_tokens([_msg("user", "🔥" * 50_000)])
        assert 100_000 <= tokens <= 170_000

    def test_flag_and_zwj_sequences_counted(self):
        """国旗与 ZWJ 组合的 token 开销同样高于普通字符。"""
        flags = counter.count_tokens([_msg("user", "🇨🇳" * 500)])
        family = counter.count_tokens([_msg("user", "👨‍👩‍👧‍👦" * 500)])
        assert flags > counter.count_tokens([_msg("user", "ab" * 500)]) * 5
        assert family > counter.count_tokens([_msg("user", "abcdefg" * 500)]) * 2

    def test_plain_text_estimate_unchanged(self):
        """纯文本与中文的估算值不受 emoji 分支影响。"""
        assert counter.count_tokens([_msg("user", "a" * 100)]) == 30
        assert counter.count_tokens([_msg("user", "你" * 100)]) == 60


class TestTrustedUsage:
    def test_trusted_overrides(self):
        """如果 API 返回了 token 数，直接用它不做估算。"""
        msg = _msg(
            "user",
            [
                TextPart(text="hello"),
                ImageURLPart(
                    image_url=ImageURLPart.ImageURL(url="data:image/png;base64,x")
                ),
            ],
        )
        tokens = counter.count_tokens([msg], trusted_token_usage=42)
        assert tokens == 42


class TestToolCalls:
    def test_tool_calls_counted(self):
        msg = Message(
            role="assistant",
            content="calling tool",
            tool_calls=[
                {
                    "type": "function",
                    "id": "1",
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"city": "Beijing"}',
                    },
                }
            ],
        )
        tokens = counter.count_tokens([msg])
        # 文本 + tool call JSON 都应被计算
        text_only = counter.count_tokens([_msg("assistant", "calling tool")])
        assert tokens > text_only
