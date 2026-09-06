"""Regression tests: request-time context processing must never mutate the
persistent conversation history (``run_context.messages``).
"""
from types import SimpleNamespace

from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner


def test_request_messages_separated_from_persistent_history():
    """Request messages used for the provider must not replace run_context."""
    runner = ToolLoopAgentRunner()
    runner.run_context = SimpleNamespace(messages=["full-a", "full-b"])

    # Simulate request-time context processing producing a compressed list.
    runner._request_messages = ["compressed"]

    assert runner._effective_request_messages() == ["compressed"]
    # Persistent history must stay untouched.
    assert runner.run_context.messages == ["full-a", "full-b"]


def test_request_messages_fallback_to_run_context():
    """When no request-time result is set, fall back to the full history."""
    runner = ToolLoopAgentRunner()
    runner.run_context = SimpleNamespace(messages=["full-a", "full-b"])
    runner._request_messages = None

    assert runner._effective_request_messages() == ["full-a", "full-b"]


def test_empty_request_messages_do_not_fall_back_to_full():
    """An empty request result must NOT silently fall back to the full history.

    Otherwise a (wrongly) empty compressed result would bypass the empty-message
    error guard and send the whole, over-window history to the provider.
    """
    runner = ToolLoopAgentRunner()
    runner.run_context = SimpleNamespace(messages=["full-a", "full-b"])
    runner._request_messages = []

    assert runner._effective_request_messages() == []


def test_run_context_not_mutated_after_processing():
    """Queueing a request result must not write back into the persistent list."""
    runner = ToolLoopAgentRunner()
    runner.run_context = SimpleNamespace(messages=["full-a", "full-b"])
    runner._request_messages = ["compressed"]

    # Even if later re-fetched, run_context must remain the source of truth.
    assert runner.run_context.messages == ["full-a", "full-b"]
    runner._request_messages = None
    assert runner._effective_request_messages() == ["full-a", "full-b"]
