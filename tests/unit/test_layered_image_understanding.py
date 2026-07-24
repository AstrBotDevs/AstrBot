import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from data.plugins.astrbot_plugin_image_processor.main import (
    ImageProcessorPlugin,
    VisionEvidence,
    VisionPreflight,
)
from data.plugins.astrbot_plugin_semantic_router.main import SemanticRouterPlugin


def make_plugin(tmp_path: Path) -> ImageProcessorPlugin:
    plugin = ImageProcessorPlugin.__new__(ImageProcessorPlugin)
    plugin.local_ocr_enabled = False
    plugin.max_deep_tiles = 6
    plugin.vision_temp_dir = tmp_path / "vision_inputs"
    plugin.vision_temp_dir.mkdir()
    plugin._local_ocr_details = lambda _: ("", 0)
    plugin._local_qr = lambda _: ""
    return plugin


def test_preflight_routes_long_image_to_deep(tmp_path):
    plugin = make_plugin(tmp_path)
    image_path = tmp_path / "long.png"
    Image.new("RGB", (400, 1600), "white").save(image_path)

    result = plugin._preflight_images([str(image_path)], "请看一下")

    assert result.route == "deep"
    assert "extreme-aspect-ratio" in result.reasons


def test_explicit_brief_request_keeps_fast_route(tmp_path):
    plugin = make_plugin(tmp_path)
    image_path = tmp_path / "long.png"
    Image.new("RGB", (400, 1600), "white").save(image_path)

    result = plugin._preflight_images([str(image_path)], "简单说说就行")

    assert result.route == "fast"
    assert result.reasons == ["explicit-fast-request"]


def test_dense_ocr_routes_to_deep(tmp_path):
    plugin = make_plugin(tmp_path)
    plugin._local_ocr_details = lambda _: ("文字" * 70, 25)
    image_path = tmp_path / "document.png"
    Image.new("RGB", (1000, 1000), "white").save(image_path)

    result = plugin._preflight_images([str(image_path)], "这是什么")

    assert result.route == "deep"
    assert "dense-ocr-text" in result.reasons
    assert "many-text-boxes" in result.reasons


def test_deep_preparation_is_bounded_and_ordered(tmp_path):
    plugin = make_plugin(tmp_path)
    image_path = tmp_path / "document.png"
    Image.new("RGB", (600, 2400), "white").save(image_path)

    prepared = plugin._prepare_deep_images([str(image_path)])

    assert len(prepared) == 7
    assert Path(prepared[0]).name.startswith("overview_")
    assert all(Path(path).exists() for path in prepared)


def test_json_parser_accepts_markdown_fence():
    result = ImageProcessorPlugin._parse_json_object(
        '```json\n{"category":"meme","confidence":0.9}\n```'
    )

    assert result == {"category": "meme", "confidence": 0.9}


def test_vision_evidence_rejects_invalid_contract():
    with pytest.raises(ValueError, match="route"):
        VisionEvidence(
            route="unknown",
            category="meme",
            model_id="test",
            confidence=0.5,
            payload={},
        )


def test_vision_evidence_normalizes_numeric_confidence_strings():
    evidence = VisionEvidence(
        route="deep",
        category="complex",
        model_id="gemini-deep",
        confidence="0.86",
        payload={"overall_summary": "ok"},
    )

    assert evidence.confidence == 0.86


@pytest.mark.asyncio
async def test_fast_vision_accepts_plain_text_model_output(tmp_path):
    plugin = ImageProcessorPlugin.__new__(ImageProcessorPlugin)
    plugin.fast_vision_provider_id = "gemini-fast"
    plugin.daily_fast_limit = 0
    plugin.fast_vision_timeout = 2
    plugin._circuit_open_until = {}
    plugin._daily_count = lambda route: 0
    plugin._prepare_fast_images = lambda paths: paths
    plugin._trip_circuit = lambda provider_id, exc: None

    async def llm_generate(**kwargs):
        return SimpleNamespace(completion_text="这是一张表达困惑和无语的表情包。")

    plugin.context = SimpleNamespace(llm_generate=llm_generate)
    preflight = VisionPreflight(
        route="fast",
        reasons=["simple-or-ambiguous-image"],
        image_count=1,
        width=512,
        height=512,
        frame_count=1,
        ocr_text="怎么会这样",
        ocr_box_count=1,
    )

    evidence = await plugin._run_fast_vision(
        [str(tmp_path / "meme.png")], "这是什么意思", preflight
    )

    assert evidence.category == "simple_photo"
    assert evidence.confidence == 0.75
    assert "困惑和无语" in evidence.payload["social_intent"]


@pytest.mark.asyncio
async def test_deep_vision_coerces_numeric_confidence_string(tmp_path):
    plugin = ImageProcessorPlugin.__new__(ImageProcessorPlugin)
    plugin.deep_vision_provider_id = "gemini-deep"
    plugin.daily_deep_limit = 0
    plugin.deep_vision_timeout = 2
    plugin._circuit_open_until = {}
    plugin._daily_count = lambda route: 0
    plugin._prepare_deep_images = lambda paths: paths
    plugin._trip_circuit = lambda provider_id, exc: None

    async def llm_generate(**kwargs):
        return SimpleNamespace(
            completion_text='{"overall_summary":"ok","confidence":"0.81"}'
        )

    plugin.context = SimpleNamespace(llm_generate=llm_generate)
    preflight = VisionPreflight(
        route="deep",
        reasons=["dense-ocr-text"],
        image_count=1,
        width=1600,
        height=900,
        frame_count=1,
        ocr_text="text",
        ocr_box_count=21,
    )

    evidence = await plugin._run_deep_vision(
        [str(tmp_path / "document.png")], "璇峰垎鏋愭枃妗?", preflight
    )

    assert evidence.confidence == 0.81


@pytest.mark.asyncio
async def test_image_paths_use_router_extra_when_tool_event_has_empty_chain(tmp_path):
    plugin = ImageProcessorPlugin.__new__(ImageProcessorPlugin)
    plugin.max_image_size_mb = 20
    image_path = tmp_path / "restored.png"
    Image.new("RGB", (16, 16), "white").save(image_path)
    event = SimpleNamespace(
        message_obj=SimpleNamespace(message=[]),
        get_extra=lambda key, default=None: (
            [str(image_path)]
            if key == "semantic_router_recent_image_paths"
            else default
        ),
    )

    paths = await plugin._image_paths(event)

    assert paths == [str(image_path.resolve())]


@pytest.mark.asyncio
async def test_router_image_context_preserves_restored_paths_for_tool(tmp_path):
    image_plugin = ImageProcessorPlugin.__new__(ImageProcessorPlugin)
    image_plugin.max_image_size_mb = 20
    image_path = tmp_path / "router-restored.png"
    Image.new("RGB", (16, 16), "white").save(image_path)
    extras = {"semantic_router_recent_image_paths": [str(image_path)]}
    event = SimpleNamespace(
        message_str="亚托莉，我上面发的图片是什么意思",
        message_obj=SimpleNamespace(message=[]),
        get_extra=lambda key, default=None: extras.get(key, default),
        set_extra=lambda key, value: extras.__setitem__(key, value),
    )
    router = SemanticRouterPlugin.__new__(SemanticRouterPlugin)

    async def execute_controlled_tool(tool_event, tool_name, args, timeout):
        paths = await image_plugin._image_paths(tool_event)
        assert tool_name == "understand_current_images"
        assert args["prompt"] == event.message_str
        assert timeout == 18
        assert paths == [str(image_path.resolve())]
        tool_event.set_extra(
            "vision_execution",
            {"route": "fast", "model_id": "gemini-fast", "elapsed_ms": 25},
        )
        return True, '{"category":"meme","social_intent":"困惑"}'

    router._execute_controlled_tool = execute_controlled_tool

    context = await router._build_image_context(event)

    assert context["ok"] is True
    assert context["route"] == "fast"
    assert context["model_id"] == "gemini-fast"
    assert "困惑" in context["summary"]


@pytest.mark.asyncio
async def test_fast_timeout_reuses_preflight_without_second_ocr(tmp_path):
    plugin = ImageProcessorPlugin.__new__(ImageProcessorPlugin)
    plugin._semaphore = asyncio.Semaphore(1)
    plugin.fast_vision_provider_id = "gemini-fast"
    plugin.deep_vision_provider_id = "gemini-deep"
    plugin.local_analysis_timeout = 0.05
    plugin.route_confidence_threshold = 0.72
    plugin.local_fallback_enabled = True
    plugin._preflight_images = lambda paths, prompt: VisionPreflight(
        route="fast",
        reasons=["simple-or-ambiguous-image"],
        image_count=1,
        width=512,
        height=512,
        frame_count=1,
        ocr_text="可见文字",
        ocr_box_count=1,
    )
    plugin._vision_cache_key = lambda *args: "cache-key"
    plugin._cache_get = lambda key: None
    plugin._cache_put = lambda key, evidence: None
    plugin._record_usage = lambda *args, **kwargs: None
    plugin._describe_images_locally = lambda *args: (_ for _ in ()).throw(
        AssertionError("fallback must not run OCR twice")
    )

    async def fail_fast(*args):
        raise asyncio.TimeoutError

    plugin._run_fast_vision = fail_fast
    event = SimpleNamespace(
        unified_msg_origin="qq:group:1", set_extra=lambda key, value: None
    )
    image_path = tmp_path / "meme.png"
    Image.new("RGB", (512, 512), "white").save(image_path)

    context = await plugin.describe_image_for_context(
        event,
        prompt="这是什么意思",
        image_paths=[str(image_path)],
    )
    evidence = json.loads(context)

    assert evidence["category"] == "preflight_fallback"
    assert evidence["model_id"] == "local/preflight"
    assert evidence["payload"]["visible_text"] == "可见文字"
