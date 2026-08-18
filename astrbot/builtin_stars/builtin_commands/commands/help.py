from html import escape

import aiohttp

from astrbot import logger
from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.config import AstrBotConfig
from astrbot.core.config.default import VERSION
from astrbot.core.utils.io import get_dashboard_version


class HelpCommand:
    def __init__(self, context: star.PluginContext) -> None:
        self.context = context

    async def _query_astrbot_notice(self):
        try:
            from astrbot.core.utils.proxy_route import (
                create_aiohttp_session,
                current_aiohttp_proxy,
            )

            async with create_aiohttp_session() as session:
                async with session.get(
                    "https://astrbot.app/notice.json",
                    timeout=aiohttp.ClientTimeout(total=2),
                    proxy=current_aiohttp_proxy(),
                ) as resp:
                    return (await resp.json())["notice"]
        except Exception:
            return ""

    async def _build_reserved_commands(self) -> list[tuple[str, str]]:
        """
        使用实时指令配置生成内置指令清单，确保重命名/禁用后与实际生效状态保持一致。
        """
        try:
            commands = await self.context.runtime_info.commands()
        except Exception:
            return []

        lines: list[tuple[str, str]] = []

        def walk(items: list[dict], indent: int = 0) -> None:
            for item in items:
                if not item.get("reserved") or not item.get("enabled"):
                    continue
                # 仅展示顶级指令或指令组
                if item.get("type") == "sub_command":
                    continue
                if item.get("parent_signature"):
                    continue

                effective = (
                    item.get("effective_command")
                    or item.get("original_command")
                    or item.get("handler_name")
                )
                if not effective or effective in {"help", "variable"}:
                    continue

                description = item.get("description") or ""
                desc_text = f" - {description}" if description else ""
                indent_prefix = "  " * indent
                lines.append((f"{indent_prefix}/{effective}", desc_text))

        walk(commands)
        return lines

    def _build_plain_text_message(
        self,
        *,
        dashboard_version: str | None,
        commands: list[tuple[str, str]],
        notice: str,
    ) -> str:
        dashboard_label = dashboard_version or "unknown"
        commands_section = (
            "\n".join(f"{command}{desc}" for command, desc in commands)
            if commands
            else "No enabled built-in commands."
        )
        msg_parts = [
            f"AstrBot v{VERSION}(WebUI: {dashboard_label})",
            commands_section,
            "Tip: use `/help --image` to render the visual help card.",
        ]
        if notice:
            msg_parts.append(notice)
        return "\n".join(msg_parts)

    def _build_image_markup(
        self,
        *,
        dashboard_version: str | None,
        commands: list[tuple[str, str]],
        notice: str,
    ) -> str:
        dashboard_label = dashboard_version or "unknown"
        cards = []
        for command, desc in commands:
            description = escape(desc.removeprefix(" - ").strip() or "No description")
            cards.append(
                "\n".join(
                    [
                        '<div class="help-card">',
                        f'  <div class="help-card__command"><code>{escape(command)}</code></div>',
                        f"  <p>{description}</p>",
                        "</div>",
                    ]
                )
            )

        if not cards:
            cards.append(
                "\n".join(
                    [
                        '<div class="help-card">',
                        '  <div class="help-card__command"><code>/help</code></div>',
                        "  <p>No enabled built-in commands.</p>",
                        "</div>",
                    ]
                )
            )

        lines = [
            '<div class="help-meta">',
            '  <span class="help-pill">Core Commands</span>',
            f'  <span class="help-pill">AstrBot v{escape(str(VERSION))}</span>',
            f'  <span class="help-pill">WebUI {escape(str(dashboard_label))}</span>',
            "</div>",
            '<div class="help-callout">Use <code>/help</code> for the compact text version.</div>',
            '<section class="help-section">',
            "  <h2>Built-in Commands</h2>",
            '  <div class="help-grid">',
            "\n".join(cards),
            "  </div>",
            "</section>",
        ]
        if notice:
            lines.extend(
                [
                    '<section class="notice-box">',
                    "  <h2>Notice</h2>",
                    f"  <p>{escape(notice)}</p>",
                    "</section>",
                ],
            )
        return "\n".join(lines)

    def _get_event_config(self, event: AstrMessageEvent) -> AstrBotConfig | None:
        try:
            return self.context.config.get(umo=event.unified_msg_origin)
        except Exception:
            return None

    def _get_callback_base(self, event: AstrMessageEvent) -> str:
        config = self._get_event_config(event)
        if config is not None:
            try:
                callback_api_base = str(
                    config.get("callback_api_base", "") or ""
                ).strip()
                if callback_api_base:
                    return callback_api_base.rstrip("/")
            except Exception:
                pass
        return ""

    async def help(self, event: AstrMessageEvent, image: bool = False) -> None:
        """查看帮助。"""
        event.should_call_llm(True)
        notice = ""
        try:
            notice = await self._query_astrbot_notice()
        except Exception:
            pass

        dashboard_version = await get_dashboard_version()
        commands = await self._build_reserved_commands()
        plain_text = self._build_plain_text_message(
            dashboard_version=dashboard_version,
            commands=commands,
            notice=notice,
        )

        if not image:
            event.set_result(MessageEventResult().message(plain_text).use_t2i(False))
            return

        image_markup = self._build_image_markup(
            dashboard_version=dashboard_version,
            commands=commands,
            notice=notice,
        )
        try:
            rendered_image = await self.context.rendering.text_to_image(
                image_markup,
                template_name="astrbot_help",
            )
        except Exception as exc:
            logger.warning("Failed to render help image: %s", exc)
            event.set_result(MessageEventResult().message(plain_text).use_t2i(False))
            return

        if rendered_image.startswith(("http://", "https://")):
            event.set_result(
                MessageEventResult().url_image(rendered_image).use_t2i(False)
            )
            return

        if hasattr(event, "track_temporary_local_file"):
            event.track_temporary_local_file(rendered_image)

        callback_base = self._get_callback_base(event)
        if callback_base:
            try:
                token = await self.context.files.publish(rendered_image)
                image_url = f"{callback_base}/api/v1/files/tokens/{token}"
                event.set_result(
                    MessageEventResult().url_image(image_url).use_t2i(False)
                )
                return
            except Exception as exc:
                logger.warning(
                    "Failed to expose local help image via file token: %s", exc
                )

        logger.debug(
            "Sending local help image without a callback URL: %s",
            rendered_image,
        )
        event.set_result(MessageEventResult().file_image(rendered_image).use_t2i(False))
