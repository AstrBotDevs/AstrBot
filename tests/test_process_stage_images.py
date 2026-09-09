"""Exercise the real preprocess/process/build/reset sequence with generated images."""

import asyncio
import base64
import copy
import inspect
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
    image_input,
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
    for module in (media, internal, preprocess):
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
async def test_profile_toggle_and_preprocess_to_first_model(
    harness, tmp_path, monkeypatch, enabled, fmt
):
    source = source_image(tmp_path, fmt)
    original = source.read_bytes()
    event = make_event([Image(file=str(source))], text="")
    if enabled is None:
        harness.config["provider_settings"].pop("image_compress_enabled", None)
    else:
        harness.config["provider_settings"]["image_compress_enabled"] = enabled
    if enabled is False:
        monkeypatch.setattr(
            media,
            "_read_valid_cached_image_bytes",
            lambda *args: pytest.fail("disabled must not query derived cache"),
        )
    await process_event(harness, event, preprocess_first=True)
    assert len(harness.captured) == 1
    req = harness.captured[0].req
    with PILImage.open(req.image_urls[0]) as image:
        assert image.format == (fmt if enabled is False else "PNG")
        assert image.size == (
            (90, 45) if enabled is not False and fmt == "GIF" else (60, 30)
        )
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


@pytest.mark.asyncio
async def test_profile_reload_and_concurrent_requests(harness, tmp_path):
    source = source_image(tmp_path)
    before = copy.deepcopy(harness.provider.provider_config)
    stage = await process_event(
        harness, make_event([Image(file=str(source))], session="first")
    )
    other_config = copy.deepcopy(harness.config)
    other_config["provider_settings"]["image_compress_enabled"] = False
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
            make_event([Image(file=str(source))], session="off"),
            stage=other_stage,
        ),
    )
    results = {
        runner.req.session_id.split(":")[-1]: runner.req for runner in harness.captured
    }
    with PILImage.open(results["small"].image_urls[0]) as image:
        assert max(image.size) == 30
    assert Path(results["off"].image_urls[0]).read_bytes() == source.read_bytes()
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
        p["image_url"]["url"].startswith("data:image/png;base64,") for p in images
    )
    assert all(p["image_url"].get("id") != "dict-id" for p in images)
    paths = list(event._temporary_local_files)
    cache_files = list((harness.work / media.CONVERT_CACHE_DIR_NAME).glob("*.png"))
    event.cleanup_temporary_local_files()
    assert all(not Path(path).exists() for path in paths)
    assert cache_files and all(path.exists() for path in cache_files)
    assert all(
        base64.b64decode(p["image_url"]["url"].split(",", 1)[1]).startswith(b"\x89PNG")
        for p in images
    )
    from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic

    anthropic = object.__new__(ProviderAnthropic)
    _, payload = anthropic._prepare_payload([saved[-1]])
    visual = [part for part in payload[0]["content"] if part["type"] == "image"]
    assert len(visual) == len(images)
    assert all(part["source"]["media_type"] == "image/png" for part in visual)


@pytest.mark.asyncio
@pytest.mark.parametrize("plugin", [False, True])
async def test_caption_first_call_uses_prepared_quote(harness, tmp_path, plugin):
    source = source_image(tmp_path)
    harness.provider.provider_config["modalities"] = ["text"]
    harness.config["provider_settings"]["default_image_caption_provider_id"] = "caption"
    caption = MagicMock(spec=Provider)
    captured = []

    async def describe(**kwargs):
        assert "image_settings" not in kwargs
        for ref in kwargs["image_urls"]:
            with PILImage.open(ref) as image:
                assert image.format == "PNG" and getattr(image, "n_frames", 1) == 1
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
        source = path.read_text()
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
    assert (str(path) in event._temporary_local_files) == (
        enabled or reference != "file"
    )
    with PILImage.open(path) as image:
        assert image.format == ("PNG" if enabled else "GIF")
    if not enabled:
        assert path.read_bytes() == source.read_bytes()


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
            assert image.format == "PNG"
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
async def test_late_image_component_sources_are_event_owned(
    harness, tmp_path, monkeypatch, quoted
):
    source = source_image(tmp_path)
    ref = "base64://" + base64.b64encode(source.read_bytes()).decode()
    late_image = Image(file=ref)

    async def hook(event, kind, *args):
        if kind == EventType.OnWaitingLLMRequestEvent:
            event.message_obj.message.append(
                Reply(id="late", chain=[late_image]) if quoted else late_image
            )
        return False

    monkeypatch.setattr(internal, "call_event_hook", hook)
    event = make_event()
    await process_event(harness, event, preprocess_first=True)
    owned = [Path(path) for path in event._temporary_local_files]
    assert len(owned) == 2
    assert sorted(PILImage.open(path).format for path in owned) == ["GIF", "PNG"]
    assert late_image.file == ref
    assert all(path.exists() for path in owned)


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit", [False, True])
async def test_direct_build_keeps_raw_images_and_quote_collection(
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
    monkeypatch.setattr(
        image_input,
        "prepare_model_image",
        AsyncMock(side_effect=AssertionError("direct build must not convert")),
    )
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
    assert result and result.provider_request.image_urls == [str(source)]
    quote_parts = [
        part
        for part in result.provider_request.extra_user_content_parts
        if isinstance(part, TextPart) and part.text.startswith("<Quoted Message>")
    ]
    assert len(quote_parts) == 1 and "quoted text" in quote_parts[0].text
    with PILImage.open(result.provider_request.image_urls[0]) as image:
        assert image.format == "GIF" and image.n_frames == 2


@pytest.mark.asyncio
async def test_materialized_sources_remain_owned_when_collection_fails(
    harness, tmp_path, monkeypatch
):
    source = source_image(tmp_path)
    event = make_event(
        [Image(file="base64://" + base64.b64encode(source.read_bytes()).decode())]
    )
    monkeypatch.setattr(
        main,
        "_get_session_conv",
        AsyncMock(side_effect=RuntimeError("conversation unavailable")),
    )
    with pytest.raises(RuntimeError, match="conversation unavailable"):
        await main.collect_initial_request(
            event, harness.context, main.MainAgentBuildConfig(tool_call_timeout=60)
        )
    assert len(event._temporary_local_files) == 1
    owned = Path(event._temporary_local_files[0])
    assert owned.read_bytes() == source.read_bytes()
    event.cleanup_temporary_local_files()
    assert not owned.exists() and source.exists()
