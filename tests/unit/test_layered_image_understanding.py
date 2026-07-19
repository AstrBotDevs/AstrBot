from pathlib import Path

from PIL import Image

from data.plugins.astrbot_plugin_image_processor.main import ImageProcessorPlugin


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
