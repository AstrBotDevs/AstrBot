from unittest.mock import MagicMock

from astrbot.core.agent.execution_policy import (
    AGENT_EXECUTION_POLICY_EXTRA_KEY,
    AgentExecutionPolicy,
    get_agent_execution_policy,
)


def test_policy_parses_valid_mapping():
    policy = AgentExecutionPolicy.from_value(
        {
            "route": "standard",
            "provider_id": "deepseek/pro",
            "allowed_tools": ["search", "search", "memory"],
            "knowledge_mode": "retrieve",
            "max_steps": 3,
            "tool_timeout_seconds": 25,
            "request_max_retries": 1,
            "principal_id": "qq:123",
            "permission_snapshot": {"role": "member"},
        }
    )

    assert policy is not None
    assert policy.allowed_tools == ("search", "memory")
    assert policy.provider_id == "deepseek/pro"
    assert policy.permission_snapshot == {"role": "member"}


def test_policy_rejects_invalid_limits_and_types():
    assert AgentExecutionPolicy.from_value({"route": "unknown"}) is None
    assert (
        AgentExecutionPolicy.from_value(
            {"route": "fast", "max_steps": 0, "tool_timeout_seconds": 30}
        )
        is None
    )
    assert (
        AgentExecutionPolicy.from_value(
            {
                "route": "fast",
                "max_steps": 1,
                "tool_timeout_seconds": 30,
                "request_max_retries": 2,
            }
        )
        is None
    )
    assert (
        AgentExecutionPolicy.from_value(
            {
                "route": "fast",
                "max_steps": 1,
                "tool_timeout_seconds": 30,
                "allowed_tools": "search",
            }
        )
        is None
    )


def test_get_policy_preserves_legacy_behavior_without_extra():
    event = MagicMock()
    event.get_extra.return_value = None

    assert get_agent_execution_policy(event) is None
    event.get_extra.assert_called_once_with(AGENT_EXECUTION_POLICY_EXTRA_KEY)
