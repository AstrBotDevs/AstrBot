"""Import smoke tests for the live_chat route module.

Verifies that the ``LiveChatRoute`` and ``LiveChatSession`` classes
from ``live_chat.py`` can be imported without errors, and checks key
method signatures.
"""

import inspect

from astrbot.dashboard.routes.live_chat import (
    LiveChatRoute,
    LiveChatSession,
)
from astrbot.dashboard.routes.route import Route


def test_live_chat_route_class():
    assert LiveChatRoute is not None
    assert issubclass(LiveChatRoute, Route)


def test_live_chat_session_class():
    assert LiveChatSession is not None


def test_live_chat_route_init_signature():
    sig = inspect.signature(LiveChatRoute.__init__)
    params = list(sig.parameters.keys())
    assert "self" in params
    assert "context" in params
    assert "db" in params
    assert "core_lifecycle" in params


def test_live_chat_route_handle_chat_message_signature():
    sig = inspect.signature(LiveChatRoute._handle_chat_message)
    params = list(sig.parameters.keys())
    assert "self" in params
    assert "session" in params
    assert "message" in params


def test_live_chat_route_process_audio_signature():
    sig = inspect.signature(LiveChatRoute._process_audio)
    params = list(sig.parameters.keys())
    assert "self" in params
    assert "session" in params
    assert "audio_path" in params
    assert "assemble_duration" in params


def test_live_chat_session_init_signature():
    sig = inspect.signature(LiveChatSession.__init__)
    params = list(sig.parameters.keys())
    assert "self" in params
    assert "session_id" in params
    assert "username" in params


def test_live_chat_session_start_speaking_signature():
    sig = inspect.signature(LiveChatSession.start_speaking)
    params = list(sig.parameters.keys())
    assert "self" in params
    assert "stamp" in params


def test_live_chat_session_end_speaking_signature():
    sig = inspect.signature(LiveChatSession.end_speaking)
    params = list(sig.parameters.keys())
    assert "self" in params
    assert "stamp" in params


def test_live_chat_session_cleanup_signature():
    sig = inspect.signature(LiveChatSession.cleanup)
    params = list(sig.parameters.keys())
    assert "self" in params
