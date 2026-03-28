from __future__ import annotations

from typing import Any

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.core.context_memory import ensure_context_memory_settings

PINNED_PREVIEW_MAX_CHARS = 180


class ContextMemoryCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    def _get_provider_settings(
        self, event: AstrMessageEvent
    ) -> tuple[Any, dict[str, Any]]:
        cfg = self.context.get_config(umo=event.unified_msg_origin)
        provider_settings = cfg.get("provider_settings", {})
        if not isinstance(provider_settings, dict):
            provider_settings = {}
            cfg["provider_settings"] = provider_settings
        return cfg, provider_settings

    @staticmethod
    def _save_config(cfg: Any) -> None:
        save_func = getattr(cfg, "save_config", None)
        if callable(save_func):
            save_func()

    @staticmethod
    def _parse_switch(value: str) -> bool | None:
        normalized = value.strip().lower()
        if normalized in {"1", "true", "on", "yes", "enable", "enabled"}:
            return True
        if normalized in {"0", "false", "off", "no", "disable", "disabled"}:
            return False
        return None

    async def status(self, event: AstrMessageEvent) -> None:
        _, provider_settings = self._get_provider_settings(event)
        cm_cfg = ensure_context_memory_settings(provider_settings)
        pinned = cm_cfg.get("pinned_memories", [])
        if not isinstance(pinned, list):
            pinned = []

        lines = ["上下文记忆状态："]
        lines.append(
            "启用="
            + ("是" if bool(cm_cfg.get("enabled", False)) else "否")
            + " | 注入顶层记忆="
            + ("是" if bool(cm_cfg.get("inject_pinned_memory", True)) else "否")
        )
        lines.append(
            f"顶层记忆条数={len(pinned)}"
            f" | 最大条数={cm_cfg.get('pinned_max_items', '?')}"
            f" | 单条最大字符={cm_cfg.get('pinned_max_chars_per_item', '?')}"
        )
        lines.append(
            "检索增强(开发中)="
            + ("是" if bool(cm_cfg.get("retrieval_enabled", False)) else "否")
            + f" | backend={cm_cfg.get('retrieval_backend', '') or '-'}"
            + f" | top_k={cm_cfg.get('retrieval_top_k', '?')}"
        )
        await event.send(MessageChain().message("\n".join(lines)))

    async def ls(self, event: AstrMessageEvent) -> None:
        _, provider_settings = self._get_provider_settings(event)
        cm_cfg = ensure_context_memory_settings(provider_settings)
        pinned = cm_cfg.get("pinned_memories", [])
        if not isinstance(pinned, list) or not pinned:
            await event.send(MessageChain().message("当前没有手动顶层记忆。"))
            return

        configured_max_chars = cm_cfg.get("pinned_max_chars_per_item", 400)
        try:
            configured_max_chars = int(configured_max_chars)
        except Exception:
            configured_max_chars = 400
        preview_max_chars = min(
            max(1, configured_max_chars),
            PINNED_PREVIEW_MAX_CHARS,
        )

        lines = ["手动顶层记忆列表："]
        for idx, text in enumerate(pinned, start=1):
            text_str = str(text)
            if len(text_str) > preview_max_chars:
                text_str = text_str[:preview_max_chars] + "..."
            lines.append(f"{idx}. {text_str}")
        await event.send(MessageChain().message("\n".join(lines)))

    async def add(self, event: AstrMessageEvent, text: str) -> None:
        content = str(text or "").strip()
        if not content:
            await event.send(MessageChain().message("用法: /ctxmem add <记忆内容>"))
            return

        cfg, provider_settings = self._get_provider_settings(event)
        cm_cfg = ensure_context_memory_settings(provider_settings)
        pinned = cm_cfg.get("pinned_memories", [])
        if not isinstance(pinned, list):
            pinned = []
            cm_cfg["pinned_memories"] = pinned

        max_items = int(cm_cfg.get("pinned_max_items", 8) or 8)
        if len(pinned) >= max_items:
            await event.send(
                MessageChain().message(
                    f"已达到顶层记忆最大条数({max_items})，请先使用 /ctxmem rm <序号> 或 /ctxmem clear。",
                )
            )
            return

        max_chars = int(cm_cfg.get("pinned_max_chars_per_item", 400) or 400)
        truncated = False
        if len(content) > max_chars:
            content = content[:max_chars]
            truncated = True

        pinned.append(content)
        self._save_config(cfg)

        msg = f"已添加顶层记忆 #{len(pinned)}。"
        if truncated:
            msg += f" 内容超过上限，已截断到 {max_chars} 字符。"
        await event.send(MessageChain().message(msg))

    async def rm(self, event: AstrMessageEvent, index: int) -> None:
        cfg, provider_settings = self._get_provider_settings(event)
        cm_cfg = ensure_context_memory_settings(provider_settings)
        pinned = cm_cfg.get("pinned_memories", [])
        if not isinstance(pinned, list) or not pinned:
            await event.send(MessageChain().message("当前没有可删除的顶层记忆。"))
            return

        if index < 1 or index > len(pinned):
            await event.send(
                MessageChain().message(f"序号超出范围。请输入 1~{len(pinned)}。")
            )
            return

        removed = str(pinned.pop(index - 1))
        self._save_config(cfg)
        preview = removed if len(removed) <= 80 else removed[:80] + "..."
        await event.send(MessageChain().message(f"已删除顶层记忆 #{index}: {preview}"))

    async def clear(self, event: AstrMessageEvent) -> None:
        cfg, provider_settings = self._get_provider_settings(event)
        cm_cfg = ensure_context_memory_settings(provider_settings)
        pinned = cm_cfg.get("pinned_memories", [])
        count = len(pinned) if isinstance(pinned, list) else 0
        cm_cfg["pinned_memories"] = []
        self._save_config(cfg)
        await event.send(MessageChain().message(f"已清空顶层记忆，共 {count} 条。"))

    async def enable(self, event: AstrMessageEvent, value: str = "") -> None:
        cfg, provider_settings = self._get_provider_settings(event)
        cm_cfg = ensure_context_memory_settings(provider_settings)
        enabled = bool(cm_cfg.get("enabled", False))

        value = str(value or "").strip()
        if value:
            parsed = self._parse_switch(value)
            if parsed is None:
                await event.send(
                    MessageChain().message("参数错误。用法: /ctxmem enable [on|off]")
                )
                return
            enabled = parsed
        else:
            enabled = not enabled

        cm_cfg["enabled"] = enabled
        self._save_config(cfg)
        await event.send(
            MessageChain().message(
                "上下文记忆注入已" + ("开启。" if enabled else "关闭。")
            )
        )

    async def retrieval(self, event: AstrMessageEvent, value: str = "") -> None:
        cfg, provider_settings = self._get_provider_settings(event)
        cm_cfg = ensure_context_memory_settings(provider_settings)
        enabled = bool(cm_cfg.get("retrieval_enabled", False))

        value = str(value or "").strip()
        if value:
            parsed = self._parse_switch(value)
            if parsed is None:
                await event.send(
                    MessageChain().message("参数错误。用法: /ctxmem retrieval [on|off]")
                )
                return
            enabled = parsed
        else:
            enabled = not enabled

        cm_cfg["retrieval_enabled"] = enabled
        self._save_config(cfg)
        await event.send(
            MessageChain().message(
                "检索增强开关(开发中)已" + ("开启。" if enabled else "关闭。")
            )
        )
