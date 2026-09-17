"""Exercise the real preprocess/process/build/reset sequence with generated images."""

import asyncio
import base64
import copy
import inspect
import os
import random
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image as PILImage

from astrbot.core import astr_main_agent as main
from astrbot.core.agent.message import (
    ImageURLPart,
    TextPart,
    dump_messages_with_checkpoints,
)
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.message.components import Image, Plain, Reply
from astrbot.core.pipeline.preprocess_stage import stage as preprocess
from astrbot.core.pipeline.process_stage.method.agent_sub_stages import (
    internal,
)
from astrbot.core.pipeline.process_stage.stage import ProcessStage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.provider.provider import Provider
from astrbot.core.star.star_handler import EventType
from astrbot.core.utils import image_input
from astrbot.core.utils import media_utils as media


def make_event(parts=None, text="hello", session="images"):
    message = AstrBotMessage()
    message.message = parts or [Plain(text=text)]
    message.message_str = text
    message.type = MessageType.FRIEND_MESSAGE
    message.sender = MessageMember(user_id="user", nickname="User")
    message.self_id = "bot"
    event = AstrMessageEvent(
        text,
        message,
        PlatformMetadata(name="test", id="test", description="test"),
        session,
    )
    event.is_at_or_wake_command = True
    event.send = AsyncMock()
    event.send_typing = AsyncMock()
    event.stop_typing = AsyncMock()
    return event


def source_image(tmp_path, fmt="GIF"):
    path = tmp_path / f"source.{fmt.lower()}"
    image = PILImage.new(
        "RGBA" if fmt == "PNG" else "RGB",
        (60, 30),
        (255, 0, 0, 128) if fmt == "PNG" else "red",
    )
    image.save(
        path,
        fmt,
        **(
            {
                "save_all": True,
                "append_images": [PILImage.new("RGB", (60, 30), "blue")],
                "duration": 100,
                "loop": 0,
            }
            if fmt == "GIF"
            else {}
        ),
    )
    return path


@pytest.fixture
def harness(tmp_path, monkeypatch):
    work = tmp_path / "work"
    for module in (media, image_input, preprocess):
        monkeypatch.setattr(module, "get_astrbot_temp_path", lambda: str(work))
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["provider_settings"].update(
        {
            "streaming_response": False,
            "image_compress_options": {"max_size": 90},
            "enable": True,
        }
    )
    context = MagicMock(spec=main.Context)
    context.persona_manager = MagicMock()
    context.conversation_manager = MagicMock()
    context.get_config.return_value = config
    context.persona_manager.resolve_selected_persona = AsyncMock(
        return_value=(None, None, None, False)
    )
    context.persona_manager.personas_v3 = []
    context.subagent_orchestrator = None
    context.get_llm_tool_manager.return_value.get_builtin_tool.side_effect = (
        lambda cls, **kwargs: cls(**kwargs)
    )
    conversation = SimpleNamespace(
        cid="conv", persona_id=None, history="[]", token_usage=None
    )
    context.conversation_manager.get_curr_conversation_id = AsyncMock(
        return_value="conv"
    )
    context.conversation_manager.get_conversation = AsyncMock(return_value=conversation)
    context.conversation_manager.update_conversation = AsyncMock()
    provider = MagicMock(spec=Provider)
    provider.provider_config = {
        "id": "primary",
        "model": "test",
        "modalities": ["text", "image", "tool_use"],
        "max_context_tokens": 4096,
    }
    provider.get_model.return_value = "test"
    provider.text_chat = AsyncMock(
        return_value=LLMResponse(role="assistant", completion_text="done")
    )

    async def stream(**kwargs):
        yield await provider.text_chat(**kwargs)

    provider.text_chat_stream = stream
    context.get_using_provider_async = AsyncMock(return_value=provider)
    context.get_provider_by_id.return_value = provider
    ctx = SimpleNamespace(
        astrbot_config=config, plugin_manager=SimpleNamespace(context=context)
    )
    captured = []
    hooks = []

    async def hook(event, kind, *args):
        hooks.append(kind)
        return False

    monkeypatch.setattr(internal, "call_event_hook", hook)
    monkeypatch.setattr(internal, "try_capture_follow_up", lambda event: None)
    monkeypatch.setattr(internal, "_record_internal_agent_stats", AsyncMock())
    monkeypatch.setattr(internal.Metric, "upload", AsyncMock())
    monkeypatch.setattr(main, "retrieve_knowledge_base", AsyncMock(return_value=None))
    from astrbot.core.pipeline.process_stage.method.agent_request import (
        SessionServiceManager,
    )

    monkeypatch.setattr(
        SessionServiceManager,
        "should_process_llm_request",
        AsyncMock(return_value=True),
    )

    async def run(runner, *args, **kwargs):
        captured.append(runner)
        async for response in runner._iter_llm_responses_with_fallback():
            runner.final_llm_resp = response
            yield None

    monkeypatch.setattr(internal, "run_agent", run)
    return SimpleNamespace(
        config=config,
        context=context,
        ctx=ctx,
        provider=provider,
        captured=captured,
        hooks=hooks,
        work=work,
    )


async def process_event(harness, event, *, preprocess_first=False, stage=None):
    if preprocess_first:
        first = preprocess.PreProcessStage()
        await first.initialize(harness.ctx)
        await first.process(event)
    stage = stage or ProcessStage()
    if not hasattr(stage, "ctx"):
        await stage.initialize(harness.ctx)
    async for _ in stage.process(event):
        result = event.get_result()
        if result and result.async_stream:
            async for _ in result.async_stream:
                pass
    assert not event.send.await_count, event.send.await_args_list
    return stage


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [None, True, False])
@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "BMP", "WEBP", "GIF"])
async def test_legacy_toggle_does_not_disable_preparation(
    harness, tmp_path, monkeypatch, enabled, fmt
):
    source = source_image(tmp_path, fmt)
    original = source.read_bytes()
    event = make_event([Image(file=str(source))], text="")
    if enabled is None:
        harness.config["provider_settings"].pop("image_compress_enabled", None)
    else:
        harness.config["provider_settings"]["image_compress_enabled"] = enabled
    await process_event(harness, event, preprocess_first=True)
    assert len(harness.captured) == 1
    req = harness.captured[0].req
    with PILImage.open(req.image_urls[0]) as image:
        expected = fmt if fmt in {"JPEG", "PNG"} else "JPEG"
        assert image.format == expected
        assert image.size == ((90, 45) if fmt == "GIF" else (60, 30))
        if fmt == "PNG":
            assert image.getpixel((0, 0))[3] == 128
    assert source.read_bytes() == original
    assert Path(event.get_messages()[0].file).read_bytes() == original
    assert str(source) not in event._temporary_local_files
    assert any(
        str(source) in p.text
        for p in req.extra_user_content_parts
        if isinstance(p, TextPart)
    )
    assert harness.provider.text_chat.await_count == 1
    assert "image_settings" not in harness.provider.text_chat.await_args.kwargs
    visual_path = Path(req.image_urls[0])
    assert (visual_path == source) == (fmt in {"JPEG", "PNG"})
    event.cleanup_temporary_local_files()
    assert source.read_bytes() == original
    assert visual_path.exists() == (fmt in {"JPEG", "PNG"})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("runtime", "booter", "fmt"),
    [
        ("sandbox", "cua", "PNG"),
        ("sandbox", "cua", "WEBP"),
        ("sandbox", "shipyard_neo", "PNG"),
        ("local", "cua", "PNG"),
    ],
)
async def test_all_runtimes_apply_configured_image_limit(
    harness, tmp_path, runtime, booter, fmt
):
    """User attachments obey the image limit for every computer runtime."""
    path = tmp_path / f"big.{fmt.lower()}"
    PILImage.new("RGB", (200, 100), "red").save(path, fmt)
    original = path.read_bytes()
    harness.config["provider_settings"]["computer_use_runtime"] = runtime
    harness.config["provider_settings"]["sandbox"] = {"booter": booter}
    event = make_event([Image(file=str(path))], text="")
    await process_event(harness, event, preprocess_first=True)
    assert len(harness.captured) == 1
    req = harness.captured[0].req
    with PILImage.open(req.image_urls[0]) as image:
        assert image.size == (90, 45)
        assert image.format == "JPEG"
    assert path.read_bytes() == original


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("runtime", "booter", "big"),
    [
        ("sandbox", "cua", True),
        ("sandbox", "cua", False),
        ("sandbox", "shipyard_neo", True),
    ],
)
async def test_cua_inputs_obey_byte_limit(
    harness, tmp_path, monkeypatch, runtime, booter, big
):
    """Large user inputs are bounded even in CUA sessions."""
    dims = (1500, 1500) if big else (60, 30)
    path = tmp_path / "shot.png"
    if big:
        # Noise stays incompressible, keeping the PNG above the 5 MB threshold.
        PILImage.frombytes("RGB", dims, os.urandom(dims[0] * dims[1] * 3)).save(
            path, "PNG"
        )
    else:
        PILImage.new("RGB", dims, "red").save(path, "PNG")
    original = path.read_bytes()
    harness.config["provider_settings"]["computer_use_runtime"] = runtime
    harness.config["provider_settings"]["sandbox"] = {"booter": booter}
    warning = MagicMock()
    monkeypatch.setattr(internal.logger, "warning", warning)
    event = make_event([Image(file=str(path))], text="")
    await process_event(harness, event, preprocess_first=True)
    assert len(harness.captured) == 1
    req = harness.captured[0].req
    assert Path(req.image_urls[0]).stat().st_size < 512 * 1024
    with PILImage.open(req.image_urls[0]) as image:
        assert max(image.size) <= 90
    assert path.read_bytes() == original
    assert not any("upload limits" in str(call) for call in warning.call_args_list)


@pytest.mark.asyncio
async def test_cua_montage_keeps_configured_cap(harness, tmp_path):
    """Animated inputs keep the configured montage cap under CUA pixel mode."""
    path = tmp_path / "anim.gif"
    frames = [PILImage.new("RGB", (600, 400), c) for c in ("red", "green", "blue")]
    frames[0].save(path, "GIF", save_all=True, append_images=frames[1:])
    harness.config["provider_settings"]["computer_use_runtime"] = "sandbox"
    harness.config["provider_settings"]["sandbox"] = {"booter": "cua"}
    event = make_event([Image(file=str(path))], text="")
    await process_event(harness, event, preprocess_first=True)
    assert len(harness.captured) == 1
    req = harness.captured[0].req
    with PILImage.open(req.image_urls[0]) as image:
        # With the configured cap 90, 600x400 frames produce a 90x60 montage;
        # the CUA still-image passthrough must not unbound the montage canvas.
        assert max(image.size) <= 90


@pytest.mark.asyncio
async def test_animation_montage_notice_reaches_model(harness, tmp_path):
    """Animated inputs tell the model that the image is a frame montage."""
    animated = tmp_path / "anim.gif"
    frames = [PILImage.new("RGB", (60, 30), c) for c in ("red", "green", "blue")]
    frames[0].save(animated, "GIF", save_all=True, append_images=frames[1:])

    still = tmp_path / "still.png"
    PILImage.new("RGB", (60, 30), "red").save(still)
    # Legacy settings cannot disable animation preparation.
    for source, enabled, expected in (
        (animated, True, True),
        (animated, True, True),
        (still, True, False),
        (animated, False, True),
    ):
        harness.config["provider_settings"]["image_compress_enabled"] = enabled
        await process_event(harness, make_event([Image(file=str(source))]))
        notices = [
            part
            for part in harness.captured[-1].req.extra_user_content_parts
            if isinstance(part, TextPart)
            and part.text.startswith(
                "<system_notice>\nImages labeled as animation montages"
            )
        ]
        assert len(notices) == int(expected)
        if expected:
            assert notices[0]._no_save
            assert notices[0].text.startswith("<system_notice>\n")
            assert notices[0].text.endswith("\n</system_notice>")
            assert "contain frames in reading order" in notices[0].text
            assert "Treat them as animations" in notices[0].text
            assert "do not mention the conversion or frame layout" in notices[0].text


@pytest.mark.asyncio
async def test_profile_reload_and_concurrent_requests(harness, tmp_path):
    source = source_image(tmp_path)
    before = copy.deepcopy(harness.provider.provider_config)
    stage = await process_event(
        harness, make_event([Image(file=str(source))], session="first")
    )
    other_config = copy.deepcopy(harness.config)
    other_config["provider_settings"]["image_compress_options"]["max_size"] = 60
    other_ctx = SimpleNamespace(
        astrbot_config=other_config, plugin_manager=harness.ctx.plugin_manager
    )
    other_stage = ProcessStage()
    await other_stage.initialize(other_ctx)
    harness.config["provider_settings"]["image_compress_options"]["max_size"] = 30
    await stage.initialize(harness.ctx)
    await asyncio.gather(
        process_event(
            harness, make_event([Image(file=str(source))], session="small"), stage=stage
        ),
        process_event(
            harness,
            make_event([Image(file=str(source))], session="other"),
            stage=other_stage,
        ),
    )
    results = {
        runner.req.session_id.split(":")[-1]: runner.req for runner in harness.captured
    }
    with PILImage.open(results["small"].image_urls[0]) as image:
        assert max(image.size) == 30
    with PILImage.open(results["other"].image_urls[0]) as image:
        assert max(image.size) == 60
    assert harness.provider.provider_config == before


@pytest.mark.asyncio
async def test_plugin_request_extra_metadata_hook_and_history(
    harness, tmp_path, monkeypatch
):
    source = source_image(tmp_path)
    replacement = source_image(tmp_path, "BMP")
    extra = ImageURLPart(
        image_url=ImageURLPart.ImageURL(url=str(source), id="keep-id")
    ).mark_as_temp()
    detail = {
        "type": "image_url",
        "image_url": {"url": str(source), "detail": "high", "id": "dict-id"},
        "_no_save": True,
    }
    historical = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/gif;base64,"
                        + base64.b64encode(source.read_bytes()).decode()
                    },
                }
            ],
        }
    ]
    original = ProviderRequest(
        prompt="plugin",
        image_urls=[str(source)],
        extra_user_content_parts=[
            TextPart(text="first"),
            extra,
            detail,
            TextPart(text="last"),
        ],
        contexts=historical,
    )
    event = make_event()
    event.set_extra("provider_request", original)
    convert = AsyncMock(wraps=image_input.prepare_model_image)
    monkeypatch.setattr(image_input, "prepare_model_image", convert)
    seen = []

    async def hook(event, kind, *args):
        seen.append(kind)
        if kind == EventType.OnLLMRequestEvent:
            req = args[0]
            assert Path(req.image_urls[0]).is_file()
            assert req.extra_user_content_parts[1]._no_save
            assert req.extra_user_content_parts[1].image_url.id == "keep-id"
            req.image_urls.append(str(source))
            req.image_urls.append(str(replacement))
            req.extra_user_content_parts[1] = ImageURLPart(
                image_url=ImageURLPart.ImageURL(url=str(replacement), id="new")
            )
        return False

    monkeypatch.setattr(internal, "call_event_hook", hook)
    await process_event(harness, event)
    assert seen == [EventType.OnWaitingLLMRequestEvent, EventType.OnLLMRequestEvent]
    assert convert.await_count == 2
    req = harness.captured[0].req
    assert req is not original and original.image_urls == [str(source)]
    assert extra.image_url.url == str(source) and extra._no_save
    assert detail["image_url"]["url"] == str(source)
    assert req.extra_user_content_parts[2]["image_url"]["detail"] == "high"
    assert req.extra_user_content_parts[2]["_no_save"]
    saved = dump_messages_with_checkpoints(harness.captured[0].run_context.messages)
    old_user = next(message for message in saved if message["role"] == "user")
    assert (
        old_user["content"][0]["image_url"]["url"]
        == historical[0]["content"][0]["image_url"]["url"]
    )
    assert req.contexts == historical
    images = [p for p in saved[-1]["content"] if p["type"] == "image_url"]
    assert images and all(
        p["image_url"]["url"].startswith("data:image/jpeg;base64,") for p in images
    )
    assert all(p["image_url"].get("id") != "dict-id" for p in images)
    paths = list(event._temporary_local_files)
    event.cleanup_temporary_local_files()
    assert all(not Path(path).exists() for path in paths)
    assert not list(harness.work.rglob("model_image_*"))
    assert all(
        base64.b64decode(p["image_url"]["url"].split(",", 1)[1]).startswith(b"\xff\xd8")
        for p in images
    )
    from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic

    anthropic = object.__new__(ProviderAnthropic)
    _, payload = anthropic._prepare_payload([saved[-1]])
    visual = [part for part in payload[0]["content"] if part["type"] == "image"]
    assert len(visual) == len(images)
    assert all(part["source"]["media_type"] == "image/jpeg" for part in visual)


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["attachment", "quote", "plugin", "hook"])
@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "GIF"])
async def test_provider_and_history_keep_bounded_previews_and_original_paths(
    harness, tmp_path, monkeypatch, entry, fmt
):
    source = tmp_path / f"original.{fmt.lower()}"
    pixels = random.Random(9703).randbytes(1280 * 960 * 3)
    image = PILImage.frombytes("RGB", (1280, 960), pixels)
    if fmt == "PNG":
        image.putalpha(128)
    if fmt == "GIF":
        image.save(
            source,
            fmt,
            save_all=True,
            append_images=[image.transpose(PILImage.Transpose.FLIP_LEFT_RIGHT)],
        )
    else:
        image.save(source, fmt, quality=100)
    original = source.read_bytes()
    assert len(original) >= 512 * 1024
    harness.config["provider_settings"]["image_compress_options"] = {
        "max_size": 1280,
        "quality": 100,
    }
    harness.config["provider_settings"]["image_compress_enabled"] = False
    part = Image(file=str(source))
    event = make_event(
        [Reply(id="quoted", chain=[part])] if entry == "quote" else [part]
    )
    if entry in {"plugin", "hook"}:
        event = make_event()
        original_request = ProviderRequest(
            prompt="describe",
            image_urls=[str(source)],
            conversation=harness.context.conversation_manager.get_conversation.return_value,
            extra_user_content_parts=[
                TextPart(text=f"[Image Attachment: path {source}]")
            ],
        )
        if entry == "plugin":
            event.set_extra("provider_request", original_request)
        else:

            async def hook(event, kind, *args):
                if kind == EventType.OnLLMRequestEvent:
                    request = args[0]
                    request.image_urls = original_request.image_urls
                    request.extra_user_content_parts = (
                        original_request.extra_user_content_parts
                    )
                return False

            monkeypatch.setattr(internal, "call_event_hook", hook)
    await process_event(harness, event, preprocess_first=True)
    req = harness.captured[0].req
    preview = Path(req.image_urls[0])
    assert preview != source and preview.stat().st_size < 512 * 1024
    texts = [
        part.text for part in req.extra_user_content_parts if isinstance(part, TextPart)
    ]
    assert any(str(source) in text for text in texts)
    assert all(str(preview) not in text for text in texts)
    provider_messages = harness.provider.text_chat.await_args.kwargs["contexts"]
    history = (
        harness.context.conversation_manager.update_conversation.await_args.kwargs[
            "history"
        ]
    )
    for messages in (provider_messages, history):
        images = [
            part
            for message in messages
            if isinstance(message.get("content"), list)
            for part in message["content"]
            if part["type"] == "image_url"
        ]
        assert images
        for part in images:
            data_uri = part["image_url"]["url"]
            data = base64.b64decode(data_uri.split(",", 1)[1])
            assert len(data) < 512 * 1024
            assert data == preview.read_bytes()
            assert data_uri.startswith(
                "data:image/png;" if fmt == "PNG" else "data:image/jpeg;"
            )
    event.cleanup_temporary_local_files()
    assert not preview.exists()
    assert source.read_bytes() == original


@pytest.mark.asyncio
@pytest.mark.parametrize("plugin", [False, True])
@pytest.mark.parametrize("fmt", ["GIF", "JPEG"])
async def test_caption_first_call_uses_prepared_quote(harness, tmp_path, plugin, fmt):
    source = source_image(tmp_path, fmt)
    harness.provider.provider_config["modalities"] = ["text"]
    harness.config["provider_settings"]["default_image_caption_provider_id"] = "caption"
    harness.config["provider_settings"]["image_caption_prompt"] = "Describe in Chinese."
    caption = MagicMock(spec=Provider)
    captured = []

    async def describe(**kwargs):
        assert "image_settings" not in kwargs
        prompt = kwargs["prompt"]
        if not plugin:
            assert prompt.startswith("Describe in Chinese.")
        if fmt == "GIF":
            assert "positions 1 (1-based)" in prompt
            assert "single image of frames in reading order" in prompt
            assert "Describe them as animations" in prompt
            assert "do not mention the conversion or frame layout" in prompt
        else:
            assert "<system_notice>" not in prompt
        for ref in kwargs["image_urls"]:
            with PILImage.open(ref) as image:
                assert image.format == "JPEG" and getattr(image, "n_frames", 1) == 1
        captured.extend(kwargs["image_urls"])
        return LLMResponse(role="assistant", completion_text="caption")

    caption.text_chat = AsyncMock(side_effect=describe)
    harness.context.get_provider_by_id.return_value = caption
    event = make_event(
        [Reply(id="quote", chain=[Image(file=str(source))], message_str="quoted")]
    )
    if plugin:
        event.set_extra("provider_request", ProviderRequest(prompt="plugin"))
    await process_event(harness, event, preprocess_first=True)
    assert caption.text_chat.await_count == 1 and captured
    assert all(Path(ref).is_file() for ref in captured)
    req = harness.captured[0].req
    assert any(
        "caption" in part.text
        for part in req.extra_user_content_parts
        if isinstance(part, TextPart)
    )


@pytest.mark.asyncio
async def test_caption_animation_notice_uses_actual_image_order(harness, tmp_path):
    still = source_image(tmp_path, "JPEG")
    animated = source_image(tmp_path, "GIF")
    harness.provider.provider_config["modalities"] = ["text"]
    harness.config["provider_settings"]["default_image_caption_provider_id"] = "caption"
    caption = MagicMock(spec=Provider)
    caption.text_chat = AsyncMock(
        return_value=LLMResponse(role="assistant", completion_text="caption")
    )
    harness.context.get_provider_by_id.return_value = caption
    event = make_event([Image(file=str(still)), Image(file=str(animated))])

    await process_event(harness, event, preprocess_first=True)

    caption.text_chat.assert_awaited_once()
    args = caption.text_chat.await_args.kwargs
    assert len(args["image_urls"]) == 2
    assert args["image_urls"][0] == str(still)
    assert "positions 2 (1-based)" in args["prompt"]
    assert "Describe them as animations" in args["prompt"]
    assert "do not mention the conversion or frame layout" in args["prompt"]


@pytest.mark.asyncio
async def test_reply_fallback_limit_and_deduplication(harness, tmp_path, monkeypatch):
    paths = []
    for i in range(3):
        path = tmp_path / f"{i}.bmp"
        PILImage.new("RGB", (12, 12), "red").save(path)
        paths.append(str(path))
    extract = AsyncMock(return_value=[paths[0], paths[0], paths[1], paths[2]])
    monkeypatch.setattr(main, "extract_quoted_message_images", extract)
    harness.config["provider_settings"]["max_quoted_fallback_images"] = 2
    event = make_event([Reply(id="one"), Reply(id="two")])
    await process_event(harness, event)
    assert extract.await_count == 2
    assert len(harness.captured[0].req.image_urls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text,good", [("", False), ("keep text", False), ("keep text", True)]
)
async def test_failed_images_keep_valid_input(harness, tmp_path, text, good):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"broken")
    refs = [str(bad)] + ([str(source_image(tmp_path))] if good else [])
    event = make_event()
    event.set_extra("provider_request", ProviderRequest(prompt=text, image_urls=refs))
    await process_event(harness, event)
    req = harness.captured[0].req
    assert len(req.image_urls) == int(good)
    assert req.prompt == (text or "[Image unavailable]")
    assert harness.captured[0].run_context.messages[-1].content


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", ["ordinary", "quote", "plugin", "hook"])
@pytest.mark.parametrize("with_valid_image", [False, True])
async def test_oversized_images_explain_omission_and_keep_original_path(
    harness, tmp_path, monkeypatch, origin, with_valid_image
):
    source = tmp_path / "oversized.png"
    PILImage.new("RGB", (4, 4)).save(source)
    with source.open("ab") as file:
        file.truncate(64 * 1024 * 1024 + 1)
    refs = [str(source)]
    if with_valid_image:
        refs.append(str(source_image(tmp_path, "JPEG")))
    attachments = [Image(file=ref) for ref in refs]
    event = make_event(text="describe")
    if origin == "ordinary":
        event.message_obj.message = attachments
    elif origin == "quote":
        event.message_obj.message = [Reply(id="large", chain=attachments)]
    elif origin == "plugin":
        event.set_extra(
            "provider_request",
            ProviderRequest(
                prompt="describe",
                image_urls=refs,
                conversation=harness.context.conversation_manager.get_conversation.return_value,
            ),
        )
    else:

        async def hook(event, kind, *args):
            if kind == EventType.OnLLMRequestEvent:
                args[0].image_urls.extend(refs)
            return False

        monkeypatch.setattr(internal, "call_event_hook", hook)
    await process_event(harness, event, preprocess_first=True)
    req = harness.captured[0].req
    assert len(req.image_urls) == int(with_valid_image)
    payload = harness.provider.text_chat.await_args.kwargs["contexts"][-1]["content"]
    notices = [
        part["text"]
        for part in payload
        if part["type"] == "text" and "skipped: exceeds" in part["text"]
    ]
    assert len(notices) == 1
    assert "64 MiB" in notices[0] and str(source) in notices[0]
    advice = [
        part["text"]
        for part in payload
        if part["type"] == "text"
        and "astrbot_file_read_tool if available" in part["text"]
    ]
    assert len(advice) == 1
    assert "resend a smaller image" in advice[0]
    saved = harness.context.conversation_manager.update_conversation.await_args.kwargs[
        "history"
    ]
    assert any(
        part.get("text") == notices[0]
        for message in saved
        if message["role"] == "user"
        for part in message["content"]
    )
    assert all(
        "resend a smaller image" not in part.get("text", "")
        for message in saved
        if message["role"] == "user"
        for part in message["content"]
    )
    event.cleanup_temporary_local_files()
    assert source.stat().st_size == 64 * 1024 * 1024 + 1
    assert not list(harness.work.rglob("model_image_*"))


@pytest.mark.asyncio
async def test_oversized_plugin_download_is_retained_for_file_tool(
    harness, tmp_path, monkeypatch
):
    source = tmp_path / "source.png"
    PILImage.new("RGB", (4, 4)).save(source)
    original = source.read_bytes()

    async def download(url, target):
        path = Path(target)
        path.write_bytes(original)
        with path.open("ab") as file:
            file.truncate(64 * 1024 * 1024 + 1)

    monkeypatch.setattr(media, "download_file", download)
    event = make_event()
    req = ProviderRequest(image_urls=["https://example.com/large.png"])
    prepared = {}
    for _ in range(2):
        req.image_urls = ["https://example.com/large.png"]
        await image_input.prepare_request_images(
            req, event, max_size=1280, output_dir=harness.work, prepared=prepared
        )
        assert not req.image_urls
    assert len(req.extra_user_content_parts) == 2
    assert not req.extra_user_content_parts[0]._no_save
    assert req.extra_user_content_parts[1]._no_save
    context = await req.assemble_context()
    notices = [part["text"] for part in context["content"] if part["type"] == "text"]
    downloaded = list(harness.work.glob("media_image_*"))
    assert len(downloaded) == 1
    assert any(str(downloaded[0]) in notice for notice in notices)
    event.cleanup_temporary_local_files()
    assert downloaded[0].stat().st_size == 64 * 1024 * 1024 + 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "streaming,fallback", [(False, False), (True, False), (False, True), (True, True)]
)
async def test_stage_stream_and_fallback_reuse_prepared_input(
    harness, tmp_path, monkeypatch, streaming, fallback
):
    source = source_image(tmp_path)
    harness.config["provider_settings"]["streaming_response"] = streaming
    convert = AsyncMock(wraps=image_input.prepare_model_image)
    monkeypatch.setattr(image_input, "prepare_model_image", convert)
    secondary = MagicMock(spec=Provider)
    secondary.provider_config = {"id": "secondary", "modalities": ["text", "image"]}
    secondary.text_chat = AsyncMock(
        return_value=LLMResponse(role="assistant", completion_text="fallback")
    )

    async def stream(**kwargs):
        yield await secondary.text_chat(**kwargs)

    secondary.text_chat_stream = stream
    if fallback:
        harness.provider.text_chat.side_effect = RuntimeError("primary unavailable")
        monkeypatch.setattr(
            main, "_get_fallback_chat_providers", lambda *args: [secondary]
        )
    event = make_event([Image(file=str(source))])
    await process_event(harness, event)
    assert convert.await_count == 1
    primary_payload = harness.provider.text_chat.await_args.kwargs
    if fallback:
        assert (
            primary_payload["contexts"]
            == secondary.text_chat.await_args.kwargs["contexts"]
        )
    assert "image_settings" not in primary_payload
    assert Path(harness.captured[0].req.image_urls[0]).is_file()


@pytest.mark.asyncio
async def test_non_image_and_disabled_ai_do_not_prepare(harness, tmp_path, monkeypatch):
    convert = AsyncMock(side_effect=AssertionError("unexpected image preparation"))
    monkeypatch.setattr(image_input, "prepare_model_image", convert)
    await process_event(harness, make_event())
    harness.config["provider_settings"]["enable"] = False
    await process_event(harness, make_event([Image(file=str(source_image(tmp_path)))]))
    assert convert.await_count == 0 and len(harness.captured) == 1


def test_image_preparation_stays_outside_agent_runner_and_providers():
    root = Path(__file__).parents[1] / "astrbot" / "core"
    paths = [root / "astr_main_agent.py", root / "astr_agent_tool_exec.py"]
    paths += list((root / "agent").rglob("*.py")) + list(
        (root / "provider").rglob("*.py")
    )
    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert (
            "prepare_model_image" not in source
            and "resolve_image_ref_to_images" not in source
        )
        assert "image_settings" not in source
    from astrbot.core.tools.computer_tools.cua import CuaMouseClickTool

    assert (
        "coordinate_space" not in inspect.signature(CuaMouseClickTool.call).parameters
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("reference", ["data", "base64", "http", "file"])
async def test_localized_reference_lifetime_and_ownership(
    harness, tmp_path, monkeypatch, enabled, reference
):
    source = source_image(tmp_path)
    encoded = base64.b64encode(source.read_bytes()).decode()
    refs = {
        "data": "data:image/gif;base64," + encoded,
        "base64": "base64://" + encoded,
        "http": "https://example.com/source?secret=hidden",
        "file": source.as_uri(),
    }

    async def download(url, target):
        Path(target).write_bytes(source.read_bytes())

    monkeypatch.setattr(media, "download_file", download)
    harness.config["provider_settings"]["image_compress_enabled"] = enabled
    event = make_event()
    event.set_extra(
        "provider_request", ProviderRequest(prompt="", image_urls=[refs[reference]])
    )
    await process_event(harness, event)
    path = Path(harness.captured[0].req.image_urls[0])
    assert path.is_file()
    assert str(source) not in event._temporary_local_files
    assert str(path) in event._temporary_local_files
    with PILImage.open(path) as image:
        assert image.format == "JPEG"
    event.cleanup_temporary_local_files()
    assert not path.exists()
    assert source.is_file()


@pytest.mark.asyncio
@pytest.mark.parametrize("fmt", ["JPEG", "PNG"])
@pytest.mark.parametrize("reference", ["data", "base64", "http", "file", "path"])
async def test_compliant_plugin_images_reuse_localized_file_with_correct_ownership(
    harness, tmp_path, monkeypatch, fmt, reference
):
    source = source_image(tmp_path, fmt)
    original = source.read_bytes()
    encoded = base64.b64encode(original).decode()
    refs = {
        "data": f"data:image/{fmt.lower()};base64," + encoded,
        "base64": "base64://" + encoded,
        "http": "https://example.com/source",
        "file": source.as_uri(),
        "path": str(source),
    }

    async def download(url, target):
        Path(target).write_bytes(original)

    monkeypatch.setattr(media, "download_file", download)
    event = make_event()
    event.set_extra(
        "provider_request",
        ProviderRequest(prompt="image", image_urls=[refs[reference]]),
    )
    await process_event(harness, event)
    path = Path(harness.captured[0].req.image_urls[0])
    assert path.read_bytes() == original
    borrowed = reference in {"file", "path"}
    assert (path == source) == borrowed
    assert event._temporary_local_files == []
    assert set(harness.work.rglob("*")) == (set() if borrowed else {path})
    event.cleanup_temporary_local_files()
    assert path.exists()
    assert source.read_bytes() == original


@pytest.mark.asyncio
async def test_two_plugin_requests_on_one_event_are_prepared_independently(
    harness, tmp_path, monkeypatch
):
    first = ProviderRequest(prompt="first", image_urls=[str(source_image(tmp_path))])
    second = ProviderRequest(
        prompt="second", image_urls=[str(source_image(tmp_path, "BMP"))]
    )
    stage = ProcessStage()
    await stage.initialize(harness.ctx)

    async def plugin(event):
        yield first
        yield second

    monkeypatch.setattr(stage.star_request_sub_stage, "process", plugin)
    event = make_event()
    event.set_extra("activated_handlers", [object()])
    event.call_llm = True
    await process_event(harness, event, stage=stage)
    assert len(harness.captured) == 2
    for runner in harness.captured:
        with PILImage.open(runner.req.image_urls[0]) as image:
            assert image.format == "JPEG"
    assert first.image_urls[0].endswith(".gif") and second.image_urls[0].endswith(
        ".bmp"
    )


@pytest.mark.asyncio
async def test_third_party_route_retains_original_images(
    harness, tmp_path, monkeypatch
):
    from astrbot.core.pipeline.process_stage.method.agent_sub_stages.third_party import (
        ThirdPartyAgentSubStage,
    )

    harness.config["agent_runner"] = {"runner_type": "dify", "config": {}}
    source = source_image(tmp_path)
    seen = []

    async def backend(self, event, prefix):
        seen.append(event.get_messages()[0].file)
        yield None

    monkeypatch.setattr(ThirdPartyAgentSubStage, "process", backend)
    monkeypatch.setattr(
        image_input,
        "prepare_model_image",
        AsyncMock(side_effect=AssertionError("third party must not prepare")),
    )
    await process_event(
        harness, make_event([Image(file=str(source))]), preprocess_first=True
    )
    assert seen == [str(source)] and not harness.captured


@pytest.mark.asyncio
async def test_wake_prefix_rejection_does_not_prepare(harness, tmp_path, monkeypatch):
    harness.config["provider_settings"]["wake_prefix"] = "ask "
    monkeypatch.setattr(
        image_input,
        "prepare_model_image",
        AsyncMock(side_effect=AssertionError("not woken")),
    )
    await process_event(harness, make_event([Image(file=str(source_image(tmp_path)))]))
    assert not harness.captured


@pytest.mark.asyncio
async def test_plugin_and_hook_image_list_normalization(harness, tmp_path, monkeypatch):
    source = source_image(tmp_path)
    event = make_event()
    original = ProviderRequest(
        prompt="plugin", image_urls=[None, "", "  " + str(source) + "  ", str(source)]
    )
    event.set_extra("provider_request", original)

    async def hook(event, kind, *args):
        if kind == EventType.OnLLMRequestEvent and event.session_id == "images":
            args[0].image_urls.extend([None, "  ", "  " + str(source) + "  "])
        return False

    monkeypatch.setattr(internal, "call_event_hook", hook)
    await process_event(harness, event)
    assert len(harness.captured[0].req.image_urls) == 1
    assert original.image_urls[0] is None and original.image_urls[2].startswith("  ")
    empty = make_event(session="empty-plugin")
    empty.set_extra("provider_request", ProviderRequest(prompt="text", image_urls=None))
    await process_event(harness, empty)
    assert harness.captured[-1].req.image_urls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("quoted", [False, True])
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("late", [False, True])
@pytest.mark.parametrize("reference", ["file", "base64", "data", "http"])
@pytest.mark.parametrize("fmt", ["JPEG", "GIF"])
async def test_attachment_sources_survive_event_cleanup(
    harness, monkeypatch, quoted, enabled, late, reference, fmt
):
    harness.work.mkdir()
    source = source_image(harness.work, fmt)
    original = source.read_bytes()
    encoded = base64.b64encode(original).decode()
    ref = {
        "file": source.as_uri(),
        "base64": "base64://" + encoded,
        "data": f"data:image/{fmt.lower()};base64," + encoded,
        "http": "https://example.com/image",
    }[reference]
    image = Image(file=ref)
    attachment = Reply(id="image", chain=[image]) if quoted else image
    event = make_event() if late else make_event([attachment])
    if reference == "file":
        event.track_temporary_local_file(str(source))
    unrelated = harness.work / "other.tmp"
    unrelated.write_bytes(b"temporary")
    event.track_temporary_local_file(str(unrelated))
    harness.config["provider_settings"]["image_compress_enabled"] = enabled
    harness.config["provider_settings"]["image_compress_options"]["max_size"] = 12

    async def download(url, target):
        Path(target).write_bytes(original)

    async def hook(event, kind, *args):
        if kind == EventType.OnWaitingLLMRequestEvent:
            event.message_obj.message.append(attachment)
        return False

    monkeypatch.setattr(media, "download_file", download)
    if late:
        monkeypatch.setattr(internal, "call_event_hook", hook)
    await process_event(harness, event, preprocess_first=True)
    req = harness.captured[0].req
    label = "Image 1 in quoted message" if quoted else "Image 1"
    prefix = f"[{label}: original path "
    text = next(
        part.text
        for part in req.extra_user_content_parts
        if isinstance(part, TextPart) and part.text.startswith(prefix)
    )
    attachment_path = Path(
        text[len(prefix) : -1].removesuffix(
            "; animation converted to a 3x3 frame montage"
        )
    )
    visual_path = Path(req.image_urls[0])
    assert attachment_path.read_bytes() == original
    assert str(attachment_path) not in event._temporary_local_files
    assert visual_path != attachment_path
    with PILImage.open(visual_path) as visual_image:
        assert visual_image.format == "JPEG"
        assert max(visual_image.size) == 12

    owned = [Path(path) for path in event._temporary_local_files]
    assert len(owned) == 2
    assert unrelated in owned
    event.cleanup_temporary_local_files()
    assert attachment_path.read_bytes() == original
    assert all(not path.exists() for path in owned)
    assert not visual_path.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
async def test_stage_failure_preserves_sources_and_cleans_working_files(
    harness, monkeypatch, failure
):
    harness.work.mkdir()
    source = source_image(harness.work)
    original = source.read_bytes()
    event = make_event([Image(file=str(source))])
    preprocess_stage = preprocess.PreProcessStage()
    await preprocess_stage.initialize(harness.ctx)
    await preprocess_stage.process(event)

    async def hook(event, kind, *args):
        if kind == EventType.OnLLMRequestEvent:
            raise failure("request interrupted")
        return False

    monkeypatch.setattr(internal, "call_event_hook", hook)
    stage = ProcessStage()
    await stage.initialize(harness.ctx)
    expectation = (
        pytest.raises(asyncio.CancelledError, match="request interrupted")
        if failure is asyncio.CancelledError
        else nullcontext()
    )
    with expectation:
        async for _ in stage.process(event):
            pass
    owned = [Path(path) for path in event._temporary_local_files]
    assert len(owned) == 1 and owned[0].is_file()
    assert owned[0] != source
    assert not harness.captured
    event.cleanup_temporary_local_files()
    assert not owned[0].exists()
    assert source.read_bytes() == original


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit", [False, True])
async def test_direct_build_prepares_images_and_quote_collection(
    harness, tmp_path, monkeypatch, explicit
):
    source = source_image(tmp_path)
    event = make_event(
        [
            Image(file=str(source)),
            Reply(
                id="direct",
                chain=[Plain(text="quoted text"), Image(file=str(source))],
                message_str="quoted text",
            ),
        ]
    )
    convert = AsyncMock(wraps=image_input.prepare_model_image)
    monkeypatch.setattr(image_input, "prepare_model_image", convert)
    req = (
        ProviderRequest(prompt="direct", image_urls=[str(source)]) if explicit else None
    )
    result = await main.build_main_agent(
        event=event,
        plugin_context=harness.context,
        config=main.MainAgentBuildConfig(
            tool_call_timeout=60, provider_settings=harness.config["provider_settings"]
        ),
        provider=harness.provider,
        req=req,
    )
    assert result and len(result.provider_request.image_urls) == 1
    assert convert.await_count == 1
    assert result.provider_request.image_urls[0] != str(source)
    quote_parts = [
        part
        for part in result.provider_request.extra_user_content_parts
        if isinstance(part, TextPart) and part.text.startswith("<Quoted Message>")
    ]
    assert len(quote_parts) == 1 and "quoted text" in quote_parts[0].text
    with PILImage.open(result.provider_request.image_urls[0]) as image:
        assert image.format == "JPEG" and image.size == (90, 45)
    assert Path(result.provider_request.image_urls[0]).stat().st_size < 512 * 1024
    event.cleanup_temporary_local_files()
    assert source.is_file()
    assert not Path(result.provider_request.image_urls[0]).exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("quoted", [False, True])
@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
@pytest.mark.parametrize("fail_at", ["attachment", "conversation"])
async def test_materialized_sources_remain_owned_when_collection_fails(
    harness, tmp_path, monkeypatch, quoted, failure, fail_at
):
    source = source_image(tmp_path)
    attachments = [
        Image(file="base64://" + base64.b64encode(source.read_bytes()).decode())
    ]
    event = make_event(
        [Reply(id="failed", chain=attachments)] if quoted else attachments
    )
    if fail_at == "attachment":
        failing_image = MagicMock(spec=Image)
        failing_image.convert_to_file_path = AsyncMock(
            side_effect=failure("unavailable")
        )
        chain = event.message_obj.message[0].chain if quoted else event.get_messages()
        chain.append(failing_image)
    else:
        monkeypatch.setattr(
            main,
            "_get_session_conv",
            AsyncMock(side_effect=failure("unavailable")),
        )
    with pytest.raises(failure, match="unavailable"):
        await main.collect_initial_request(
            event, harness.context, main.MainAgentBuildConfig(tool_call_timeout=60)
        )
    assert len(event._temporary_local_files) == 1
    owned = Path(event._temporary_local_files[0])
    assert owned.read_bytes() == source.read_bytes()
    event.cleanup_temporary_local_files()
    assert not owned.exists() and source.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("remove_image", [False, True])
@pytest.mark.parametrize("rewrite_text_parts", [False, True])
async def test_final_image_labels_follow_mixed_visuals_after_hook(
    harness, tmp_path, monkeypatch, remove_image, rewrite_text_parts
):
    oversized = tmp_path / "oversized.png"
    PILImage.new("RGB", (4, 4)).save(oversized)
    with oversized.open("ab") as file:
        file.truncate(64 * 1024 * 1024 + 1)
    still = source_image(tmp_path, "JPEG")
    animation = source_image(tmp_path, "GIF")
    inserted = source_image(tmp_path, "BMP")
    event = make_event(
        [
            Image(file=str(oversized)),
            Image(file=str(still)),
            Reply(id="animation", chain=[Image(file=str(animation))]),
        ]
    )
    convert = AsyncMock(wraps=image_input.prepare_model_image)
    monkeypatch.setattr(image_input, "prepare_model_image", convert)

    async def hook(event, kind, *args):
        if kind == EventType.OnLLMRequestEvent:
            req = args[0]
            if rewrite_text_parts:
                req.extra_user_content_parts = []
            # Extra image parts precede image_urls in the actual provider payload.
            req.extra_user_content_parts.insert(
                0, ImageURLPart(image_url=ImageURLPart.ImageURL(url=str(inserted)))
            )
            req.extra_user_content_parts.append(
                TextPart(text="[Image captions supplied by a plugin]")
            )
            req.image_urls = ([] if remove_image else [str(animation)]) + [
                str(still),
                str(oversized),
                str(still),
            ]
        return False

    monkeypatch.setattr(internal, "call_event_hook", hook)
    await process_event(harness, event, preprocess_first=True)
    assert convert.await_count == 4
    req = harness.captured[0].req
    payload = harness.provider.text_chat.await_args.kwargs["contexts"][-1]["content"]
    expected = [inserted, still] if remove_image else [inserted, animation, still]
    images = [
        index for index, part in enumerate(payload) if part["type"] == "image_url"
    ]
    assert len(images) == len(expected)
    visual_paths = [
        part.image_url.url
        for part in req.extra_user_content_parts
        if isinstance(part, ImageURLPart)
    ] + req.image_urls
    for number, (position, original) in enumerate(zip(images, expected), 1):
        label = next(
            part
            for part in payload
            if part["type"] == "text"
            and part["text"].startswith(f"[Image {number}:")
            or part["type"] == "text"
            and part["text"].startswith(f"[Image {number} in quoted message:")
        )
        assert f"original path {original}" in label["text"]
        assert ("in quoted message" in label["text"]) == (original == animation)
        assert ("3x3 frame montage" in label["text"]) == (original == animation)
        data = base64.b64decode(payload[position]["image_url"]["url"].split(",", 1)[1])
        assert data == Path(visual_paths[number - 1]).read_bytes()
    texts = [part["text"] for part in payload if part["type"] == "text"]
    assert "[Image captions supplied by a plugin]" in texts
    for original in (oversized, still, animation, inserted):
        assert sum(str(original) in text for text in texts) == 1
    assert any(
        str(oversized) in text and "skipped: exceeds 64 MiB" in text for text in texts
    )
    if remove_image:
        assert any(
            str(animation) in text and "not included in this request" in text
            for text in texts
        )
    history = (
        harness.context.conversation_manager.update_conversation.await_args.kwargs[
            "history"
        ]
    )
    saved = next(message["content"] for message in history if message["role"] == "user")
    assert [
        p["text"]
        for p in saved
        if p["type"] == "text" and p["text"].startswith("[Image")
    ] == [text for text in texts if text.startswith("[Image")]
    event.cleanup_temporary_local_files()
    assert all(path.is_file() for path in (oversized, still, animation, inserted))


@pytest.mark.asyncio
@pytest.mark.parametrize("add_uncaptioned_image", [False, True])
async def test_captioned_quote_has_status_without_visual_index(
    harness, tmp_path, monkeypatch, add_uncaptioned_image
):
    source = source_image(tmp_path)
    harness.provider.provider_config["modalities"] = ["text"]
    harness.config["provider_settings"]["default_image_caption_provider_id"] = "caption"
    caption = MagicMock(spec=Provider)
    caption.text_chat = AsyncMock(
        return_value=LLMResponse(
            role="assistant", completion_text="An animated red square."
        )
    )
    harness.context.get_provider_by_id.return_value = caption
    event = make_event([Reply(id="quoted", chain=[Image(file=str(source))])])
    inserted = source_image(tmp_path, "JPEG")

    async def hook(event, kind, *args):
        if kind == EventType.OnLLMRequestEvent and add_uncaptioned_image:
            args[0].image_urls.append(str(inserted))
        return False

    monkeypatch.setattr(internal, "call_event_hook", hook)
    await process_event(harness, event, preprocess_first=True)
    assert caption.text_chat.await_count == 1
    payload = harness.provider.text_chat.await_args.kwargs["contexts"][-1]["content"]
    assert not any(part["type"] == "image_url" for part in payload)
    labels = [
        part["text"]
        for part in payload
        if part["type"] == "text" and str(source) in part["text"]
    ]
    assert len(labels) == 1
    assert "in quoted message" in labels[0]
    assert "description included as text" in labels[0]
    assert "[Image 1" not in labels[0]
    if add_uncaptioned_image:
        label = next(
            part["text"] for part in payload if str(inserted) in part.get("text", "")
        )
        assert "not included in this request" in label
        assert "description included as text" not in label


@pytest.mark.asyncio
async def test_temporary_skipped_image_does_not_persist_its_path(harness, tmp_path):
    from astrbot.core.agent.message import Message

    source = tmp_path / "private.png"
    PILImage.new("RGB", (4, 4)).save(source)
    with source.open("ab") as file:
        file.truncate(64 * 1024 * 1024 + 1)
    req = ProviderRequest(
        prompt="describe",
        extra_user_content_parts=[
            ImageURLPart(
                image_url=ImageURLPart.ImageURL(url=str(source))
            ).mark_as_temp()
        ],
    )
    await image_input.prepare_request_images(
        req, make_event(), max_size=1280, output_dir=harness.work, prepared={}
    )
    context = await req.assemble_context()
    assert any(str(source) in part.get("text", "") for part in context["content"])
    saved = dump_messages_with_checkpoints([Message.model_validate(context)])
    assert saved[0]["content"] == [{"type": "text", "text": "describe"}]


@pytest.mark.asyncio
async def test_duplicate_current_and_quoted_image_share_one_visual_label(
    harness, tmp_path
):
    source = source_image(tmp_path, "JPEG")
    event = make_event(
        [
            Image(file=str(source)),
            Reply(id="same", chain=[Image(file=str(source))]),
        ]
    )
    await process_event(harness, event, preprocess_first=True)
    content = harness.provider.text_chat.await_args.kwargs["contexts"][-1]["content"]
    images = [i for i, part in enumerate(content) if part["type"] == "image_url"]
    assert len(images) == 1
    label = next(
        part["text"]
        for part in content
        if part.get("text", "").startswith("[Image 1 in quoted message:")
    )
    assert label == f"[Image 1 in quoted message: original path {source}]"
    assert sum(str(source) in part.get("text", "") for part in content) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", ["image_urls", "image_part", "dict_part"])
@pytest.mark.parametrize(
    "size_case", ["compliant", "boundary", "compress", "oversized"]
)
async def test_hook_only_new_refs_receive_full_image_policy(
    harness, tmp_path, monkeypatch, origin, size_case
):
    initial = tmp_path / "initial.jpg"
    PILImage.new("RGB", (300, 150), "blue").save(initial)
    added = tmp_path / "added.jpg"
    PILImage.new("RGB", (600, 300), "red").save(added)
    if size_case == "compress":
        added = tmp_path / "added.png"
        pixels = random.Random(42).randbytes(1000 * 800 * 3)
        PILImage.frombytes("RGB", (1000, 800), pixels).save(added)
        assert 512 * 1024 < added.stat().st_size < 64 * 1024 * 1024
    elif size_case in {"boundary", "oversized"}:
        with added.open("ab") as file:
            file.truncate(
                512 * 1024 if size_case == "boundary" else 64 * 1024 * 1024 + 1
            )
    original_bytes = added.read_bytes() if size_case != "oversized" else None
    convert = AsyncMock(wraps=image_input.prepare_model_image)
    monkeypatch.setattr(image_input, "prepare_model_image", convert)

    async def hook(event, kind, *args):
        if kind == EventType.OnLLMRequestEvent:
            req = args[0]
            assert convert.await_count == 1
            with PILImage.open(req.image_urls[0]) as image:
                assert image.size == (90, 45)
            # Reintroducing an already processed original must also reuse its preview.
            req.image_urls.append(str(initial))
            if origin == "image_urls":
                req.image_urls.append(str(added))
            elif origin == "image_part":
                req.extra_user_content_parts.append(
                    ImageURLPart(image_url=ImageURLPart.ImageURL(url=str(added)))
                )
            else:
                req.extra_user_content_parts.append(
                    {"type": "image_url", "image_url": {"url": str(added)}}
                )
        return False

    monkeypatch.setattr(internal, "call_event_hook", hook)
    event = make_event([Image(file=str(initial))])
    await process_event(harness, event, preprocess_first=True)
    assert [call.args[0] for call in convert.await_args_list] == [
        str(initial),
        str(added),
    ]
    assert [call.kwargs["max_size"] for call in convert.await_args_list] == [90, 90]
    payload = harness.provider.text_chat.await_args.kwargs["contexts"][-1]["content"]
    images = [part for part in payload if part["type"] == "image_url"]
    assert len(images) == (1 if size_case == "oversized" else 2)
    for image in images:
        assert (
            len(base64.b64decode(image["image_url"]["url"].split(",", 1)[1]))
            < 512 * 1024
        )
    if size_case == "oversized":
        assert any(
            str(added) in part.get("text", "")
            and "skipped: exceeds 64 MiB" in part["text"]
            for part in payload
        )
    else:
        req = harness.captured[0].req
        if origin == "image_urls":
            result_path = req.image_urls[-1]
        else:
            part = next(
                part
                for part in req.extra_user_content_parts
                if isinstance(part, ImageURLPart)
                or isinstance(part, dict)
                and part.get("type") == "image_url"
            )
            result_path = (
                part["image_url"]["url"]
                if isinstance(part, dict)
                else part.image_url.url
            )
        with PILImage.open(result_path) as image:
            assert max(image.size) <= 90
        assert result_path != str(added)
        assert Path(result_path).stat().st_size < 512 * 1024
    event.cleanup_temporary_local_files()
    assert initial.exists() and added.exists()
    if original_bytes is not None:
        assert added.read_bytes() == original_bytes


@pytest.mark.asyncio
@pytest.mark.parametrize("with_image", [False, True])
@pytest.mark.parametrize("as_dict", [False, True])
async def test_plugin_image_notices_are_not_parsed(
    harness, tmp_path, monkeypatch, with_image, as_dict
):
    source = source_image(tmp_path, "JPEG")
    texts = [
        "[Image Attachment: path /plugin/reference-only.png]",
        f"[Image 1: original path {source}]",
        "<system_notice>\nFor skipped images, keep this plugin instruction.\n</system_notice>",
        "<system_notice>\nImages labeled as animation montages contain frames in reading order. "
        "Treat them as animations; do not mention the conversion or frame layout.\n</system_notice>",
        "<image_caption>This text is supplied by a plugin.</image_caption>",
    ]
    plugin_parts = [
        {"type": "text", "text": text} if as_dict else TextPart(text=text)
        for text in texts
    ]
    req = ProviderRequest(
        prompt="Use these references if needed",
        image_urls=[str(source)] if with_image else [],
        extra_user_content_parts=list(plugin_parts),
    )
    prepared = {}
    convert = AsyncMock(wraps=image_input.prepare_model_image)
    monkeypatch.setattr(image_input, "prepare_model_image", convert)
    for _ in range(2):
        await image_input.prepare_request_images(
            req, make_event(), max_size=90, prepared=prepared, output_dir=harness.work
        )
        for part in plugin_parts:
            assert any(current is part for current in req.extra_user_content_parts)
        content = (await req.assemble_context())["content"]
        for text in texts:
            assert any(part.get("text") == text for part in content)
        assert len(req.extra_user_content_parts) == len(plugin_parts) + int(with_image)
    assert convert.await_count == int(with_image)


@pytest.mark.asyncio
@pytest.mark.parametrize("drop_extra_in_hook", [False, True])
async def test_only_actually_captioned_images_receive_caption_status(
    harness, tmp_path, monkeypatch, drop_extra_in_hook
):
    main_image = source_image(tmp_path, "JPEG")
    extra_image = source_image(tmp_path, "PNG")
    harness.provider.provider_config["modalities"] = ["text"]
    harness.config["provider_settings"]["default_image_caption_provider_id"] = "caption"
    caption = MagicMock(spec=Provider)
    caption.text_chat = AsyncMock(
        return_value=LLMResponse(role="assistant", completion_text="A red square.")
    )
    harness.context.get_provider_by_id.return_value = caption
    event = make_event()
    event.set_extra(
        "provider_request",
        ProviderRequest(
            prompt="describe both",
            image_urls=[str(main_image)],
            extra_user_content_parts=[
                ImageURLPart(image_url=ImageURLPart.ImageURL(url=str(extra_image)))
            ],
            conversation=harness.context.conversation_manager.get_conversation.return_value,
        ),
    )

    async def hook(event, kind, *args):
        if kind == EventType.OnLLMRequestEvent and drop_extra_in_hook:
            req = args[0]
            req.extra_user_content_parts = [
                part
                for part in req.extra_user_content_parts
                if not isinstance(part, ImageURLPart)
            ]
        return False

    monkeypatch.setattr(internal, "call_event_hook", hook)
    await process_event(harness, event)
    assert caption.text_chat.await_count == 1
    assert caption.text_chat.await_args.kwargs["image_urls"] == [str(main_image)]
    content = harness.provider.text_chat.await_args.kwargs["contexts"][-1]["content"]
    assert not any(part["type"] == "image_url" for part in content)
    for path, captioned in ((main_image, True), (extra_image, False)):
        labels = [part["text"] for part in content if str(path) in part.get("text", "")]
        assert len(labels) == 1
        assert ("description included as text" in labels[0]) == captioned
        assert ("not included in this request" in labels[0]) != captioned
