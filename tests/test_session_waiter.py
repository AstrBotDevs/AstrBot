from astrbot.core.utils import session_waiter as session_waiter_module
from astrbot.core.utils.session_waiter import DefaultSessionFilter, SessionWaiter


def test_cleanup_only_removes_its_own_session_waiter(monkeypatch):
    monkeypatch.setattr(session_waiter_module, "USER_SESSIONS", {})
    monkeypatch.setattr(session_waiter_module, "FILTERS", [])

    old_waiter = SessionWaiter(DefaultSessionFilter(), "same-session", False)
    new_waiter = SessionWaiter(DefaultSessionFilter(), "same-session", False)
    session_waiter_module.USER_SESSIONS["same-session"] = new_waiter

    old_waiter._cleanup()

    assert session_waiter_module.USER_SESSIONS["same-session"] is new_waiter


def test_cleanup_removes_waiter_when_it_owns_the_session(monkeypatch):
    monkeypatch.setattr(session_waiter_module, "USER_SESSIONS", {})
    monkeypatch.setattr(session_waiter_module, "FILTERS", [])

    waiter = SessionWaiter(DefaultSessionFilter(), "same-session", False)
    session_waiter_module.USER_SESSIONS["same-session"] = waiter

    waiter._cleanup()

    assert "same-session" not in session_waiter_module.USER_SESSIONS
