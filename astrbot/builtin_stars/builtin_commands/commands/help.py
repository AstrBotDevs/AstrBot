from html import escape

import aiohttp

from astrbot.api import logger, star
from astrbot.api.event import AstrMessageEvent

from .reply import reply_image_file, reply_image_url, reply_text


class HelpCommand:
    def __init__(self, context: star.PluginContext) -> None:
        self.context = context

    async def _query_astrbot_notice(self):
        try:
            timeout = aiohttp.ClientTimeout(total=2)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get("https://astrbot.app/notice.json") as resp:
                    return (await resp.json())["notice"]
        except Exception:
            return ""

    async def _build_reserved_commands(self) -> list[tuple[str, str]]:
        """Build the enabled reserved command list from live command configs."""
        try:
            commands = await self.context.runtime_info.commands()
        except Exception:
            return []

        lines: list[tuple[str, str]] = []

        def walk(items: list[dict]) -> None:
            for item in items:
                if not item.get("reserved") or not item.get("enabled"):
                    continue
                if item.get("type") == "sub_command":
                    continue
                if item.get("parent_signature"):
                    continue

                effective = item.get("effective_command") or item.get(
                    "original_command"
                )
                if not effective or effective == "help":
                    continue

                description = item.get("description") or ""
                desc_text = f" - {description}" if description else ""
                lines.append((f"/{effective}", desc_text))
                for sub in item.get("sub_commands") or []:
                    if not sub.get("enabled"):
                        continue
                    sub_effective = sub.get("effective_command") or sub.get(
                        "original_command"
                    )
                    if not sub_effective:
                        continue
                    sub_description = sub.get("description") or ""
                    sub_desc = f" - {sub_description}" if sub_description else ""
                    lines.append((f"  /{sub_effective}", sub_desc))

        walk(commands)
        return lines

    async def _build_plain_text_message(
        self,
        event: AstrMessageEvent,
        *,
        dashboard_version: str | None,
        commands: list[tuple[str, str]],
        notice: str,
    ) -> str:
        dashboard_label = dashboard_version or await self.context.i18n.t(
            event, "help.unknown"
        )
        if commands:
            commands_section = "\n".join(
                f"{command}{desc}" for command, desc in commands
            )
        else:
            commands_section = await self.context.i18n.t(event, "help.empty")
        header = await self.context.i18n.t(
            event,
            "help.header",
            version=self.context.runtime_info.version,
            dashboard=dashboard_label,
        )
        tip = await self.context.i18n.t(event, "help.tip")
        msg_parts = [header, commands_section, tip]
        if notice:
            msg_parts.append(notice)
        return "\n".join(msg_parts)

    async def _build_image_markup(
        self,
        event: AstrMessageEvent,
        *,
        dashboard_version: str | None,
        commands: list[tuple[str, str]],
        notice: str,
    ) -> str:
        dashboard_label = dashboard_version or await self.context.i18n.t(
            event, "help.unknown"
        )
        empty_desc = await self.context.i18n.t(event, "help.no_description")
        cards = []
        for command, desc in commands:
            description = escape(desc.removeprefix(" - ").strip() or empty_desc)
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
            empty = await self.context.i18n.t(event, "help.empty")
            cards.append(
                "\n".join(
                    [
                        '<div class="help-card">',
                        '  <div class="help-card__command"><code>/help</code></div>',
                        f"  <p>{escape(empty)}</p>",
                        "</div>",
                    ]
                )
            )

        core_label = await self.context.i18n.t(event, "help.meta_core")
        version_pill = await self.context.i18n.t(
            event,
            "help.image_version",
            version=self.context.runtime_info.version,
        )
        webui_pill = await self.context.i18n.t(
            event,
            "help.image_webui",
            dashboard=dashboard_label,
        )
        callout = await self.context.i18n.t(event, "help.image_callout")
        section_title = await self.context.i18n.t(event, "help.section_title")
        lines = [
            '<div class="help-meta">',
            f'  <span class="help-pill">{escape(core_label)}</span>',
            f'  <span class="help-pill">{escape(version_pill)}</span>',
            f'  <span class="help-pill">{escape(webui_pill)}</span>',
            "</div>",
            f'<div class="help-callout">{escape(callout)}</div>',
            '<section class="help-section">',
            f"  <h2>{escape(section_title)}</h2>",
            '  <div class="help-grid">',
            "\n".join(cards),
            "  </div>",
            "</section>",
        ]
        if notice:
            notice_title = await self.context.i18n.t(event, "help.notice_title")
            lines.extend(
                [
                    '<section class="notice-box">',
                    f"  <h2>{escape(notice_title)}</h2>",
                    f"  <p>{escape(notice)}</p>",
                    "</section>",
                ],
            )
        return "\n".join(lines)

    def _get_callback_base(self, event: AstrMessageEvent) -> str:
        try:
            config = self.context.config.get(umo=event.unified_msg_origin)
        except Exception:
            return ""
        try:
            callback_api_base = str(config.get("callback_api_base", "") or "").strip()
            if callback_api_base:
                return callback_api_base.rstrip("/")
        except Exception:
            return ""
        return ""

    async def help(self, event: AstrMessageEvent, image: bool = False) -> None:
        """Show help for enabled built-in commands."""
        notice = ""
        try:
            notice = await self._query_astrbot_notice()
        except Exception:
            pass

        dashboard_version = await self.context.runtime_info.dashboard_version()
        commands = await self._build_reserved_commands()
        plain_text = await self._build_plain_text_message(
            event,
            dashboard_version=dashboard_version,
            commands=commands,
            notice=notice,
        )

        if not image:
            reply_text(event, plain_text)
            return

        image_markup = await self._build_image_markup(
            event,
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
            reply_text(event, plain_text)
            return

        if rendered_image.startswith(("http://", "https://")):
            reply_image_url(event, rendered_image)
            return

        if hasattr(event, "track_temporary_local_file"):
            event.track_temporary_local_file(rendered_image)

        callback_base = self._get_callback_base(event)
        if callback_base:
            try:
                token = await self.context.files.publish(rendered_image)
                image_url = f"{callback_base}/api/v1/files/tokens/{token}"
                reply_image_url(event, image_url)
                return
            except Exception as exc:
                logger.warning(
                    "Failed to expose local help image via file token: %s", exc
                )

        logger.debug(
            "Sending local help image without a callback URL: %s",
            rendered_image,
        )
        reply_image_file(event, rendered_image)
