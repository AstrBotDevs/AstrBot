"""Regression guards for collecting video attachments into the provider request."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from astrbot.core import agent_media as media_build
from astrbot.core.astr_agent_runtime import main_agent
from astrbot.core.message.components import Video
from astrbot.core.provider.entities import ProviderRequest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_append_video_attachment_collects_the_resolved_path(tmp_path):
    """The resolved local path must reach `req.video_urls`.

    `append_video_attachment` is the single funnel for the current message and
    for the quoted message, so a provider that declares the `video` modality
    only receives the payload when this collection happens. The text part must
    stay untouched for every other provider and for the persisted history.

    Args:
        tmp_path: Temporary directory holding the stand-in video file.
    """
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    req = ProviderRequest(prompt="look")

    with patch.object(
        Video,
        "convert_to_file_path",
        AsyncMock(return_value=str(video_path)),
    ):
        await media_build.append_video_attachment(req, Video(file="file:///clip.mp4"))

    assert req.video_urls == [str(video_path)]
    assert [part.text for part in req.extra_user_content_parts] == [
        f"[Video Attachment: name clip.mp4, path {video_path}]"
    ]


def test_agent_module_is_a_package_only():
    """Stale `astr_main_agent` paths must not come back alongside the 4.30 layout.

    `#10934` split `astr_main_agent.py` into a package and `#11051` reorganized
    it under `astrbot/core/astr_agent_runtime/main_agent/` plus
    `astrbot/core/agent_media.py`. A resurrected legacy module or directory
    would silently shadow or split future edits away from the live modules.

    Raises:
        AssertionError: When a stale `astr_main_agent` module/package exists
            again, or when the live runtime package/media module paths differ.
    """
    core_dir = REPO_ROOT / "astrbot" / "core"
    package_dir = core_dir / "astr_agent_runtime" / "main_agent"

    assert not (core_dir / "astr_main_agent.py").exists()
    assert not (core_dir / "astr_main_agent").exists()
    assert (package_dir / "__init__.py").is_file()
    assert (
        Path(main_agent.__file__).resolve() == (package_dir / "__init__.py").resolve()
    )
    assert (
        Path(media_build.__file__).resolve() == (core_dir / "agent_media.py").resolve()
    )
