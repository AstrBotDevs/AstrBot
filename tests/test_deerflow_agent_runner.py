import base64
from io import BytesIO

import pytest
from PIL import Image as PILImage

from astrbot.core.agent.runners.deerflow.deerflow_agent_runner import (
    DeerFlowAgentRunner,
)
from astrbot.core.agent.runners.deerflow.deerflow_content_mapper import (
    build_user_content_resolved,
)


def _png_base64() -> str:
    image_buffer = BytesIO()
    PILImage.new("RGBA", (1, 1), (255, 0, 0, 255)).save(image_buffer, format="PNG")
    return base64.b64encode(image_buffer.getvalue()).decode("ascii")


def test_build_payload_includes_configurable_runtime_overrides_and_legacy_context():
    runner = DeerFlowAgentRunner()
    runner.assistant_id = "lead_agent"
    runner.thinking_enabled = True
    runner.plan_mode = True
    runner.subagent_enabled = True
    runner.max_concurrent_subagents = 5
    runner.model_name = "gpt-4.1"
    runner.recursion_limit = 321

    payload = runner._build_payload(
        thread_id="thread-123",
        prompt="hello deerflow",
        image_urls=[],
        system_prompt=None,
    )

    expected_runtime = {
        "thread_id": "thread-123",
        "thinking_enabled": True,
        "is_plan_mode": True,
        "subagent_enabled": True,
        "max_concurrent_subagents": 5,
        "model_name": "gpt-4.1",
    }

    assert payload["assistant_id"] == "lead_agent"
    assert payload["stream_mode"] == ["values", "messages-tuple", "custom"]
    assert payload["config"]["recursion_limit"] == 321
    assert payload["config"]["configurable"] == expected_runtime
    assert payload["context"] == expected_runtime


@pytest.mark.asyncio
async def test_build_user_content_resolved_supports_base64_scheme(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "astrbot.core.utils.media_utils.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )
    image_base64 = _png_base64()

    content = await build_user_content_resolved(
        "look",
        [f"base64://{image_base64}"],
    )

    assert content == [
        {"type": "text", "text": "look"},
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{image_base64}"},
        },
    ]
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_build_payload_resolved_supports_local_image_path(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "astrbot.core.utils.media_utils.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )
    image_path = tmp_path / "image.png"
    image_base64 = _png_base64()
    image_path.write_bytes(base64.b64decode(image_base64))

    runner = DeerFlowAgentRunner()
    runner.assistant_id = "lead_agent"
    runner.thinking_enabled = False
    runner.plan_mode = False
    runner.subagent_enabled = False
    runner.max_concurrent_subagents = 3
    runner.model_name = ""
    runner.recursion_limit = 1000

    payload = await runner._build_payload_resolved(
        thread_id="thread-123",
        prompt="look",
        image_urls=[str(image_path)],
        system_prompt=None,
    )

    content = payload["input"]["messages"][-1]["content"]
    assert content[0] == {"type": "text", "text": "look"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"] == f"data:image/png;base64,{image_base64}"
