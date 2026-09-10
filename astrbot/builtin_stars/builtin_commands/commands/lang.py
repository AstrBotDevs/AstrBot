"""/lang 指令:查看与设置全局语言。仅管理员。"""

from __future__ import annotations

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.utils.lang_utils import (
    DEFAULT_LANG,
    SUPPORTED_LANGS,
    normalize_lang,
)

from .utils.i18n import t


class LangCommand:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def lang(self, event: AstrMessageEvent, value: str | None = None) -> None:
        """查看或设置全局语言(仅管理员)。"""
        umo = event.unified_msg_origin
        cfg = self.context.get_config()
        global_value = cfg.get("language")

        # 查看
        if value is None:
            lines = [
                await t(
                    self.context,
                    umo,
                    "lang.current",
                    lang=global_value or DEFAULT_LANG,
                    source="global",
                )
            ]
            if global_value and normalize_lang(global_value) is None:
                lines.append(
                    await t(
                        self.context,
                        umo,
                        "lang.global_invalid",
                        value=global_value,
                        lang=DEFAULT_LANG,
                    )
                )
            event.set_result(
                MessageEventResult().message("\n".join(lines)).use_t2i(False)
            )
            return

        # reset:恢复默认语言
        if value.strip().lower() == "reset":
            cfg["language"] = DEFAULT_LANG
            cfg.save_config()
            ret = await t(self.context, umo, "lang.reset", lang=DEFAULT_LANG)
            event.set_result(MessageEventResult().message(ret).use_t2i(False))
            return

        # 设置:归一化校验后写入全局配置
        norm = normalize_lang(value)
        if norm is None:
            ret = await t(
                self.context,
                umo,
                "lang.invalid",
                value=value.strip(),
                langs=" / ".join(SUPPORTED_LANGS),
            )
            event.set_result(MessageEventResult().message(ret).use_t2i(False))
            return

        cfg["language"] = norm
        cfg.save_config()
        ret = await t(self.context, umo, "lang.set", lang=norm)
        event.set_result(MessageEventResult().message(ret).use_t2i(False))
