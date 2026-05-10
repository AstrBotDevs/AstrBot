from types import SimpleNamespace

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.tools.computer_tools.sandbox import (
    CopyFileBetweenSandboxesTool,
    ScreenshotSandboxTool,
)


class FakeEvent:
    unified_msg_origin = "session-a"
    role = "member"

    def get_sender_id(self):
        return "user-a"


def _context():
    plugin_context = SimpleNamespace(
        get_config=lambda umo=None: {
            "provider_settings": {"computer_use_require_admin": True}
        }
    )
    return ContextWrapper(
        context=SimpleNamespace(event=FakeEvent(), context=plugin_context)
    )


@pytest.mark.asyncio
async def test_screenshot_sandbox_tool_requires_admin_permission():
    result = await ScreenshotSandboxTool().call(_context(), "sandbox-1")

    assert "Permission denied" in str(result)


@pytest.mark.asyncio
async def test_copy_file_between_sandboxes_tool_requires_admin_permission():
    result = await CopyFileBetweenSandboxesTool().call(
        _context(),
        "source-1",
        "/tmp/source.txt",
        "target-1",
        "/tmp/target.txt",
    )

    assert "Permission denied" in str(result)
