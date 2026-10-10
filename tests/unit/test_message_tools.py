"""Tests for send_message_to_user session handling and delivery."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.config import default as config_defaults
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.pipeline.respond.stage import RespondStage
from astrbot.core.tools.message_tools import SendMessageToUserTool


def _make_context(
    current_session="feishu:GroupMessage:oc_xxx",
    role="admin",
    require_admin=True,
    runtime="local",
    local_permissions=None,
):
    """Build a minimal ContextWrapper for SendMessageToUserTool."""
    cfg = {
        "provider_settings": {
            "computer_use_require_admin": require_admin,
            "computer_use_runtime": runtime,
        }
    }
    if local_permissions is not None:
        cfg["provider_settings"]["computer_use_local_permissions"] = local_permissions
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
async def test_send_message_returns_platform_error_to_tool_result():
    """Platform send failures are returned to the agent as tool errors."""
    tool = SendMessageToUserTool()
    ctx = _make_context(current_session="qq_official:GroupMessage:group-1")
    ctx.context.context.send_message.side_effect = RuntimeError(
        "413 Request Entity Too Large"
    )

    result = await tool.call(
        ctx,
        messages=[{"type": "plain", "text": "hello"}],
    )

    assert result == (
        "error: failed to send message to session "
        "qq_official:GroupMessage:group-1: 413 Request Entity Too Large"
    )
    assert ctx.context.event._has_send_oper is False


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
async def test_repeated_text_delivery_is_sent_once_per_event():
    """Repeated model calls reuse successful delivery even with session aliases."""
    ctx = _make_context(role="member")
    for index in range(30):
        result = await SendMessageToUserTool().call(
            ctx,
            messages=[{"type": "PLAIN", "text": " hello "}],
            session=[None, "oc_xxx", "feishu:GroupMessage:oc_xxx"][index % 3],
        )
        if index == 0:
            assert "Message sent" in result
        else:
            assert "already sent" in result

    ctx.context.context.send_message.assert_awaited_once()
    assert ctx.context.event.get_extra(
        "_send_message_to_user_current_session_plain_texts"
    ) == ["hello"]


@pytest.mark.asyncio
async def test_concurrent_duplicate_delivery_is_sent_once():
    """A second call cannot send while the first delivery is still in flight."""
    ctx = _make_context()
    tool = SendMessageToUserTool()
    started = asyncio.Event()
    release = asyncio.Event()

    async def send(*args):
        started.set()
        await release.wait()
        return True

    ctx.context.context.send_message.side_effect = send
    first = asyncio.create_task(
        tool.call(ctx, messages=[{"type": "plain", "text": "hello"}])
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    second = asyncio.create_task(
        tool.call(ctx, messages=[{"type": "plain", "text": "hello"}])
    )
    release.set()
    results = await asyncio.wait_for(asyncio.gather(first, second), timeout=1)

    assert "Message sent" in results[0]
    assert "already sent" in results[1]
    ctx.context.context.send_message.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, RuntimeError("temporary failure")])
async def test_failed_delivery_can_be_retried(failure):
    """Only confirmed deliveries enter the event cache."""
    ctx = _make_context()
    ctx.context.context.send_message.side_effect = [failure, True]
    tool = SendMessageToUserTool()
    messages = [{"type": "plain", "text": "hello"}]

    assert (await tool.call(ctx, messages=messages)).startswith("error:")
    assert ctx.context.event._has_send_oper is False
    assert "Message sent" in await tool.call(ctx, messages=messages)
    assert "already sent" in await tool.call(ctx, messages=messages)
    assert ctx.context.context.send_message.await_count == 2


@pytest.mark.asyncio
async def test_cancelled_delivery_does_not_block_retry():
    """Cancellation releases the send lock without caching success."""
    ctx = _make_context()
    tool = SendMessageToUserTool()
    started = asyncio.Event()

    async def send(*args):
        started.set()
        await asyncio.Event().wait()

    ctx.context.context.send_message.side_effect = send
    messages = [{"type": "plain", "text": "hello"}]
    task = asyncio.create_task(tool.call(ctx, messages=messages))
    await asyncio.wait_for(started.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    ctx.context.context.send_message.side_effect = None
    ctx.context.context.send_message.return_value = True
    result = await asyncio.wait_for(tool.call(ctx, messages=messages), timeout=1)
    assert "Message sent" in result
    assert ctx.context.context.send_message.await_count == 2


@pytest.mark.asyncio
async def test_delivery_cache_preserves_distinct_messages_and_sessions():
    """Changing text, mentions, component order or target keeps a send distinct."""
    ctx = _make_context()
    tool = SendMessageToUserTool()
    plain = {"type": "plain", "text": "hello"}
    mention = {"type": "mention_user", "mention_user_id": "one"}
    calls = [
        ([plain], None),
        ([{"type": "plain", "text": "world"}], None),
        ([mention, plain], None),
        ([plain, mention], None),
        ([{"type": "mention_user", "mention_user_id": "two"}, plain], None),
        ([plain], "feishu:GroupMessage:other"),
    ]
    for messages, session in calls:
        assert "Message sent" in await tool.call(
            ctx, messages=messages, session=session
        )
        assert "already sent" in await tool.call(
            ctx, messages=messages, session=session
        )
    assert ctx.context.context.send_message.await_count == len(calls)


@pytest.mark.asyncio
async def test_delivery_cache_does_not_leak_to_a_new_event():
    """A new chat turn or cron wakeup may legitimately repeat a prior message."""
    tool = SendMessageToUserTool()
    first, second = _make_context(), _make_context()
    for ctx in (first, second):
        assert "Message sent" in await tool.call(
            ctx, messages=[{"type": "plain", "text": "hello"}]
        )
        ctx.context.context.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_cached_delivery_does_not_bypass_session_permission():
    """Permissions are checked even when an identical delivery is cached."""
    ctx = _make_context()
    tool = SendMessageToUserTool()
    kwargs = {
        "messages": [{"type": "plain", "text": "hello"}],
        "session": "other",
    }
    assert "Message sent" in await tool.call(ctx, **kwargs)
    ctx.context.event.role = "member"
    assert "Permission denied" in await tool.call(ctx, **kwargs)
    ctx.context.context.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalid_session_is_rejected_before_resolving_media(monkeypatch):
    """Malformed targets must not trigger sandbox downloads."""
    resolve = AsyncMock()
    monkeypatch.setattr(SendMessageToUserTool, "_resolve_path_from_sandbox", resolve)
    ctx = _make_context()
    result = await SendMessageToUserTool().call(
        ctx,
        messages=[{"type": "image", "path": "/sandbox/report.png"}],
        session="feishu:invalid:session",
    )
    assert "invalid session" in result
    resolve.assert_not_awaited()
    ctx.context.context.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_media_paths_are_resolved_once_per_call_only(tmp_path, monkeypatch):
    """Reuse a download within a batch, but resolve mutable files again next call."""
    local_file = tmp_path / "report.png"
    local_file.write_bytes(b"first version")
    resolve = AsyncMock(return_value=(str(local_file), True))
    monkeypatch.setattr(SendMessageToUserTool, "_resolve_path_from_sandbox", resolve)
    ctx = _make_context(runtime="sandbox")
    tool = SendMessageToUserTool()
    messages = [
        {"type": kind, "path": "/sandbox/report.png"}
        for kind in ("image", "record", "video", "file")
    ]
    for index in range(2):
        local_file.write_bytes(f"version {index}".encode())
        assert "Message sent" in await tool.call(ctx, messages=messages)
        assert resolve.await_count == index + 1

    assert ctx.context.context.send_message.await_count == 2
    chain = ctx.context.context.send_message.await_args.args[1].chain
    assert len(chain) == 4
    assert chain[-1].name == "report.png"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["image", "record", "video", "file"])
async def test_media_urls_are_not_deduplicated(kind):
    """A URL may return new content on a subsequent call."""
    ctx = _make_context()
    tool = SendMessageToUserTool()
    messages = [{"type": kind, "url": "https://example.com/latest"}]
    for _ in range(2):
        assert "Message sent" in await tool.call(ctx, messages=messages)
    assert ctx.context.context.send_message.await_count == 2


@pytest.mark.asyncio
async def test_send_message_missing_image_path_stops_before_send(tmp_path, monkeypatch):
    """Missing image paths fail before sending any message components."""
    tool = SendMessageToUserTool()
    # Sandbox runtime so the booter is still consulted for missing paths;
    # local runtime now rejects them before any booter call.
    ctx = _make_context(runtime="sandbox")
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
@pytest.mark.parametrize("system", ["Windows", "Linux", "Darwin"])
@pytest.mark.parametrize("component_type", ["file", "image", "record", "video"])
@pytest.mark.parametrize(
    ("role", "scope"),
    [
        ("member", None),
        ("member", "none"),
        ("admin", "none"),
        ("member", "workspace"),
        ("admin", "workspace"),
    ],
)
async def test_restricted_role_cannot_send_arbitrary_local_absolute_file(
    tmp_path, monkeypatch, system, component_type, role, scope
):
    """Only explicit host access permits sending files outside trusted roots."""
    monkeypatch.setattr(
        config_defaults, "platform", SimpleNamespace(system=lambda: system)
    )
    tool = SendMessageToUserTool()
    ctx = _make_context(
        role=role,
        local_permissions={role: {"filesystem_scope": scope}} if scope else None,
    )
    secret_path = tmp_path / "secret.txt"
    secret_path.write_text("secret", encoding="utf-8")

    result = await tool.call(
        ctx,
        messages=[{"type": component_type, "path": str(secret_path)}],
    )

    assert "error: Local file send is restricted for this user" in result
    assert str(secret_path) in result
    ctx.context.context.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_member_with_host_scope_can_send_local_absolute_file(tmp_path):
    """Host filesystem scope should cover the local file-send bridge."""
    permissions = {
        "member": {
            "allow_execution": False,
            "allow_network": False,
            "filesystem_scope": "host",
        }
    }
    tool = SendMessageToUserTool()
    ctx = _make_context(role="member", local_permissions=permissions)
    file_path = tmp_path / "result.txt"
    file_path.write_text("result", encoding="utf-8")

    result = await tool.call(
        ctx,
        messages=[{"type": "file", "path": str(file_path)}],
    )

    assert "Message sent to session" in result
    ctx.context.context.send_message.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["none", "workspace"])
async def test_non_admin_can_send_workspace_file(tmp_path, monkeypatch, scope):
    """Non-admin users can send files inside their per-session workspace."""
    tool = SendMessageToUserTool()
    ctx = _make_context(
        current_session="feishu:GroupMessage:oc_workspace",
        role="member",
        require_admin=True,
        local_permissions={"member": {"filesystem_scope": scope}},
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
@pytest.mark.parametrize("scope", ["none", "workspace"])
async def test_non_admin_can_send_temp_file(tmp_path, monkeypatch, scope):
    """Non-admin users can send generated files under AstrBot temp."""
    tool = SendMessageToUserTool()
    ctx = _make_context(
        role="member", local_permissions={"member": {"filesystem_scope": scope}}
    )
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
        # The local temp path keeps the original remote basename; separators
        # are platform-native, so only the basename is asserted here.
        assert local_path.endswith("report.txt")
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


@pytest.mark.asyncio
async def test_send_message_local_runtime_skips_sandbox_file_probe(
    tmp_path, monkeypatch
):
    """Local runtime must resolve send-file paths only via permission-checked branches.

    Falling through to the booter branch would probe the host shell without
    the caller's filesystem permissions.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    secret = tmp_path / "host-only.txt"
    secret.write_text("host-only marker", encoding="utf-8")
    allowed = workspace / "allowed.txt"
    allowed.write_text("workspace file", encoding="utf-8")

    async def mock_workspace_root_for_context(_context):
        return workspace

    async def mock_get_booter(*args, **kwargs):
        del args, kwargs
        raise AssertionError("local runtime must not query a sandbox booter")

    monkeypatch.setattr(
        "astrbot.core.tools.message_tools.workspace_root_for_context",
        mock_workspace_root_for_context,
    )
    monkeypatch.setattr(
        "astrbot.core.tools.message_tools.get_booter",
        mock_get_booter,
    )

    tool = SendMessageToUserTool()
    ctx = _make_context(
        role="member",
        local_permissions={
            "member": {
                "allow_execution": False,
                "allow_network": False,
                "filesystem_scope": "workspace",
            }
        },
    )

    resolved, downloaded = await tool._resolve_path_from_sandbox(ctx, "allowed.txt")
    assert resolved == str(allowed.resolve())
    assert downloaded is False

    with pytest.raises(FileNotFoundError):
        await tool._resolve_path_from_sandbox(ctx, "host-only.txt")
