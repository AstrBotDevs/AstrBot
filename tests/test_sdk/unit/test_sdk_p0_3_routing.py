# ruff: noqa: E402
from __future__ import annotations

from pathlib import Path

import pytest

from astrbot_sdk.filters import (
    CustomFilter,
    MessageTypeFilter,
    PlatformFilter,
    all_of,
)
from astrbot_sdk.protocol.descriptors import LocalFilterRefSpec
from astrbot_sdk.runtime.loader import load_plugin, load_plugin_spec, validate_plugin_spec


@pytest.mark.unit
def test_composite_filter_keeps_descriptor_serializable() -> None:
    binding = all_of(
        PlatformFilter(["qq"]),
        MessageTypeFilter(["group"]),
        CustomFilter(lambda *, event: event.text == "ok", filter_id="demo.filter"),
    )
    spec, local_bindings = binding.compile()

    assert isinstance(spec, LocalFilterRefSpec)
    assert local_bindings


@pytest.mark.unit
def test_greedy_str_non_last_fails_at_load_time(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "bad_plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")
    (plugin_dir / "plugin.yaml").write_text(
        "\n".join(
            [
                "name: bad_plugin",
                "runtime:",
                '  python: "3.11"',
                "components:",
                "  - class: main:BadPlugin",
            ]
        ),
        encoding="utf-8",
    )
    (plugin_dir / "main.py").write_text(
        "\n".join(
            [
                "from astrbot_sdk import Star",
                "from astrbot_sdk.decorators import on_command",
                "from astrbot_sdk.events import MessageEvent",
                "from astrbot_sdk.types import GreedyStr",
                "",
                "class BadPlugin(Star):",
                '    @on_command("broken")',
                "    async def broken(self, event: MessageEvent, phrase: GreedyStr, extra: str):",
                '        await event.reply("never")',
            ]
        ),
        encoding="utf-8",
    )

    plugin = load_plugin_spec(plugin_dir)
    validate_plugin_spec(plugin)
    with pytest.raises(ValueError, match="GreedyStr"):
        load_plugin(plugin)
