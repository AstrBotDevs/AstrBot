"""Built-in media sends must obey the owning turn's delivery policy."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.astr_agent_runtime.tools.computer_tools import cua, fs, python


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["screenshot", "download", "python"])
async def test_builtin_media_is_prepared_without_sending(kind, monkeypatch, tmp_path):
    """Caller-owned media stays available for review without claiming delivery."""
    output_turn = SimpleNamespace(done=False, emit=MagicMock())
    event = SimpleNamespace(
        role="admin",
        unified_msg_origin="test:FriendMessage:user",
        send=AsyncMock(),
        get_platform_name=lambda: "webchat",
    )
    context = ContextWrapper(
        context=SimpleNamespace(
            event=event,
            send_to_user=False,
            _output_turn=output_turn,
            context=SimpleNamespace(get_config=lambda **kwargs: {}),
        )
    )

    async def screenshot(path):
        Path(path).write_bytes(b"png")
        return {"base64": "cG5n", "mime_type": "image/png"}

    async def download(remote_path, local_path):
        Path(local_path).write_bytes(b"downloaded")

    booter = SimpleNamespace(
        gui=SimpleNamespace(screenshot=screenshot),
        download_file=download,
        python=SimpleNamespace(
            exec=AsyncMock(
                return_value={"data": {"output": {"images": [{"image/png": "cG5n"}]}}}
            )
        ),
    )
    module = {"screenshot": cua, "download": fs, "python": python}[kind]
    monkeypatch.setattr(module, "get_booter", AsyncMock(return_value=booter))
    if kind != "python":
        monkeypatch.setattr(module, "get_astrbot_temp_path", lambda: str(tmp_path))

    if kind == "screenshot":
        result = await cua.CuaScreenshotTool().call(context)
        assert result.content[1].data == "cG5n"
        payload = json.loads(result.content[0].text)
        assert payload["sent_to_user"] is False
        assert payload["delivery"] == "prepared_for_caller"
    elif kind == "download":
        result = await fs.FileDownloadTool().call(context, remote_path="report.txt")
        assert "It has not been sent" in result
    else:
        result = await python.PythonTool().call(context, code="plot()")
        assert result.content[0].data == "cG5n"
        assert "have not been sent" in result.content[1].text

    event.send.assert_not_awaited()
    output_turn.emit.assert_called_once()
    output = output_turn.emit.call_args.args[0]
    assert output.type == "output.ready"
    assert output.source == "tool"
    assert output.target_umo == event.unified_msg_origin
    part = output.content[0]
    assert part.type == ("file" if kind == "download" else "image")
    if kind == "python":
        assert part.source.data == "cG5n"
    else:
        path = part.source.path.removeprefix("file://")
        assert Path(path).read_bytes() == (
            b"png" if kind == "screenshot" else b"downloaded"
        )
    if kind == "download":
        assert part.name == "report.txt"
