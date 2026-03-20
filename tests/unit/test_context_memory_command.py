from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.builtin_stars.builtin_commands.commands.context_memory import (
    ContextMemoryCommands,
)


class DummyConfig(dict):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.save_calls = 0

    def save_config(self) -> None:
        self.save_calls += 1


def _build_command_with_cfg(cfg: DummyConfig) -> ContextMemoryCommands:
    context = SimpleNamespace(get_config=lambda umo=None: cfg)
    return ContextMemoryCommands(context=context)


def _build_event() -> SimpleNamespace:
    return SimpleNamespace(unified_msg_origin="umo:test", send=AsyncMock())


@pytest.mark.asyncio
async def test_status_shows_defaults() -> None:
    cfg = DummyConfig({"provider_settings": {}})
    command = _build_command_with_cfg(cfg)
    event = _build_event()

    await command.status(event)

    event.send.assert_awaited_once()
    text = event.send.await_args.args[0].get_plain_text(with_other_comps_mark=True)
    assert "上下文记忆状态" in text
    assert "启用=否" in text
    assert "顶层记忆条数=0" in text


@pytest.mark.asyncio
async def test_add_list_and_remove_memory() -> None:
    cfg = DummyConfig(
        {
            "provider_settings": {
                "context_memory": {
                    "enabled": True,
                    "inject_pinned_memory": True,
                    "pinned_memories": [],
                    "pinned_max_items": 4,
                    "pinned_max_chars_per_item": 120,
                }
            }
        }
    )
    command = _build_command_with_cfg(cfg)
    event = _build_event()

    await command.add(event, "用户喜欢先给结论再解释。")
    assert cfg.save_calls == 1
    stored = cfg["provider_settings"]["context_memory"]["pinned_memories"]
    assert stored == ["用户喜欢先给结论再解释。"]

    await command.ls(event)
    text = event.send.await_args.args[0].get_plain_text(with_other_comps_mark=True)
    assert "手动顶层记忆列表" in text
    assert "用户喜欢先给结论再解释" in text

    await command.rm(event, 1)
    assert cfg["provider_settings"]["context_memory"]["pinned_memories"] == []


@pytest.mark.asyncio
async def test_add_rejects_when_reaching_max_items() -> None:
    cfg = DummyConfig(
        {
            "provider_settings": {
                "context_memory": {
                    "pinned_memories": ["A"],
                    "pinned_max_items": 1,
                    "pinned_max_chars_per_item": 100,
                }
            }
        }
    )
    command = _build_command_with_cfg(cfg)
    event = _build_event()

    await command.add(event, "B")

    # only normalization happened in-memory, no successful add/save
    assert cfg["provider_settings"]["context_memory"]["pinned_memories"] == ["A"]
    text = event.send.await_args.args[0].get_plain_text(with_other_comps_mark=True)
    assert "已达到顶层记忆最大条数" in text


@pytest.mark.asyncio
async def test_enable_and_retrieval_toggles() -> None:
    cfg = DummyConfig({"provider_settings": {"context_memory": {"enabled": False}}})
    command = _build_command_with_cfg(cfg)
    event = _build_event()

    await command.enable(event)
    assert cfg["provider_settings"]["context_memory"]["enabled"] is True

    await command.retrieval(event, "on")
    assert cfg["provider_settings"]["context_memory"]["retrieval_enabled"] is True


@pytest.mark.asyncio
async def test_add_truncates_long_memory_item() -> None:
    cfg = DummyConfig(
        {
            "provider_settings": {
                "context_memory": {
                    "pinned_memories": [],
                    "pinned_max_items": 3,
                    "pinned_max_chars_per_item": 10,
                }
            }
        }
    )
    command = _build_command_with_cfg(cfg)
    event = _build_event()

    await command.add(event, "1234567890abcdef")

    stored = cfg["provider_settings"]["context_memory"]["pinned_memories"]
    assert stored == ["1234567890"]
    text = event.send.await_args.args[0].get_plain_text(with_other_comps_mark=True)
    assert "已截断到 10 字符" in text
