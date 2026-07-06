"""Tests for send_message_to_user session handling."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.pipeline.respond.stage import RespondStage
from astrbot.core.tools.message_tools import SendMessageToUserTool


def _make_context(
    current_session="feishu:GroupMessage:oc_xxx",
    role="admin",
    require_admin=True,
    runtime="local",
):
    """Build a minimal ContextWrapper for SendMessageToUserTool."""
    cfg = {
        "provider_settings": {
            "computer_use_require_admin": require_admin,
            "computer_use_runtime": runtime,
        }
    }
    extras = {}
    event = SimpleNamespace(
        unified_msg_origin=current_session,
        role=role,
        _has_send_oper=False,
        get_sender_id=lambda: "user-1",
    )
    event.set_extra = lambda key, value: extras.__setitem__(key, value)
    event.get_extra = lambda key, default=None: extras.get(key, default)
    return SimpleNamespace(
        context=SimpleNamespace(
            event=event,
            context=SimpleNamespace(
                get_config=lambda umo: cfg,
                send_message=AsyncMock(),
            ),
        )
    )


class _DummyRespondEvent:
    def __init__(self, result_text: str, sent_plain_texts: list[str]) -> None:
        self._extras = {
            "_send_message_to_user_current_session_plain_texts": sent_plain_texts,
        }
        self._result = MessageEventResult().message(result_text)
        self.send = AsyncMock()
        self.plugins_name = []

    def get_result(self):
        """Return the current message result."""
        return self._result

    def set_extra(self, key, value) -> None:
        """Set pipeline extra data."""
        self._extras[key] = value

    def get_extra(self, key, default=None):
        """Get pipeline extra data."""
        return self._extras.get(key, default)

    def get_sender_name(self) -> str:
        """Return a sender name for respond-stage logging."""
        return "tester"

    def get_sender_id(self) -> str:
        """Return a sender ID for respond-stage logging."""
        return "user-1"

    def get_platform_id(self) -> str:
        """Return a platform ID for respond-stage logging."""
        return "test"

    def get_platform_name(self) -> str:
        """Return a platform name for segmented-reply checks."""
        return "test"

    def _outline_chain(self, chain) -> str:
        """Return a readable outline for respond-stage logging."""
        return " ".join(comp.text for comp in chain if hasattr(comp, "text"))

    def is_stopped(self) -> bool:
        """Return whether this dummy event has stopped."""
        return False

    def clear_result(self) -> None:
        """Clear the current message result."""
        self._result = None


def _make_respond_stage() -> RespondStage:
    """Build a minimally initialized RespondStage for unit tests."""
    stage = RespondStage()
    stage.config = {"provider_settings": {}}
    stage.platform_settings = {"path_mapping": []}
    stage.enable_seg = False
    return stage


@pytest.mark.asyncio
async def test_send_message_with_full_three_part_session():
    """LLM passes a complete three-part session string."""
    tool = SendMessageToUserTool()
    ctx = _make_context(current_session="feishu:GroupMessage:oc_aaa")
    result = await tool.call(
        ctx,
        messages=[{"type": "plain", "text": "hello"}],
        session="feishu:GroupMessage:oc_aaa",
    )
    assert "Message sent to session" in result


@pytest.mark.asyncio
async def test_send_message_with_partial_session_id_fallback():
    """LLM passes only session_id (no colons) — fallback to current_session's prefix."""
    tool = SendMessageToUserTool()
    ctx = _make_context(current_session="feishu:GroupMessage:oc_abc")
    result = await tool.call(
        ctx,
        messages=[{"type": "plain", "text": "hello"}],
        session="oc_abc",
    )
    assert "Message sent to session" in result
    # Verify the target session was reconstructed with current_session's platform/msg_type
    call_args = ctx.context.context.send_message.call_args
    target_session = call_args[0][0]
    assert target_session.platform_id == "feishu"
    assert target_session.message_type.value == "GroupMessage"
    assert target_session.session_id == "oc_abc"


@pytest.mark.asyncio
async def test_send_message_defaults_to_current_session():
    """LLM does not pass session — uses current_session directly."""
    tool = SendMessageToUserTool()
    ctx = _make_context(current_session="feishu:GroupMessage:oc_xxx")
    result = await tool.call(
        ctx,
        messages=[{"type": "plain", "text": "hello"}],
    )
    assert "Message sent to session" in result
    call_args = ctx.context.context.send_message.call_args
    target_session = call_args[0][0]
    assert str(target_session) == "feishu:GroupMessage:oc_xxx"
    assert ctx.context.event._has_send_oper is True
    assert ctx.context.event.get_extra(
        "_send_message_to_user_current_session_plain_texts",
    ) == ["hello"]


@pytest.mark.asyncio
async def test_send_message_other_session_does_not_record_current_text():
    """Messages sent to another session do not affect current-session dedupe."""
    tool = SendMessageToUserTool()
    ctx = _make_context(current_session="feishu:GroupMessage:oc_xxx")
    result = await tool.call(
        ctx,
        messages=[{"type": "plain", "text": "hello"}],
        session="feishu:GroupMessage:oc_other",
    )
    assert "Message sent to session" in result
    assert ctx.context.event._has_send_oper is False
    assert (
        ctx.context.event.get_extra(
            "_send_message_to_user_current_session_plain_texts",
        )
        is None
    )


@pytest.mark.asyncio
async def test_respond_stage_skips_same_text_after_send_message_to_user():
    """RespondStage skips only when the tool already sent the same text."""
    stage = _make_respond_stage()
    event = _DummyRespondEvent(
        result_text="duplicate reply",
        sent_plain_texts=["duplicate reply"],
    )

    result = await stage.process(event)

    assert result is None
    event.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_respond_stage_sends_different_text_after_send_message_to_user():
    """RespondStage still sends a distinct completion after the tool call."""
    stage = _make_respond_stage()
    event = _DummyRespondEvent(
        result_text="I have sent the message with the tool.",
        sent_plain_texts=["duplicate reply"],
    )

    result = await stage.process(event)

    assert result is None
    event.send.assert_awaited_once()
    assert event.get_result() is None


@pytest.mark.asyncio
async def test_send_message_partial_session_falls_back_to_current():
    """LLM passes session_id matching current_session's id — same session, just incomplete format."""
    tool = SendMessageToUserTool()
    ctx = _make_context(current_session="qq_official:GroupMessage:g123")
    result = await tool.call(
        ctx,
        messages=[{"type": "plain", "text": "world"}],
        session="g123",
    )
    assert "Message sent to session" in result
    call_args = ctx.context.context.send_message.call_args
    target_session = call_args[0][0]
    assert target_session.platform_id == "qq_official"
    assert target_session.message_type.value == "GroupMessage"
    assert target_session.session_id == "g123"


@pytest.mark.asyncio
async def test_cron_context_current_session_is_target_session():
    """在 cron 场景中，current_session 就是 cron 任务的目标 session。

    cron 是主动唤醒，没有用户消息触发，因此没有"正在聊天的 session"。
    event.unified_msg_origin 来自 CronMessageEvent.session，
    而 CronMessageEvent.session 来自 cron job payload.session，
    即用户在 cron 配置中填写的目标会话。
    """
    tool = SendMessageToUserTool()
    # cron 任务的目标 session（用户配置的完整三段式）
    cron_target_session = "feishu:GroupMessage:oc_cron_target"
    ctx = _make_context(current_session=cron_target_session)

    # LLM 在 cron 上下文中只传了 session_id 部分
    result = await tool.call(
        ctx,
        messages=[{"type": "plain", "text": "cron message"}],
        session="oc_cron_target",
    )
    assert "Message sent to session" in result
    call_args = ctx.context.context.send_message.call_args
    target_session = call_args[0][0]
    # 补全后的 session 应与 cron 目标 session 完全一致
    assert str(target_session) == cron_target_session
    assert target_session.platform_id == "feishu"
    assert target_session.message_type.value == "GroupMessage"
    assert target_session.session_id == "oc_cron_target"


@pytest.mark.asyncio
async def test_send_message_empty_messages_returns_error():
    """Empty or missing messages returns error before session resolution."""
    tool = SendMessageToUserTool()
    ctx = _make_context()
    result = await tool.call(ctx, messages=[], session="oc_xxx")
    assert "error:" in result
    assert "messages" in result.lower()


@pytest.mark.asyncio
async def test_send_message_missing_image_path_stops_before_send(tmp_path, monkeypatch):
    """Missing image paths fail before sending any message components."""
    tool = SendMessageToUserTool()
    ctx = _make_context()
    missing_image_path = tmp_path / "missing.png"

    async def mock_get_booter(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("sandbox unavailable")

    monkeypatch.setattr(
        "astrbot.core.tools.message_tools.get_booter",
        mock_get_booter,
    )

    result = await tool.call(
        ctx,
        messages=[
            {"type": "plain", "text": "before image"},
            {"type": "image", "path": str(missing_image_path)},
        ],
    )

    assert "error: failed to build messages[1] component: sandbox unavailable" in result
    ctx.context.context.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_non_admin_cannot_send_arbitrary_local_absolute_file(tmp_path):
    """Non-admin users cannot send host files outside the allowed local roots."""
    tool = SendMessageToUserTool()
    ctx = _make_context(role="member", require_admin=True)
    secret_path = tmp_path / "secret.txt"
    secret_path.write_text("secret", encoding="utf-8")

    result = await tool.call(
        ctx,
        messages=[{"type": "file", "path": str(secret_path)}],
    )

    assert "error: Local file send is restricted for this user" in result
    assert str(secret_path) in result
    ctx.context.context.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_non_admin_can_send_workspace_file(tmp_path, monkeypatch):
    """Non-admin users can send files inside their per-session workspace."""
    tool = SendMessageToUserTool()
    ctx = _make_context(
        current_session="feishu:GroupMessage:oc_workspace",
        role="member",
        require_admin=True,
    )
    workspace_root = tmp_path / "workspaces"
    workspace_file = workspace_root / "feishu_GroupMessage_oc_workspace" / "result.txt"
    workspace_file.parent.mkdir(parents=True)
    workspace_file.write_text("result", encoding="utf-8")
    monkeypatch.setattr(
        "astrbot.core.tools.computer_tools.util.get_astrbot_workspaces_path",
        lambda: str(workspace_root),
    )

    result = await tool.call(
        ctx,
        messages=[{"type": "file", "path": "result.txt"}],
    )

    assert "Message sent to session" in result
    ctx.context.context.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_non_admin_can_send_temp_file(tmp_path, monkeypatch):
    """Non-admin users can send generated files under AstrBot temp."""
    tool = SendMessageToUserTool()
    ctx = _make_context(role="member", require_admin=True)
    temp_root = tmp_path / "temp"
    temp_root.mkdir()
    output_path = temp_root / "output.txt"
    output_path.write_text("output", encoding="utf-8")
    monkeypatch.setattr(
        "astrbot.core.tools.message_tools.get_astrbot_temp_path",
        lambda: str(temp_root),
    )

    result = await tool.call(
        ctx,
        messages=[{"type": "file", "path": str(output_path)}],
    )

    assert "Message sent to session" in result
    ctx.context.context.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_send_message_downloads_windows_sandbox_file_with_original_name(
    tmp_path, monkeypatch
):
    """Windows sandbox paths keep their basename when sent as files."""
    tool = SendMessageToUserTool()
    ctx = _make_context(runtime="sandbox")
    temp_root = tmp_path / "temp"
    temp_root.mkdir()
    monkeypatch.setattr(
        "astrbot.core.tools.message_tools.get_astrbot_temp_path",
        lambda: str(temp_root),
    )

    async def _exec(_command):
        return {"content": "_&exists_"}

    async def _download_file(_remote_path, local_path):
        assert local_path.endswith("report.txt")
        assert "\\" not in local_path
        with open(local_path, "w", encoding="utf-8") as file:
            file.write("report")

    booter = SimpleNamespace(
        shell=SimpleNamespace(exec=AsyncMock(side_effect=_exec)),
        download_file=AsyncMock(side_effect=_download_file),
    )

    async def mock_get_booter(*args, **kwargs):
        del args, kwargs
        return booter

    monkeypatch.setattr(
        "astrbot.core.tools.message_tools.get_booter",
        mock_get_booter,
    )

    result = await tool.call(
        ctx,
        messages=[{"type": "file", "path": r"C:\Users\AstrBot\report.txt"}],
    )

    assert "Message sent to session" in result
    sent_chain = ctx.context.context.send_message.await_args.args[1]
    sent_file = sent_chain.chain[0]
    assert sent_file.name == "report.txt"


@pytest.mark.asyncio
async def test_send_message_downloads_trailing_slash_sandbox_file_with_basename(
    tmp_path, monkeypatch
):
    tool = SendMessageToUserTool()
    ctx = _make_context(runtime="sandbox")
    temp_root = tmp_path / "temp"
    temp_root.mkdir()
    monkeypatch.setattr(
        "astrbot.core.tools.message_tools.get_astrbot_temp_path",
        lambda: str(temp_root),
    )

    async def _exec(_command):
        return {"content": "_&exists_"}

    async def _download_file(_remote_path, local_path):
        assert local_path.endswith("export")
        with open(local_path, "w", encoding="utf-8") as file:
            file.write("export")

    booter = SimpleNamespace(
        shell=SimpleNamespace(exec=AsyncMock(side_effect=_exec)),
        download_file=AsyncMock(side_effect=_download_file),
    )

    async def mock_get_booter(*args, **kwargs):
        del args, kwargs
        return booter

    monkeypatch.setattr(
        "astrbot.core.tools.message_tools.get_booter",
        mock_get_booter,
    )

    result = await tool.call(
        ctx,
        messages=[{"type": "file", "path": "reports/export/"}],
    )

    assert "Message sent to session" in result
    sent_chain = ctx.context.context.send_message.await_args.args[1]
    sent_file = sent_chain.chain[0]
    assert sent_file.name == "export"
