import base64
from io import BytesIO

import pytest
from PIL import Image as PILImage

import astrbot.core.utils.media_utils as media_utils
from astrbot.core.provider.provider import DEFAULT_FALLBACK_IMAGE_FORMATS, Provider
from astrbot.core.provider.sources.oai_aihubmix_source import ProviderAIHubMix
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial
from astrbot.core.provider.sources.openrouter_source import ProviderOpenRouter
from astrbot.core.provider.sources.ssycloud_source import ProviderSSYCloud
from astrbot.core.provider.sources.xai_source import ProviderXAI


class _DummyProvider(Provider):
    supported_image_formats = frozenset({"image/jpeg", "image/png", "image/webp"})

    def get_current_key(self) -> str:
        return ""

    def set_key(self, key: str) -> None:
        pass

    async def get_models(self) -> list[str]:
        return []

    async def text_chat(self, **kwargs):
        raise NotImplementedError


class _UndeclaredProvider(_DummyProvider):
    supported_image_formats = None


def _make_dummy(provider_config: dict | None = None) -> _DummyProvider:
    return _DummyProvider(provider_config or {}, {})


def test_config_override_wins_over_class_default():
    provider = _make_dummy({"image_formats": ["jpeg", "png"]})
    assert provider.resolve_allowed_image_formats() == frozenset(
        {"image/jpeg", "image/png"}
    )


def test_config_star_disables_restriction():
    provider = _make_dummy({"image_formats": ["*"]})
    assert provider.resolve_allowed_image_formats() is None


def test_config_accepts_mime_types_and_is_case_insensitive():
    provider = _make_dummy({"image_formats": ["image/webp", " JPEG "]})
    assert provider.resolve_allowed_image_formats() == frozenset(
        {"image/webp", "image/jpeg"}
    )


def test_class_default_used_when_not_configured():
    provider = _make_dummy()
    assert provider.resolve_allowed_image_formats() == frozenset(
        {"image/jpeg", "image/png", "image/webp"}
    )


def test_fallback_used_when_class_undeclared():
    provider = _UndeclaredProvider({}, {})
    assert provider.resolve_allowed_image_formats() == DEFAULT_FALLBACK_IMAGE_FORMATS


def test_unknown_config_entries_fall_back_to_class_default():
    provider = _make_dummy({"image_formats": ["not-a-format"]})
    assert provider.resolve_allowed_image_formats() == frozenset(
        {"image/jpeg", "image/png", "image/webp"}
    )


def test_unknown_config_entries_log_warning(caplog):
    provider = _make_dummy({"image_formats": ["not-a-format"]})
    with caplog.at_level("WARNING"):
        provider.resolve_allowed_image_formats()
    assert "no valid entries" in caplog.text
    assert "not-a-format" in caplog.text


def test_aggregators_do_not_inherit_openai_format_set():
    assert ProviderOpenRouter.supported_image_formats is None
    assert ProviderAIHubMix.supported_image_formats is None
    assert ProviderSSYCloud.supported_image_formats is None
    assert ProviderOpenAIOfficial.supported_image_formats == frozenset(
        {"image/png", "image/jpeg", "image/webp", "image/gif"}
    )
    assert ProviderXAI.supported_image_formats == frozenset({"image/jpeg", "image/png"})


def test_animated_strategy_defaults():
    provider = _make_dummy()
    assert provider.get_animated_image_strategy() == ("first_frame", 4)


def test_animated_strategy_from_config_and_clamped():
    provider = _make_dummy(
        {"animated_image_strategy": "multi_frame", "animated_image_max_frames": 100}
    )
    assert provider.get_animated_image_strategy() == ("multi_frame", 16)

    provider = _make_dummy({"animated_image_max_frames": 0})
    assert provider.get_animated_image_strategy() == ("first_frame", 1)

    provider = _make_dummy({"animated_image_strategy": "bogus"})
    assert provider.get_animated_image_strategy() == ("first_frame", 4)


def _animated_gif_data_uri(colors: list[tuple[int, int, int]]) -> str:
    frames = [PILImage.new("RGB", (8, 8), color) for color in colors]
    buffer = BytesIO()
    frames[0].save(
        buffer,
        "GIF",
        save_all=True,
        append_images=frames[1:],
        duration=50,
        loop=0,
    )
    return f"data:image/gif;base64,{base64.b64encode(buffer.getvalue()).decode()}"


@pytest.mark.asyncio
async def test_xai_animated_gif_reduced_to_still(tmp_path, monkeypatch):
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    provider = ProviderXAI(
        {
            "id": "test-xai",
            "type": "xai_chat_completion",
            "model": "grok-4",
            "key": ["test-key"],
        },
        {},
    )
    try:
        gif_ref = _animated_gif_data_uri([(255, 0, 0), (0, 255, 0), (0, 0, 255)])
        message = await provider.assemble_context("look", image_urls=[gif_ref])

        content = message["content"]
        image_blocks = [block for block in content if block["type"] == "image_url"]
        assert len(image_blocks) == 1
        url = image_blocks[0]["image_url"]["url"]
        # xAI only accepts JPEG/PNG; the animated GIF must become a still image.
        assert url.startswith(("data:image/jpeg;base64,", "data:image/png;base64,"))
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_openai_multi_frame_strategy_expands_image_blocks(tmp_path, monkeypatch):
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    provider = ProviderOpenAIOfficial(
        {
            "id": "test-openai",
            "type": "openai_chat_completion",
            "model": "gpt-4o-mini",
            "key": ["test-key"],
            "animated_image_strategy": "multi_frame",
            "animated_image_max_frames": 3,
        },
        {},
    )
    try:
        gif_ref = _animated_gif_data_uri(
            [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (0, 255, 255)]
        )
        message = await provider.assemble_context("look", image_urls=[gif_ref])

        image_blocks = [
            block for block in message["content"] if block["type"] == "image_url"
        ]
        assert len(image_blocks) == 3
        for block in image_blocks:
            assert block["image_url"]["url"].startswith("data:image/")
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_anthropic_context_skips_unsupported_format():
    from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic

    provider = ProviderAnthropic(
        {
            "id": "test-anthropic",
            "type": "anthropic_chat_completion",
            "model": "claude-sonnet-4-5",
            "key": ["test-key"],
        },
        {},
    )
    try:
        # A BMP data URI must not be mislabeled as image/jpeg in the payload.
        bmp_buffer = BytesIO()
        PILImage.new("RGB", (4, 4), (1, 2, 3)).save(bmp_buffer, "BMP")
        bmp_data_uri = (
            f"data:image/bmp;base64,{base64.b64encode(bmp_buffer.getvalue()).decode()}"
        )
        _system_prompt, messages = provider._prepare_payload(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "look"},
                        {"type": "image_url", "image_url": {"url": bmp_data_uri}},
                    ],
                }
            ]
        )

        content = messages[0]["content"]
        image_blocks = [block for block in content if block.get("type") == "image"]
        assert image_blocks == []
    finally:
        await provider.terminate()


def _make_openai(provider_config: dict) -> ProviderOpenAIOfficial:
    config = {
        "id": "test-openai",
        "type": "openai_chat_completion",
        "model": "deepseek-v4-flash-vision-exp",
        "key": ["test-key"],
        **provider_config,
    }
    return ProviderOpenAIOfficial(config, {})


@pytest.mark.asyncio
async def test_vendor_brand_overrides_adapter_declared_formats():
    provider = _make_openai({"provider": "xai", "type": "openai_responses"})
    try:
        assert provider.resolve_allowed_image_formats() == frozenset(
            {"image/jpeg", "image/png"}
        )
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_unknown_brand_keeps_adapter_declared_formats():
    provider = _make_openai({"provider": "some-unknown-vendor"})
    try:
        assert provider.resolve_allowed_image_formats() == frozenset(
            {"image/png", "image/jpeg", "image/webp", "image/gif"}
        )
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_config_override_wins_over_vendor_brand():
    provider = _make_openai({"provider": "xai", "image_formats": ["webp"]})
    try:
        assert provider.resolve_allowed_image_formats() == frozenset({"image/webp"})
    finally:
        await provider.terminate()


def test_vendor_map_matches_adapter_declarations():
    from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic
    from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI
    from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial
    from astrbot.core.provider.sources.xai_source import ProviderXAI
    from astrbot.core.provider.sources.zhipu_source import ProviderZhipu
    from astrbot.core.utils.media_utils import VENDOR_IMAGE_FORMATS

    assert (
        ProviderOpenAIOfficial.supported_image_formats is VENDOR_IMAGE_FORMATS["openai"]
    )
    assert ProviderXAI.supported_image_formats is VENDOR_IMAGE_FORMATS["xai"]
    assert ProviderZhipu.supported_image_formats is VENDOR_IMAGE_FORMATS["zhipu"]
    assert ProviderGoogleGenAI.supported_image_formats is VENDOR_IMAGE_FORMATS["google"]
    assert (
        ProviderAnthropic.supported_image_formats is VENDOR_IMAGE_FORMATS["anthropic"]
    )


def test_vendor_map_matches_vendor_adapter_declarations():
    from astrbot.core.provider.sources.groq_source import ProviderGroq
    from astrbot.core.provider.sources.kimi_code_source import ProviderKimiCode
    from astrbot.core.provider.sources.minimax_token_plan_source import (
        ProviderMiniMaxTokenPlan,
    )
    from astrbot.core.provider.sources.xiaomi_source import ProviderXiaomi
    from astrbot.core.provider.sources.xiaomi_token_plan_source import (
        ProviderXiaomiTokenPlan,
    )
    from astrbot.core.utils.media_utils import VENDOR_IMAGE_FORMATS

    assert ProviderGroq.supported_image_formats is VENDOR_IMAGE_FORMATS["groq"]
    assert ProviderXiaomi.supported_image_formats is VENDOR_IMAGE_FORMATS["xiaomi"]
    assert ProviderKimiCode.supported_image_formats is VENDOR_IMAGE_FORMATS["kimi-code"]
    assert (
        ProviderMiniMaxTokenPlan.supported_image_formats
        is VENDOR_IMAGE_FORMATS["minimax-token-plan"]
    )
    assert (
        ProviderXiaomiTokenPlan.supported_image_formats
        is VENDOR_IMAGE_FORMATS["xiaomi-token-plan"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("brand", "expected"),
    [
        ("deepseek", {"image/jpeg", "image/png", "image/webp", "image/gif"}),
        (
            "moonshot",
            {
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "image/bmp",
                "image/heic",
                "image/heif",
            },
        ),
        ("minimax", {"image/jpeg", "image/png", "image/webp", "image/gif"}),
        ("xiaomi", {"image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp"}),
        ("groq", {"image/jpeg", "image/png"}),
        ("nvidia", {"image/jpeg", "image/png"}),
    ],
)
async def test_vendor_brand_format_sets(brand, expected):
    provider = _make_openai({"provider": brand})
    try:
        assert provider.resolve_allowed_image_formats() == frozenset(expected)
    finally:
        await provider.terminate()
