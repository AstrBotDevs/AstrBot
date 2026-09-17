import base64
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image as PILImage

from astrbot.core.agent.runners.base import AgentState
from astrbot.core.agent.runners.coze.coze_agent_runner import CozeAgentRunner
from astrbot.core.agent.runners.deerflow.deerflow_agent_runner import (
    DeerFlowAgentRunner,
)
from astrbot.core.agent.runners.dify.dify_agent_runner import DifyAgentRunner
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.utils.image_media_store import ImageMediaStore
from astrbot.core.utils.media_utils import ImagePayloadTooLargeError


def _png_data_url() -> tuple[str, bytes]:
    image_buffer = BytesIO()
    PILImage.new("RGBA", (1, 1), (255, 0, 0, 255)).save(image_buffer, format="PNG")
    image_bytes = image_buffer.getvalue()
    return (
        f"data:image/png;base64,{base64.b64encode(image_bytes).decode()}",
        image_bytes,
    )


@pytest.mark.asyncio
async def test_dify_image_upload_uses_media_resolver_for_data_url():
    image_ref, image_bytes = _png_data_url()
    captured: dict[str, object] = {}

    class _FakeDifyClient:
        async def file_upload(self, **kwargs):
            captured.update(kwargs)
            return {"id": "file-1"}

    runner = DifyAgentRunner.__new__(DifyAgentRunner)
    runner.api_client = _FakeDifyClient()

    payload = await runner._upload_image_for_dify(image_ref, "session-1")

    assert payload == {
        "type": "image",
        "transfer_method": "local_file",
        "upload_file_id": "file-1",
    }
    assert captured["file_data"] == image_bytes
    assert captured["mime_type"] == "image/png"
    assert captured["file_name"] == "image.png"


@pytest.mark.asyncio
async def test_coze_image_upload_uses_media_resolver_for_data_url():
    image_ref, image_bytes = _png_data_url()
    captured: dict[str, bytes] = {}

    class _FakeCozeClient:
        async def upload_file(self, file_data: bytes) -> str:
            captured["file_data"] = file_data
            return "file-1"

    runner = CozeAgentRunner.__new__(CozeAgentRunner)
    runner.api_client = _FakeCozeClient()
    runner.file_id_cache = {}

    file_id = await runner._download_and_upload_image(image_ref, "session-1")

    assert file_id == "file-1"
    assert captured["file_data"] == image_bytes
    assert list(runner.file_id_cache["session-1"].values()) == ["file-1"]


@pytest.mark.asyncio
async def test_coze_history_reference_is_materialized_before_upload(
    tmp_path, monkeypatch
):
    import astrbot.core.agent.runners.coze.coze_agent_runner as coze_module

    image_ref, image_bytes = _png_data_url()
    stored = ImageMediaStore(tmp_path / "media").put(
        base64.b64decode(image_ref.split(",", 1)[1])
    )
    captured: dict[str, object] = {}
    uploaded: list[str] = []
    upload_options = []

    async def get_async(*_args, **_kwargs):
        return ""

    monkeypatch.setattr(coze_module.sp, "get_async", get_async)
    monkeypatch.setattr(
        coze_module,
        "get_astrbot_data_path",
        lambda: str(tmp_path),
    )

    class _FakeCozeClient:
        async def chat_messages(self, **kwargs):
            captured.update(kwargs)
            yield {"event": "conversation.message.completed", "data": {}}
            yield {"event": "conversation.chat.completed", "data": {}}

    runner = CozeAgentRunner.__new__(CozeAgentRunner)
    runner.req = ProviderRequest(
        session_id="session-1",
        contexts=[{"role": "user", "content": [stored.model_dump()]}],
    )
    runner.auto_save_history = False
    runner.api_client = _FakeCozeClient()
    runner.bot_id = "bot-1"
    runner.timeout = 10
    runner.streaming = False
    runner._state = AgentState.RUNNING

    async def on_agent_done(*_args, **_kwargs):
        return None

    runner.agent_hooks = SimpleNamespace(
        on_agent_done=on_agent_done,
    )
    runner.run_context = SimpleNamespace()

    async def capture_upload(image_url, _session_id, *, image_options=None):
        uploaded.append(image_url)
        upload_options.append(image_options)
        return "file-1"

    runner._download_and_upload_image = capture_upload

    responses = [response async for response in runner._execute_coze_request()]

    assert len(responses) == 1
    assert len(uploaded) == 1
    assert upload_options[0].enabled is False
    assert base64.b64decode(uploaded[0].split(",", 1)[1]) == image_bytes
    assert captured["additional_messages"][0]["content"][0] == {
        "type": "file",
        "file_id": "file-1",
        "file_url": uploaded[0],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("runner_cls", "execute_method"),
    [
        (DifyAgentRunner, "_execute_dify_request"),
        (CozeAgentRunner, "_execute_coze_request"),
        (DeerFlowAgentRunner, "_execute_deerflow_request"),
    ],
)
async def test_resource_failure_is_not_converted_to_agent_response(
    runner_cls, execute_method
):
    failure = ImagePayloadTooLargeError("image exceeds the request budget")

    async def failed_request():
        raise failure
        yield  # pragma: no cover

    runner = runner_cls.__new__(runner_cls)
    runner.req = ProviderRequest(prompt="hello")
    runner._state = AgentState.IDLE
    runner.agent_hooks = SimpleNamespace(on_agent_begin=AsyncMock())
    runner.run_context = SimpleNamespace()
    setattr(runner, execute_method, failed_request)
    if runner_cls in {DifyAgentRunner, CozeAgentRunner}:
        runner.api_client = SimpleNamespace(close=AsyncMock())

    with pytest.raises(ImagePayloadTooLargeError) as caught:
        async for _ in runner.step():
            pass

    assert caught.value is failure
    assert runner._state == AgentState.ERROR
