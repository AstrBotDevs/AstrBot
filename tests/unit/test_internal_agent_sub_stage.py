from types import SimpleNamespace

import pytest

from astrbot.core.astr_main_agent import MainAgentBuildConfig
from astrbot.core.message.components import File, Reply
from astrbot.core.pipeline.process_stage.method.agent_sub_stages import internal


class _FakeLock:
    def __init__(self, events: list[str]):
        self.events = events

    async def __aenter__(self):
        self.events.append("lock")

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_file_download_finishes_before_session_lock(monkeypatch):
    events: list[str] = []
    component = File(name="report.pdf", url="https://example.test/report.pdf")

    async def fake_get_file(_self):
        if not _self.file_:
            events.append("download")
            _self.file_ = "/tmp/report.pdf"
        return _self.file_

    async def fake_build_main_agent(**kwargs):
        await kwargs["event"].message_obj.message[0].get_file()
        return None

    event = SimpleNamespace(
        message_str="read the attached report",
        message_obj=SimpleNamespace(message=[component]),
        unified_msg_origin="private:session",
        get_extra=lambda _key: None,
        send_typing=lambda: _completed(),
        stop_typing=lambda: _completed(),
    )

    async def fake_call_event_hook(*_args, **_kwargs):
        return False

    async def _completed():
        return None

    monkeypatch.setattr(File, "get_file", fake_get_file)
    monkeypatch.setattr(internal, "build_main_agent", fake_build_main_agent)
    monkeypatch.setattr(internal, "call_event_hook", fake_call_event_hook)
    monkeypatch.setattr(internal, "try_capture_follow_up", lambda _event: None)
    monkeypatch.setattr(
        internal.session_lock_manager,
        "acquire_lock",
        lambda _session_id: _FakeLock(events),
    )

    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = True
    stage.show_reasoning = False
    stage.main_agent_cfg = MainAgentBuildConfig(tool_call_timeout=120)
    stage.ctx = SimpleNamespace(plugin_manager=SimpleNamespace(context=object()))

    async for _ in stage.process(event, ""):
        pass

    assert events[:2] == ["download", "lock"]


@pytest.mark.asyncio
async def test_prepare_file_attachments_includes_quoted_files(monkeypatch):
    downloaded: list[File] = []
    direct_file = File(name="direct.pdf", url="https://example.test/direct.pdf")
    quoted_file = File(name="quoted.pdf", url="https://example.test/quoted.pdf")

    async def fake_get_file(component):
        downloaded.append(component)
        return "/tmp/file.pdf"

    monkeypatch.setattr(File, "get_file", fake_get_file)

    event = SimpleNamespace(
        message_obj=SimpleNamespace(
            message=[direct_file, Reply(id="1", chain=[quoted_file])],
        ),
    )

    await internal._prepare_file_attachments(event)

    assert downloaded == [direct_file, quoted_file]
