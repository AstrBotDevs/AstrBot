from __future__ import annotations

import re

from astrbot_sdk._internal.plugin_logger import PluginLogger

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class _CapturingLogger:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self._current_opt: dict[str, object] = {}

    def bind(self, **_kwargs):
        return self

    def opt(self, *args, **kwargs):
        self._current_opt = dict(kwargs)
        return self

    def log(self, level, message, *args, **kwargs) -> None:
        self.calls.append(
            {
                "level": level,
                "message": message,
                "args": args,
                "kwargs": kwargs,
                "opt": dict(self._current_opt),
            }
        )
        self._current_opt = {}


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def test_plugin_logger_formats_like_core_console(monkeypatch) -> None:
    logger = _CapturingLogger()
    plugin_logger = PluginLogger(plugin_id="ai_girlfriend", logger=logger)
    monkeypatch.setattr(
        plugin_logger,
        "_caller_info",
        lambda: ("D:/repo/data/sdk_plugins/ai_girlfriend/gf_plugin.py", 321),
    )

    plugin_logger.info("hello {}", "world")

    assert len(logger.calls) == 1
    call = logger.calls[0]
    assert call["level"] == "INFO"
    assert call["opt"] == {"raw": True}
    assert re.match(
        r"^\[\d{2}:\d{2}:\d{2}\.\d{3}\] \[Plug\] \[INFO\] "
        r"\[ai_girlfriend\.gf_plugin:321\]: hello world\n$",
        _strip_ansi(str(call["message"])),
    )


def test_plugin_logger_uses_core_tag_for_sdk_internal_paths(monkeypatch) -> None:
    logger = _CapturingLogger()
    plugin_logger = PluginLogger(plugin_id="ai_girlfriend", logger=logger)
    monkeypatch.setattr(
        plugin_logger,
        "_caller_info",
        lambda: ("D:/repo/astrbot-sdk/src/astrbot_sdk/context.py", 88),
    )

    plugin_logger.warning("watch {}", "out")

    assert len(logger.calls) == 1
    call = logger.calls[0]
    assert call["level"] == "WARNING"
    assert call["opt"] == {"raw": True}
    rendered = _strip_ansi(str(call["message"]))
    assert "[Core] [WARN]" in rendered
    assert "[astrbot_sdk.context:88]: watch out\n" in rendered
