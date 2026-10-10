import asyncio
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from aiohttp import web
from PIL import Image as PillowImage

from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.message.components import Image, Plain
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.pipeline.result_decorate.stage import ResultDecorateStage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.utils.t2i.renderer import HtmlRenderer


@pytest_asyncio.fixture
async def render_service(tmp_path, monkeypatch, response_status):
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    (tmp_path / "data" / "temp").mkdir(parents=True)
    started = asyncio.Event()
    release = asyncio.Event()

    async def render(request):
        await request.read()
        started.set()
        await release.wait()
        return web.json_response({"data": {"id": "result.png"}}, status=response_status)

    # The real template embeds the multi-megabyte Shiki runtime.
    app = web.Application(client_max_size=8 * 1024 * 1024)
    app.router.add_post("/text2img/generate", render)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    endpoint = f"http://127.0.0.1:{runner.addresses[0][1]}/text2img"
    try:
        yield HtmlRenderer(endpoint), started, release, tmp_path
    finally:
        release.set()
        await runner.cleanup()


@pytest.fixture
def response_status():
    return 200


@pytest_asyncio.fixture
async def decorated_reply(render_service, monkeypatch):
    renderer, _, _, _ = render_service
    config = deepcopy(DEFAULT_CONFIG)
    config["t2i"] = True
    config["t2i_word_threshold"] = 50
    config["t2i_endpoint"] = renderer.network_strategy.BASE_RENDER_URL
    config["t2i_use_file_service"] = False
    config["provider_tts_settings"]["enable"] = False
    config["platform_settings"]["segmented_reply"]["enable"] = False
    config["content_safety"]["also_use_in_response"] = False
    context = SimpleNamespace(
        astrbot_config=config,
        plugin_manager=SimpleNamespace(
            context=SimpleNamespace(
                get_using_tts_provider_async=AsyncMock(return_value=None)
            )
        ),
    )
    stage = ResultDecorateStage()
    await stage.initialize(context)
    monkeypatch.setattr(
        "astrbot.core.pipeline.result_decorate.stage.html_renderer", renderer
    )

    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.sender = MessageMember("test-user", "Test User")
    message.message = [Plain("hello")]
    event = AstrMessageEvent(
        "hello", message, PlatformMetadata("test", "Test platform", "test"), "test-user"
    )
    event.plugins_name = []
    event.set_result(MessageEventResult(chain=[Plain("hello " * 12)]))
    return stage, event


@pytest.mark.asyncio
async def test_cancelled_remote_render_does_not_fall_back_to_local(render_service):
    renderer, started, release, root = render_service
    task = asyncio.create_task(renderer.render_t2i("hello", return_url=True))
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5)
        assert task.cancelled()
        assert not list((root / "data" / "temp").iterdir())
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancelled_result_decoration_propagates_cancellation(
    render_service, decorated_reply
):
    _, started, release, root = render_service
    stage, event = decorated_reply
    process = stage.process(event)
    task = asyncio.create_task(anext(process, None))
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5)
        assert task.cancelled()
        assert not list((root / "data" / "temp").iterdir())
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await process.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("response_status", [200, 503])
async def test_renderer_preserves_success_and_ordinary_error_fallback(
    render_service, response_status
):
    renderer, _, release, root = render_service
    release.set()

    result = await asyncio.wait_for(renderer.render_t2i("hello", return_url=True), 5)

    if response_status == 200:
        assert result == f"{renderer.network_strategy.BASE_RENDER_URL}/result.png"
        assert not list((root / "data" / "temp").iterdir())
    else:
        assert Path(result).parent == root / "data" / "temp"
        with PillowImage.open(result) as image:
            assert image.width == 800


@pytest.mark.asyncio
@pytest.mark.parametrize("response_status", [200, 503])
async def test_result_decoration_preserves_image_output(
    render_service, decorated_reply, response_status
):
    renderer, _, release, _ = render_service
    stage, event = decorated_reply
    release.set()

    async for _ in stage.process(event):
        pass

    result = event.get_result()
    assert len(result.chain) == 1
    assert isinstance(result.chain[0], Image)
    if response_status == 200:
        assert result.chain[0].file == (
            f"{renderer.network_strategy.BASE_RENDER_URL}/result.png"
        )
    else:
        assert Path(result.chain[0].path).is_file()


@pytest.mark.asyncio
@pytest.mark.parametrize("response_status", [503])
async def test_result_decoration_keeps_text_if_local_fallback_also_fails(
    render_service, decorated_reply, monkeypatch
):
    _, _, release, _ = render_service
    stage, event = decorated_reply
    release.set()
    monkeypatch.setattr(
        PillowImage.Image, "save", MagicMock(side_effect=OSError("image save failed"))
    )

    async for _ in stage.process(event):
        pass

    result = event.get_result()
    assert len(result.chain) == 1
    assert isinstance(result.chain[0], Plain)
    assert result.chain[0].text == "hello " * 12
