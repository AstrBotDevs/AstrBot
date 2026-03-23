from __future__ import annotations

from pathlib import Path

import pytest

from astrbot_sdk.context import Context
from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.testing import MockContext, PluginHarness


def _write_permission_plugin(plugin_dir: Path) -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.yaml").write_text(
        """
_schema_version: 2
name: permission_runtime_plugin
author: tests
version: 1.0.0
desc: permission runtime tests

runtime:
  python: "3.12"

components:
  - class: main:PermissionRuntimePlugin
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")
    (plugin_dir / "main.py").write_text(
        """
from astrbot_sdk import Context, MessageEvent, Star
from astrbot_sdk.decorators import on_command, require_permission


class PermissionRuntimePlugin(Star):
    @on_command("panel")
    @require_permission("admin")
    async def panel(self, event: MessageEvent, ctx: Context) -> None:
        await event.reply("admin-only")

    @on_command("ping")
    @require_permission("member")
    async def ping(self, event: MessageEvent, ctx: Context) -> None:
        await event.reply("member-ok")
""".lstrip(),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_mock_context_permission_clients_and_manager_gates() -> None:
    ctx = MockContext(plugin_id="plain-plugin")
    ctx.router.set_admin_ids(["root", "maintainer"])

    check = await ctx.permission.check("root", session_id="demo:group:42")

    assert check.is_admin is True
    assert check.role == "admin"
    assert await ctx.permission.get_admins() == ["root", "maintainer"]

    elevated_plain = Context(
        peer=ctx.mock_peer,
        plugin_id="plain-plugin",
        source_event_payload={"is_admin": True},
    )
    with pytest.raises(AstrBotError, match="reserved/system"):
        await elevated_plain.permission_manager.add_admin("alice")

    reserved_ctx = MockContext(
        plugin_id="reserved-plugin",
        plugin_metadata={"reserved": True},
    )
    reserved_ctx.router.set_admin_ids(["root"])

    admin_ctx = Context(
        peer=reserved_ctx.mock_peer,
        plugin_id="reserved-plugin",
        source_event_payload={"is_admin": True},
    )
    viewer_ctx = Context(
        peer=reserved_ctx.mock_peer,
        plugin_id="reserved-plugin",
        source_event_payload={"is_admin": False},
    )

    assert await admin_ctx.permission_manager.add_admin("alice") is True
    assert await admin_ctx.permission_manager.add_admin("alice") is False
    assert await admin_ctx.permission.get_admins() == ["root", "alice"]
    assert await admin_ctx.permission_manager.remove_admin("alice") is True
    assert await admin_ctx.permission_manager.remove_admin("alice") is False

    with pytest.raises(AstrBotError, match="active admin event context"):
        await viewer_ctx.permission_manager.add_admin("bob")


@pytest.mark.asyncio
async def test_plugin_harness_respects_require_permission_roles(
    tmp_path: Path,
) -> None:
    plugin_dir = tmp_path / "permission_runtime_plugin"
    _write_permission_plugin(plugin_dir)

    async with PluginHarness.from_plugin_dir(plugin_dir) as harness:
        panel_payload = harness.build_event_payload(
            text="panel",
            request_id="req-panel-member",
        )
        with pytest.raises(AstrBotError, match="未找到匹配的 handler"):
            await harness.dispatch_event(panel_payload, request_id="req-panel-member")

        admin_payload = harness.build_event_payload(
            text="panel",
            request_id="req-panel-admin",
        )
        admin_payload["is_admin"] = True
        admin_records = await harness.dispatch_event(
            admin_payload,
            request_id="req-panel-admin",
        )

        member_payload = harness.build_event_payload(
            text="ping",
            request_id="req-ping-member",
        )
        member_records = await harness.dispatch_event(
            member_payload,
            request_id="req-ping-member",
        )

    assert len(admin_records) == 1
    assert admin_records[0].text == "admin-only"
    assert len(member_records) == 1
    assert member_records[0].text == "member-ok"
