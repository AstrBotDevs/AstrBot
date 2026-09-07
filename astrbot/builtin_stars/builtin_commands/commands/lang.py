"""/lang 指令:查看与设置会话语言。仅管理员。"""

from __future__ import annotations

from astrbot.api import sp, star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.utils.lang_utils import (
    DEFAULT_LANG,
    normalize_lang,
    resolve_lang,
)

from .utils.i18n import t


class LangCommand:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def _resolve_and_reply(
        self,
        event: AstrMessageEvent,
        session_lang: str | None,
    ) -> str:
        """解析语言并返回带回显的文案行,不构造完整回复。"""
        umo = event.unified_msg_origin
        cfg = self.context.get_config(umo)
        lang = resolve_lang(cfg, session_lang)

        # 标注来源
        if session_lang:
            source = "session"
        elif cfg.get("language"):
            source = "global"
        else:
            source = "default"

        visible = lang
        if session_lang:
            visible = normalize_lang(session_lang) or session_lang
        elif cfg.get("language"):
            visible = cfg["language"]
        lines = [
            await t(self.context, umo, "lang.current", lang=visible, source=source)
        ]

        # 全局配置非法时提示(选项 B:保留原值,提示按默认生效)
        global_value = cfg.get("language")
        if normalize_lang(global_value) is None and global_value:
            lines.append(
                await t(
                    self.context,
                    umo,
                    "lang.global_invalid",
                    value=global_value,
                    lang=DEFAULT_LANG,
                )
            )
        return "\n".join(lines)

    async def lang(self, event: AstrMessageEvent, value: str | None = None) -> None:
        """查看或设置当前会话语言(仅管理员)。"""
        umo = event.unified_msg_origin
        session_lang = await sp.session_get(umo, "lang", None)

        # 查看
        if value is None:
            ret = await self._resolve_and_reply(event, session_lang)
            event.set_result(MessageEventResult().message(ret).use_t2i(False))
            return

        # reset:移除会话级设置
        if value.strip().lower() == "reset":
            if session_lang:
                await sp.session_remove(umo, "lang")
            ret = await t(self.context, umo, "lang.reset")
            event.set_result(MessageEventResult().message(ret).use_t2i(False))
            return

        # 设置:归一化校验
        norm = normalize_lang(value)
        if norm is None:
            ret = await t(
                self.context,
                umo,
                "lang.invalid",
                value=value.strip(),
                langs="zh-CN / en-US / ru-RU / ja-JP",
            )
            event.set_result(MessageEventResult().message(ret).use_t2i(False))
            return

        await sp.session_put(umo, "lang", norm)
        ret = await t(self.context, umo, "lang.set", lang=norm)
        event.set_result(MessageEventResult().message(ret).use_t2i(False))
