"""Tests for EstimateTokenCounter multimodal support."""

import sys
from types import SimpleNamespace

from astrbot.core.agent.context.token_counter import (
    AUDIO_TOKEN_ESTIMATE,
    IMAGE_TOKEN_ESTIMATE,
    EstimateTokenCounter,
    TokenizerTokenCounter,
    create_token_counter,
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


class TestCounterFactory:
    def test_create_estimate_mode(self):
        created = create_token_counter("estimate")
        assert isinstance(created, EstimateTokenCounter)

    def test_create_unknown_mode_fallback(self):
        created = create_token_counter("unknown-mode")
        assert isinstance(created, EstimateTokenCounter)

    def test_create_tokenizer_mode_returns_valid_counter_type(self):
        created = create_token_counter("tokenizer", model="gpt-4")
        assert isinstance(created, (TokenizerTokenCounter, EstimateTokenCounter))

    def test_tokenizer_counter_gracefully_handles_broken_fallback_encoder(
        self, monkeypatch
    ):
        fake_tiktoken = SimpleNamespace(
            encoding_for_model=lambda _model: (_ for _ in ()).throw(RuntimeError("boom")),
            get_encoding=lambda _name: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        monkeypatch.setitem(sys.modules, "tiktoken", fake_tiktoken)

        counter = TokenizerTokenCounter(model="gpt-4")
        assert counter.available is False

        created = create_token_counter("tokenizer", model="gpt-4")
        assert isinstance(created, EstimateTokenCounter)


class TestTokenizerTokenCounterBehavior:
    def test_count_tokens_uses_trusted_usage_and_skips_encode(self, monkeypatch):
        counter = TokenizerTokenCounter(model="gpt-4")

        def _encode_should_not_be_called(_text):  # pragma: no cover - safety guard
            raise AssertionError(
                "_encode should not be called when trusted_token_usage is provided"
            )

        monkeypatch.setattr(counter, "_encode", _encode_should_not_be_called)

        messages = [
            _msg(
                "user",
                [
                    TextPart(text="hello"),
                    ThinkPart(think="internal thoughts"),
                    ImageURLPart(
                        image_url=ImageURLPart.ImageURL(
                            url="data:image/png;base64,abc"
                        )
                    ),
                    AudioURLPart(
                        audio_url=AudioURLPart.AudioURL(url="https://x.com/a.mp3")
                    ),
                ],
            )
        ]

        trusted_usage = 123
        result = counter.count_tokens(messages, trusted_token_usage=trusted_usage)
        assert result == trusted_usage

    def test_encode_error_falls_back_to_estimate_text_tokens(self, monkeypatch):
        counter = TokenizerTokenCounter(model="gpt-4")

        def broken_encode(_text):
            raise RuntimeError("tiktoken failure")

        captured: dict[str, str] = {}

        def fake_estimate(text: str) -> int:
            captured["text"] = text
            return 42

        monkeypatch.setattr(counter, "_encode", broken_encode)
        monkeypatch.setattr(counter._estimate, "estimate_text_tokens", fake_estimate)

        result = counter._encode_len("fallback text")
        assert result == 42
        assert captured["text"] == "fallback text"

    def test_tokenizer_mode_mixed_modalities_use_fixed_estimates(self, monkeypatch):
        counter = TokenizerTokenCounter(model="gpt-4")
        counter._available = True

        def fake_encode_len(text: str) -> int:
            return len(text.split())

        monkeypatch.setattr(counter, "_encode_len", fake_encode_len)

        messages = [
            _msg(
                "user",
                [
                    TextPart(text="hello world"),
                    ImageURLPart(
                        image_url=ImageURLPart.ImageURL(
                            url="data:image/png;base64,image"
                        )
                    ),
                ],
            ),
            _msg(
                "assistant",
                [
                    ThinkPart(think="thinking hard"),
                    AudioURLPart(
                        audio_url=AudioURLPart.AudioURL(url="https://x.com/a.mp3")
                    ),
                ],
            ),
        ]

        expected_text_tokens = fake_encode_len("hello world") + fake_encode_len(
            "thinking hard"
        )
        expected_non_text_tokens = IMAGE_TOKEN_ESTIMATE + AUDIO_TOKEN_ESTIMATE

        tokens = counter.count_tokens(messages)
        assert tokens == expected_text_tokens + expected_non_text_tokens
