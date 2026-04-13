from astrbot.core.agent.runners.deerflow.deerflow_agent_runner import (
    DeerFlowAgentRunner,
)


def test_build_payload_includes_configurable_runtime_overrides_and_legacy_context():
    runner = DeerFlowAgentRunner()
    runner.assistant_id = "lead_agent"
    runner.thinking_enabled = True
    runner.plan_mode = True
    runner.subagent_enabled = True
    runner.max_concurrent_subagents = 5
    runner.model_name = "gpt-4.1"
    runner.recursion_limit = 321

    payload = runner._build_payload(
        thread_id="thread-123",
        prompt="hello deerflow",
        image_urls=[],
        system_prompt=None,
    )

    expected_runtime = {
        "thread_id": "thread-123",
        "thinking_enabled": True,
        "is_plan_mode": True,
        "subagent_enabled": True,
        "max_concurrent_subagents": 5,
        "model_name": "gpt-4.1",
    }

    assert payload["assistant_id"] == "lead_agent"
    assert payload["stream_mode"] == ["values", "messages-tuple", "custom"]
    assert payload["config"]["recursion_limit"] == 321
    assert payload["config"]["configurable"] == expected_runtime
    assert payload["context"] == expected_runtime
