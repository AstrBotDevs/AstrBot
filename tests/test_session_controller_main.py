from __future__ import annotations

from astrbot.api.star import Star
from astrbot.builtin_stars.session_controller.main import Main


def test_session_controller_main_imported():
    assert Main is not None


def test_session_controller_main_class():
    assert issubclass(Main, Star)


def test_session_controller_main_methods():
    assert hasattr(Main, "handle_session_control_agent")
    assert hasattr(Main, "handle_empty_mention")
