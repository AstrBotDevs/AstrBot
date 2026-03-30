"""
Tests for ToolSessionManager and ToolSessionState.
"""

import pytest

from astrbot.core.agent.tool_session_manager import (
    ToolSessionManager,
    ToolSessionState,
)


class TestToolSessionState:
    def test_get_state_creates_if_not_exists(self):
        state = ToolSessionState(umo="umo1", tool_name="tool1")
        assert state.umo == "umo1"
        assert state.tool_name == "tool1"
        assert len(state) == 0

    def test_dict_like_behavior(self):
        state = ToolSessionState(umo="umo1", tool_name="tool1")
        state["cwd"] = "/tmp"
        state["env"] = {"PATH": "/usr/bin"}
        assert state["cwd"] == "/tmp"
        assert state["env"] == {"PATH": "/usr/bin"}
        assert len(state) == 2

    def test_persistent_keys(self):
        state = ToolSessionState(umo="umo1", tool_name="tool1")
        state["temp"] = "data"
        state.set_persistent("persistent_data")
        state["persistent_data"] = "important"
        assert state.is_persistent("persistent_data") is True
        assert state.is_persistent("temp") is False

    def test_iter_and_len(self):
        state = ToolSessionState(umo="umo1", tool_name="tool1")
        state["a"] = 1
        state["b"] = 2
        assert list(state) == ["a", "b"]
        assert len(state) == 2

    def test_delitem(self):
        state = ToolSessionState(umo="umo1", tool_name="tool1")
        state["key"] = "value"
        del state["key"]
        assert "key" not in state


class TestToolSessionManager:
    def test_get_state_creates_if_not_exists(self):
        mgr = ToolSessionManager()
        state1 = mgr.get_state("umo1", "tool1")
        state2 = mgr.get_state("umo1", "tool1")
        assert state1 is state2  # Same instance

    def test_different_tools_have_different_state(self):
        mgr = ToolSessionManager()
        state1 = mgr.get_state("umo1", "tool1")
        state1["key"] = "value"
        state2 = mgr.get_state("umo1", "tool2")
        assert "key" not in state2

    def test_different_sessions_have_different_state(self):
        mgr = ToolSessionManager()
        state1 = mgr.get_state("umo1", "tool1")
        state1["key"] = "value1"
        state2 = mgr.get_state("umo2", "tool1")
        state2["key"] = "value2"
        assert state1["key"] == "value1"
        assert state2["key"] == "value2"

    def test_clear_session_keeps_persistent(self):
        mgr = ToolSessionManager()
        state = mgr.get_state("umo1", "tool1")
        state["temp"] = "data"
        state.set_persistent("persistent_data")
        state["persistent_data"] = "important"

        mgr.clear_session("umo1")

        assert "temp" not in state
        assert state["persistent_data"] == "important"

    def test_clear_session_only_clears_target_umo(self):
        mgr = ToolSessionManager()
        state1 = mgr.get_state("umo1", "tool1")
        state1["key"] = "value1"
        state2 = mgr.get_state("umo2", "tool1")
        state2["key"] = "value2"

        mgr.clear_session("umo1")

        assert "key" not in state1
        assert state2["key"] == "value2"

    def test_state_persistence_across_clears(self):
        mgr = ToolSessionManager()
        state1 = mgr.get_state("umo1", "tool1")
        state1["key"] = "value1"
        mgr.clear_session("umo1")
        # After clear, state is still accessible (just emptied of non-persistent)
        assert len(state1) == 0
        state1["key"] = "value1_after"
        assert mgr.get_state("umo1", "tool1")["key"] == "value1_after"
