"""Update commands for AstrBot.

Provides /update subcommands: check, now, auto, status.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from astrbot.api.event import MessageChain
from astrbot.core.config.default import VERSION

if TYPE_CHECKING:
    from astrbot.api.event import AstrMessageEvent
    from astrbot.api.star import Context


class UpdateCommands:
    """Chat commands for checking and triggering AstrBot updates."""

    def __init__(self, context: Context) -> None:
        self.context = context

    async def update_check(self, event: AstrMessageEvent) -> None:
        """Check for new AstrBot versions."""
        await event.send(MessageChain().message("🔍 Checking for updates..."))

        auto_update_mgr = self._get_auto_update_manager()
        if auto_update_mgr is None:
            await event.send(
                MessageChain().message("⚠️ Update manager is not available.")
            )
            return

        try:
            result = await auto_update_mgr.check_now()
        except Exception as exc:
            await event.send(
                MessageChain().message(f"❌ Failed to check for updates: {exc}")
            )
            return

        if result.get("error"):
            await event.send(
                MessageChain().message(
                    f"❌ Failed to check for updates: {result['error']}"
                )
            )
            return

        if result["has_update"]:
            msg = (
                f"🔔 A new version is available!\n"
                f"Current: {result['current_version']}\n"
                f"Latest: {result['latest_version']}\n"
                f"Published: {result.get('published_at', 'N/A')}\n\n"
                f"Use /update now to update."
            )
        else:
            msg = (
                f"✅ You are running the latest version.\n"
                f"Current: {result['current_version']}"
            )

        await event.send(MessageChain().message(msg))

    async def update_now(
        self, event: AstrMessageEvent, version: str | None = None
    ) -> None:
        """Trigger an update immediately.

        Args:
            version: Specific version tag to update to, or None for latest.
        """
        auto_update_mgr = self._get_auto_update_manager()
        if auto_update_mgr is None:
            await event.send(
                MessageChain().message("⚠️ Update manager is not available.")
            )
            return

        await event.send(
            MessageChain().message(
                f"⏳ Starting update to {version or 'latest version'}...\n"
                f"A backup will be created before the update.\n"
                f"The bot will restart after the update is complete."
            )
        )

        try:
            # 在后台触发更新，让当前消息先发出去
            asyncio.create_task(
                self._trigger_update_with_delay(auto_update_mgr, version)
            )
        except Exception as exc:
            await event.send(
                MessageChain().message(f"❌ Failed to trigger update: {exc}")
            )

    async def update_auto(self, event: AstrMessageEvent, action: str) -> None:
        """Toggle auto-update on/off.

        Args:
            action: "on" or "off".
        """
        action = action.strip().lower() if action else ""
        if action not in ("on", "off"):
            await event.send(
                MessageChain().message(
                    "Usage: /update auto on|off\n"
                    "  on  — Enable automatic updates\n"
                    "  off — Disable automatic updates"
                )
            )
            return

        enable = action == "on"

        # 更新运行时配置
        config = self.context.get_config()
        if "auto_update" not in config:
            config["auto_update"] = {}
        config["auto_update"]["enabled"] = enable

        await event.send(
            MessageChain().message(
                f"{'✅' if enable else '🛑'} Auto-update is now "
                f"{'ENABLED' if enable else 'DISABLED'}.\n"
                + (
                    "AstrBot will automatically check for and apply updates."
                    if enable
                    else "AstrBot will NOT automatically update itself."
                )
            )
        )

    async def update_status(self, event: AstrMessageEvent) -> None:
        """Show current version and auto-update status."""
        auto_update_mgr = self._get_auto_update_manager()
        config = self.context.get_config()
        auto_cfg = config.get("auto_update", {})

        enabled = auto_cfg.get("enabled", False)
        check_interval_h = (auto_cfg.get("check_interval", 86400)) / 3600
        retention_days = auto_cfg.get("backup_retention_days", 14)

        new_version = None
        if auto_update_mgr:
            new_version = auto_update_mgr.get_new_version_info()

        msg = (
            f"📋 AstrBot Update Status\n"
            f"Current version: {VERSION}\n"
            f"Auto-update: {'✅ Enabled' if enabled else '⛔ Disabled'}\n"
            f"Check interval: {check_interval_h:.0f}h\n"
            f"Backup retention: {retention_days} days\n"
        )
        if new_version:
            msg += f"New version available: {new_version}\n"

        msg += "\nCommands:\n"
        msg += "  /update check  — Check for new version\n"
        msg += "  /update now    — Update now\n"
        msg += "  /update auto on|off — Toggle auto-update\n"

        await event.send(MessageChain().message(msg))

    # ---- helpers ----

    @staticmethod
    async def _trigger_update_with_delay(
        auto_update_mgr, version: str | None = None
    ) -> None:
        """Delay then trigger update, giving the chat message time to send."""
        await asyncio.sleep(3)
        await auto_update_mgr.trigger_update(version)

    def _get_auto_update_manager(self):
        """Get the AutoUpdateManager from core_lifecycle via star context."""
        core_lifecycle = getattr(self.context, "core_lifecycle", None)
        if core_lifecycle is None:
            return None
        return getattr(core_lifecycle, "auto_update_manager", None)
